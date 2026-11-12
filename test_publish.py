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


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
