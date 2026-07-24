"""Transformation pipeline driver used inside /analyze.

Runs the Data Quality Copilot end to end for one analysis run: detect -> score ->
plan -> auto-apply high-confidence repairs -> re-score the clean layer -> decide
readiness. Returns a small JSON-serialisable summary (resume-safe) and materialises
the clean layer in the live connector.

Readiness policy (full-auto friendly): a critical issue that HAS an available
repair is not a hard blocker — high-confidence repairs auto-apply and low-confidence
ones (e.g. fiscal-vs-calendar Quarter) are flagged as pending approval. The run only
BLOCKS when the clean-layer score is still below the floor or a critical issue has
no repair path at all.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from atlas.connectors.base import Connector, TableRef
from atlas.quality import clean_layer as cl
from atlas.quality.detectors import critical_issues, detect_issues
from atlas.quality.rules_loader import readiness_thresholds
from atlas.quality.score import score_table


@dataclass
class CopilotSummary:
    source: str
    base_table: str
    clean_table: str
    score_before: float
    score_after: float
    business_readiness: str
    applied: list[str] = field(default_factory=list)
    pending_approval: list[str] = field(default_factory=list)
    unrepairable_critical: list[str] = field(default_factory=list)
    warnings: int = 0
    ready: bool = True
    decision: str = "GO"                 # GO | GO-WITH-CAVEATS | NO-GO
    reason: str = ""

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def run_copilot(con: Connector, table: TableRef, source: str | None = None,
                run_dir: Path | None = None) -> CopilotSummary:
    source = source or con.name
    issues = detect_issues(con, table)
    before = score_table(con, table, issues=issues)

    plan = cl.build_plan(con, table, source)
    if not plan.transforms:
        # Nothing to repair (e.g. the clean EMEA fixture) — clean table == base.
        return _decide(source, table.name, table.name, before, before, [], [], [])

    res = cl.apply(con, table, source=source, run_dir=run_dir, persist=False)
    applied = [t.module_id for t in res.applied]
    pending = [t.module_id for t in res.skipped]

    # A critical issue is "unrepairable" only if no module produced a transform for it.
    repairable_cols = {t.column for t in plan.transforms}
    unrepairable = [f"{i.module_id}:{i.column}" for i in critical_issues(res.after.issues)
                    if i.column not in repairable_cols]
    return _decide(source, table.name, res.clean_table, before, res.after,
                   applied, pending, unrepairable)


def _decide(source, base, clean, before, after, applied, pending, unrepairable) -> CopilotSummary:
    t = readiness_thresholds()
    ready, decision, reason = True, "GO", ""
    if after.overall_score < t["min_overall_score"] or unrepairable:
        ready, decision = False, "NO-GO"
        reason = (f"clean-layer score {after.overall_score:.0f} < {t['min_overall_score']:.0f}"
                  if after.overall_score < t["min_overall_score"]
                  else f"unrepairable critical issue(s): {unrepairable}")
    elif pending or after.overall_score < t["caveats_below"] or after.warning_count:
        decision = "GO-WITH-CAVEATS"
        reason = (f"{len(pending)} repair(s) pending approval" if pending
                  else f"score {after.overall_score:.0f}; {after.warning_count} warning(s)")
    return CopilotSummary(
        source=source, base_table=base, clean_table=clean,
        score_before=before.overall_score, score_after=after.overall_score,
        business_readiness=after.business_readiness, applied=applied,
        pending_approval=pending, unrepairable_critical=unrepairable,
        warnings=after.warning_count, ready=ready, decision=decision, reason=reason)
