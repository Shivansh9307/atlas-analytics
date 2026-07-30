"""Provenance and tier rules for model-derived numbers.

These are the guarantees that let a coefficient appear on a slide at all. Each test
tries to break one.
"""
import json

import pytest

from atlas.lib.gates import gate4_provenance
from atlas.lib.model_provenance import (
    ModelFingerprint, ScoringFingerprint, fingerprint_exists, write_fingerprint,
)
from atlas.lib.provenance import Claim, ProvenanceLedger
from atlas.lib.risk_tiers import load_policy


def _fp(**kw):
    base = dict(
        algorithm="statsmodels.Logit", algorithm_version="0.14.0", seed=42,
        train_query_hash="abc123", train_result_hash="def456",
        feature_names=("Age", "Tenure"),
        preprocessing=(("Age", "zscore:mu=41,sd=13"),),
        split=("stratified", 0.25, True),
        hyperparams=(("method", "newton"),),
        coefficients=(("Age", 0.5), ("Tenure", -0.2)), intercept=-1.0)
    base.update(kw)
    return ModelFingerprint(**base)


# --------------------------- digest behaviour ---------------------------
def test_digest_is_stable_for_identical_recipes():
    assert _fp().digest() == _fp().digest()


@pytest.mark.parametrize("change", [
    {"seed": 43},
    {"coefficients": (("Age", 0.5000001), ("Tenure", -0.2))},
    {"feature_names": ("Age",)},
    {"train_result_hash": "different"},
    {"split": ("stratified", 0.30, True)},
])
def test_digest_changes_when_anything_that_matters_changes(change):
    """The digest IS the claim's result_hash. If it collided across different fits,
    two different numbers would share a provenance id."""
    assert _fp(**change).digest() != _fp().digest()


def test_fingerprint_is_written_and_discoverable(tmp_path):
    d = write_fingerprint(tmp_path, _fp(), kind="model")
    assert fingerprint_exists(tmp_path, d)
    assert not fingerprint_exists(tmp_path, "0000000000000000")
    payload = json.loads(next((tmp_path / "model").glob("*.json")).read_text())
    # the recipe must be reconstructable, not just hashed
    assert payload["seed"] == 42
    assert payload["train_query_hash"] == "abc123"
    assert payload["coefficients"][0] == ["Age", 0.5]


def test_fingerprints_are_not_written_into_evidence(tmp_path):
    """`QueryStore.verify()` re-hashes evidence rows; a derivation digest is not a
    row hash, so storing it there would make verification report a false mismatch."""
    write_fingerprint(tmp_path, _fp(), kind="model")
    assert (tmp_path / "model").exists()
    assert not (tmp_path / "evidence").exists()


# --------------------------- ledger rules ---------------------------
def test_derived_claim_uses_real_parent_query_and_derivation_digest():
    led = ProvenanceLedger("r1")
    fp = _fp()
    c = led.record_derived("c_or_age", "Odds ratio, Age", 1.65,
                           parent_query_hash="abc123", parent_result_hash="def456",
                           derivation_hash=fp.digest(), derivation_label="model:x")
    assert c.query_hash == "abc123"          # the REAL training query
    assert c.result_hash == fp.digest()      # the derivation digest
    assert led.resolves("c_or_age")          # therefore GATE 4 can pass honestly
    assert led.derived() == [c]


@pytest.mark.parametrize("tier", ["decomposed", "tested"])
def test_derived_claim_cannot_claim_a_tier_it_has_not_earned(tier):
    """An observational fit is correlational even with p < 1e-300. Enforced, not
    left to whoever writes the next playbook to remember."""
    led = ProvenanceLedger("r1")
    with pytest.raises(ValueError, match="never 'decomposed' or 'tested'"):
        led.record_derived("c", "t", 1.0, parent_query_hash="q",
                           parent_result_hash="r", derivation_hash="d",
                           derivation_label="model:d", evidence_tier=tier)


@pytest.mark.parametrize("missing", [
    {"parent_query_hash": ""},
    {"parent_result_hash": ""},
    {"derivation_hash": ""},
])
def test_derived_claim_refuses_a_missing_link(missing):
    led = ProvenanceLedger("r1")
    kw = dict(parent_query_hash="q", parent_result_hash="r", derivation_hash="d",
              derivation_label="model:d")
    kw.update(missing)
    with pytest.raises(ValueError):
        led.record_derived("c", "t", 1.0, **kw)


def test_existing_provenance_json_still_loads(tmp_path):
    """`Claim(**c)` must keep parsing files written before the new fields existed."""
    old = {"run_id": "r0", "claims": [{
        "claim_id": "c1", "text": "t", "value": 1.0, "query_hash": "q",
        "result_hash": "r", "evidence_tier": "decomposed", "slide_number": None,
        "notes": ""}]}
    p = tmp_path / "provenance.json"
    p.write_text(json.dumps(old))
    led = ProvenanceLedger.load(p)
    assert led.get("c1").derivation == ""
    assert led.get("c1").parent_claims == []


# --------------------------- gate 4 ---------------------------
def test_gate4_blocks_a_derived_claim_with_no_persisted_recipe():
    g = gate4_provenance([], ["c_or_age"])
    assert not g.passed
    assert "unfingerprinted" in g.summary
    assert g.defects[0].kind == "unprovenanced_number"


def test_gate4_signature_stays_backward_compatible():
    """tests/test_gates.py calls this positionally with one argument."""
    assert gate4_provenance([]).passed
    assert not gate4_provenance(["c7"]).passed


# --------------------------- risk tiers ---------------------------
def test_tier_policy_loads_and_validates():
    p = load_policy("default")
    assert p.band_names() == ["Low", "Medium", "High"]
    assert p.flag_threshold == 0.5
    assert "not a business decision" in p.flag_threshold_note


def test_csv_and_dax_tiering_agree_across_the_whole_probability_range():
    """The join key between risk_scores.csv and the dashboard. If these drift, the
    exported list and the report disagree about who is High risk."""
    import re
    p = load_policy("default")
    dax = p.dax_switch("RiskScores[churn_probability]")
    # parse the generated SWITCH back into (bound, label) pairs
    bounds = [(float(m.group(1)), m.group(2))
              for m in re.finditer(r"<\s*([0-9.]+),\s*\"([^\"]+)\"", dax)]
    fallback = re.findall(r'"([^"]+)"\s*\n\)', dax)[-1]

    def dax_tier(x: float) -> str:
        for bound, label in bounds:
            if x < bound:
                return label
        return fallback

    for i in range(0, 1001):
        x = i / 1000
        assert dax_tier(x) == p.tier_of(x), f"disagreement at p={x}"


def test_sql_case_uses_the_same_boundaries_as_python():
    p = load_policy("default")
    sql = p.sql_case("churn_probability")
    for b in p.bands[:-1]:
        assert repr(b.max) in sql
    for name in p.band_names():
        assert f"'{name}'" in sql


def test_tier_policy_digest_changes_with_the_bands():
    from atlas.lib.risk_tiers import Band, TierPolicy
    a = load_policy("default")
    b = TierPolicy(profile="x", score_field=a.score_field, method=a.method,
                   bands=(Band("Low", 0.0, 0.5), Band("High", 0.5, 1.01)),
                   flag_threshold=a.flag_threshold)
    assert a.digest() != b.digest()


def test_tier_policy_rejects_a_gap_between_bands():
    from atlas.lib.risk_tiers import Band, TierPolicy
    bad = TierPolicy(profile="x", score_field="p", method="fixed_probability",
                     bands=(Band("Low", 0.0, 0.4), Band("High", 0.5, 1.01)),
                     flag_threshold=0.5)
    with pytest.raises(ValueError, match="gap or overlap"):
        bad.validate()


def test_scoring_fingerprint_binds_model_and_tier_policy_together():
    s = ScoringFingerprint(model_digest="m1", score_query_hash="q",
                           score_result_hash="r", tier_policy_digest="t1",
                           flag_threshold=0.5, output_sha256="abc", row_count=10)
    s2 = ScoringFingerprint(model_digest="m1", score_query_hash="q",
                            score_result_hash="r", tier_policy_digest="t2",
                            flag_threshold=0.5, output_sha256="abc", row_count=10)
    # changing the tier policy must change the scoring identity
    assert s.digest() != s2.digest()
