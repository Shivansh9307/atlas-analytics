from atlas.connectors.base import TableRef
from atlas.lib.decomposition import (
    additive_contribution,
    decompose_margin,
    simpsons_check,
)
from atlas.lib.profiling import profile_table, verdict_for
from atlas.lib.stats import proportion_ci, two_proportion_ztest


def _emea_rows(finance, quarter):
    res = finance.run(
        f"SELECT product_line, segment, revenue, cogs FROM finance "
        f"WHERE region = 'EMEA' AND quarter = '{quarter}'"
    )
    return res.rows


def test_margin_drop_is_reproduced_and_mostly_mix(finance):
    q1 = _emea_rows(finance, "Q1")
    q2 = _emea_rows(finance, "Q2")
    dec = decompose_margin(q1, q2, dim="product_line")

    # headline: exactly the 4pt drop the question asks about
    assert round(dec.m1 * 100, 2) == 60.00
    assert round(dec.m2 * 100, 2) == 56.00
    assert round(dec.delta_pts, 2) == -4.00

    # identity holds exactly
    assert round(dec.mix_total + dec.rate_total + dec.interaction_total, 10) == round(dec.delta, 10)

    # the story is a MIX shift toward low-margin Hardware, not a rate collapse
    assert dec.dominant_effect() == "mix"
    assert round(dec.mix_total * 100, 2) == -4.00
    assert abs(dec.rate_total * 100) < 0.01


def test_additive_revenue_contribution(finance):
    q1 = _emea_rows(finance, "Q1")
    q2 = _emea_rows(finance, "Q2")
    contribs = additive_contribution(q1, q2, dim="product_line", value_key="revenue")
    by = {c["key"]: c for c in contribs}
    # revenue mix moved: Software -80, Hardware +80, net 0
    assert round(by["Software"]["contribution"], 2) == -80.00
    assert round(by["Hardware"]["contribution"], 2) == 80.00


def test_no_false_simpson_paradox(finance):
    q1 = _emea_rows(finance, "Q1")
    q2 = _emea_rows(finance, "Q2")
    chk = simpsons_check(q1, q2, dim="product_line")
    # aggregate fell but within-line margins are flat -> not a paradox
    assert chk["paradox"] is False


def test_profiling_go_verdict(finance):
    report = profile_table(finance, TableRef("finance"))
    assert report.row_count == 16
    v = verdict_for(report)
    assert v.decision.startswith("GO")


def test_stats_ci_and_ztest_flag_small_samples():
    lo, hi = proportion_ci(3, 20)
    assert 0 <= lo < hi <= 1
    res = two_proportion_ztest(2, 20, 8, 20)
    assert "under-powered" in " ".join(res.flags)
