"""Query archaeology — retrieve proven SQL before authoring new.

Every query that produced a validated headline is archived keyed by
(source | metric | intent-tags). Before the sql-engineer writes a new query for the
same shape of question, it retrieves the closest proven pattern — so the team stops
re-deriving the same SQL (and stops re-making the same SQL mistakes).

Stored in memory/query_archive.jsonl. Dedup is by the same normalised query hash the
QueryStore uses, so an identical query is reused (times_reused++) rather than
duplicated.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from atlas.config import PATHS
from atlas.lib.query_store import hash_query

ARCHIVE = PATHS.memory / "query_archive.jsonl"


@dataclass
class ArchivedQuery:
    id: str
    source: str
    dialect: str
    metric: str
    intent_tags: list[str]
    sql: str
    query_hash: str
    result_hash: str = ""
    run_id: str = ""
    notes: str = ""
    times_reused: int = 0
    created: str = field(default_factory=lambda: date.today().isoformat())
    last_used: str | None = None


def _load(path: Path | None = None) -> list[dict]:
    p = path or ARCHIVE
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def _save(rows: list[dict], path: Path | None = None) -> None:
    p = path or ARCHIVE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in rows) + ("\n" if rows else ""))


def _next_id(rows: list[dict]) -> str:
    n = 1 + max((int(r["id"].split("-")[1]) for r in rows if r.get("id", "").startswith("Q-")),
                default=0)
    return f"Q-{n:04d}"


def archive(
    sql: str,
    *,
    source: str,
    dialect: str,
    metric: str,
    intent_tags: list[str],
    result_hash: str = "",
    run_id: str = "",
    notes: str = "",
    path: Path | None = None,
) -> ArchivedQuery:
    """Add a proven query. If the same normalised query already exists, reuse it."""
    rows = _load(path)
    qh = hash_query(sql, source, dialect)
    for r in rows:
        if r["query_hash"] == qh:
            r["times_reused"] = r.get("times_reused", 0) + 1
            r["last_used"] = date.today().isoformat()
            # merge any new tags
            r["intent_tags"] = sorted(set(r.get("intent_tags", [])) | set(intent_tags))
            _save(rows, path)
            return ArchivedQuery(**r)
    aq = ArchivedQuery(
        id=_next_id(rows), source=source, dialect=dialect, metric=metric,
        intent_tags=sorted(set(intent_tags)), sql=sql.strip(), query_hash=qh,
        result_hash=result_hash, run_id=run_id, notes=notes,
    )
    rows.append(asdict(aq))
    _save(rows, path)
    return aq


def retrieve(
    *,
    source: str | None = None,
    metric: str | None = None,
    intent_tags: list[str] | None = None,
    limit: int = 5,
    path: Path | None = None,
) -> list[ArchivedQuery]:
    """Return proven queries best matching the request, ranked.

    Ranking: exact source match and metric match are required when provided; ties
    broken by intent-tag overlap (Jaccard) then times_reused.
    """
    tags = set(intent_tags or [])
    scored: list[tuple[float, int, dict]] = []
    for r in _load(path):
        if source and r["source"] != source:
            continue
        if metric and r["metric"] != metric:
            continue
        rtags = set(r.get("intent_tags", []))
        overlap = len(tags & rtags) / len(tags | rtags) if (tags or rtags) else 0.0
        scored.append((overlap, r.get("times_reused", 0), r))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [ArchivedQuery(**r) for _, _, r in scored[:limit]]


def stats(path: Path | None = None) -> dict:
    rows = _load(path)
    return {
        "total": len(rows),
        "reused": sum(r.get("times_reused", 0) for r in rows),
        "by_metric": _count(rows, "metric"),
        "by_source": _count(rows, "source"),
    }


def _count(rows: list[dict], key: str) -> dict:
    out: dict[str, int] = {}
    for r in rows:
        out[r.get(key, "?")] = out.get(r.get(key, "?"), 0) + 1
    return out
