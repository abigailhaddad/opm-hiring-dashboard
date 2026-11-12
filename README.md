# opm-hiring-dashboard

**The data:** [huggingface.co/datasets/abigailhaddad/opm-hiring-dashboard](https://huggingface.co/datasets/abigailhaddad/opm-hiring-dashboard), every table as Parquet and CSV, checked weekly and updated when OPM refreshes the dashboard (`.github/workflows/update.yml`, `publish.py`). Read the dataset card's "Things to know before using it" section before analyzing it.

Pulls the row-level tables behind OPM's [Federal Hiring Assessment and Selection Outcome Dashboard](https://www.opm.gov/policy-data-oversight/federal-hiring-and-selection-outcome-dashboard/) and writes each one to CSV.

The dashboard is an embedded Power BI report. OPM doesn't publish a download link, but the embed answers the same `querydata` requests its charts use, and the underlying model includes announcement-level tables. This script reads the model's schema and requests every column of every table, paging through the results.

## What it covers

Competitive-service job announcements (delegated examining and merit promotion) opened from fiscal year 2020 on, from USA Staffing and one other hiring system. Per the dashboard, it leaves out announcements the agency tagged Direct Hire, Excepted Service, or EO 13932 Exempt, and it may be incomplete for some agencies. Selections for the most recent four months of announcements are still coming in.

## Setup

```
uv venv myenv
uv pip install --python myenv/bin/python -r requirements.txt
```

## Run

```
myenv/bin/python pull.py                      # every table into ./data
myenv/bin/python pull.py --tables "USAS Source" "Announcement Fact"
myenv/bin/python pull.py --out somewhere --page-size 2000
```

Output is one CSV per table, e.g. `data/usas_source.csv`. `USAS Source` is the main one: one row per USA Staffing announcement with agency, job title, pay plan/series/grade, open and close dates, applications, selections and assessment method. The dashboard's own counts come from `Announcement Fact`, which also includes the other hiring system's announcements.

Datetime columns are written as ISO timestamps, converted from Power BI's stored values with no time zone attached. `USAS Source` stores numbers as text, so its numeric columns come through as strings.

## Checking against the dashboard

```
myenv/bin/python check_dashboard.py --data data --fy 2026 --selection-fy 2025
```

prints the numbers shown on three of the dashboard's pages (default filters), computed from the pulled tables, to compare with the live dashboard. `checks/` holds dated records of these comparisons, with screenshots.

## Tests

```
myenv/bin/python test_pull.py
myenv/bin/python test_publish.py
```

These run against responses captured from the live endpoint (`fixtures/`), so they need no network.

## Notes

- Power BI returns the distinct combinations of the requested columns, so fully identical rows in a table would be collapsed into one. `USAS Source` and `Announcement Fact` include the USAJOBS Control Number, so they aren't affected. The bridge tables and `Assessment Fact` might be.
- The `DAX Measures` table holds only the dashboard's calculated measures and is skipped.
- The script fails with an error if the schema, paging or response format isn't what it expects. If OPM republishes the dashboard under a new link, update `EMBED_URL` in `pull.py`; if Microsoft moves the API cluster, update `API_BASE`.
- The data is whatever OPM has published; the dataset card on Hugging Face gives the refresh time of the copy there. Check with HX@opm.gov about reuse questions.
