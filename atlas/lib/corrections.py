"""Corrections + miss-rate tracking.

A *correction* is the analyst telling Atlas it got something wrong (wrong column,
wrong metric meaning, wrong filter). It is a stronger signal than a passively-observed
lesson: corrections are logged explicitly and, for the mechanical classes, suggest a
promotion to a hard artefact (e.g. lock a metric definition).

A *miss* is any time the knowledge system failed to prevent a mistake or lacked the
context it should have had. Tracking the miss-rate over runs shows whether the
learning loop is actually improving — honest instrumentation, not a vanity metric.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from atlas.config import PATHS

CORRECTIONS = PATHS.memory / "corrections.jsonl"
MISS_RATE = PATHS.memory / "miss_rate.jsonl"

# correction classes that can be promoted to a mechanical guarantee
PROMOTABLE = {
    "metric-definition": "lock the formula in atlas/semantic/metrics.yaml",
    "source-quirk": "add an assertion in memory/quirks/<source>.md",
    "unsafe-write": "add a rule in .claude/hooks/pre_tool_use.py",
    "filter-leakage": "add an assertion in the query template",
}


@dataclass
class Correction:
    id: str
    what: str                  # what was wrong
    correct: str               # the right answer
    wrong: str = ""            # what Atlas had
    cls: str = "analytical"    # correction class (see PROMOTABLE)
    scope: str = ""            # e.g. "metric:gross_margin" / "source:prod_pg"
    run_id: str = ""
    promoted: bool = False
    created: str = field(default_factory=lambda: date.today().isoformat())

    @property
    def promotion_hint(self) -> str | None:
        return PROMOTABLE.get(self.cls)


def _load(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()] \
        if path.exists() else []


def _next_id(rows: list[dict]) -> str:
    n = 1 + max((int(r["id"].split("-")[1]) for r in rows if r.get("id", "").startswith("C-")),
                default=0)
    return f"C-{n:04d}"


def log_correction(
    what: str, correct: str, *, wrong: str = "", cls: str = "analytical",
    scope: str = "", run_id: str = "", path: Path | None = None,
) -> Correction:
    p = path or CORRECTIONS
    rows = _load(p)
    c = Correction(id=_next_id(rows), what=what, correct=correct, wrong=wrong,
                   cls=cls, scope=scope, run_id=run_id)
    rows.append(asdict(c))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return c


def log_miss(kind: str, detail: str = "", *, prevented: bool = False,
             path: Path | None = None) -> None:
    """Record whether the knowledge system prevented a mistake (or missed it)."""
    p = path or MISS_RATE
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(),
            "kind": kind, "detail": detail, "prevented": prevented,
        }) + "\n")


def miss_rate(last_n: int | None = None, path: Path | None = None) -> dict:
    """Fraction of tracked events that were misses (not prevented)."""
    rows = _load(path or MISS_RATE)
    if last_n:
        rows = rows[-last_n:]
    total = len(rows)
    prevented = sum(1 for r in rows if r.get("prevented"))
    misses = total - prevented
    return {
        "events": total,
        "prevented": prevented,
        "misses": misses,
        "miss_rate": (misses / total) if total else 0.0,
    }
