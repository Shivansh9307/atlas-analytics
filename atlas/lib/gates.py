"""Validation gates + rework routing.

A gate does not merely stop the pipeline; a FAIL returns a specific fix list to
the agent that OWNS the defect, capped at N loops, then escalates to the human
with a "here's what's blocking and what I need" report — never a degraded deck.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class GateStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    ESCALATE = "ESCALATE"  # rework cap exhausted -> hand to human


# Which agent owns which defect class, and the per-gate rework cap.
ROUTING: dict[str, tuple[str, int]] = {
    "unprovenanced_number": ("sql-engineer", 2),
    "bad_number": ("sql-engineer", 2),
    "unsupported_claim": ("narrative-writer", 2),
    "weak_causal_logic": ("root-cause-analyst", 2),
    "underpowered_stat": ("statistician", 2),
    "metric_ambiguity": ("semantic-architect", 1),
    "column_binding": ("semantic-architect", 1),
    "unanswered_stakeholder_q": ("narrative-writer", 2),
    "failed_rederivation": ("sql-engineer", 2),
    "data_not_ready": ("data-quality-copilot", 2),
}


@dataclass
class Defect:
    kind: str          # key into ROUTING
    detail: str        # human-readable specifics
    ref: str = ""      # e.g. claim_id / slide / metric name

    @property
    def owner(self) -> str:
        return ROUTING.get(self.kind, ("orchestrator", 0))[0]

    @property
    def cap(self) -> int:
        return ROUTING.get(self.kind, ("orchestrator", 0))[1]


@dataclass
class GateResult:
    gate: str
    status: GateStatus
    defects: list[Defect] = field(default_factory=list)
    summary: str = ""

    @property
    def passed(self) -> bool:
        return self.status == GateStatus.PASS


@dataclass
class ReworkTracker:
    """Counts rework attempts per (gate, defect_kind) and decides escalate."""
    _counts: dict[tuple[str, str], int] = field(default_factory=dict)

    def register(self, gate: str, defect: Defect) -> GateStatus:
        key = (gate, defect.kind)
        self._counts[key] = self._counts.get(key, 0) + 1
        if self._counts[key] > defect.cap:
            return GateStatus.ESCALATE
        return GateStatus.FAIL

    def attempts(self, gate: str, kind: str) -> int:
        return self._counts.get((gate, kind), 0)


def routing_note(result: "GateResult") -> str:
    """Who owns each defect in a failed gate, and how many attempts it gets.

    Deliberately informational rather than an automatic retry loop. In the
    deterministic engine a gate's inputs are already-computed stored values, so
    re-running the same evaluator produces a bit-identical failure — a rework loop
    would burn budget to reach the same conclusion and make an honest hard block look
    intermittent. What is genuinely useful is telling whoever picks this up which
    agent owns the fix, which is what ROUTING encodes.
    """
    if result.passed or not result.defects:
        return ""
    lines = ["", "## Who owns this", ""]
    seen: set[tuple[str, str]] = set()
    for d in result.defects:
        key = (d.kind, d.owner)
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"- `{d.kind}` -> **{d.owner}** (rework cap {d.cap})")
    return "\n".join(lines)


# --- concrete gate evaluators (pure functions over already-computed inputs) ---

def gate1_profiling(verdicts: dict[str, str]) -> GateResult:
    """GATE 1: at least one source returns GO."""
    gos = [s for s, v in verdicts.items() if str(v).upper().startswith("GO")]
    if gos:
        return GateResult("GATE1_profiling", GateStatus.PASS,
                          summary=f"GO sources: {gos}")
    return GateResult("GATE1_profiling", GateStatus.FAIL,
                      summary="all sources NO-GO; cannot answer — report data needs")


def gate2_semantics(unresolved: list[str]) -> GateResult:
    """GATE 2: zero unresolved metric ambiguity."""
    if not unresolved:
        return GateResult("GATE2_semantics", GateStatus.PASS)
    defects = [Defect("metric_ambiguity", f"'{m}' not resolvable against metrics.yaml", m)
               for m in unresolved]
    return GateResult("GATE2_semantics", GateStatus.FAIL, defects,
                      summary=f"unresolved metrics: {unresolved}")


def gate3_redteam(rederivation_ok: bool, surviving_attacks: list[str]) -> GateResult:
    """GATE 3: red-team PASS AND re-derivation within tolerance."""
    defects: list[Defect] = []
    if not rederivation_ok:
        defects.append(Defect("failed_rederivation",
                              "independent re-derivation outside tolerance"))
    for a in surviving_attacks:
        defects.append(Defect("weak_causal_logic", a))
    if defects:
        return GateResult("GATE3_redteam", GateStatus.FAIL, defects,
                          summary="red-team veto")
    return GateResult("GATE3_redteam", GateStatus.PASS)


def gate4_provenance(orphan_claim_ids: list[str],
                     unfingerprinted: list[str] | None = None) -> GateResult:
    """GATE 4: every deck number resolves in the ledger, and every model-derived
    number has its recipe persisted.

    `unfingerprinted` is defaulted so existing single-argument call sites are
    unaffected. A derived claim whose `ModelFingerprint` was never written to disk is
    exactly as unsourced as a fabricated one: nobody can re-derive it.
    """
    unfingerprinted = unfingerprinted or []
    if not orphan_claim_ids and not unfingerprinted:
        return GateResult("GATE4_provenance", GateStatus.PASS)
    defects = [Defect("unprovenanced_number", f"claim {cid} has no ledger entry", cid)
               for cid in orphan_claim_ids]
    defects += [Defect("unprovenanced_number",
                       f"claim {cid} is model-derived but its fingerprint was not "
                       f"persisted, so the number cannot be re-derived", cid)
                for cid in unfingerprinted]
    bits = []
    if orphan_claim_ids:
        bits.append(f"{len(orphan_claim_ids)} orphan number(s)")
    if unfingerprinted:
        bits.append(f"{len(unfingerprinted)} unfingerprinted derived number(s)")
    return GateResult("GATE4_provenance", GateStatus.FAIL, defects,
                      summary=" and ".join(bits) + " block export")


def gate_readiness(ready: bool, decision: str, reasons: list[str]) -> GateResult:
    """Data Readiness Gate: the clean layer must be analysable before analysis runs.

    Repairable critical issues are not blockers (high-confidence repairs auto-apply;
    low-confidence ones are flagged pending). The gate FAILs only when the copilot
    reports the source is not ready (score below floor or an unrepairable critical)."""
    if ready:
        return GateResult("GATE_readiness", GateStatus.PASS,
                          summary=f"data ready ({decision})")
    defects = [Defect("data_not_ready", r) for r in (reasons or ["data not ready"])]
    return GateResult("GATE_readiness", GateStatus.FAIL, defects,
                      summary=f"data not ready: {decision}")


def gate5_stakeholder(unanswered: list[str]) -> GateResult:
    """GATE 5: all hard stakeholder questions answerable from deck + notes."""
    if not unanswered:
        return GateResult("GATE5_stakeholder", GateStatus.PASS)
    defects = [Defect("unanswered_stakeholder_q", q) for q in unanswered]
    return GateResult("GATE5_stakeholder", GateStatus.FAIL, defects,
                      summary=f"{len(unanswered)} hard question(s) unanswered")
