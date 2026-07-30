"""Export a completed run to additional formats — HTML, PDF, Slack, email, exec.

Rebuilds the DeckSpec from the run's persisted node outputs (Phase 1 run-state) and
its provenance.json, then produces each requested format. Every format passes the
same Gate 4 (no orphan numbers) via export_gate. "Build every export from one run."
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from atlas.config import PATHS
from atlas.lib.export_registry import ExportUnavailable
from atlas.lib.provenance import ProvenanceLedger
from atlas.lib.run_state import RunState


def _rebuild_spec(state: RunState, ledger: ProvenanceLedger):
    """Reconstruct the DeckSpec from persisted node outputs.

    Playbook-aware: the id recorded at run time selects how to deserialise the stored
    result, so a churn run exports its own deck rather than being forced through the
    margin renderer. Falls back to the margin path for runs written before playbooks
    existed (their `explore` output has a `dec` key and no `playbook`).
    """
    from atlas.playbooks import PLAYBOOK_REGISTRY

    explore = state.outputs.get("explore", {}) or {}
    frame = state.outputs.get("frame", {}) or {}
    semantics = state.outputs.get("semantics", {}) or {}
    assumptions = (semantics.get("assumptions")
                   or frame.get("assumptions", []))

    pb_id = semantics.get("playbook") or explore.get("playbook")
    pb = PLAYBOOK_REGISTRY.get(pb_id) if pb_id else None

    if pb is not None:
        body = {k: v for k, v in explore.items() if k != "playbook"}
        model = state.outputs.get("model") or {}
        if model and any(k not in ("playbook", "fitted") for k in model):
            body.update({k: v for k, v in model.items()
                         if k not in ("playbook", "fitted")})
        res = pb.deserialize(body)
        ctx = _ExportShim(state=state, ledger=ledger, assumptions=assumptions)
        return pb.deck_spec(ctx, res)

    # Legacy margin path.
    from atlas.orchestrator import _build_deck_spec, _deser_dec, _extract_hints
    dec = _deser_dec(explore["dec"])
    add = explore.get("add", [])
    h = _extract_hints(state.question)
    return _build_deck_spec(h["region"], h["p1"], h["p2"], dec, add,
                            "VP Finance, EMEA", assumptions, ledger)


@dataclass
class _ExportShim:
    """The minimal surface `Playbook.deck_spec()` reads, for a run being re-exported
    outside the pipeline (no live connector, no budget)."""
    state: RunState
    ledger: ProvenanceLedger
    assumptions: list = field(default_factory=list)
    decision_owner: str = "VP Finance, EMEA"

    def __post_init__(self):
        self.scratch = {"assumptions": list(self.assumptions)}
        self.region = "EMEA"
        self.dim = ""
        self.p1 = self.p2 = ""
        self.question = getattr(self.state, "question", "")

    def analysis_table(self) -> str:
        return ""


def export_run(run_id: str, formats: list[str] | None = None,
               runs_root: Path | None = None) -> dict:
    """Export a completed run. Unknown formats raise rather than silently no-op."""
    import atlas.exporters  # noqa: F401  (registers the built-in exporters)
    from atlas.lib.export_registry import ExportContext, get_exporter

    formats = formats or ["html", "slack", "email"]
    runs_root = runs_root or PATHS.runs
    run_dir = runs_root / run_id
    state = RunState.load(run_id, runs_root)
    prov = run_dir / "provenance.json"
    if not prov.exists():
        raise FileNotFoundError(f"run '{run_id}' has no provenance.json to export")
    ledger = ProvenanceLedger.load(prov)
    spec = _rebuild_spec(state, ledger)

    semantics = state.outputs.get("semantics", {}) or {}
    ctx = ExportContext(
        run_id=run_id, run_dir=run_dir, state=state, ledger=ledger, spec=spec,
        playbook_id=semantics.get("playbook", ""))

    out: dict[str, str] = {}
    # `pdf` implies `html`, and ordering keeps the shared deck.html build once.
    ordered = [f for f in ("html", "pdf") if f in formats]
    ordered += [f for f in formats if f not in ("html", "pdf")]

    for fmt in ordered:
        exporter = get_exporter(fmt)          # raises UnknownExportFormat
        ok, why = exporter.available(ctx)
        if not ok:
            raise ExportUnavailable(why)
        written = exporter.emit(ctx)
        if fmt == "pdf":
            out["pdf"] = str(ctx.options.get("pdf_status", {}))
        elif written:
            out[fmt] = str(run_dir / written[0])
    return out
