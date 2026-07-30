"""Cliff detection: it must fire on a real step and stay silent on a smooth trend.

The false-positive tests matter as much as the positive one. If `detect_threshold`
fired on a linear ramp, the modelling stage would bin a variable that a linear term
already handles, throwing away information for no reason.
"""
from atlas.lib.binning import (
    buckets_from_rows, edges_to_dax_switch, edges_to_labels, edges_to_sql_case,
    ntile_sql, should_group_by_value, value_group_sql,
)
from atlas.lib.thresholds import Bucket, ThresholdFinding, detect_threshold


def _buckets(rates, n=1000, lo_start=0, width=1):
    """Buckets with exact event counts for the given rates."""
    return [Bucket(index=i + 1, lo=lo_start + i * width, hi=lo_start + (i + 1) * width - 1,
                   n=n, x=round(r * n))
            for i, r in enumerate(rates)]


def test_detects_a_clean_cliff():
    # flat at 0.10, then a step to 0.70 — the churn.csv Payment Delay shape
    f = detect_threshold(_buckets([.10, .10, .10, .10, .70, .70, .70, .70]),
                         column="Payment Delay")
    assert f.kind == "cliff"
    assert f.recommend_bin is True
    assert f.cut_values and f.cut_values[0] == 4.0     # lo of the first high bucket
    assert abs(f.jump - 0.60) < 1e-9
    assert abs(f.ratio - 7.0) < 1e-9
    # the decisive condition: a step explains it far better than a line
    assert f.step_r2 > f.linear_r2 + 0.15


def test_does_not_fire_on_a_smooth_linear_ramp():
    f = detect_threshold(_buckets([.10, .20, .30, .40, .50, .60, .70, .80]),
                         column="ramp")
    assert f.recommend_bin is False
    assert f.kind == "monotone"
    # a line already explains a ramp, so the step gains little
    assert (f.step_r2 - f.linear_r2) < 0.15


def test_does_not_fire_on_a_flat_column():
    f = detect_threshold(_buckets([.30, .30, .30, .30, .30]), column="flat")
    assert f.recommend_bin is False
    assert f.jump == 0.0


def test_small_jump_below_threshold_does_not_recommend_binning():
    # a 4-point step is real but not material enough to restructure the model for
    f = detect_threshold(_buckets([.30, .30, .34, .34]), column="tiny")
    assert f.recommend_bin is False


def test_insufficient_data_is_reported_not_guessed():
    assert detect_threshold(_buckets([.1, .8]), column="c").kind == "insufficient"
    thin = detect_threshold(_buckets([.1, .1, .8, .8], n=5), column="c")
    assert thin.kind == "insufficient" and "fewer than" in thin.detail


def test_double_staircase_reports_both_cuts():
    """The real Payment Delay shape: 0.10 -> 0.58 -> 0.77 is two steps, not one."""
    rates = [.10, .10, .10, .10, .10, .10, .58, .58, .58, .77, .77, .77]
    f = detect_threshold(_buckets(rates), column="Payment Delay", max_cuts=2)
    assert f.recommend_bin is True
    assert len(f.cut_values) >= 2, f.cut_values
    assert f.cut_values == sorted(f.cut_values)


def test_tie_in_jump_breaks_on_lowest_index_deterministically():
    rates = [.10, .70, .70, .10]      # equal gaps at two candidate splits
    a = detect_threshold(_buckets(rates), column="c")
    b = detect_threshold(_buckets(rates), column="c")
    assert a.cut_values == b.cut_values     # reproducible
    assert a.kind in {"cliff", "non_monotone"}


def test_finding_round_trips_through_json():
    import json
    f = detect_threshold(_buckets([.10, .10, .10, .70, .70, .70]), column="c")
    again = ThresholdFinding.from_dict(json.loads(json.dumps(f.as_dict())))
    assert again.cut_values == f.cut_values
    assert again.recommend_bin == f.recommend_bin
    assert [b.rate for b in again.buckets] == [b.rate for b in f.buckets]


# --------------------------- binning helpers ---------------------------
def test_edges_to_labels_matches_the_churn_bins():
    assert edges_to_labels([16, 21]) == ["0-15", "16-20", "21+"]
    assert edges_to_labels([]) == ["all"]


def test_sql_case_and_dax_switch_use_identical_boundaries():
    edges, labels = [16.0, 21.0], edges_to_labels([16, 21])
    sql = edges_to_sql_case("Payment Delay", edges, labels)
    dax = edges_to_dax_switch("Churn[Payment Delay]", edges, labels)
    for cut in ("16.0", "21.0"):
        assert cut in sql and cut in dax
    for lab in labels:
        assert lab in sql and lab in dax
    assert '"Payment Delay"' in sql          # identifier quoted for the space


def test_low_cardinality_falls_back_to_grouping_by_value():
    assert should_group_by_value(8, 10) is True
    assert should_group_by_value(900, 10, row_count=64374) is False
    # 31 distinct values over 64k rows: each value has ~2000 rows, so group by value.
    # This is what makes the reported cut EXACTLY 16 instead of a decile edge of 15.
    assert should_group_by_value(31, 10, row_count=64374) is True
    # same 31 values but only 300 rows -> ~10 per value, too thin; use quantiles
    assert should_group_by_value(31, 10, row_count=300) is False
    q = value_group_sql("churn", "Support Calls", "Churn")
    assert '"Support Calls"' in q and "GROUP BY" in q


def test_ntile_sql_quotes_identifiers_and_is_read_only():
    from atlas.lib.sqlguard import is_read_only
    q = ntile_sql("churn", "Payment Delay", "Churn", 10)
    assert '"Payment Delay"' in q and "NTILE(10)" in q
    assert is_read_only(q)


def test_buckets_from_rows_orders_by_value_and_reindexes():
    rows = [{"bucket": 2, "lo": 10, "hi": 19, "n": 5, "x": 3},
            {"bucket": 1, "lo": 0, "hi": 9, "n": 5, "x": 1}]
    bs = buckets_from_rows(rows)
    assert [b.lo for b in bs] == [0.0, 10.0]
    assert [b.index for b in bs] == [1, 2]
