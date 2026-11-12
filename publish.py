"""Publish the pulled tables to Hugging Face as Parquet and CSV, with a dataset card built from the data.

    HF_TOKEN=... myenv/bin/python publish.py [--data data] [--dry-run] [--force]

The dashboard's refresh time comes from USAS Source, whose last column is named after it (for example
"<month>/<day>/<year> <time>"). That column is renamed `dashboard_refreshed_at` so the schema stays the same from
one refresh to the next. Nothing is uploaded if the dataset already holds this refresh, unless --force.
Every count in the card is computed from the files.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

REPO_ID = "abigailhaddad/opm-hiring-dashboard"
PROJECT_URL = "https://github.com/abigailhaddad/opm-hiring-dashboard"
DASHBOARD_URL = "https://www.opm.gov/policy-data-oversight/federal-hiring-and-selection-outcome-dashboard/"
REFRESH_HEADER = re.compile(r"^\d{1,2}/\d{1,2}/\d{4} \d{1,2}:\d{2}:\d{2} [AP]M$")
MARKER = "Dashboard refreshed: "


def load(data: Path) -> tuple[dict[str, pd.DataFrame], str]:
    tables, refreshed = {}, None
    for f in sorted(p for p in data.glob("*.csv") if not p.name.startswith("_")):
        df = pd.read_csv(f, dtype=str, keep_default_na=False, na_values=[""])
        stamp = [c for c in df.columns if REFRESH_HEADER.match(c)]
        if stamp:
            df = df.rename(columns={stamp[0]: "dashboard_refreshed_at"})
            vals = df["dashboard_refreshed_at"].dropna().unique()
            if len(vals) != 1:
                raise SystemExit(f"{f.name}: expected one refresh time, got {list(vals)[:5]}")
            refreshed = vals[0]
        tables[f.stem] = df
    if not refreshed:
        raise SystemExit("no refresh-time column found in any table (expected one in usas_source.csv)")
    return tables, refreshed


def count_check(counts: dict) -> str:
    """The card's sentence on pulled vs model row counts, from pull.py's _counts.json."""
    off = {n: c for n, c in counts.items() if c["pulled"] != c["in_model"]}
    lead = (f"Each table's row count was compared with the count the dashboard's own model reports for it "
            f"(a separate query). {len(counts) - len(off)} of {len(counts)} match")
    if not off:
        return lead + "."
    bits = "; ".join(f"`{n}` {c['pulled']:,} pulled vs {c['in_model']:,} in the model" for n, c in off.items())
    return (lead + f". The others: {bits}. The dashboard's query interface returns distinct rows, so rows "
            f"identical in every column come back once; a table short by a few rows has that many duplicates.")


def fiscal_year(dates: pd.Series) -> pd.Series:
    d = pd.to_datetime(dates.str[:10])
    return d.dt.year + (d.dt.month >= 10).astype(int)


def quirks(u: pd.DataFrame) -> str:
    """Bullets on columns that don't mean what they look like they mean; every count comes from the data."""
    dh = u["Direct Hire Indicator"].value_counts()
    ann_dup = u["Announcement Number"].duplicated(keep=False).sum()
    status = u["Announcement Status"].value_counts()
    status_txt = ", ".join(f"{s} {n:,}" for s, n in status.items())
    manual = u["Manual Assessment Method"].isna().mean()
    opened = pd.to_datetime(u["Announcement Open Date"].str[:10])
    last = opened.dt.to_period("M").max()
    sel = u["Selection Made for Vacancy?"].eq("Yes")
    early = opened.dt.to_period("M") == last - 6
    late = opened.dt.to_period("M") == last
    term = u.loc[u["Appointment Type ID"] == "2", "Appointment Type"].unique()
    dh_txt = (f"`false` on all {len(u):,} rows" if list(dh.index) == ["false"]
              else "; ".join(f"`{v}` {n:,}" for v, n in dh.items()))
    return f"""- `Direct Hire Indicator` is {dh_txt}. The dashboard says it excludes announcements
  where the agency applied a Direct Hire, Excepted Service, or EO 13932 Exempt tag, so this column can't be
  used to find direct-hire jobs.
- Selections are still coming in for recent announcements. Of announcements opened in {last}, {sel[late].mean():.0%}
  show a selection; of those opened in {last - 6}, {sel[early].mean():.0%}. The dashboard only reports selections
  for jobs opened about four months before the end of its data; do the same when computing selection rates.
- The dashboard's announcement counts come from `announcement_fact`, which includes the announcements that are
  not in `usas_source`. Use `announcement_fact` to match its numbers.
- `Announcement Status` includes announcements that were removed or are still open: {status_txt}.
- `USAJOBS Control Number` is the unique key. `Announcement Number` is not: {ann_dup:,} rows share
  theirs with another row.
- `Appointment Type ID` is 2 only for `Appointment Type` {", ".join(f"`{t}`" for t in term)}; every other
  appointment type, including seasonal and intermittent, is 1.
- The manual assessment columns (`Manual Assessment Method`, `Manual Assessment Method Details`,
  `Method Details Clean`) are blank on about {manual:.0%} of rows."""


def card(tables: dict[str, pd.DataFrame], refreshed: str, counts: dict) -> str:
    u, a = tables["usas_source"], tables["announcement_fact"]
    only_a = (~a["USAJOBS Control Number"].isin(u["USAJOBS Control Number"])).sum()
    years = fiscal_year(u["Announcement Open Date"]).value_counts().sort_index()
    first, last = u["Announcement Open Date"].min()[:10], u["Announcement Open Date"].max()[:10]
    rows = "\n".join(f"| `{n}` | {len(df):,} | {len(df.columns)} |" for n, df in tables.items())
    configs = "\n".join(f"- config_name: {n}\n  data_files: data/{n}.parquet" + ("\n  default: true" if n == "usas_source" else "")
                        for n in tables)
    return f"""---
license: other
license_name: us-government-public-data
pretty_name: OPM Federal Hiring Assessment and Selection Outcome Dashboard, all tables
language: [en]
tags: [government, federal-hiring, opm, usajobs]
configs:
{configs}
---

# OPM federal hiring dashboard: the tables behind it

Every table behind OPM's [Federal Hiring Assessment and Selection Outcome Dashboard]({DASHBOARD_URL}),
pulled from the dashboard's public Power BI embed. OPM publishes the dashboard but no download; this is the
same data, row by row. Code: {PROJECT_URL}.

{MARKER}**{refreshed}** (the time the dashboard's data was last refreshed, from the dashboard itself).
Checked for updates every week; a new pull is published only when this changes.

## Tables

| Table | Rows | Columns |
|---|---|---|
{rows}

`usas_source` is the main one: one row per USA Staffing job announcement ({len(u):,}, opened
{first} to {last}, fiscal years {years.index.min()}–{years.index.max()}), with agency, job title, pay plan,
series, grade, open and close dates, applications, selections and assessment method. Numbers in it are stored
as text, as the dashboard has them.

Announcements opened per fiscal year in `usas_source`: """ + ", ".join(f"FY{y} {n:,}" for y, n in years.items()) + f""".

## Things to know before using it

{quirks(u)}

## Checks

- {count_check(counts)}
- `USAJOBS Control Number`: {u["USAJOBS Control Number"].nunique():,} distinct of {len(u):,} rows in `usas_source`,
  {a["USAJOBS Control Number"].nunique():,} of {len(a):,} in `announcement_fact`.
- `announcement_fact` has {only_a:,} announcements that are not in `usas_source`, in every year; every
  `usas_source` announcement is in `announcement_fact`. The dashboard names two sources: USA Staffing, and
  Monster Government Solutions (in the `data_definitions` table) or Apply Government Solutions (on its General
  Information page). The extra announcements are probably from that second system. That is an inference, not
  something the dashboard states.

## Notes

- The data is what OPM publishes; see the dashboard and its `data_definitions` table for definitions.
  Questions about the data go to OPM (HX@opm.gov).
- Datetime columns are ISO timestamps as the dashboard stores them.
- The refresh-time column (`dashboard_refreshed_at`) is named after the refresh time in the dashboard
  itself; it is renamed here so the schema doesn't change between refreshes.
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--out", type=Path, default=Path("publish"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    tables, refreshed = load(a.data)
    if not a.force and not a.dry_run:
        from huggingface_hub import HfApi, hf_hub_download
        try:
            old = Path(hf_hub_download(REPO_ID, "README.md", repo_type="dataset")).read_text()
            if f"{MARKER}**{refreshed}**" in old:
                print(f"dataset already holds the refresh of {refreshed}; nothing uploaded")
                return 0
        except Exception:  # noqa: BLE001 - a new or empty dataset has no card yet
            pass
    (a.out / "data").mkdir(parents=True, exist_ok=True)
    for n, df in tables.items():
        df.to_parquet(a.out / "data" / f"{n}.parquet", index=False)
        df.to_csv(a.out / "data" / f"{n}.csv", index=False)
    counts_file = a.data / "_counts.json"
    if not counts_file.exists():
        raise SystemExit(f"{counts_file} is missing: run pull.py, which writes it")
    (a.out / "README.md").write_text(card(tables, refreshed, json.loads(counts_file.read_text())))
    print({n: len(df) for n, df in tables.items()}, "refreshed", refreshed)
    if a.dry_run:
        print(f"dry run: wrote {a.out}, uploaded nothing")
        return 0
    from huggingface_hub import HfApi
    api = HfApi()
    api.create_repo(REPO_ID, repo_type="dataset", exist_ok=True)
    info = api.upload_folder(repo_id=REPO_ID, repo_type="dataset", folder_path=str(a.out),
                             commit_message=f"Dashboard refresh of {refreshed}")
    print(info)
    return 0


if __name__ == "__main__":
    sys.exit(main())
