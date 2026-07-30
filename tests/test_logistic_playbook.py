"""The logistic playbook end-to-end, plus the contracts it must not be able to break.

The fixture plants a Payment Delay cliff at 16/21, so "did it bin the non-linear
column" has a ground-truth answer rather than a stylistic one.
"""
import csv

import pytest

from atlas.lib.provenance import ProvenanceLedger
from atlas.lib.risk_tiers import load_policy
from atlas.orchestrator import run_analysis
from atlas.playbooks.base import BinningSpec, FeaturePlan, PlaybookBlocked
from atlas.playbooks.logistic import LogisticPlaybook

Q = "who is about to churn"
SRC = dict(source="churn_fixture", table="churn", playbook="logistic",
           decision_owner="VP Customer Success")


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    """One run shared across assertions — the fit is the slow part."""
    return run_analysis(Q, runs_root=tmp_path_factory.mktemp("logit"), **SRC)


def test_completes_with_every_gate_passing(run):
    assert run.status == "COMPLETE", run.blocked_reason
    for g in ("GATE1_profiling", "GATE2_semantics", "GATE_readiness",
              "GATE3_redteam", "GATE4_provenance", "GATE5_stakeholder"):
        assert run.gates[g] == "PASS", f"{g} -> {run.gates[g]}"


def test_writes_the_model_artefacts(run):
    for rel in ("risk_scores.csv", "model_card.md", "feature_plan.json"):
        assert (run.run_dir / rel).exists(), f"missing {rel}"
    fps = list((run.run_dir / "model").glob("*.json"))
    kinds = {p.name.split("_")[0] for p in fps}
    assert kinds == {"model", "scoring"}, kinds


def test_risk_scores_contract(run):
    """This file is the join key to any dashboard, so its shape is a contract."""
    policy = load_policy()
    with (run.run_dir / "risk_scores.csv").open() as fh:
        rows = list(csv.DictReader(fh))
    assert rows
    assert "CustomerID" in rows[0], "must key on the same entity id used elsewhere"
    assert policy.score_field in rows[0]
    assert "risk_tier" in rows[0] and "top_factor_1" in rows[0]

    ids = [r["CustomerID"] for r in rows]
    assert len(ids) == len(set(ids)), "one row per entity"
    for r in rows:
        p = float(r[policy.score_field])
        assert 0.0 <= p <= 1.0
        # the tier in the file must be the tier the locked policy assigns
        assert r["risk_tier"] == policy.tier_of(p)
        assert r["risk_tier"] in policy.band_names()
        assert int(r["flagged"]) == int(p >= policy.flag_threshold)


def test_the_planted_cliff_is_binned_not_fitted_linearly(run):
    """Payment Delay steps at 16 and 21. A raw linear term would underfit it, so the
    design must carry bin dummies and no bare `Payment Delay` coefficient."""
    card = (run.run_dir / "model_card.md").read_text()
    assert "Payment Delay=16-20" in card or "Payment Delay=21+" in card
    coef_lines = [ln for ln in card.splitlines() if ln.startswith("| Payment Delay |")]
    assert not coef_lines, "Payment Delay entered the model as a raw linear term"


def test_model_card_reports_more_than_accuracy(run):
    card = (run.run_dir / "model_card.md").read_text()
    for metric in ("ROC-AUC", "Precision", "Recall", "F1", "Majority-class accuracy"):
        assert metric in card, metric
    assert "Confusion matrix" in card
    # the cutoff must be presented as a choice, with the trade-off visible
    assert "not a business decision" in card
    assert "| threshold | flagged | precision | recall | F1 |" in card


def test_odds_ratios_are_reported_with_intervals_and_no_causal_language(run):
    """The disclaimer may legitimately contain the word "causes" ("associations,
    never causes"), so the ban applies to the CLAIM lines, not the whole document."""
    card = (run.run_dir / "model_card.md").read_text()
    assert "95% CI" in card
    assert "associational" in card.lower()
    assert "never causes" in card.lower()          # the limitation is stated outright

    claims = [ln for ln in card.splitlines()
              if ln.startswith("- Customers ")]     # phrase_odds_ratio output
    assert claims, "no plain-language odds-ratio statements were emitted"
    for ln in claims:
        low = ln.lower()
        for verb in ("causes", "drives", "leads to", "results in", "because of",
                     "increases churn", "reduces churn"):
            assert verb not in low, f"causal verb '{verb}' in claim: {ln}"
        assert "odds" in low and "not a demonstrated cause" in low


def test_model_derived_claims_are_capped_at_correlational(run):
    led = ProvenanceLedger.load(run.run_dir / "provenance.json")
    derived = led.derived()
    assert derived, "the odds ratios should be recorded as derived claims"
    for c in derived:
        assert c.evidence_tier == "correlational"
        assert c.query_hash and c.result_hash          # resolves honestly
        assert c.derivation.startswith("model:")
        # the derivation digest must be the persisted recipe
        digest = c.derivation.split(":", 1)[1]
        assert (run.run_dir / "model" / f"model_{digest}.json").exists()


def test_tier_counts_are_measured_in_sql_not_summed_in_python(run):
    """Counts about the model are ordinary claims because the scores were registered
    as a queryable view; only the coefficients stay derived."""
    led = ProvenanceLedger.load(run.run_dir / "provenance.json")
    tier_claims = [c for c in led.all() if c.claim_id.startswith("c_tier_")]
    assert tier_claims
    for c in tier_claims:
        assert not c.derivation, "a SQL-measured count must not be a derived claim"
        assert c.evidence_tier == "decomposed"


def test_red_team_recomputes_the_confusion_matrix_in_sql(run):
    v = (run.run_dir / "validation.md").read_text()
    for cell in ("tp", "fp", "tn", "fn"):
        assert f"confusion {cell} (SQL vs Python)" in v
    assert "best single-rule cut" in v


def test_headline_refuses_causal_framing(run):
    assert "associations, not causes" in run.headline
    assert "AUC" in run.headline


# --------------------------- the contracts it must not break ---------------------------
def _plan_with_binning():
    return FeaturePlan(
        table="churn", target="Churn", entity="CustomerID",
        numeric=["Payment Delay"], categorical=[],
        binnings=[BinningSpec(column="Payment Delay", edges=[16.0, 21.0],
                              labels=["0-15", "16-20", "21+"],
                              reason="cliff at 16")])


class _FakeDM:
    """A design matrix that ignored the plan and used a raw linear term."""
    feature_names = ["Payment Delay"]


def test_refuses_to_fit_a_flagged_column_as_a_raw_linear_term():
    with pytest.raises(PlaybookBlocked, match="raw linear term"):
        LogisticPlaybook._assert_no_flagged_column_left_raw(
            _plan_with_binning(), _FakeDM())


def test_refuses_when_binning_produced_no_dummies():
    class _Empty:
        feature_names = ["Age"]
    with pytest.raises(PlaybookBlocked, match="no bin dummies"):
        LogisticPlaybook._assert_no_flagged_column_left_raw(
            _plan_with_binning(), _Empty())


def test_refuses_when_a_binned_column_is_absent_from_the_training_set():
    with pytest.raises(PlaybookBlocked, match="will not silently fit a linear term"):
        LogisticPlaybook._assert_binnings_honoured(
            _plan_with_binning(), [{"Churn": 1, "Age": 30}])


def test_accepts_a_correctly_binned_design():
    class _Good:
        feature_names = ["Payment Delay=16-20", "Payment Delay=21+"]
    LogisticPlaybook._assert_no_flagged_column_left_raw(_plan_with_binning(), _Good())


def test_sign_flip_check_ignores_one_hot_contrasts():
    """A dummy's sign is relative to an arbitrary baseline, so comparing it against a
    continuous correlation invents contradictions. This pins the scoping fix."""
    from atlas.playbooks.descriptive import Finding
    from atlas.playbooks.logistic import LogisticResult

    res = LogisticResult(
        target="Churn",
        findings=[Finding(finding_id="f_corr_tenure", kind="correlation",
                          column="Tenure", headline="", effect=+0.20,
                          effect_kind="pearson_r", n=1000, query_hash="q",
                          result_hash="r", p_value=1e-9, significant=True)],
        fit={"coefficients": [
            # negative dummy vs baseline -> NOT a contradiction of a positive r
            {"name": "Tenure=6-23", "coef": -0.42, "source_column": "Tenure",
             "p_value": 1e-11},
        ]})
    assert LogisticPlaybook()._sign_flips(res) == []


def test_sign_flip_check_ignores_effects_that_are_not_significant():
    from atlas.playbooks.descriptive import Finding
    from atlas.playbooks.logistic import LogisticResult
    res = LogisticResult(
        target="Churn",
        findings=[Finding(finding_id="f", kind="correlation", column="Last Interaction",
                          headline="", effect=-0.003, effect_kind="pearson_r", n=64374,
                          query_hash="q", result_hash="r", p_value=0.47,
                          significant=False)],
        fit={"coefficients": [{"name": "Last Interaction", "coef": +0.015,
                               "source_column": "Last Interaction", "p_value": 0.335}]})
    assert LogisticPlaybook()._sign_flips(res) == []


def test_sign_flip_check_still_catches_a_real_continuous_contradiction():
    from atlas.playbooks.descriptive import Finding
    from atlas.playbooks.logistic import LogisticResult
    res = LogisticResult(
        target="Churn",
        findings=[Finding(finding_id="f", kind="correlation", column="Total Spend",
                          headline="", effect=+0.30, effect_kind="pearson_r", n=1000,
                          query_hash="q", result_hash="r", p_value=1e-20,
                          significant=True)],
        fit={"coefficients": [{"name": "Total Spend", "coef": -0.8,
                               "source_column": "Total Spend", "p_value": 1e-30}]})
    assert LogisticPlaybook()._sign_flips(res) == ["Total Spend"]
