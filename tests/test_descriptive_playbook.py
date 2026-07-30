"""The descriptive playbook end-to-end on a schema with no revenue/cogs/date column.

The fixture (tests/fixtures/make_churn_fixture.py) plants a known structure, so these
are ground-truth assertions rather than "it ran without crashing" assertions:

  * Payment Delay steps at 16 and 21          -> must be found, and binned
  * Contract Length 'Monthly' churns far more -> must rank as a real segment gap
  * Gender has NO effect                      -> must NOT be reported as significant
"""
import json
from pathlib import Path

from pptx import Presentation

from atlas.lib.provenance import ProvenanceLedger
from atlas.orchestrator import run_analysis
from atlas.playbooks.base import FeaturePlan

Q = "what drives churn"
SRC = dict(source="churn_fixture", table="churn", playbook="descriptive",
           decision_owner="VP Customer Success")


def _run(tmp_path):
    return run_analysis(Q, runs_root=tmp_path, **SRC)


def test_completes_with_no_revenue_cogs_or_date_column(tmp_path):
    res = _run(tmp_path)
    assert res.status == "COMPLETE", res.blocked_reason
    for g in ("GATE1_profiling", "GATE2_semantics", "GATE_readiness",
              "GATE3_redteam", "GATE4_provenance", "GATE5_stakeholder"):
        assert res.gates[g] == "PASS", f"{g} -> {res.gates[g]}"


def test_produces_the_full_artefact_set(tmp_path):
    res = _run(tmp_path)
    for rel in ("brief.md", "hypotheses.md", "findings.md", "validation.md",
                "narrative.md", "deck.pptx", "speaker_notes.md", "provenance.json",
                "feature_plan.json"):
        assert (res.run_dir / rel).exists(), f"missing {rel}"
    assert list((res.run_dir / "queries").glob("*.sql"))
    assert list((res.run_dir / "evidence").glob("*.json"))


def test_finds_the_planted_payment_delay_cliff(tmp_path):
    """The fixture plants a rate step at 16 and again at 21. Both must be recovered."""
    res = _run(tmp_path)
    plan = FeaturePlan.from_dict(
        json.loads((res.run_dir / "feature_plan.json").read_text()))
    binning = plan.binning_for("Payment Delay")
    assert binning is not None, "the cliff was not detected at all"
    assert binning.edges == [16.0, 21.0], binning.edges
    assert binning.labels == ["0-15", "16-20", "21+"]


def test_inert_columns_are_not_reported_as_drivers(tmp_path):
    """Gender is generated with no relationship to churn. Saying otherwise would be
    the single most damaging failure mode for this playbook."""
    res = _run(tmp_path)
    findings = (res.run_dir / "findings.md").read_text()
    gender = [ln for ln in findings.splitlines() if "| Gender |" in ln]
    assert gender, "Gender should still be listed, just not as significant"
    assert "correlational" in gender[0]
    assert "tested" not in gender[0]


def test_headline_names_the_real_driver_and_refuses_causal_language(tmp_path):
    res = _run(tmp_path)
    assert "Payment Delay" in res.headline
    assert "correlational" in res.headline.lower()
    for causal in ("drives", "causes", "because of", "leads to"):
        assert causal not in res.headline.lower(), f"causal verb '{causal}' in headline"


def test_every_deck_number_resolves_to_a_query(tmp_path):
    res = _run(tmp_path)
    led = ProvenanceLedger.load(res.run_dir / "provenance.json")
    base = led.get("c_base_rate")
    assert base is not None
    assert 0 < base.value < 100                      # a percentage, not a fraction
    for claim in led.all():
        assert claim.query_hash and claim.result_hash, f"{claim.claim_id} unprovenanced"
    prs = Presentation(str(res.run_dir / "deck.pptx"))
    assert len(prs.slides) >= 4


def test_findings_declare_the_ranking_is_a_heuristic(tmp_path):
    """The rank score mixes r, pp-gaps and jumps onto one scale. Presenting that as
    a statistical ordering would overstate it."""
    res = _run(tmp_path)
    text = (res.run_dir / "findings.md").read_text()
    assert "not a statistical statement" in text
    assert "Nothing in this document establishes causation" in text


def test_methodology_states_the_evidence_tier_is_correlational(tmp_path):
    res = _run(tmp_path)
    notes = (res.run_dir / "speaker_notes.md").read_text().lower()
    assert "association" in notes


def test_red_team_checks_the_law_of_total_probability(tmp_path):
    res = _run(tmp_path)
    v = (res.run_dir / "validation.md").read_text()
    assert "weighted rates over" in v
    assert "no window function" in v
    assert "**PASS**" in v


def test_resume_rehydrates_the_descriptive_result(tmp_path):
    """serialize/deserialize round-trip: a bad pair only shows up on /resume."""
    from atlas.lib.run_state import RunState
    res = _run(tmp_path)
    state = RunState.load(res.run_id, tmp_path)
    keep = {"profile", "frame", "quality", "semantics", "readiness_gate", "explore"}
    state.nodes = {k: v for k, v in state.nodes.items() if k in keep}
    state.outputs = {k: v for k, v in state.outputs.items() if k in keep}
    state.status = "FAILED"
    state.save(tmp_path)
    (res.run_dir / "deck.pptx").unlink()

    again = run_analysis(Q, runs_root=tmp_path, resume_run_id=res.run_id, **SRC)
    assert again.status == "COMPLETE", again.blocked_reason
    assert (res.run_dir / "deck.pptx").exists()
    assert "Payment Delay" in again.headline


def test_binding_can_be_pinned_explicitly(tmp_path):
    """`bind=` overrides inference, and the override is recorded as such."""
    res = run_analysis(Q, runs_root=tmp_path, bind={"target": "Churn"}, **SRC)
    assert res.status == "COMPLETE", res.blocked_reason
    brief = (res.run_dir / "brief.md").read_text()
    # a pinned column is NOT reported as an inferred assumption
    assert "Role 'target' inferred" not in brief
