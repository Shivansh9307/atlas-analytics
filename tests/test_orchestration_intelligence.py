"""Phase 5: CAO routing, multi-level confidence, executive recommendations."""
from __future__ import annotations

from atlas.quality.cao import plan_run
from atlas.quality.confidence import grade_score, overall_confidence
from atlas.quality.recommendations import FOLLOW_UP_OFFERS, executive_recommendation


# ---- CAO / dynamic routing ----
def test_cao_simple_lookup_takes_cheap_path():
    p = plan_run("What is our revenue last month?")
    assert p.level == 1 and p.command == "/quick"
    assert p.agents[0] == "quality"          # copilot always first
    assert "explorer" not in p.agents and p.skipped   # full team skipped
    assert p.estimated_queries < 60


def test_cao_root_cause_engages_full_team():
    p = plan_run("Why did churn increase last quarter?")
    assert p.level == 3
    assert {"explorer", "root-cause-analyst", "red-team-validator", "deck-builder"} <= set(p.agents)
    assert p.skipped == []


def test_cao_quality_never_skipped_and_estimates_scale():
    simple = plan_run("conversion by device")
    full = plan_run("why did conversion drop?")
    assert simple.agents[0] == "quality" and full.agents[0] == "quality"
    assert full.estimated_queries > simple.estimated_queries


# ---- multi-level confidence ----
def test_confidence_dragged_toward_weakest_link():
    strong = overall_confidence(data_quality=0.95, metric_definition=0.95,
                                statistics=0.95, business_logic=0.95, narrative=0.95)
    weak_link = overall_confidence(data_quality=0.30, metric_definition=0.95,
                                   statistics=0.95, business_logic=0.95, narrative=0.95)
    assert strong.overall > 0.9 and strong.band == "Very High"
    assert weak_link.weakest == "data_quality"
    # one weak link should pull overall well below the simple mean (~0.82)
    assert weak_link.overall < 0.75


def test_grade_score_mapping():
    assert grade_score("A") > grade_score("C") > grade_score("F")
    assert grade_score("?") == 0.5


# ---- executive recommendations ----
def test_exec_recommendation_has_all_parts_and_offers():
    rec = executive_recommendation(
        root_cause="mix shift", recommendation="rebalance mix",
        estimated_impact="≈ 1,200,000", confidence="High", level=3,
        pending_approvals=["quarter_repair"])
    d = rec.as_dict()
    assert d["root_cause"] and d["recommendation"] and d["estimated_impact"]
    assert any("Approve pending repair" in a for a in rec.next_best_actions)
    assert rec.follow_up_offers == FOLLOW_UP_OFFERS


def test_pipeline_writes_confidence_and_recommendation(tmp_path):
    from atlas.orchestrator import run_analysis
    r = run_analysis("Why did EMEA margin fall in Q2?", runs_root=tmp_path)
    assert r.status == "COMPLETE"
    assert (tmp_path / r.run_id / "confidence.md").exists()
    assert (tmp_path / r.run_id / "recommendations.md").exists()
