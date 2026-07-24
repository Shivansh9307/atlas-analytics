"""Export a completed run to additional formats — HTML, PDF, Slack, email, exec.

Rebuilds the DeckSpec from the run's persisted node outputs (Phase 1 run-state) and
its provenance.json, then produces each requested format. Every format passes the
same Gate 4 (no orphan numbers) via export_gate. "Build every export from one run."
"""
from __future__ import annotations

from pathlib import Path

from atlas.config import PATHS
from atlas.lib import comms as comms_mod
from atlas.lib.comms import FindingBundle
from atlas.lib.deck_html import build_html, export_pdf
from atlas.lib.provenance import ProvenanceLedger
from atlas.lib.run_state import RunState


def _rebuild_spec(state: RunState, ledger: ProvenanceLedger):
    """Reconstruct the DeckSpec from persisted node outputs."""
    from atlas.orchestrator import (
        _build_deck_spec, _deser_dec, _extract_hints,
    )
    explore = state.outputs.get("explore", {})
    frame = state.outputs.get("frame", {})
    dec = _deser_dec(explore["dec"])
    add = explore.get("add", [])
    assumptions = frame.get("assumptions", [])
    h = _extract_hints(state.question)
    owner = "VP Finance, EMEA"
    return _build_deck_spec(h["region"], h["p1"], h["p2"], dec, add, owner,
                            assumptions, ledger)


def _bundle(state: RunState, ledger: ProvenanceLedger, spec) -> FindingBundle:
    key = []
    for cid in ("c_gm_p1", "c_gm_p2", "c_delta", "c_mix"):
        c = ledger.get(cid)
        if c:
            key.append({"label": c.text, "value": c.value, "claim_id": cid})
    rec = next((s.title for s in spec.slides if s.kind == "recommendation"),
               "See recommendation.")
    return FindingBundle(headline=state.headline or spec.title,
                         decision_owner=spec.decision_owner, key_numbers=key,
                         recommendation=rec)


def export_run(run_id: str, formats: list[str] | None = None,
               runs_root: Path | None = None) -> dict:
    formats = formats or ["html", "slack", "email"]
    runs_root = runs_root or PATHS.runs
    run_dir = runs_root / run_id
    state = RunState.load(run_id, runs_root)
    prov = run_dir / "provenance.json"
    if not prov.exists():
        raise FileNotFoundError(f"run '{run_id}' has no provenance.json to export")
    ledger = ProvenanceLedger.load(prov)
    spec = _rebuild_spec(state, ledger)

    out: dict[str, str] = {}
    if "html" in formats or "pdf" in formats:
        html_path = build_html(spec, ledger, run_dir / "deck.html")
        out["html"] = str(html_path)
        if "pdf" in formats:
            out["pdf"] = str(export_pdf(html_path))
    if any(f in formats for f in ("slack", "email", "exec")):
        bundle = _bundle(state, ledger, spec)
        if "slack" in formats:
            p = run_dir / "comms_slack.md"
            p.write_text(comms_mod.slack_summary(bundle, ledger))
            out["slack"] = str(p)
        if "email" in formats:
            eb = comms_mod.email_brief(bundle, ledger)
            p = run_dir / "comms_email.md"
            p.write_text(f"Subject: {eb['subject']}\n\n{eb['body']}")
            out["email"] = str(p)
        if "exec" in formats:
            p = run_dir / "comms_exec.md"
            p.write_text(comms_mod.exec_summary(bundle, ledger))
            out["exec"] = str(p)
    return out
