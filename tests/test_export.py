import base64

import pytest

from atlas.lib.close_the_loop import Recommendation, close_the_loop
from atlas.lib.comms import FindingBundle, email_brief, exec_summary, slack_summary
from atlas.lib.deck_html import build_html
from atlas.lib.deck_pptx import Chart, DeckSpec, Slide
from atlas.lib.export_gate import OrphanNumberError, assert_no_orphans
from atlas.lib.exporters import export_run
from atlas.lib.provenance import ProvenanceLedger
from atlas.orchestrator import run_analysis

Q = "Why did EMEA gross margin drop 4pts in Q2?"


def _ledger():
    led = ProvenanceLedger("r")
    led.record("c1", "EMEA Q2 GM", 56.0, "qh", "rh")
    return led


def _spec(claim_ids):
    return DeckSpec(
        title="EMEA margin fell 4pts", subtitle="Q2 vs Q1", decision_owner="VP Finance",
        slides=[Slide("insight", "Margin dropped to 56%",
                      chart=Chart("column", ["Q1", "Q2"], {"GM %": [60.0, 56.0]}),
                      claim_ids=claim_ids)],
        assumptions=["gross margin"], methodology="decomposition",
        provenance=[{"text": "EMEA Q2 GM", "value": "56.0%", "query_hash": "qh",
                     "tier": "decomposed"}])


# ---- export gate ----
def test_gate_blocks_orphan():
    with pytest.raises(OrphanNumberError):
        assert_no_orphans(_ledger(), ["c1", "c_missing"])
    assert_no_orphans(_ledger(), ["c1"])   # ok


# ---- HTML ----
def test_html_is_self_contained(tmp_path):
    out = build_html(_spec(["c1"]), _ledger(), tmp_path / "deck.html")
    txt = out.read_text()
    assert txt.startswith("<!doctype html>")
    assert "data:image/png;base64," in txt      # chart embedded, not linked
    assert "http://" not in txt and "https://" not in txt   # no external requests
    assert "Provenance" in txt


def test_html_blocked_on_orphan(tmp_path):
    with pytest.raises(OrphanNumberError):
        build_html(_spec(["c_missing"]), _ledger(), tmp_path / "deck.html")


# ---- comms ----
def test_comms_formats_and_gate():
    led = _ledger()
    b = FindingBundle(headline="Margin fell 4pts", decision_owner="VP Finance, EMEA",
                      key_numbers=[{"label": "Q2 GM", "value": "56%", "claim_id": "c1"}],
                      recommendation="Rebalance mix")
    assert "Margin fell 4pts" in slack_summary(b, led)
    assert email_brief(b, led)["subject"].startswith("[Analysis]")
    assert "provenance" in exec_summary(b, led).lower()

    orphan = FindingBundle(headline="x", decision_owner="y",
                           key_numbers=[{"label": "z", "value": "1", "claim_id": "nope"}],
                           recommendation="r")
    with pytest.raises(OrphanNumberError):
        slack_summary(orphan, led)


# ---- close the loop ----
def test_recommendation_defaults_and_completeness():
    r = Recommendation(action="Rebalance mix", decision_owner="VP Finance",
                       success_metric="conversion", fallback="revert pricing")
    assert r.guardrail_metric                    # auto-paired guardrail
    assert r.follow_up                            # auto date
    assert r.complete
    res = close_the_loop([r])
    assert res["complete"]


def test_incomplete_recommendation_flagged():
    r = Recommendation(action="do thing", decision_owner="", success_metric="x",
                       fallback="")
    assert not r.complete
    assert "decision_owner" in r.missing_fields()


# ---- integration: export a real run to all formats ----
def test_export_run_all_formats(tmp_path):
    res = run_analysis(Q, runs_root=tmp_path)
    out = export_run(res.run_id, formats=["html", "slack", "email", "exec"],
                     runs_root=tmp_path)
    assert set(out) >= {"html", "slack", "email", "exec"}
    html = (tmp_path / res.run_id / "deck.html").read_text()
    assert "data:image/png;base64," in html
    assert "56.0" in (tmp_path / res.run_id / "comms_slack.md").read_text()
