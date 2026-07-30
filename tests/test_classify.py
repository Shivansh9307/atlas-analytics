"""Classification metrics against hand-computed fixtures, plus the split/encoding rules."""
import math

import pytest

from atlas.lib.classify import (
    ConfusionMatrix, brier_score, calibration_bins, confusion_at, majority_baseline,
    roc_auc, threshold_table,
)
from atlas.lib.logit import (
    Standardizer, phrase_odds_ratio, stratified_split, Coefficient,
)


def test_confusion_matrix_arithmetic_by_hand():
    y = [1, 1, 1, 0, 0, 0, 0, 0]
    s = [.9, .8, .3, .7, .2, .1, .1, .05]
    cm = confusion_at(y, s, 0.5)
    assert (cm.tp, cm.fp, cm.tn, cm.fn) == (2, 1, 4, 1)
    assert cm.precision == 2 / 3
    assert cm.recall == 2 / 3
    assert cm.f1 == pytest.approx(2 / 3)
    assert cm.accuracy == 6 / 8
    assert cm.specificity == 4 / 5


def test_roc_auc_perfect_and_inverted_and_random():
    y = [0, 0, 1, 1]
    assert roc_auc(y, [.1, .2, .8, .9]) == 1.0        # perfectly ranked
    assert roc_auc(y, [.9, .8, .2, .1]) == 0.0        # perfectly inverted
    # all-tied scores must be exactly 0.5, not sort-order dependent
    assert roc_auc(y, [.5, .5, .5, .5]) == 0.5


def test_roc_auc_handles_partial_ties_with_mid_ranks():
    """A tie block straddling the class boundary must be counted as half a win.

    Enumerating the four positive/negative pairs by hand:
      .5 vs .1 -> win (1.0)      .5 vs .5 -> tie  (0.5)
      .9 vs .1 -> win (1.0)      .9 vs .5 -> win  (1.0)
    => 3.5 / 4 = 0.875. Naive ranking without mid-ranks gives 1.0 or 0.75
    depending on sort order, which is the bug this pins.
    """
    y = [0, 0, 1, 1]
    assert roc_auc(y, [.1, .5, .5, .9]) == pytest.approx(0.875)


def test_roc_auc_is_none_when_a_class_is_absent():
    assert roc_auc([1, 1, 1], [.2, .5, .9]) is None


def test_majority_baseline_is_the_floor_a_model_must_beat():
    y = [1] * 47 + [0] * 53
    base = majority_baseline(y)
    # predicting the majority scores 53% accuracy while catching zero positives
    assert base.accuracy == pytest.approx(0.53)
    assert base.recall == 0.0


def test_threshold_table_shows_the_precision_recall_tradeoff():
    y = [1, 1, 1, 0, 0, 0]
    s = [.9, .6, .4, .5, .2, .1]
    rows = threshold_table(y, s, [0.3, 0.5, 0.7])
    assert [r["threshold"] for r in rows] == [0.3, 0.5, 0.7]
    # recall must be non-increasing as the cutoff rises
    recalls = [r["recall"] for r in rows]
    assert recalls == sorted(recalls, reverse=True)


def test_brier_and_calibration():
    y = [1, 0]
    assert brier_score(y, [1.0, 0.0]) == 0.0          # perfect
    assert brier_score(y, [0.5, 0.5]) == 0.25         # coin flip
    bins = calibration_bins([1, 1, 0, 0], [.9, .8, .2, .1], k=2)
    assert len(bins) == 2
    assert all("gap" in b for b in bins)


# --------------------------- split + encoding ---------------------------
def test_stratified_split_preserves_class_balance_and_is_reproducible():
    y = [1] * 40 + [0] * 60
    ids = list(range(100))
    tr1, te1 = stratified_split(y, ids, test_frac=0.25, seed=42)
    tr2, te2 = stratified_split(y, ids, test_frac=0.25, seed=42)
    assert (tr1, te1) == (tr2, te2)                    # deterministic
    assert set(tr1) & set(te1) == set()                # disjoint
    assert len(tr1) + len(te1) == 100                  # exhaustive
    # class balance preserved in the test split (10 of 40 pos, 15 of 60 neg)
    assert sum(y[i] for i in te1) == 10
    assert len(te1) == 25


def test_stratified_split_changes_with_the_seed():
    y = [1] * 40 + [0] * 60
    ids = list(range(100))
    assert stratified_split(y, ids, seed=1) != stratified_split(y, ids, seed=2)


def test_standardizer_round_trip():
    rows = [{"x": 10.0}, {"x": 20.0}, {"x": 30.0}]
    s = Standardizer().fit(rows, ["x"])
    assert s.means["x"] == 20.0
    assert s.sds["x"] == pytest.approx(10.0)
    assert s.z("x", 30.0) == pytest.approx(1.0)


def test_standardizer_survives_a_constant_column():
    s = Standardizer().fit([{"x": 5.0}, {"x": 5.0}], ["x"])
    assert s.sds["x"] == 1.0            # no divide-by-zero
    assert s.z("x", 5.0) == 0.0


# --------------------------- phrasing discipline ---------------------------
def _coef(**kw):
    base = dict(name="Payment Delay", coef=0.83, std_err=0.02, z=41.0, p_value=1e-90,
                odds_ratio=2.3, or_ci_low=2.2, or_ci_high=2.4,
                unit="per 1 SD (6.9) of Payment Delay", source_column="Payment Delay")
    base.update(kw)
    return Coefficient(**base)


def test_odds_ratio_phrasing_is_associational_never_causal():
    text = phrase_odds_ratio(_coef())
    assert "2.30x higher odds" in text
    assert "95% CI 2.20-2.40" in text
    assert "not a demonstrated cause" in text
    for verb in ("causes", "drives", "leads to", "results in", "because of",
                 "increases churn"):
        assert verb not in text.lower(), f"causal verb '{verb}' leaked into model prose"


def test_protective_effects_are_phrased_as_lower_odds():
    text = phrase_odds_ratio(_coef(odds_ratio=0.5, or_ci_low=0.45, or_ci_high=0.55))
    assert "2.00x lower odds" in text


def test_causal_phrasing_is_refused_outright():
    with pytest.raises(ValueError, match="observational"):
        phrase_odds_ratio(_coef(), causal=True)
