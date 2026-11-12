import publish


def test_count_check_all_match():
    counts = {"a": {"table": "A", "pulled": 3, "in_model": 3}, "b": {"table": "B", "pulled": 5, "in_model": 5}}
    assert publish.count_check(counts).endswith("2 of 2 match.")


def test_count_check_names_the_tables_that_differ():
    counts = {"a": {"table": "A", "pulled": 3, "in_model": 3}, "b": {"table": "B", "pulled": 1004, "in_model": 1005}}
    text = publish.count_check(counts)
    assert "1 of 2 match" in text and "`b` 1,004 pulled vs 1,005 in the model" in text and "`a`" not in text


def test_refresh_header_pattern():
    assert publish.REFRESH_HEADER.match("10/1/2026 11:41:37 AM")
    assert not publish.REFRESH_HEADER.match("Total Applications")


def test_fiscal_year_starts_in_october():
    import pandas as pd
    fy = publish.fiscal_year(pd.Series(["2019-09-30", "2019-10-01", "2026-09-30T00:00:00"]))
    assert list(fy) == [2019, 2020, 2026]


def test_quirks_reports_counts_from_the_data():
    import pandas as pd
    u = pd.DataFrame({
        "Direct Hire Indicator": ["false"] * 4,
        "Announcement Number": ["A", "A", "B", "C"],
        "Announcement Status": ["Closed", "Closed", "Removed", "Open"],
        "Manual Assessment Method": [None, None, None, "Interview"],
        "Announcement Open Date": ["2026-03-02", "2026-03-05", "2026-09-01", "2026-09-02"],
        "Selection Made for Vacancy?": ["Yes", "Yes", "No", "Yes"],
        "Appointment Type ID": ["1", "2", "1", "1"],
        "Appointment Type": ["Permanent", "Term", "Seasonal", "Permanent"],
    })
    text = publish.quirks(u)
    assert "`false` on all 4 rows" in text
    assert "opened in 2026-09, 50%" in text and "opened in 2026-03, 100%" in text
    assert "2 rows share" in text and "Closed 2, Removed 1, Open 1" in text
    assert "`Term`;" in text and "about 75% of rows" in text


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
