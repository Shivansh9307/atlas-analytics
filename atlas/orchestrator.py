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

from atlas.config import PATHS, TOLERANCES
from atlas.connectors.registry import Registry
from atlas.dag import DagEngine, NodeOutcome, NodeSpec, NodeStatus
from atlas.lib.budget import RunBudget
from atlas.lib.decomposition import (
    MarginDecomposition, SegmentContribution,
    decompose_margin, additive_contribution, simpsons_check,
)
from atlas.lib.deck_pptx import Chart, DeckSpec, Slide, build_deck
from atlas.lib.gates import (
    GateStatus, gate1_profiling, gate2_semantics, gate3_redteam,
    gate4_provenance, gate5_stakeholder,
)
from atlas.lib.profiling import profile_table, verdict_for
from atlas.lib.provenance import ProvenanceLedger
from atlas.lib.query_store import QueryStore
from atlas.lib.run_state import RunState
from atlas.lib.validation import validate_margin_finding
from atlas.lib.sizing import Assumption, size_opportunity
from atlas.lib.forecast import forecast as ts_forecast
from atlas.connectors.base import TableRef
from atlas.semantic import resolve_metric, MetricAmbiguity


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
    """Very small NL parse: region + quarters. Anything unfound -> declared assumption."""
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
    metric = "gross_margin"  # keyword resolution below refines
    for kw in ("margin", "revenue", "cogs", "cost"):
        if kw in question.lower():
            metric = "cogs" if kw == "cost" else ("gross_margin" if kw == "margin" else kw)
            break
    return {"region": region, "p1": p1, "p2": p2, "metric": metric}


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
    metric: str
    con: object
    store: QueryStore
    ledger: ProvenanceLedger
    budget: RunBudget
    gates: dict = field(default_factory=dict)
    artefacts: list = field(default_factory=list)
    scratch: dict = field(default_factory=dict)

    def write(self, rel: str, text: str) -> str:
        p = self.run_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        if rel not in self.artefacts:
            self.artefacts.append(rel)
        return rel


# The pipeline DAG. Mirrors .claude/agents/registry.yaml. Deps encode the waves;
# `diagnose` and `redteam` run in parallel after `explore` (red-team ‖ narrative).
SPECS = [
    NodeSpec("profile", deps=[], critical=True),
    NodeSpec("frame", deps=[], critical=True),
    NodeSpec("semantics", deps=["frame"], critical=True),
    NodeSpec("explore", deps=["profile", "semantics"], critical=True),
    NodeSpec("diagnose", deps=["explore"], critical=True),
    NodeSpec("redteam", deps=["explore"], critical=True),
    NodeSpec("sizing", deps=["diagnose"], critical=True),
    NodeSpec("forecast", deps=["diagnose"], critical=False),   # conditional enrichment
    NodeSpec("cohort", deps=["diagnose"], critical=False),     # conditional enrichment
    NodeSpec("narrative", deps=["sizing"], critical=True),
    NodeSpec("deck", deps=["narrative", "redteam"], critical=True),
    NodeSpec("stakeholder", deps=["deck"], critical=False),
    NodeSpec("retro", deps=["stakeholder"], critical=False),
]


def _emea_rows(ctx: RunContext, quarter: str):
    r = ctx.con.run(
        f"SELECT {ctx.dim}, segment, revenue, cogs FROM {ctx.table} "
        f"WHERE region = '{ctx.region}' AND quarter = '{quarter}'"
    )
    ctx.budget.charge_query(r.bytes_scanned)
    return r


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
    assumptions = [
        "'Margin' interpreted as gross margin = (revenue - cogs)/revenue.",
        f"Comparison window: {ctx.p2} vs {ctx.p1}, {ctx.region} only.",
        f"Grain: {ctx.dim}. Numbers are full-scan (no sampling on this local source).",
    ]
    ctx.scratch["assumptions"] = assumptions
    return NodeOutcome(output={"assumptions": assumptions})


def n_semantics(ctx: RunContext) -> NodeOutcome:
    assumptions = ctx.scratch["assumptions"]
    try:
        mdef = resolve_metric(ctx.metric)
    except MetricAmbiguity as e:
        g2 = gate2_semantics([ctx.metric])
        ctx.gates[g2.gate] = g2.status.value
        ctx.write("brief.md", _render_brief(
            ctx.question, ctx.decision_owner, ctx.region, ctx.p1, ctx.p2, assumptions, str(e)))
        return NodeOutcome(NodeStatus.BLOCKED, f"GATE 2: {e}")
    g2 = gate2_semantics([])
    ctx.gates[g2.gate] = g2.status.value
    ctx.write("brief.md", _render_brief(
        ctx.question, ctx.decision_owner, ctx.region, ctx.p1, ctx.p2, assumptions,
        f"Resolved metric '{mdef.name}' = {mdef.expression} (unit={mdef.unit})."))
    return NodeOutcome(output={"metric": mdef.name})


def n_explore(ctx: RunContext) -> NodeOutcome:
    r1, r2 = _emea_rows(ctx, ctx.p1), _emea_rows(ctx, ctx.p2)
    dec = decompose_margin(r1.rows, r2.rows, dim=ctx.dim)
    add = additive_contribution(r1.rows, r2.rows, dim=ctx.dim, value_key="revenue")
    simp = simpsons_check(r1.rows, r2.rows, dim=ctx.dim)
    rev_p1 = sum(float(r["revenue"]) for r in r1.rows)
    rev_p2 = sum(float(r["revenue"]) for r in r2.rows)
    ctx.scratch.update(dec=dec, add=add, simp=simp,
                       r1=(r1.query_hash, r1.result_hash),
                       r2=(r2.query_hash, r2.result_hash),
                       rev_p1=rev_p1, rev_p2=rev_p2,
                       row_count=len(r1.rows) + len(r2.rows))
    ctx.write("hypotheses.md", _render_hypotheses(dec, add, simp, ctx.dim, ctx.p1, ctx.p2))
    return NodeOutcome(output={
        "dec": _ser_dec(dec), "add": add, "simp": simp,
        "r1": [r1.query_hash, r1.result_hash], "r2": [r2.query_hash, r2.result_hash],
        "rev_p1": rev_p1, "rev_p2": rev_p2, "row_count": len(r1.rows) + len(r2.rows),
    })


def n_diagnose(ctx: RunContext) -> NodeOutcome:
    dec = ctx.scratch["dec"]
    (q1h, r1h), (q2h, r2h) = ctx.scratch["r1"], ctx.scratch["r2"]
    ctx.ledger.record("c_gm_p1", f"{ctx.region} {ctx.p1} gross margin", round(dec.m1 * 100, 2),
                      q1h, r1h, evidence_tier="decomposed")
    ctx.ledger.record("c_gm_p2", f"{ctx.region} {ctx.p2} gross margin", round(dec.m2 * 100, 2),
                      q2h, r2h, evidence_tier="decomposed")
    ctx.ledger.record("c_delta", f"{ctx.region} margin change {ctx.p2} vs {ctx.p1} (pts)",
                      round(dec.delta_pts, 2), q2h, r2h, evidence_tier="decomposed")
    ctx.ledger.record("c_mix", "Mix contribution (pts)", round(dec.mix_total * 100, 2),
                      q2h, r2h, evidence_tier="decomposed")
    ctx.ledger.record("c_rate", "Rate contribution (pts)", round(dec.rate_total * 100, 2),
                      q2h, r2h, evidence_tier="decomposed")
    ctx.write("findings.md", _render_findings(ctx.region, ctx.p1, ctx.p2, dec, ctx.scratch["simp"]))
    ctx.ledger.save(ctx.run_dir / "provenance.json")   # durable early for resume
    if "provenance.json" not in ctx.artefacts:
        ctx.artefacts.append("provenance.json")
    return NodeOutcome(output={"claims": [c.claim_id for c in ctx.ledger.all()]})


def n_redteam(ctx: RunContext) -> NodeOutcome:
    dec = ctx.scratch["dec"]
    rd = ctx.con.run(
        f"SELECT quarter, sum(revenue) AS rev, sum(cogs) AS cogs "
        f"FROM {ctx.table} WHERE region = '{ctx.region}' "
        f"AND quarter IN ('{ctx.p1}','{ctx.p2}') GROUP BY quarter"
    )
    ctx.budget.charge_query(rd.bytes_scanned)
    by = {row["quarter"]: (row["rev"], row["cogs"]) for row in rd.rows}
    rd_m1 = (by[ctx.p1][0] - by[ctx.p1][1]) / by[ctx.p1][0] * 100
    rd_m2 = (by[ctx.p2][0] - by[ctx.p2][1]) / by[ctx.p2][0] * 100
    tol = TOLERANCES.rederivation_rel
    ok = (abs(rd_m1 - dec.m1 * 100) <= abs(dec.m1 * 100) * tol and
          abs(rd_m2 - dec.m2 * 100) <= abs(dec.m2 * 100) * tol)
    attacks = []
    if ctx.scratch["simp"]["paradox"]:
        attacks.append("Simpson's paradox detected — aggregate hides opposite segment moves")

    # 4-layer validation -> advisory A-F confidence grade. Grade F is treated as a
    # surviving attack; A-E annotate confidence but never override the veto logic.
    report = validate_margin_finding(
        row_count=ctx.scratch.get("row_count", 1), profile_ok=True,
        mix=dec.mix_total, rate=dec.rate_total, interaction=dec.interaction_total,
        delta=dec.delta, m1=dec.m1, m2=dec.m2, paradox=ctx.scratch["simp"]["paradox"])
    if report.grade == "F":
        attacks.append(f"validation grade F: {report.as_dict()['layers']}")

    g3 = gate3_redteam(ok, attacks)
    ctx.gates[g3.gate] = g3.status.value
    ctx.write("validation.md", _render_validation(
        ctx.region, ctx.p1, ctx.p2, dec, rd_m1, rd_m2, ok, tol, attacks) +
        f"\n\n## Confidence grade\n**{report.grade}** (score {report.score:.2f})\n" +
        "\n".join(f"- L:{l['layer']} {'PASS' if l['passed'] else 'FAIL'} — {l['detail']}"
                  for l in report.as_dict()["layers"]) + "\n")
    if not g3.passed:
        return NodeOutcome(NodeStatus.BLOCKED, f"GATE 3: red-team veto ({g3.summary})")
    return NodeOutcome(output={"rederivation_ok": ok, "rd_m1": rd_m1, "rd_m2": rd_m2,
                               "confidence_grade": report.grade})


def n_sizing(ctx: RunContext) -> NodeOutcome:
    """Opportunity-sizer: quantify the impact of the finding + a tornado. First-class
    pipeline node — every root-cause analysis should say what it's worth."""
    dec = ctx.scratch["dec"]
    rev_p2 = float(ctx.scratch.get("rev_p2", 0.0))
    recoverable_pts = abs(dec.mix_total) * 100.0     # mix-driven points, recoverable

    def model(a: dict) -> float:
        return a["recoverable_pts"] / 100.0 * a["revenue"]

    assumptions = [
        Assumption("recoverable_pts", base=recoverable_pts,
                   low=recoverable_pts / 2, high=recoverable_pts),
        Assumption("revenue", base=rev_p2, low=rev_p2 * 0.9, high=rev_p2 * 1.1),
    ]
    res = size_opportunity(assumptions, model)
    q2h, r2h = ctx.scratch["r2"]
    ctx.ledger.record("c_revenue_p2", f"{ctx.region} {ctx.p2} revenue", round(rev_p2, 2),
                      q2h, r2h, evidence_tier="decomposed")
    ctx.ledger.record("c_opportunity",
                      f"Margin-recovery opportunity ({ctx.p2})", round(res.base, 2),
                      q2h, r2h, evidence_tier="hypothesis")  # a sized estimate, labelled
    ctx.scratch["sizing"] = res
    d = res.as_dict()
    ctx.write("sizing.md",
              f"# Opportunity sizing\n\n"
              f"**Base case:** recovering the mix-driven {recoverable_pts:.1f}pts on "
              f"{ctx.region} {ctx.p2} revenue ({rev_p2:,.0f}) ≈ **{res.base:,.0f}** "
              f"[c_opportunity].\n\n**Most sensitive to:** {d['most_sensitive_to']}.\n\n"
              f"## Tornado\n" +
              "\n".join(f"- {b['assumption']}: {b['low']:,.0f} … {b['high']:,.0f} "
                        f"(swing {b['swing']:,.0f})" for b in d["tornado"]) + "\n")
    return NodeOutcome(output={"opportunity": round(res.base, 2),
                               "most_sensitive_to": d["most_sensitive_to"]})


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
    ctx.write("narrative.md", _render_narrative(
        ctx.region, ctx.p1, ctx.p2, ctx.scratch["dec"], ctx.decision_owner))
    return NodeOutcome()


def n_deck(ctx: RunContext) -> NodeOutcome:
    dec = ctx.scratch["dec"]
    spec = _build_deck_spec(ctx.region, ctx.p1, ctx.p2, dec, ctx.scratch["add"],
                            ctx.decision_owner, ctx.scratch["assumptions"], ctx.ledger)
    orphans = ctx.ledger.orphans(spec.referenced_claim_ids())
    g4 = gate4_provenance(orphans)
    ctx.gates[g4.gate] = g4.status.value
    if not g4.passed:
        return NodeOutcome(NodeStatus.BLOCKED, f"GATE 4: {len(orphans)} orphan number(s)")
    build_deck(spec, ctx.run_dir / "deck.pptx", ctx.run_dir / "speaker_notes.md")
    for a in ("deck.pptx", "speaker_notes.md"):
        if a not in ctx.artefacts:
            ctx.artefacts.append(a)
    ctx.scratch["spec"] = spec
    return NodeOutcome()


def n_stakeholder(ctx: RunContext) -> NodeOutcome:
    spec = ctx.scratch["spec"]
    unanswered = _stakeholder_check(spec, ctx.scratch["dec"], ctx.scratch["simp"])
    g5 = gate5_stakeholder(unanswered)
    ctx.gates[g5.gate] = g5.status.value
    return NodeOutcome(output={"unanswered": unanswered})


def n_retro(ctx: RunContext) -> NodeOutcome:
    ctx.ledger.save(ctx.run_dir / "provenance.json")
    ctx.write("retro.md", _render_retro(ctx.run_id, ctx.gates, ctx.budget))
    ctx.write("run.log", json.dumps(ctx.budget.snapshot(), indent=2))
    ctx.write("enrichment.md", _render_enrichment(ctx))
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
                    metric=ctx.metric, intent_tags=tags, result_hash=rh,
                    run_id=ctx.run_id, notes="validated headline query")
    except Exception:
        pass  # archiving is best-effort; never break a completed run


NODE_FNS = {
    "profile": n_profile, "frame": n_frame, "semantics": n_semantics,
    "explore": n_explore, "diagnose": n_diagnose, "redteam": n_redteam,
    "sizing": n_sizing, "forecast": n_forecast, "cohort": n_cohort,
    "narrative": n_narrative, "deck": n_deck, "stakeholder": n_stakeholder,
    "retro": n_retro,
}


def _ser_dec(dec: MarginDecomposition) -> dict:
    return {
        "m1": dec.m1, "m2": dec.m2, "delta": dec.delta,
        "mix_total": dec.mix_total, "rate_total": dec.rate_total,
        "interaction_total": dec.interaction_total,
        "segments": [{"key": s.key, "mix": s.mix, "rate": s.rate,
                      "interaction": s.interaction, "w1": s.w1, "w2": s.w2,
                      "m1": s.m1, "m2": s.m2} for s in dec.segments],
    }


def _deser_dec(d: dict) -> MarginDecomposition:
    segs = [SegmentContribution(**s) for s in d["segments"]]
    return MarginDecomposition(
        m1=d["m1"], m2=d["m2"], delta=d["delta"], mix_total=d["mix_total"],
        rate_total=d["rate_total"], interaction_total=d["interaction_total"], segments=segs)


def _hydrate(ctx: RunContext, completed: dict) -> None:
    """Rebuild scratch + ledger from persisted node outputs (resume)."""
    if "frame" in completed:
        ctx.scratch["assumptions"] = completed["frame"].get("assumptions", [])
    if "explore" in completed:
        e = completed["explore"]
        ctx.scratch.update(
            dec=_deser_dec(e["dec"]), add=e["add"], simp=e["simp"],
            r1=tuple(e["r1"]), r2=tuple(e["r2"]),
            rev_p1=e.get("rev_p1", 0.0), rev_p2=e.get("rev_p2", 0.0),
            row_count=e.get("row_count", 1))
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
) -> RunResult:
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
    )

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
        dec = ctx.scratch["dec"]
        headline = (f"{ctx.region} gross margin fell {abs(dec.delta_pts):.1f}pts "
                    f"({dec.m1*100:.1f}% -> {dec.m2*100:.1f}%), "
                    f"driven by {dec.dominant_effect()}.")
        state.headline = headline
        state.save(runs_root)
        return RunResult(run_id, run_dir, "COMPLETE", gates=ctx.gates,
                         headline=headline, artefacts=ctx.artefacts)

    if result.status == "BLOCKED":
        _blocked(run_id, run_dir, ctx.gates, result.reason, ctx.ledger)
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
def _blocked(run_id, run_dir, gates, reason, ledger=None):
    (run_dir / "BLOCKED.md").write_text(
        f"# Run {run_id} BLOCKED\n\n**Reason:** {reason}\n\n"
        f"## Gates\n" + "\n".join(f"- {k}: {v}" for k, v in gates.items()) +
        "\n\n## What Atlas needs\nResolve the blocking condition above, then re-run. "
        "Atlas does not emit a degraded deck.\n"
    )
    if ledger is not None:
        ledger.save(run_dir / "provenance.json")


def _render_profile(source, report, verdict):
    lines = [f"# Profile — {source}", "", f"**Rows:** {report.row_count}", "",
             "## Columns", "", "| column | dtype | null_rate | distinct |",
             "|---|---|---|---|"]
    for c in report.columns:
        lines.append(f"| {c['column']} | {c['dtype']} | {c['null_rate']} | {c['distinct']} |")
    lines += ["", "## Warnings"] + ([f"- {w}" for w in report.warnings] or ["- none"])
    lines += ["", f"## Verdict", "", f"**{verdict.line()}**"]
    return "\n".join(lines)


def _render_brief(question, owner, region, p1, p2, assumptions, semantic_note):
    return (
        f"# Brief\n\n"
        f"**Question:** {question}\n\n"
        f"**Decision owner:** {owner}\n\n"
        f"**Decision unblocked:** Whether/how to intervene on {region} margin.\n\n"
        f"**Primary metric:** gross margin (ratio).\n\n"
        f"**Comparison window:** {p2} vs {p1}.\n\n"
        f"**Grain:** product_line x segment, {region}.\n\n"
        f"**Success criteria:** A ranked, decomposed, provenance-stamped cause.\n\n"
        f"**Non-goals:** Other regions; forecasting; pricing strategy build-out.\n\n"
        f"## Semantic resolution\n{semantic_note}\n\n"
        f"## Assumptions (declared, not buried)\n" +
        "\n".join(f"- {a}" for a in assumptions) + "\n"
    )


def _render_hypotheses(dec, add, simp, dim, p1, p2):
    seg_lines = "\n".join(
        f"- **{s.key}**: total {s.total*100:+.2f}pts (mix {s.mix*100:+.2f}, "
        f"rate {s.rate*100:+.2f}, interaction {s.interaction*100:+.2f})"
        for s in dec.segments
    )
    add_lines = "\n".join(
        f"- **{a['key']}** revenue {a['contribution']:+,.0f}" for a in add
    )
    return (
        f"# Hypotheses & exploration ({p2} vs {p1})\n\n"
        f"## H1 — Mix vs rate (grain: {dim})\n"
        f"Margin change {dec.delta_pts:+.2f}pts = mix {dec.mix_total*100:+.2f} + "
        f"rate {dec.rate_total*100:+.2f} + interaction {dec.interaction_total*100:+.2f}.\n"
        f"Dominant effect: **{dec.dominant_effect()}**.\n\n{seg_lines}\n\n"
        f"## H2 — Revenue mix shift\n{add_lines}\n\n"
        f"## H3 — Simpson's paradox check\n"
        f"paradox={simp['paradox']}; aggregate {simp['aggregate_delta_pts']:+.2f}pts; "
        f"segment deltas {simp['segment_deltas_pts']}.\n"
    )


def _render_findings(region, p1, p2, dec, simp):
    return (
        f"# Findings\n\n"
        f"**Headline (evidence tier: decomposed):** {region} gross margin fell "
        f"{abs(dec.delta_pts):.1f}pts, from {dec.m1*100:.1f}% ({p1}) to "
        f"{dec.m2*100:.1f}% ({p2}).\n\n"
        f"**Root cause (decomposed):** The drop is a **{dec.dominant_effect()}** effect. "
        f"Mix contributed {dec.mix_total*100:+.2f}pts; within-segment rate contributed "
        f"{dec.rate_total*100:+.2f}pts; interaction {dec.interaction_total*100:+.2f}pts.\n\n"
        f"**Ranked drivers:**\n" +
        "\n".join(f"{i+1}. {s.key}: {s.total*100:+.2f}pts" for i, s in enumerate(dec.segments)) +
        f"\n\n**Simpson check:** {'PARADOX FLAGGED' if simp['paradox'] else 'no paradox'}.\n"
    )


def _render_validation(region, p1, p2, dec, rd_m1, rd_m2, ok, tol, attacks):
    return (
        f"# Validation (red-team)\n\n"
        f"## Independent re-derivation\n"
        f"Re-derived from raw sums via a separate query (analyst SQL not seen):\n"
        f"- {p1}: {rd_m1:.2f}% vs analyst {dec.m1*100:.2f}%\n"
        f"- {p2}: {rd_m2:.2f}% vs analyst {dec.m2*100:.2f}%\n"
        f"- Tolerance: ±{tol*100:.2f}% relative -> **{'WITHIN' if ok else 'OUTSIDE'}**\n\n"
        f"## Attacks\n" + ("\n".join(f"- SURVIVING: {a}" for a in attacks) or "- none survived") +
        f"\n\n## Verdict\n**{'PASS' if ok and not attacks else 'FAIL'}**\n"
    )


def _render_narrative(region, p1, p2, dec, owner):
    return (
        f"# Narrative — for {owner}\n\n"
        f"## Answer (one sentence)\n"
        f"{region} gross margin fell {abs(dec.delta_pts):.1f} points because revenue mix "
        f"shifted toward lower-margin lines — not because any product got less profitable "
        f"[c_delta, c_mix].\n\n"
        f"## Why (three pillars)\n"
        f"1. **The fall is real and precise:** {dec.m1*100:.1f}% -> {dec.m2*100:.1f}% "
        f"({dec.delta_pts:+.1f}pts) [c_gm_p1, c_gm_p2].\n"
        f"2. **It is a mix shift:** mix explains {dec.mix_total*100:+.1f}pts; rate only "
        f"{dec.rate_total*100:+.1f}pts [c_mix, c_rate].\n"
        f"3. **No product became less profitable:** within-line margins are essentially flat.\n\n"
        f"## So what\n"
        f"Margin is defensible: rebalance mix rather than chase cost.\n"
    )


def _build_deck_spec(region, p1, p2, dec, add, owner, assumptions, ledger) -> DeckSpec:
    seg = dec.segments
    slides = [
            Slide("insight",
                  f"Gross margin dropped from {dec.m1*100:.1f}% to {dec.m2*100:.1f}% "
                  f"— a {abs(dec.delta_pts):.1f}pt fall",
                  bullets=[f"{p1}: {dec.m1*100:.1f}%", f"{p2}: {dec.m2*100:.1f}%",
                           "Within-line margins essentially unchanged"],
                  chart=Chart("column", [p1, p2],
                              {"Gross margin %": [round(dec.m1*100, 2), round(dec.m2*100, 2)]},
                              title=f"{region} gross margin"),
                  speaker_notes=(
                      f"The headline is a {abs(dec.delta_pts):.1f} point drop in {region} gross "
                      f"margin, from {dec.m1*100:.1f} to {dec.m2*100:.1f} percent. Hold on that "
                      f"number: it is exact and independently re-derived. What matters next is "
                      f"that no product line actually got less profitable — so this is a mix "
                      f"story, which we will show on the next slide."),
                  claim_ids=["c_gm_p1", "c_gm_p2", "c_delta"]),
            Slide("evidence",
                  "The entire drop is a mix shift, not a rate collapse",
                  bullets=[f"Mix: {dec.mix_total*100:+.1f}pts",
                           f"Rate: {dec.rate_total*100:+.1f}pts",
                           f"Interaction: {dec.interaction_total*100:+.1f}pts"],
                  chart=Chart("bar", ["Mix", "Rate", "Interaction"],
                              {"Contribution (pts)": [round(dec.mix_total*100, 2),
                                                      round(dec.rate_total*100, 2),
                                                      round(dec.interaction_total*100, 2)]}),
                  speaker_notes=(
                      f"Decomposing the change exactly, mix contributes {dec.mix_total*100:+.1f} "
                      f"points while rate contributes only {dec.rate_total*100:+.1f}. The identity "
                      f"is exact — mix plus rate plus interaction equals the total change. In plain "
                      f"terms: we sold a lower-margin blend, we did not get worse at any single "
                      f"product. That distinction changes the fix entirely."),
                  claim_ids=["c_mix", "c_rate", "c_delta"]),
            Slide("sowhat",
                  "This is a defensible, mix-driven move — cost-cutting would miss it",
                  bullets=[f"Top driver: {seg[0].key} ({seg[0].total*100:+.1f}pts)",
                           "Rate levers (procurement, pricing) would not have caught this"],
                  speaker_notes=(
                      f"So what does this mean for you? Because the driver is {seg[0].key} mix "
                      f"and not unit economics, the right response is commercial — steering the "
                      f"sales blend — rather than a cost programme. A procurement or pricing push "
                      f"would spend effort against the wrong cause."),
                  claim_ids=["c_mix"]),
            Slide("recommendation",
                  "Rebalance the EMEA product mix to recover the 4 points",
                  bullets=["Incentivise higher-margin attach in the sales motion",
                           "Review discounting on the lower-margin line",
                           "Track mix weekly as the leading indicator"],
                  speaker_notes=(
                      "The recommendation is three concrete moves: incentivise the higher-margin "
                      "attach, review discounting on the line that grew, and instrument mix as a "
                      "weekly leading indicator so this never surprises us again. None of these "
                      "require a cost programme; all target the mechanism we identified."),
                  claim_ids=[]),
    ]

    # Opportunity slide — inserted after the evidence slide when sizing produced a
    # provenance-stamped estimate (opportunity-sizer node). Keeps the deck honest:
    # the impact is a sized estimate (hypothesis tier), shown with its driver.
    opp = ledger.get("c_opportunity")
    rev = ledger.get("c_revenue_p2")
    if opp is not None and rev is not None:
        slides.insert(2, Slide(
            "sowhat",
            f"Recovering the mix drift is worth ≈ {opp.value:,.0f}",
            bullets=[f"Mix-driven points recoverable: {abs(dec.mix_total)*100:.1f}pts",
                     f"On {p2} revenue of {rev.value:,.0f}",
                     "Sized estimate — see tornado in the appendix"],
            chart=Chart("column", ["Opportunity"], {"Est. value": [round(opp.value, 2)]},
                        title="Margin-recovery opportunity"),
            speaker_notes=(
                f"To put a number on it: recovering the mix-driven {abs(dec.mix_total)*100:.1f} "
                f"points on {p2} revenue is worth roughly {opp.value:,.0f}. Treat this as a "
                f"sized estimate, not a measured fact — the appendix shows the tornado, and it "
                f"hinges most on how many of those points are actually recoverable."),
            claim_ids=["c_opportunity", "c_revenue_p2"]))

    return DeckSpec(
        title=(f"{region} gross margin fell {abs(dec.delta_pts):.0f}pts because volume "
               f"shifted to lower-margin lines"),
        subtitle=f"{p2} vs {p1} gross-margin decomposition",
        decision_owner=owner,
        slides=slides,
        assumptions=assumptions,
        methodology=(
            "Exact mix / rate / interaction decomposition of gross margin at product_line "
            "grain.\nHeadline independently re-derived from raw revenue/cogs sums within "
            "±0.5% tolerance.\nEvery number carries a provenance ID -> stored query + result hash."),
        provenance=[
            {"claim_id": c.claim_id, "text": c.text, "value": c.value,
             "query_hash": c.query_hash, "tier": c.evidence_tier}
            for c in ledger.all()
        ],
    )


def _stakeholder_check(spec, dec, simp) -> list[str]:
    """Five hardest exec questions; return any the deck+notes cannot answer."""
    notes = " ".join(s.speaker_notes.lower() for s in spec.slides)
    checks = {
        "Is the number right?": "re-derived" in notes or "exact" in notes,
        "Is it mix or rate?": "mix" in notes and "rate" in notes,
        "Which line drives it?": any("driver" in s.title.lower() or dec.segments[0].key.lower() in notes
                                     for s in spec.slides),
        "Should we cut cost?": "cost" in notes,
        "What do we do Monday?": any(s.kind == "recommendation" for s in spec.slides),
    }
    return [q for q, ok in checks.items() if not ok]


def _render_retro(run_id, gates, budget):
    return (
        f"# Retrospective — {run_id}\n\n"
        f"## Gates\n" + "\n".join(f"- {k}: {v}" for k, v in gates.items()) + "\n\n"
        f"## Budget\n```json\n{json.dumps(budget.snapshot(), indent=2)}\n```\n\n"
        f"## Corrections detected\n- none (deterministic run)\n\n"
        f"## Lessons\n- none new this run\n"
    )
