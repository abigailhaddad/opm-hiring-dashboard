"""Print the numbers three dashboard pages show, computed from the pulled tables, to compare by eye.

    myenv/bin/python check_dashboard.py [--data data] [--fy 2026] [--selection-fy 2025]

Pages reproduced, with the vacancy type set to Public (DE) and every other filter at "All":
  - Assessment Usage Snapshot: total announcements and the count per assessment type, for --fy.
  - Assessment Usage by Agency: percent per assessment type for each agency, for --fy.
  - Selection Usage Snapshot: total announcements, total selections, and percent with a selection per assessment
    type, for --selection-fy.
The dashboard counts announcements from `announcement_fact` (not `usas_source`) and takes the fiscal year from the
open date. A dated record of one comparison, with screenshots, is in checks/.
"""
import argparse
from pathlib import Path

import pandas as pd

PUBLIC_DE = "1"


def read(data: Path, name: str) -> pd.DataFrame:
    return pd.read_csv(data / f"{name}.csv", dtype=str, keep_default_na=False, na_values=[""])


def public_in_fy(a: pd.DataFrame, fy: int) -> pd.DataFrame:
    opened = pd.to_datetime(a["Announcement Open Date"].str[:10])
    year = opened.dt.year + (opened.dt.month >= 10).astype(int)
    return a[(year == fy) & (a["Vacancy Type ID"] == PUBLIC_DE)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--fy", type=int, default=2026)
    ap.add_argument("--selection-fy", type=int, default=2025)
    args = ap.parse_args()

    a = read(args.data, "announcement_fact")
    types = read(args.data, "assessment_types")
    names = dict(zip(types["Assessment Type ID"], types["Assessment Type Description"]))
    bridge = read(args.data, "agency_bureau_bridge")
    orgs = read(args.data, "d2d_organizations")

    s = public_in_fy(a, args.fy).copy()
    s["type"] = s["Assessment Type ID"].map(names)
    print(f"Assessment Usage Snapshot, FY{args.fy}, Public (DE): {len(s):,} announcements")
    print(s["type"].value_counts().to_string(), "\n")

    s = s.merge(bridge, on="USAJOBS Control Number", how="left").merge(orgs[["CPDF Code", "Agency"]],
                                                                       on="CPDF Code", how="left")
    by_agency = pd.crosstab(s["Agency"], s["type"], normalize="index").mul(100).round(1)
    print(f"Assessment Usage by Agency, FY{args.fy}, Public (DE), percent of each agency's announcements "
          f"({s['Agency'].isna().sum()} with no agency):")
    print(by_agency.to_string(), "\n")

    t = public_in_fy(a, args.selection_fy).copy()
    t["type"] = t["Assessment Type ID"].map(names)
    t["selected"] = t["Selection Made for Vacancy?"].eq("Yes")
    selections = pd.to_numeric(t["Number of Selections for the Vacancy"]).sum()
    print(f"Selection Usage Snapshot, FY{args.selection_fy}, Public (DE): {len(t):,} announcements, "
          f"{selections:,.0f} selections")
    g = t.groupby("type")["selected"].agg(with_selection="sum", share="mean")
    g["share"] = (g["share"] * 100).round(2)
    print(g.sort_values("share", ascending=False).to_string())


if __name__ == "__main__":
    main()
