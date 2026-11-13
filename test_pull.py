import copy
import json
from pathlib import Path

import pull

FIXTURES = Path(__file__).parent / "fixtures"

USAS_FIRST = ["483054100", "IMP-10064473-18-RB", "Office of Personnel Management", "PROGRAM ANALYST",
              "GS", "0340", "9/11", "2021-05-11", "2021-05-21", "", "0", "0"]
USAS_DENVER = ["484452100", "SSA-4100 Denver Region", "Social Security Administration",
               "SSA-4100 General Availability for Assignment - Denver", "GS", "0301",
               "4/5/6/7/8/9/10/11/12/13/14/15", "2023-11-02", "2024-10-31", "", "122", "18"]
USAS_PAGE1_LAST = ["506506200", "6Z-HILL-10272658-LTB", "Air Force Materiel Command", "Community Planner",
                   "NH", "0020", "2", "2021-04-29", "2022-04-28", "", "1", "0"]
USAS_PAGE2_SECOND = ["506791500", "6Z-HILL-10275315-LTB", "Air Force Materiel Command",
                     "ADMINISTRATIVE AND MANAGEMENT POSITIONS-0301-ACWA", "NH", "0301", "2",
                     "2025-02-25", "2025-09-25", "", "40", "0"]
USAS_PAGE2_LAST = ["513705500", "IHS-BI-10329902-DE", "Indian Health Service", "NUTRITIONIST",
                   "GS", "0630", "9/11", "2020-03-12", "2020-04-22", "", "21", "1"]


def load(name):
    return json.loads((FIXTURES / name).read_text())


def as_final_page(response):
    final = copy.deepcopy(response)
    dataset = final["results"][0]["result"]["data"]["dsr"]["DS"][0]
    dataset["IC"] = True
    del dataset["RT"]
    return final


class FakeApi:
    def __init__(self, responses):
        self.responses = list(responses)
        self.bodies = []

    def __call__(self, session, method, path, body=None):
        self.bodies.append(body)
        return self.responses.pop(0)


def with_fake_api(responses, action):
    original = pull.call_api
    fake = FakeApi(responses)
    pull.call_api = fake
    try:
        return action(), fake
    finally:
        pull.call_api = original


MODEL = {"model_id": 1, "dataset_id": "d", "report_id": "r"}
USAS_COLUMNS = [f"c{i}" for i in range(12)]


def test_resource_key():
    assert pull.resource_key(pull.EMBED_URL) == "f3a4200a-fa0b-4a89-8b2b-1a0d245f7658"


def test_decode_first_page():
    page = pull.decode_page(load("usas_page1.json"))
    assert len(page.rows) == 15
    assert page.rows[0] == USAS_FIRST
    assert page.rows[5] == USAS_DENVER
    assert page.rows[14] == USAS_PAGE1_LAST
    assert page.complete is False
    assert page.restarted is False
    assert page.restart_tokens[0][0] == "'506506200'"


def test_decode_restart_page():
    page = pull.decode_page(load("usas_page2.json"))
    assert page.restarted is True
    assert len(page.rows) == 15
    assert page.rows[0] == USAS_PAGE1_LAST
    assert page.rows[1] == USAS_PAGE2_SECOND
    assert page.rows[14] == USAS_PAGE2_LAST


def test_decode_typed_columns():
    fact = pull.decode_page(load("typed_announcement_fact.json"))
    assert fact.rows == [
        [483054100, "2021-05-11T00:00:00", 0, 0, "No"],
        [484431800, "2022-10-01T00:00:00", 139, 7, "Yes"],
        [484432400, "2022-11-01T00:00:00", 198, 4, "Yes"],
        [484444600, "2021-01-01T00:00:00", 176, 0, "No"],
    ]
    dates = pull.decode_page(load("typed_dates.json"))
    assert dates.rows[0] == ["2009-01-01T00:00:00", 2009, "09Q2", 1]
    assert dates.rows[3] == ["2009-01-04T00:00:00", 2009, "09Q2", 1]


def test_decode_nulls_and_repeats():
    schema = [{"N": "G0", "T": 4}, {"N": "G1", "T": 1, "DN": "D0"}]
    dataset = {"PH": [{"DM0": [{"S": schema, "C": [1, 0]}, {"C": [2], "Ø": 2}, {"R": 3}]}],
               "IC": True, "ValueDicts": {"D0": ["x"]}}
    page = pull.decode_page({"results": [{"result": {"data": {"dsr": {"DS": [dataset]}}}}]})
    assert page.rows == [[1, "x"], [2, None], [2, None]]


def test_decode_values_keyed_by_column_name():
    # one-column results come as {"G0": value} rather than {"C": [value]}
    schema = [{"N": "G0", "T": 4}]
    dataset = {"PH": [{"DM0": [{"S": schema, "G0": 2012}, {"G0": 2013}, {"R": 1}]}], "IC": True}
    page = pull.decode_page({"results": [{"result": {"data": {"dsr": {"DS": [dataset]}}}}]})
    assert page.rows == [[2012], [2013], [2013]]


def test_decode_rejects_misaligned_row():
    schema = [{"N": "G0", "T": 4}, {"N": "G1", "T": 4}]
    dataset = {"PH": [{"DM0": [{"S": schema, "C": [1]}]}], "IC": True}
    try:
        pull.decode_page({"results": [{"result": {"data": {"dsr": {"DS": [dataset]}}}}]})
    except RuntimeError:
        return
    raise AssertionError("short row was accepted")


def test_pull_table_stitches_pages():
    page1, page2 = load("usas_page1.json"), load("usas_page2.json")
    rows, fake = with_fake_api(
        [page1, as_final_page(page2)],
        lambda: pull.pull_table(None, MODEL, "T", USAS_COLUMNS, 15),
    )
    assert len(rows) == 29
    assert rows[14] == USAS_PAGE1_LAST
    assert rows[15] == USAS_PAGE2_SECOND
    assert rows[28] == USAS_PAGE2_LAST
    assert len({row[0] for row in rows}) == 29
    first_window = fake.bodies[0]["queries"][0]["Query"]["Commands"][0]["SemanticQueryDataShapeCommand"][
        "Binding"]["DataReduction"]["Primary"]["Window"]
    second_window = fake.bodies[1]["queries"][0]["Query"]["Commands"][0]["SemanticQueryDataShapeCommand"][
        "Binding"]["DataReduction"]["Primary"]["Window"]
    assert first_window == {"Count": 15}
    assert second_window == {"Count": 15, "RestartTokens": page1["results"][0]["result"]["data"]["dsr"]["DS"][0]["RT"]}


def test_pull_table_rejects_bad_restart_page():
    page1, page2 = load("usas_page1.json"), load("usas_page2.json")
    del page2["results"][0]["result"]["data"]["dsr"]["DS"][0]["PH"][0]["DM0"][0]["RF"]
    try:
        with_fake_api([page1, as_final_page(page2)], lambda: pull.pull_table(None, MODEL, "T", USAS_COLUMNS, 15))
    except RuntimeError:
        return
    raise AssertionError("restart page without RF was accepted")


def test_pull_table_rejects_stalled_paging():
    page1 = load("usas_page1.json")
    try:
        with_fake_api([page1, page1], lambda: pull.pull_table(None, MODEL, "T", USAS_COLUMNS, 15))
    except RuntimeError:
        return
    raise AssertionError("stalled paging was accepted")


def test_fetch_tables_keeps_columns_only():
    schema = {"schemas": [{"error": None, "schema": {"Entities": [
        {"Name": "A", "Properties": [{"Name": "id", "Column": {}}, {"Name": "total", "Measure": {}}]},
        {"Name": "B", "Properties": [{"Name": "x", "Column": {}}]},
    ]}}]}
    tables, _ = with_fake_api([schema], lambda: pull.fetch_tables(None, MODEL))
    assert tables == {"A": ["id"], "B": ["x"]}


def test_build_query_selects_columns_in_order():
    query = pull.build_query(MODEL, "T", ["a", "b"], 10, None)
    command = query["queries"][0]["Query"]["Commands"][0]["SemanticQueryDataShapeCommand"]
    assert [s["Column"]["Property"] for s in command["Query"]["Select"]] == ["a", "b"]
    assert command["Binding"]["Primary"]["Groupings"][0]["Projections"] == [0, 1]
    assert "RestartTokens" not in command["Binding"]["DataReduction"]["Primary"]["Window"]
    assert query["modelId"] == 1


def test_dictionary_column_accepts_literal_text():
    # Dates."Month Year" on 2017-05-01 came back as "May 2017", not an index.
    column = {"N": "G0", "T": 1, "DN": "D0"}
    dicts = {"D0": ["January 2009", "February 2009"]}
    assert pull.convert_cell(1, column, dicts) == "February 2009"
    assert pull.convert_cell("May 2017", column, dicts) == "May 2017"


def test_csv_name():
    assert pull.csv_name("Pay Plan/Grade Lookup") == "pay_plan_grade_lookup.csv"
    assert pull.csv_name("USAS Source") == "usas_source.csv"


if __name__ == "__main__":
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_")]
    for name, fn in tests:
        fn()
        print(f"ok  {name}")
    print(f"{len(tests)} passed")
