"""Atlas orchestrator — deterministic wave scheduler.

This drives the numeric backbone of the pipeline: profiling -> framing/semantic
gate -> exploration -> decomposition + stats -> red-team re-derivation ->
narrative -> deck -> stakeholder sim -> retro, writing every artefact to
runs/<run_id>/ and enforcing the gates.

The Claude Code sub-agents (.claude/agents/*) layer *reasoning and prose* on top
of this backbone via the /analyze command. The numbers, provenance, gates and
budgets live here so they are deterministic and testable without any LLM call.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from atlas.config import PATHS
from atlas.connectors.registry import Registry
from atlas.dag import DagEngine, NodeOutcome, NodeSpec, NodeStatus
from atlas.lib.budget import RunBudget
from atlas.lib.deck_pptx import build_deck
from atlas.lib.gates import (
    GateStatus, gate1_profiling, gate2_semantics, gate3_redteam,
    gate4_provenance, gate5_stakeholder, gate_readiness,
)
from atlas.quality.pipeline import run_copilot, CopilotSummary
from atlas.lib.profiling import profile_table, verdict_for
from atlas.lib.provenance import ProvenanceLedger
from atlas.lib.query_store import QueryStore
from atlas.lib.run_state import RunState
from atlas.lib.validation import grade_layers
from atlas.lib.forecast import forecast as ts_forecast
from atlas.connectors.base import TableRef
from atlas.playbooks import (
    PLAYBOOK_REGISTRY, BriefFields, PlaybookBlocked, select_playbook,
    supported_decompositions,
)
# Margin renderers live with the margin playbook now; re-exported here because
# `atlas/lib/exporters.py` imports them from this module.
from atlas.playbooks.margin import (  # noqa: F401
    _build_deck_spec, _deser_dec, _ser_dec,
)
from atlas.semantic import (
    resolve_metric, metric_from_text, known_metrics, MetricAmbiguity,
)


@dataclass
class RunResult:
    run_id: str
    run_dir: Path
    status: str                       # COMPLETE | BLOCKED
    blocked_reason: str = ""
    gates: dict[str, str] = field(default_factory=dict)
    headline: str = ""
    artefacts: list[str] = field(default_factory=list)


def new_run_id() -> str:
    return "r-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _extract_hints(question: str) -> dict:
    """Very small NL parse: region + quarters. Anything unfound -> declared assumption.

    The metric is NOT parsed here — it is resolved against the semantic layer
    (`metrics.yaml`) and is None when the question names no known metric, so
    `n_semantics` can escalate. It must never default: a default silently turns an
    unrecognised question into a gross-margin analysis that passes every gate.
    """
    q = question.upper()
    region = next((r for r in ("EMEA", "AMER", "APAC") if r in q), "EMEA")
    quarters = re.findall(r"Q[1-4]", q)
    if len(quarters) >= 2:
        p1, p2 = quarters[0], quarters[1]
    elif len(quarters) == 1:
        # "in Q2" -> compare Q2 vs the prior quarter
        idx = int(quarters[0][1])
        p1, p2 = f"Q{max(1, idx-1)}", quarters[0]
    else:
        p1, p2 = "Q1", "Q2"
    mdef = metric_from_text(question)
    return {"region": region, "p1": p1, "p2": p2,
            "metric": mdef.name if mdef else None}


# --------------------- run context + DAG nodes ---------------------
@dataclass
class RunContext:
    run_id: str
    run_dir: Path
    question: str
    source: str
    table: str
    dim: str
    decision_owner: str
    region: str
    p1: str
    p2: str
    metric: str | None          # None => question named no metric in metrics.yaml
    con: object
    store: QueryStore
    ledger: ProvenanceLedger
    budget: RunBudget
    gates: dict = field(default_factory=dict)
    artefacts: list = field(default_factory=list)
    scratch: dict = field(default_factory=dict)
    # Which analysis shape is running, and how its declared column roles resolved.
    playbook: object | None = None
    binding: object | None = None
    bind_overrides: dict = field(default_factory=dict)
    hints: dict = field(default_factory=dict)

    def write(self, rel: str, text: str) -> str:
        p = self.run_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        if rel not in self.artefacts:
            self.artefacts.append(rel)
        return rel

    def analysis_table(self) -> str:
        """The table analysis should read: the clean layer if the copilot built one.

        Reads whatever is present rather than depending on node ordering, so it is
        safe to call before `quality` has run (it simply returns the raw table).
        """
        c = self.scratch.get("copilot") or {}
        return c.get("clean_table") or self.table


# The pipeline DAG. Mirrors .claude/agents/registry.yaml — EDIT BOTH TOGETHER.
# Deps encode the waves; `diagnose` and `redteam` run in parallel after `model`.
#
# `model` and `emit` are present for every playbook and default to clean no-ops, so
# the DAG shape does not vary by playbook (which would make the registry.yaml mirror
# unverifiable and break resume across a playbook change).
#
# `timeout_s` is stated on every node. It used to be declared only in registry.yaml
# and dropped on the floor here, so every node silently ran at the 300s NodeSpec
# default — `readiness_gate` claimed 60s and got 300s. The documented budget is now
# the enforced one, and `tests/test_registry_drift.py` keeps the two in step.
SPECS = [
    NodeSpec("profile", deps=[], critical=True, timeout_s=120),
    NodeSpec("frame", deps=[], critical=True, timeout_s=120),
    # Depends on `quality` so column binding resolves against the clean layer
    # deterministically rather than racing it. Binding here (not in `explore`) also
    # means an unbindable table blocks before a single exploration query is spent.
    NodeSpec("semantics", deps=["frame", "quality"], critical=True, timeout_s=120),
    # Data Quality Copilot: detect -> score -> plan/preview -> auto-repair to a
    # semantic clean layer -> Data Readiness Gate. Runs before any analysis.
    NodeSpec("quality", deps=["profile"], critical=True, timeout_s=180),
    NodeSpec("readiness_gate", deps=["quality", "semantics"], critical=True,
             timeout_s=60),
    NodeSpec("explore", deps=["profile", "semantics", "readiness_gate"], critical=True,
             timeout_s=240),
    # Fitting step. 600s because a model fit over a large table must not race the
    # 300s engine default; the engine's single retry is safe because fits are seeded.
    NodeSpec("model", deps=["explore"], critical=True, timeout_s=600),
    NodeSpec("diagnose", deps=["explore", "model"], critical=True, timeout_s=240),
    NodeSpec("redteam", deps=["explore", "model"], critical=True, timeout_s=240),
    NodeSpec("sizing", deps=["diagnose"], critical=True, timeout_s=120),
    NodeSpec("forecast", deps=["diagnose"], critical=False, timeout_s=120),
    NodeSpec("cohort", deps=["diagnose"], critical=False, timeout_s=120),
    NodeSpec("narrative", deps=["sizing"], critical=True, timeout_s=180),
    NodeSpec("deck", deps=["narrative", "redteam"], critical=True, timeout_s=180),
    # Non-critical on purpose: rule 4 ("fail loudly") is about not shipping a
    # degraded deck over bad data, not about export plumbing. An exporter failing
    # after GATE 3/4 already passed must not destroy an otherwise-validated run.
    NodeSpec("emit", deps=["deck"], critical=False, timeout_s=300),
    NodeSpec("stakeholder", deps=["deck"], critical=False, timeout_s=120),
    NodeSpec("retro", deps=["stakeholder", "emit"], critical=False, timeout_s=120),
]


def n_profile(ctx: RunContext) -> NodeOutcome:
    report = profile_table(ctx.con, TableRef(ctx.table))
    verdict = verdict_for(report)
    ctx.write(f"profile/{ctx.source}.md", _render_profile(ctx.source, report, verdict))
    g1 = gate1_profiling({ctx.source: verdict.decision})
    ctx.gates[g1.gate] = g1.status.value
    if not g1.passed:
        return NodeOutcome(NodeStatus.BLOCKED, "GATE 1: no source is GO")
    return NodeOutcome(output={"verdict": verdict.decision})


def n_frame(ctx: RunContext) -> NodeOutcome:
    # The metric was inferred from the question against metrics.yaml, not named by the
    # user — so it is an assumption and gets declared, per the constitution.
    metric_note = (
        f"Metric inferred from the question as '{ctx.metric}' (locked definition in "
        f"metrics.yaml)." if ctx.metric else
        "No known metric matched the question — semantics will escalate."
    )
    assumptions = [
        metric_note,
        f"Comparison window: {ctx.p2} vs {ctx.p1}, {ctx.region} only.",
        f"Grain: {ctx.dim}. Numbers are full-scan (no sampling on this local source).",
    ]
    ctx.scratch["assumptions"] = assumptions

    # Classify the question. Until now this ran only as advisory prose in /route and
    # /cao, never inside a run; recording it here makes the level part of the run's
    # own record and lets playbook selection use it as a tiebreak.
    routing = _classify(ctx.question)
    ctx.scratch["routing"] = routing
    return NodeOutcome(output={"assumptions": assumptions, "routing": routing})


def _classify(question: str) -> dict:
    """L1-L5 routing as a plain dict. Advisory: it never overrides an explicit pin."""
    try:
        from atlas.lib.router import classify
        r = classify(question)
        return {"level": r.level, "label": r.label, "command": r.command,
                "reason": r.reason, "confidence": r.confidence}
    except Exception:
        return {}


def n_semantics(ctx: RunContext) -> NodeOutcome:
    """Resolve the metric, then check the engine can actually execute it.

    Two distinct failure modes, deliberately not conflated:
      * unresolvable  -> GATE 2 FAIL (metric_ambiguity -> semantic-architect)
      * resolved but unsupported -> GATE 2 PASSES, run BLOCKS on capability
    """
    assumptions = ctx.scratch["assumptions"]

    # 1. The question named no metric this warehouse has a locked definition for.
    if ctx.metric is None:
        marker = "<no known metric named in the question>"
        g2 = gate2_semantics([marker])
        _record_gate(ctx, g2)
        note = (f"No metric in metrics.yaml matches this question. Known: "
                f"{sorted(known_metrics())}. Name the metric explicitly, or lock a "
                f"new definition — Atlas escalates rather than guessing.")
        ctx.write("brief.md", _render_brief(ctx, assumptions, note))
        return NodeOutcome(NodeStatus.BLOCKED, f"GATE 2: {note}")

    try:
        mdef = resolve_metric(ctx.metric)
    except MetricAmbiguity as e:
        g2 = gate2_semantics([ctx.metric])
        _record_gate(ctx, g2)
        ctx.write("brief.md", _render_brief(ctx, assumptions, str(e)))
        return NodeOutcome(NodeStatus.BLOCKED, f"GATE 2: {e}")

    # Resolution succeeded — GATE 2 is genuinely satisfied either way.
    g2 = gate2_semantics([])
    _record_gate(ctx, g2)

    # 2. Locked definition exists, but no registered playbook can compute it.
    pb = select_playbook(metric_decomposition=mdef.decomposition,
                         explicit=ctx.scratch.get("explicit_playbook"),
                         question=ctx.question)
    if pb is None:
        ctx.write("brief.md", _render_brief(
            ctx, assumptions,
            f"Resolved metric '{mdef.name}' = {mdef.expression} (unit={mdef.unit}); "
            f"decomposition={mdef.decomposition}."))
        return NodeOutcome(NodeStatus.BLOCKED, (
            f"no execution path for metric '{mdef.name}': it declares "
            f"decomposition='{mdef.decomposition}', and this engine implements only "
            f"{sorted(supported_decompositions())}. The definition is valid — the "
            f"pipeline cannot compute it. Atlas will not substitute a different metric."))

    ctx.playbook = pb

    # 3. Bind the playbook's declared column roles to real columns. Doing this here
    #    means an unbindable table blocks before any exploration query is spent, and
    #    the brief can name the columns that were actually chosen.
    ctx.binding = pb.bind(ctx)
    if not ctx.binding.ok:
        msg = ctx.binding.block_message(pb.id, ctx.scratch.get("probes", {}))
        ctx.write("brief.md", _render_brief(ctx, assumptions, msg))
        return NodeOutcome(NodeStatus.BLOCKED, msg)
    # Every inferred (rather than pinned) column is an assumption — declare it.
    if ctx.binding.notes:
        assumptions = list(assumptions) + list(ctx.binding.notes)
        ctx.scratch["assumptions"] = assumptions

    ctx.write("brief.md", _render_brief(
        ctx, assumptions,
        f"Resolved metric '{mdef.name}' = {mdef.expression} (unit={mdef.unit}); "
        f"decomposition={mdef.decomposition}; playbook='{pb.id}'."))
    return NodeOutcome(output={"metric": mdef.name, "decomposition": mdef.decomposition,
                               "playbook": pb.id, "binding": ctx.binding.as_dict(),
                               "assumptions": assumptions})


def n_quality(ctx: RunContext) -> NodeOutcome:
    """Data Quality Copilot: detect issues, score, auto-repair to a semantic clean
    layer, write the audit trail. Degrades to a clean no-op when a source has no
    detectable issues (the EMEA fixture), so the existing flow is unchanged."""
    summary = run_copilot(ctx.con, TableRef(ctx.table), source=ctx.source, run_dir=ctx.run_dir)
    ctx.scratch["copilot"] = summary.as_dict()
    ctx.write("repair/readiness.md", _render_readiness(summary))
    # Semantic guardrails over the (possibly clean) table downstream agents read.
    try:
        from atlas.quality.guardrails import render_guardrails
        ctx.write("repair/guardrails.md",
                  render_guardrails(ctx.con, TableRef(summary.clean_table)))
    except Exception:
        pass  # guardrails are advisory; never break the run
    return NodeOutcome(output=summary.as_dict())


def n_readiness_gate(ctx: RunContext) -> NodeOutcome:
    """Data Readiness Gate: block analysis if the clean layer is not analysable."""
    c = ctx.scratch.get("copilot") or {}
    g = gate_readiness(bool(c.get("ready", True)), c.get("decision", "GO"),
                       [c.get("reason", "")] if c.get("reason") else [])
    _record_gate(ctx, g)
    if not g.passed:
        return NodeOutcome(NodeStatus.BLOCKED, f"GATE readiness: {g.summary}")
    return NodeOutcome(output={"ready": True, "decision": c.get("decision", "GO"),
                               "clean_table": c.get("clean_table", ctx.table)})


def n_explore(ctx: RunContext) -> NodeOutcome:
    """Run the playbook's exploration SQL. Columns were bound in `semantics`."""
    pb = _require_playbook(ctx)
    res = pb.explore(ctx)
    ctx.scratch["pb_result"] = res
    ctx.write(*pb.hypotheses_doc(ctx, res))
    return NodeOutcome(output={"playbook": pb.id, **pb.serialize(res)})


def n_model(ctx: RunContext) -> NodeOutcome:
    """Optional fitting step. A no-op for playbooks that only aggregate."""
    pb = _require_playbook(ctx)
    res = pb.model(ctx, ctx.scratch["pb_result"])
    ctx.scratch["pb_result"] = res
    return NodeOutcome(output={"playbook": pb.id, "fitted": res is not None})


def n_diagnose(ctx: RunContext) -> NodeOutcome:
    pb = _require_playbook(ctx)
    res = ctx.scratch["pb_result"]
    for s in pb.diagnose(ctx, res):
        _record_claim(ctx, s)
    ctx.write(*pb.findings_doc(ctx, res))
    ctx.ledger.save(ctx.run_dir / "provenance.json")   # durable early for resume
    if "provenance.json" not in ctx.artefacts:
        ctx.artefacts.append("provenance.json")
    return NodeOutcome(output={"claims": [c.claim_id for c in ctx.ledger.all()]})


def n_redteam(ctx: RunContext) -> NodeOutcome:
    pb = _require_playbook(ctx)
    res = ctx.scratch["pb_result"]
    rd = pb.rederive(ctx, res)

    # Layered validation -> advisory A-F confidence grade. Grade F is treated as a
    # surviving attack; A-E annotate confidence but never override the veto logic.
    report = grade_layers(pb.validation_layers(ctx, res))
    attacks = list(rd.attacks)
    if report.grade == "F":
        attacks.append(f"validation grade F: {report.as_dict()['layers']}")

    ctx.scratch["confidence_grade"] = report.grade
    g3 = gate3_redteam(rd.ok, attacks)
    _record_gate(ctx, g3)
    ctx.write(*pb.validation_doc(ctx, res, rd, report))
    if not g3.passed:
        return NodeOutcome(NodeStatus.BLOCKED, f"GATE 3: red-team veto ({g3.summary})")
    return NodeOutcome(output={"rederivation_ok": rd.ok,
                               "comparisons": rd.comparisons,
                               "confidence_grade": report.grade})


def n_sizing(ctx: RunContext) -> NodeOutcome:
    """Opportunity-sizer: quantify the impact of the finding + a tornado. First-class
    pipeline node — every root-cause analysis should say what it's worth."""
    pb = _require_playbook(ctx)
    outcome = pb.size(ctx, ctx.scratch["pb_result"])
    if outcome is None:
        return NodeOutcome(output={"sized": False})
    for s in outcome.claims:
        _record_claim(ctx, s)
    if outcome.doc:
        ctx.write(*outcome.doc)
    return NodeOutcome(output={"sized": True, **outcome.output})


def n_forecast(ctx: RunContext) -> NodeOutcome:
    """Forecaster (conditional enrichment): forecast the metric forward if there is
    enough history. Non-critical — degrades gracefully when not applicable."""
    r = ctx.con.run(
        f"SELECT DISTINCT quarter FROM {ctx.table} "
        f"WHERE region = '{ctx.region}' ORDER BY quarter")
    ctx.budget.charge_query(r.bytes_scanned)
    quarters = [row["quarter"] for row in r.rows]
    if len(quarters) < 3:
        info = {"applicable": False,
                "reason": f"only {len(quarters)} period(s) of history; need ≥3"}
        ctx.scratch["forecast"] = info
        return NodeOutcome(output=info)
    series = []
    for q in quarters:
        rq = ctx.con.run(
            f"SELECT sum(revenue) AS rev, sum(cogs) AS cogs FROM {ctx.table} "
            f"WHERE region = '{ctx.region}' AND quarter = '{q}'")
        ctx.budget.charge_query(rq.bytes_scanned)
        row = rq.rows[0]
        series.append((row["rev"] - row["cogs"]) / row["rev"] * 100)
    fc = ts_forecast(series, horizon=1)
    info = {"applicable": True, "series": series, "forecast": fc.as_dict()}
    ctx.scratch["forecast"] = info
    return NodeOutcome(output={"applicable": True, "next": round(fc.points[0], 2)})


def n_cohort(ctx: RunContext) -> NodeOutcome:
    """Cohort-analyst (conditional enrichment): retention analysis if the data has an
    entity to cohort by. Non-critical — degrades gracefully when not applicable."""
    schema = ctx.con.get_schema(TableRef(ctx.table))
    cols = {c.name.lower() for c in schema.columns}
    entity = cols & {"user", "user_id", "customer", "customer_id", "account", "account_id"}
    if not entity:
        info = {"applicable": False, "reason": "no user/entity column to cohort by"}
        ctx.scratch["cohort"] = info
        return NodeOutcome(output=info)
    # A real dataset with entities would run retention_matrix here.
    ctx.scratch["cohort"] = {"applicable": True, "entity_column": sorted(entity)[0]}
    return NodeOutcome(output={"applicable": True})


def n_narrative(ctx: RunContext) -> NodeOutcome:
    pb = _require_playbook(ctx)
    ctx.write("narrative.md", pb.narrate(ctx, ctx.scratch["pb_result"]))
    return NodeOutcome()


def n_deck(ctx: RunContext) -> NodeOutcome:
    pb = _require_playbook(ctx)
    spec = pb.deck_spec(ctx, ctx.scratch["pb_result"])
    orphans = ctx.ledger.orphans(spec.referenced_claim_ids())
    unfingerprinted = _unfingerprinted_derived_claims(ctx)
    g4 = gate4_provenance(orphans, unfingerprinted)
    _record_gate(ctx, g4)
    if not g4.passed:
        return NodeOutcome(NodeStatus.BLOCKED, f"GATE 4: {g4.summary}")
    build_deck(spec, ctx.run_dir / "deck.pptx", ctx.run_dir / "speaker_notes.md")
    for a in ("deck.pptx", "speaker_notes.md"):
        if a not in ctx.artefacts:
            ctx.artefacts.append(a)
    ctx.scratch["spec"] = spec
    return NodeOutcome()


def n_emit(ctx: RunContext) -> NodeOutcome:
    """Playbook-declared extra exports (risk scores, Power BI project, ...).

    Non-critical by design — see the SPECS comment. A failure degrades the run
    rather than discarding an already-validated deck.
    """
    pb = _require_playbook(ctx)
    ids = pb.exports(ctx, ctx.scratch.get("pb_result"))
    if not ids:
        return NodeOutcome(output={"exports": []})
    written: list[str] = []
    for eid in ids:
        written += _run_exporter(ctx, eid)
    for w in written:
        if w not in ctx.artefacts:
            ctx.artefacts.append(w)
    return NodeOutcome(output={"exports": written})


def _run_exporter(ctx: RunContext, exporter_id: str) -> list[str]:
    """Resolve and run one exporter against the live run context."""
    import atlas.exporters  # noqa: F401  (registers the built-ins)
    from atlas.lib.export_registry import ExportContext, get_exporter

    exporter = get_exporter(exporter_id)          # raises on an unknown id
    ectx = ExportContext(
        run_id=ctx.run_id, run_dir=ctx.run_dir, ledger=ctx.ledger,
        spec=ctx.scratch.get("spec"), playbook_id=getattr(ctx.playbook, "id", ""),
        result=ctx.scratch.get("pb_result"), binding=ctx.binding, con=ctx.con,
        options={"dax_table": ctx.analysis_table()})
    ok, why = exporter.available(ectx)
    if not ok:
        raise PlaybookBlocked(why)
    return exporter.emit(ectx)


def n_stakeholder(ctx: RunContext) -> NodeOutcome:
    pb = _require_playbook(ctx)
    checks = pb.stakeholder_questions(ctx, ctx.scratch["pb_result"], ctx.scratch["spec"])
    unanswered = [q for q, ok in checks.items() if not ok]
    g5 = gate5_stakeholder(unanswered)
    _record_gate(ctx, g5)
    return NodeOutcome(output={"unanswered": unanswered})


def n_retro(ctx: RunContext) -> NodeOutcome:
    ctx.ledger.save(ctx.run_dir / "provenance.json")
    ctx.write("retro.md", _render_retro(ctx.run_id, ctx.gates, ctx.budget))
    ctx.write("run.log", json.dumps(ctx.budget.snapshot(), indent=2))
    ctx.write("enrichment.md", _render_enrichment(ctx))
    # Multi-level confidence + executive recommendation (orchestration intelligence).
    try:
        _write_confidence_and_recommendation(ctx)
    except Exception:
        pass  # advisory; never break a completed run
    # Data lineage: source -> clean layer -> semantic -> SQL -> deck (via provenance).
    try:
        from atlas.quality.lineage import build_lineage, render_lineage
        c = ctx.scratch.get("copilot") or {}
        prov = [{"claim_id": cl.claim_id, "query_hash": cl.query_hash,
                 "slide_number": cl.slide_number} for cl in ctx.ledger.all()]
        lin = build_lineage(ctx.source, base_table=ctx.table,
                            clean_table=c.get("clean_table"), provenance=prov)
        ctx.write("lineage.md", render_lineage(lin))
    except Exception:
        pass  # lineage is advisory; never break a completed run
    _archive_headline_queries(ctx)   # feed query archaeology (guarded)
    return NodeOutcome()


def _render_enrichment(ctx: RunContext) -> str:
    fc = ctx.scratch.get("forecast", {"applicable": False, "reason": "not run"})
    ch = ctx.scratch.get("cohort", {"applicable": False, "reason": "not run"})
    sz = ctx.scratch.get("sizing")
    lines = ["# Enrichment (conditional analytical agents)", "", "## Opportunity sizing"]
    if sz is not None:
        lines.append(f"- base ≈ {sz.base:,.0f}; most sensitive to "
                     f"{sz.as_dict()['most_sensitive_to']}")
    else:
        lines.append("- not run")
    lines += ["", "## Forecast"]
    if fc.get("applicable"):
        lines.append(f"- next-period estimate {round(fc['forecast']['points'][0], 2)}")
    else:
        lines.append(f"- not applicable — {fc.get('reason', '')}")
    lines += ["", "## Cohort"]
    if ch.get("applicable"):
        lines.append(f"- applicable on column '{ch.get('entity_column', '')}'")
    else:
        lines.append(f"- not applicable — {ch.get('reason', '')}")
    return "\n".join(lines)


def _archive_headline_queries(ctx: RunContext) -> None:
    """Archive the validated headline queries so future runs can reuse the pattern."""
    try:
        from atlas.lib import query_archive
        tags = ["margin", "period-compare", f"by-{ctx.dim}", ctx.region.lower()]
        for (qh, rh) in (ctx.scratch.get("r1"), ctx.scratch.get("r2")):
            meta = ctx.store.load_query(qh)
            if meta and meta.get("sql"):
                query_archive.archive(
                    meta["sql"], source=ctx.source, dialect=ctx.con.dialect,
                    metric=ctx.metric or "unresolved", intent_tags=tags, result_hash=rh,
                    run_id=ctx.run_id, notes="validated headline query")
    except Exception:
        pass  # archiving is best-effort; never break a completed run


NODE_FNS = {
    "profile": n_profile, "frame": n_frame, "semantics": n_semantics,
    "quality": n_quality, "readiness_gate": n_readiness_gate,
    "explore": n_explore, "model": n_model, "diagnose": n_diagnose,
    "redteam": n_redteam, "sizing": n_sizing, "forecast": n_forecast,
    "cohort": n_cohort, "narrative": n_narrative, "deck": n_deck,
    "emit": n_emit, "stakeholder": n_stakeholder, "retro": n_retro,
}


def _record_gate(ctx: RunContext, g) -> bool:
    """Record a gate's status, remembering the first failure so BLOCKED.md can name
    the agent that owns each defect. Returns whether it passed."""
    ctx.gates[g.gate] = g.status.value
    if not g.passed and "failed_gate" not in ctx.scratch:
        ctx.scratch["failed_gate"] = g
    return g.passed


def _require_playbook(ctx: RunContext):
    """Every analysis node needs a selected playbook; its absence is a wiring bug."""
    if ctx.playbook is None:
        raise PlaybookBlocked(
            "no playbook selected — `semantics` must run (or be rehydrated) first")
    return ctx.playbook


def _record_claim(ctx: RunContext, s) -> None:
    """Write one ClaimSpec to the ledger.

    Centralised here rather than in each playbook so provenance enforcement has a
    single choke point. A spec carrying a `derivation` goes through the stricter
    `record_derived()`, which requires a real parent query and refuses any evidence
    tier above `correlational`.
    """
    if getattr(s, "derivation", ""):
        ctx.ledger.record_derived(
            s.claim_id, s.text, s.value,
            parent_query_hash=s.query_hash, parent_result_hash=s.result_hash,
            derivation_hash=s.derivation.split(":", 1)[-1],
            derivation_label=s.derivation, evidence_tier=s.evidence_tier,
            parent_claims=list(getattr(s, "parent_claims", []) or []), notes=s.notes)
        return
    ctx.ledger.record(s.claim_id, s.text, s.value, s.query_hash, s.result_hash,
                      evidence_tier=s.evidence_tier, notes=s.notes)


def _unfingerprinted_derived_claims(ctx: RunContext) -> list[str]:
    """Derived claims whose recipe was never written to runs/<id>/model/.

    A number computed by a recipe nobody can find is exactly as unsourced as an
    invented one, so GATE 4 treats it the same way.

    Early-returns before importing `model_provenance` when there is nothing derived
    to check — most playbooks (margin, descriptive) never produce a derived claim at
    all, so there is no reason for every deck build to pay for that import.
    """
    derived = ctx.ledger.derived()
    if not derived:
        return []
    from atlas.lib.model_provenance import fingerprint_exists
    out = []
    for c in derived:
        digest = c.derivation.split(":", 1)[-1]
        if not digest or not fingerprint_exists(ctx.run_dir, digest):
            out.append(c.claim_id)
    return out


def _hydrate(ctx: RunContext, completed: dict) -> None:
    """Rebuild scratch + ledger from persisted node outputs (resume)."""
    if "frame" in completed:
        ctx.scratch["assumptions"] = completed["frame"].get("assumptions", [])
    if "quality" in completed:
        ctx.scratch["copilot"] = completed["quality"]

    # Pin the playbook by the id recorded at the time, never re-select. A resumed
    # run must not silently switch analysis shape because metrics.yaml changed.
    sem = completed.get("semantics") or {}
    pb_id = sem.get("playbook") or (completed.get("explore") or {}).get("playbook")
    if pb_id:
        ctx.playbook = PLAYBOOK_REGISTRY.get(pb_id)
    if sem.get("binding"):
        from atlas.playbooks.binding import ColumnBinding
        ctx.binding = ColumnBinding.from_dict(sem["binding"])
    if sem.get("assumptions"):
        ctx.scratch["assumptions"] = list(sem["assumptions"])

    explore = completed.get("explore")
    if explore and ctx.playbook is not None:
        body = {k: v for k, v in explore.items() if k != "playbook"}
        res = ctx.playbook.deserialize(body)
        ctx.scratch["pb_result"] = res
        # Some playbooks mirror their result into legacy scratch keys that
        # orchestrator-level helpers read directly; let them re-populate.
        stash = getattr(ctx.playbook, "_stash", None)
        if stash is not None:
            stash(ctx, res)

    for opt in ("forecast", "cohort"):
        if opt in completed:
            ctx.scratch[opt] = completed[opt]
    prov = ctx.run_dir / "provenance.json"
    if prov.exists():
        ctx.ledger = ProvenanceLedger.load(prov)


def run_analysis(
    question: str,
    *,
    source: str = "emea_finance_csv",
    table: str = "finance",
    dim: str = "product_line",
    runs_root: Path | None = None,
    decision_owner: str = "VP Finance, EMEA",
    resume_run_id: str | None = None,
    playbook: str | None = None,
    bind: dict[str, str] | None = None,
) -> RunResult:
    """Run the pipeline.

    `playbook` pins the analysis shape explicitly (otherwise it is selected from the
    resolved metric's `decomposition:`). `bind` pins column roles, e.g.
    `bind={"target": "Churn"}`, overriding inference.
    """
    runs_root = runs_root or PATHS.runs

    if resume_run_id:
        state = RunState.load(resume_run_id, runs_root)
        run_id = resume_run_id
        question = state.question or question
    else:
        run_id = new_run_id()
        state = RunState(run_id=run_id, question=question)

    run_dir = runs_root / run_id
    (run_dir / "profile").mkdir(parents=True, exist_ok=True)

    hints = _extract_hints(question)
    store = QueryStore(run_dir)
    con = Registry().connector(source, store=store)
    ctx = RunContext(
        run_id=run_id, run_dir=run_dir, question=question, source=source, table=table,
        dim=dim, decision_owner=decision_owner, region=hints["region"],
        p1=hints["p1"], p2=hints["p2"], metric=hints["metric"], con=con, store=store,
        ledger=ProvenanceLedger(run_id), budget=RunBudget(), gates=dict(state.gates),
        bind_overrides=dict(bind or {}), hints=hints,
    )
    if playbook:
        ctx.scratch["explicit_playbook"] = playbook

    completed = state.completed_outputs() if resume_run_id else {}
    _hydrate(ctx, completed)

    def checkpoint(name: str, outcome: NodeOutcome) -> None:
        state.record_node(name, outcome.status.value, outcome.output)
        state.gates = dict(ctx.gates)
        state.budget = ctx.budget.snapshot()
        state.save(runs_root)

    result = DagEngine(SPECS).run(NODE_FNS, ctx, completed=completed, on_complete=checkpoint)

    try:
        con.close()
    except Exception:
        pass

    state.gates = dict(ctx.gates)
    state.status = result.status
    state.reason = result.reason

    if result.status == "COMPLETE":
        headline = _headline(ctx)
        state.headline = headline
        state.save(runs_root)
        return RunResult(run_id, run_dir, "COMPLETE", gates=ctx.gates,
                         headline=headline, artefacts=ctx.artefacts)

    if result.status == "BLOCKED":
        from atlas.lib.gates import routing_note
        failed = ctx.scratch.get("failed_gate")
        _blocked(run_id, run_dir, ctx.gates, result.reason, ctx.ledger,
                 owners=routing_note(failed) if failed is not None else "")
        state.save(runs_root)
        return RunResult(run_id, run_dir, "BLOCKED", blocked_reason=result.reason,
                         gates=ctx.gates, artefacts=ctx.artefacts + ["BLOCKED.md"])

    # FAILED
    (run_dir / "FAILED.md").write_text(
        f"# Run {run_id} FAILED\n\n**Reason:** {result.reason}\n\n"
        f"Node status: {result.node_status}\n\nResume with `/resume {run_id}` after fixing.\n")
    state.save(runs_root)
    return RunResult(run_id, run_dir, "FAILED", blocked_reason=result.reason,
                     gates=ctx.gates, artefacts=ctx.artefacts + ["FAILED.md"])


# --------------------- rendering helpers ---------------------
def _blocked(run_id, run_dir, gates, reason, ledger=None, owners=""):
    (run_dir / "BLOCKED.md").write_text(
        f"# Run {run_id} BLOCKED\n\n**Reason:** {reason}\n\n"
        f"## Gates\n" + "\n".join(f"- {k}: {v}" for k, v in gates.items()) +
        owners +
        "\n\n## What Atlas needs\nResolve the blocking condition above, then re-run. "
        "Atlas does not emit a degraded deck.\n"
    )
    if ledger is not None:
        ledger.save(run_dir / "provenance.json")


def _write_confidence_and_recommendation(ctx: RunContext) -> None:
    """Roll the chain of trust into one confidence number + an exec close."""
    from atlas.quality.confidence import grade_score, overall_confidence, render as render_conf
    from atlas.quality.recommendations import executive_recommendation, render as render_rec

    c = ctx.scratch.get("copilot") or {}
    dec = ctx.scratch.get("dec")
    grade = ctx.scratch.get("confidence_grade", "C")
    simp = ctx.scratch.get("simp", {})
    mlc = overall_confidence(
        data_quality=float(c.get("score_after", 100.0)) / 100.0,
        metric_definition=1.0 if ctx.gates.get("GATE2_semantics") == "PASS" else 0.5,
        statistics=grade_score(grade),
        business_logic=0.6 if simp.get("paradox") else 0.9,
        narrative=1.0,
    )
    ctx.write("confidence.md", render_conf(mlc))

    sizing = ctx.scratch.get("sizing")
    impact = f"≈ {sizing.base:,.0f}" if sizing is not None else "not sized"
    root_cause = (f"{ctx.region} margin move is a {dec.dominant_effect()} effect"
                  if dec is not None else "see findings")
    rec = executive_recommendation(
        root_cause=root_cause,
        recommendation="Rebalance the product mix rather than cut cost.",
        estimated_impact=impact, confidence=mlc.band, level=3,
        pending_approvals=c.get("pending_approval") or [],
        has_forecast=bool((ctx.scratch.get("forecast") or {}).get("applicable")))
    ctx.write("recommendations.md", render_rec(rec))


def _render_readiness(s: CopilotSummary) -> str:
    return (
        f"# Data Readiness — {s.source}\n\n"
        f"**Quality score:** {s.score_before:.0f} → {s.score_after:.0f}\n\n"
        f"**Business readiness:** {s.business_readiness}\n\n"
        f"**Decision:** {s.decision}   |   **Ready:** {'YES' if s.ready else 'NO'}\n\n"
        f"**Semantic layer:** {s.clean_table}\n\n"
        f"**Repairs auto-applied:** {s.applied or 'none'}\n\n"
        f"**Pending approval:** {s.pending_approval or 'none'}\n\n"
        f"**Unrepairable critical:** {s.unrepairable_critical or 'none'}\n\n"
        f"**Warnings:** {s.warnings}\n\n"
        + (f"**Reason:** {s.reason}\n" if s.reason else "")
    )


def _render_profile(source, report, verdict):
    lines = [f"# Profile — {source}", "", f"**Rows:** {report.row_count}", "",
             "## Columns", "", "| column | dtype | null_rate | distinct |",
             "|---|---|---|---|"]
    for c in report.columns:
        lines.append(f"| {c['column']} | {c['dtype']} | {c['null_rate']} | {c['distinct']} |")
    lines += ["", "## Warnings"] + ([f"- {w}" for w in report.warnings] or ["- none"])
    lines += ["", f"## Verdict", "", f"**{verdict.line()}**"]
    return "\n".join(lines)


def _headline(ctx: RunContext) -> str:
    """One-sentence answer. Playbooks that define `headline()` own their phrasing."""
    pb = ctx.playbook
    res = ctx.scratch.get("pb_result")
    fn = getattr(pb, "headline", None) if pb is not None else None
    if fn is not None and res is not None:
        return fn(ctx, res)
    return f"{ctx.question} — see findings.md."


def _brief_fields(ctx: RunContext) -> BriefFields:
    """Per-playbook framing, with a neutral fallback for a run that blocked before
    a playbook could be selected (an unresolvable metric)."""
    if ctx.playbook is not None:
        return ctx.playbook.brief_fields(ctx)
    return BriefFields(
        decision_unblocked=f"Pending metric resolution for: {ctx.question}",
        primary_metric=ctx.metric or "unresolved",
        comparison_window=f"{ctx.p2} vs {ctx.p1}",
        grain=ctx.dim,
    )


def _render_brief(ctx: RunContext, assumptions, semantic_note):
    f = _brief_fields(ctx)
    return (
        f"# Brief\n\n"
        f"**Question:** {ctx.question}\n\n"
        f"**Decision owner:** {ctx.decision_owner}\n\n"
        f"**Decision unblocked:** {f.decision_unblocked}\n\n"
        f"**Primary metric:** {f.primary_metric}.\n\n"
        f"**Comparison window:** {f.comparison_window}.\n\n"
        f"**Grain:** {f.grain}.\n\n"
        f"**Success criteria:** {f.success_criteria}\n\n"
        f"**Non-goals:** {f.non_goals}\n\n"
        f"## Semantic resolution\n{semantic_note}\n\n"
        f"## Assumptions (declared, not buried)\n" +
        "\n".join(f"- {a}" for a in assumptions) + "\n"
    )


def _render_retro(run_id, gates, budget):
    return (
        f"# Retrospective — {run_id}\n\n"
        f"## Gates\n" + "\n".join(f"- {k}: {v}" for k, v in gates.items()) + "\n\n"
        f"## Budget\n```json\n{json.dumps(budget.snapshot(), indent=2)}\n```\n\n"
        f"## Corrections detected\n- none (deterministic run)\n\n"
        f"## Lessons\n- none new this run\n"
    )
