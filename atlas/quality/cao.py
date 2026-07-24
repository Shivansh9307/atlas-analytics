"""Chief Analytics Officer — the master orchestrator layer.

Sits ABOVE the deterministic DAG. Given a question it selects the cheapest path
that answers it (dynamic agent routing), estimates the work, enforces that the
Data Quality Copilot always runs first (trust before intelligence), and frames the
final recommendation. It composes existing pieces (the router, the DAG) rather
than replacing the numeric backbone.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from atlas.lib.router import classify

# Dynamic agent routing (spec examples): simple asks run a short path; only genuine
# root-cause questions trigger the full team. Quality/validation are never skipped.
_PATHS: dict[int, list[str]] = {
    1: ["quality", "sql-engineer", "red-team-validator"],                    # lookup
    2: ["quality", "sql-engineer", "root-cause-analyst", "red-team-validator"],  # breakdown
    3: ["quality", "source-profiler", "semantic-architect", "explorer",       # root-cause
        "root-cause-analyst", "statistician", "red-team-validator",
        "opportunity-sizer", "narrative-writer", "deck-builder", "stakeholder-simulator"],
    4: ["quality", "forecaster", "statistician", "red-team-validator", "narrative-writer"],  # forecast
    5: ["quality", "experiment-designer", "statistician"],                    # experiment
}
# Rough per-agent query cost, for a cheap runtime/scan estimate.
_COST = {"quality": 30, "source-profiler": 20, "explorer": 12, "root-cause-analyst": 8,
         "statistician": 4, "red-team-validator": 3, "sql-engineer": 2, "forecaster": 6,
         "opportunity-sizer": 2, "narrative-writer": 0, "deck-builder": 0,
         "stakeholder-simulator": 0, "semantic-architect": 1, "experiment-designer": 1}


@dataclass
class CAOPlan:
    question: str
    level: int
    label: str
    command: str
    agents: list[str]
    estimated_queries: int
    estimated_runtime_s: int
    rationale: str
    skipped: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def plan_run(question: str) -> CAOPlan:
    r = classify(question)
    agents = _PATHS.get(r.level, _PATHS[3])
    all_full = set(_PATHS[3])
    skipped = sorted(all_full - set(agents)) if r.level != 3 else []
    est_q = sum(_COST.get(a, 3) for a in agents)
    est_runtime = max(5, est_q * 2)   # ~2s/query heuristic for local sources
    rationale = (f"L{r.level} ({r.label}): {r.reason}. Quality Copilot runs first "
                 f"(trust before intelligence); "
                 + ("full analytics team engaged." if r.level == 3
                    else f"cheaper path — skipped {len(skipped)} agent(s)."))
    return CAOPlan(question=question, level=r.level, label=r.label, command=r.command,
                   agents=agents, estimated_queries=est_q, estimated_runtime_s=est_runtime,
                   rationale=rationale, skipped=skipped)


def render_plan(p: CAOPlan) -> str:
    return (
        f"# CAO run plan\n\n"
        f"**Question:** {p.question}\n\n"
        f"**Route:** L{p.level} {p.label} → `{p.command}`\n\n"
        f"**Agents:** {' → '.join(p.agents)}\n\n"
        f"**Estimate:** ~{p.estimated_queries} queries, ~{p.estimated_runtime_s}s\n\n"
        f"**Skipped (cost-aware):** {p.skipped or 'none'}\n\n"
        f"**Rationale:** {p.rationale}\n"
    )
