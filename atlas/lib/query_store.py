"""Query + result store with content-addressed hashing.

Every connector.run() routes through here so that hashing and on-disk storage
are NOT optional. A number's provenance is only trustworthy if the exact query
text and the exact result bytes are both recoverable and hash-stable.

Layout per run:
  runs/<run_id>/queries/<query_hash>.sql        # exact SQL text
  runs/<run_id>/queries/<query_hash>.meta.json  # source, dialect, ts, result_hash, bytes
  runs/<run_id>/evidence/<result_hash>.json     # canonicalised result rows
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def hash_query(sql: str, source: str, dialect: str) -> str:
    """Stable hash of the *normalised* query + source identity."""
    norm = " ".join(sql.replace(";", " ").split()).strip()
    return _sha(f"{dialect}::{source}::{norm}")


def hash_result(rows: list[dict[str, Any]], columns: list[str]) -> str:
    """Stable hash of the result set, insensitive to dict key ordering."""
    canon = json.dumps(
        {"columns": columns, "rows": [[r.get(c) for c in columns] for r in rows]},
        sort_keys=True, default=str, separators=(",", ":"),
    )
    return _sha(canon)


@dataclass
class QueryResult:
    rows: list[dict[str, Any]]
    columns: list[str]
    query_hash: str
    result_hash: str
    source: str
    dialect: str
    sql: str
    bytes_scanned: int | None = None
    row_count: int = 0
    sampled: bool = False
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self):
        if not self.row_count:
            self.row_count = len(self.rows)

    def scalar(self):
        """Convenience: single-cell result."""
        if self.rows and self.columns:
            return self.rows[0][self.columns[0]]
        return None


class QueryStore:
    def __init__(self, run_dir: str | Path):
        self.run_dir = Path(run_dir)
        self.queries_dir = self.run_dir / "queries"
        self.evidence_dir = self.run_dir / "evidence"

    def _ensure(self):
        self.queries_dir.mkdir(parents=True, exist_ok=True)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

    def store(self, result: QueryResult) -> QueryResult:
        """Persist SQL + metadata + result rows. Idempotent by hash."""
        self._ensure()
        (self.queries_dir / f"{result.query_hash}.sql").write_text(result.sql)
        (self.queries_dir / f"{result.query_hash}.meta.json").write_text(json.dumps({
            "query_hash": result.query_hash,
            "result_hash": result.result_hash,
            "source": result.source,
            "dialect": result.dialect,
            "bytes_scanned": result.bytes_scanned,
            "row_count": result.row_count,
            "sampled": result.sampled,
            "ts": result.ts,
        }, indent=2))
        (self.evidence_dir / f"{result.result_hash}.json").write_text(json.dumps({
            "columns": result.columns,
            "rows": result.rows,
        }, indent=2, default=str))
        return result

    def load_query(self, query_hash: str) -> dict | None:
        meta = self.queries_dir / f"{query_hash}.meta.json"
        sql = self.queries_dir / f"{query_hash}.sql"
        if not meta.exists():
            return None
        data = json.loads(meta.read_text())
        data["sql"] = sql.read_text() if sql.exists() else None
        return data

    def load_result(self, result_hash: str) -> dict | None:
        p = self.evidence_dir / f"{result_hash}.json"
        return json.loads(p.read_text()) if p.exists() else None

    def verify(self, query_hash: str) -> bool:
        """Re-hash the stored result and confirm it matches the recorded hash.

        Underpins /replay: re-running a stored query against current data and
        checking whether the finding still holds.
        """
        meta = self.load_query(query_hash)
        if not meta:
            return False
        res = self.load_result(meta["result_hash"])
        if not res:
            return False
        return hash_result(res["rows"], res["columns"]) == meta["result_hash"]
