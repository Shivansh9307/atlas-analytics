from atlas.lib.sql_sanity import (
    check_date_bounds, check_join_cardinality, check_no_duplicate_keys,
    check_percentages_sum, check_temporal_coverage, run_all,
)


def test_percentages_sum():
    assert check_percentages_sum([{"p": 60}, {"p": 40}], "p").ok
    assert not check_percentages_sum([{"p": 60}, {"p": 30}], "p").ok


def test_duplicate_keys():
    rows = [{"r": "EMEA", "q": "Q1"}, {"r": "EMEA", "q": "Q2"}]
    assert check_no_duplicate_keys(rows, ["r", "q"]).ok
    dup = [{"r": "EMEA", "q": "Q1"}, {"r": "EMEA", "q": "Q1"}]
    c = check_no_duplicate_keys(dup, ["r", "q"])
    assert not c.ok and "1 duplicate" in c.detail


def test_date_bounds():
    assert check_date_bounds([{"d": 5}, {"d": 8}], "d", 1, 10).ok
    assert not check_date_bounds([{"d": 5}, {"d": 99}], "d", 1, 10).ok


def test_join_cardinality_detects_fanout():
    left = [{"id": 1}, {"id": 2}]
    one_to_one = [{"id": 1}, {"id": 2}]
    assert check_join_cardinality(left, one_to_one, "id").ok
    fanned = [{"id": 1}, {"id": 1}, {"id": 2}, {"id": 2}]   # 2x
    assert not check_join_cardinality(left, fanned, "id").ok


def test_temporal_coverage():
    rows = [{"q": "Q1"}, {"q": "Q2"}]
    assert check_temporal_coverage(rows, "q", ["Q1", "Q2"]).ok
    c = check_temporal_coverage(rows, "q", ["Q1", "Q2", "Q3"])
    assert not c.ok and "Q3" in c.detail


def test_run_all_aggregates():
    res = run_all([check_percentages_sum([{"p": 100}], "p"),
                   check_no_duplicate_keys([{"k": 1}], ["k"])])
    assert res["passed"] and res["failed"] == []
