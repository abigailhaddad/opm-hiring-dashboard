import argparse
import base64
import csv
import json
import re
from collections import namedtuple
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

EMBED_URL = (
    "https://app.powerbigov.us/view?r="
    "eyJrIjoiZjNhNDIwMGEtZmEwYi00YTg5LThiMmItMWEwZDI0NWY3NjU4IiwidCI6IjNjZTA3YzBiLTMwYzUtNGJjZC1hZDkyLTIzODk3NWI2NDlhZiJ9"
)
API_BASE = "https://wabi-us-gov-virginia-api.analysis.usgovcloudapi.net/public/reports/"
PAGE_SIZE = 5000
REQUEST_TIMEOUT = 120
# Holds only the dashboard's calculated measures, no stored data.
SKIP_TABLES = {"DAX Measures"}
TYPE_DATETIME = 7
EPOCH = datetime(1970, 1, 1)

Page = namedtuple("Page", "rows restart_tokens complete restarted")


def resource_key(embed_url):
    params = parse_qs(urlparse(embed_url).query)
    token = params["r"][0]
    payload = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
    return payload["k"]


def call_api(session, method, path, body=None):
    response = session.request(method, API_BASE + path, json=body, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def fetch_model(session, key):
    info = call_api(session, "GET", f"{key}/modelsAndExploration?preferReadOnlySession=true")
    if len(info["models"]) != 1:
        raise RuntimeError(f"expected exactly one model, got {len(info['models'])}")
    model = info["models"][0]
    return {
        "model_id": model["id"],
        "dataset_id": model["dbName"],
        "report_id": info["exploration"]["report"]["objectId"],
    }


def fetch_tables(session, model):
    response = call_api(session, "POST", "conceptualschema", {"modelIds": [model["model_id"]]})
    schema = response["schemas"][0]
    if schema["error"]:
        raise RuntimeError(f"schema request failed: {schema['error']}")
    return {
        entity["Name"]: [p["Name"] for p in entity["Properties"] if "Column" in p]
        for entity in schema["schema"]["Entities"]
    }


def build_query(model, table, columns, count, restart_tokens):
    window = {"Count": count}
    if restart_tokens is not None:
        window["RestartTokens"] = restart_tokens
    command = {
        "Query": {
            "Version": 2,
            "From": [{"Name": "t", "Entity": table, "Type": 0}],
            "Select": [
                {
                    "Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": column},
                    "Name": f"{table}.{column}",
                }
                for column in columns
            ],
        },
        "Binding": {
            "Primary": {"Groupings": [{"Projections": list(range(len(columns))), "Subtotal": 1}]},
            "DataReduction": {"DataVolume": 4, "Primary": {"Window": window}},
            "Version": 1,
        },
        "ExecutionMetricsKind": 1,
    }
    return {
        "version": "1.0.0",
        "queries": [
            {
                "Query": {"Commands": [{"SemanticQueryDataShapeCommand": command}]},
                "QueryId": "",
                "ApplicationContext": {
                    "DatasetId": model["dataset_id"],
                    "Sources": [{"ReportId": model["report_id"]}],
                },
            }
        ],
        "cancelQueries": [],
        "modelId": model["model_id"],
    }


def convert_cell(value, column, dicts):
    if value is None:
        return None
    # A dictionary-encoded text column usually holds an index into its value
    # list, but Power BI also sends some values as literal text (seen live in
    # Dates."Month Year": "May 2017" on 2017-05-01, row 3,043).
    if "DN" in column and isinstance(value, int):
        value = dicts[column["DN"]][value]
    if column.get("T") == TYPE_DATETIME and isinstance(value, (int, float)):
        return (EPOCH + timedelta(milliseconds=value)).isoformat()
    return value


def decode_row(raw, previous, schema, dicts):
    repeat = raw.get("R", 0)
    nulls = raw.get("Ø", 0)
    cells = iter(raw.get("C", []))
    missing = object()
    row = []
    for index, column in enumerate(schema):
        if repeat & (1 << index):
            if previous is None:
                raise RuntimeError("first row marked a column as repeated")
            row.append(previous[index])
        elif nulls & (1 << index):
            row.append(None)
        else:
            value = next(cells, missing)
            if value is missing:
                raise RuntimeError("row has fewer values than its schema expects")
            row.append(convert_cell(value, column, dicts))
    if next(cells, missing) is not missing:
        raise RuntimeError("row has more values than its schema expects")
    return row


def decode_page(response):
    result = response["results"][0]["result"]
    if "data" not in result:
        raise RuntimeError(f"query failed: {json.dumps(result)[:500]}")
    datasets = result["data"]["dsr"]["DS"]
    if len(datasets) != 1:
        raise RuntimeError(f"expected one dataset, got {len(datasets)}")
    dataset = datasets[0]
    dicts = dataset.get("ValueDicts", {})
    raw_rows = dataset["PH"][0].get("DM0", []) if dataset["PH"] else []
    rows = []
    schema = None
    previous = None
    for raw in raw_rows:
        if "S" in raw:
            schema = raw["S"]
        if schema is None:
            raise RuntimeError("row arrived before any schema")
        previous = decode_row(raw, previous, schema, dicts)
        rows.append(previous)
    restarted = bool(raw_rows) and bool(raw_rows[0].get("RF"))
    return Page(rows, dataset.get("RT"), dataset["IC"], restarted)


def pull_table(session, model, table, columns, page_size):
    rows = []
    restart_tokens = None
    while True:
        query = build_query(model, table, columns, page_size, restart_tokens)
        page = decode_page(call_api(session, "POST", "querydata?synchronous=true", query))
        page_rows = page.rows
        if restart_tokens is not None:
            # A restart page repeats the last row of the previous page first.
            if not page.restarted or page_rows[0] != rows[-1]:
                raise RuntimeError(f"{table}: restart page did not begin at the last row")
            page_rows = page_rows[1:]
        rows.extend(page_rows)
        if page.complete:
            return rows
        if page.restart_tokens is None or page.restart_tokens == restart_tokens:
            raise RuntimeError(f"{table}: paging made no progress after {len(rows)} rows")
        restart_tokens = page.restart_tokens


def model_row_count(session, model, table, columns):
    """Rows the dashboard's model holds for a table: the largest count of non-blank values in any column
    (Power BI aggregation 5). A second count, independent of the paged pull, to compare it against."""
    best = 0
    for column in columns:
        query = build_query(model, table, [column], 1, None)
        command = query["queries"][0]["Query"]["Commands"][0]["SemanticQueryDataShapeCommand"]
        command["Query"]["Select"] = [{"Aggregation": {"Expression": {"Column": {
            "Expression": {"SourceRef": {"Source": "t"}}, "Property": column}}, "Function": 5}, "Name": "c"}]
        command["Binding"] = {"Primary": {"Groupings": [{"Projections": [0]}]},
                              "DataReduction": {"DataVolume": 3, "Primary": {"Top": {}}}, "Version": 1}
        result = call_api(session, "POST", "querydata?synchronous=true", query)["results"][0]["result"]
        if "data" not in result:
            raise RuntimeError(f"{table}.{column}: count query failed: {json.dumps(result)[:300]}")
        best = max(best, result["data"]["dsr"]["DS"][0]["PH"][0]["DM0"][0].get("M0") or 0)
    return best


def csv_name(table):
    return re.sub(r"[^A-Za-z0-9]+", "_", table).strip("_").lower() + ".csv"


def write_csv(path, columns, rows):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(["" if cell is None else cell for cell in row] for row in rows)


def main():
    parser = argparse.ArgumentParser(description="Pull every table behind the OPM hiring dashboard.")
    parser.add_argument("--out", default="data", help="output directory (default: data)")
    parser.add_argument("--tables", nargs="*", help="table names to pull (default: all)")
    parser.add_argument("--page-size", type=int, default=PAGE_SIZE)
    args = parser.parse_args()
    if args.page_size < 2:
        raise ValueError("--page-size must be at least 2")

    session = requests.Session()
    session.headers["X-PowerBI-ResourceKey"] = resource_key(EMBED_URL)
    model = fetch_model(session, session.headers["X-PowerBI-ResourceKey"])
    tables = fetch_tables(session, model)

    if args.tables:
        unknown = set(args.tables) - set(tables)
        if unknown:
            raise ValueError(f"unknown tables: {sorted(unknown)}; available: {sorted(tables)}")
        selected = args.tables
    else:
        selected = [name for name in tables if name not in SKIP_TABLES]

    out_dir = Path(args.out)
    out_dir.mkdir(exist_ok=True)
    counts = {}
    for table in selected:
        rows = pull_table(session, model, table, tables[table], args.page_size)
        write_csv(out_dir / csv_name(table), tables[table], rows)
        in_model = model_row_count(session, model, table, tables[table])
        counts[csv_name(table)[:-4]] = {"table": table, "pulled": len(rows), "in_model": in_model}
        print(f"{table}: {len(rows)} rows (model: {in_model}) -> {out_dir / csv_name(table)}", flush=True)
    # read by publish.py for the dataset card's checks
    (out_dir / "_counts.json").write_text(json.dumps(counts, indent=1))


if __name__ == "__main__":
    main()
