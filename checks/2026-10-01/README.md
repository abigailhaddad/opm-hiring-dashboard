# Check against the live dashboard: refresh of 2026-10-01

Checked on 2026-11-12. The Hugging Face copy held the dashboard refresh of 2026-10-01T11:41:37; the live dashboard
said "Data through: 09/30/2026" (`home.png`). Numbers from the data come from `check_dashboard.py` run on the
Hugging Face CSVs. Filters were the dashboard's defaults: Vacancy Type Public (DE), every other filter "All".

| Dashboard page (screenshot) | Dashboard shows | From the data |
|---|---|---|
| Assessment Usage Snapshot, FY2026 (`assessment_snapshot_fy2026_public.png`) | 19,878 announcements; 11,264 / 5,384 / 2,527 / 242 / 237 / 180 / 44 by assessment type | the same, all 8 numbers |
| Assessment Usage by Agency, FY2026 (`assessment_by_agency_fy2026_public.png`) | percent by assessment type for the 21 agencies on screen | every labelled segment matches to one decimal |
| Technical Assessment Usage by Agency, FY2026 (not saved) | e.g. NASA 10.0%, USAID 36.4%, VA 53.8% | 100% minus the self-assessment-only share: 10.0, 36.4, 53.8 |
| Technical Assessment Method Usage, FY2026 (not saved) | 8,614 announcements with a technical or alternative assessment | 19,878 − 11,264 = 8,614 |
| Selection Usage Snapshot, FY2025 (`selection_snapshot_fy2025_public.png`) | 17,074 announcements, 30,565 selections; 59.09% (991), 59.05% (8,349), 55.56% (10), 38.71% (451), 33.33% (7), 7.55% (4) | the same, all 14 numbers |

Not checked: the per-method counts on the Technical Assessment Method Usage page, the trend charts (no exact
values shown), other fiscal years and vacancy types, and the three agencies below the fold on the by-agency page.

What the dashboard says about its own scope (`general_information.png`): fiscal years 2020 through 2026-Q4; data
may be incomplete for some agencies; it excludes records where the agency applied a Direct Hire, Excepted Service,
or EO 13932 Exempt tag; it covers competitive-service hiring (delegated examining and merit promotion); selection
data covers jobs opened before 5/30/2026.
