"""Read-only SQL enforcement. Shared by the connector layer and the PreToolUse hook.

Defence in depth: this is the *connector-layer* assertion. The hook layer
(.claude/hooks/pre_tool_use.py) calls the same functions so behaviour is identical
whether SQL arrives via a sub-agent's Bash call or via a direct connector.run().
"""
from __future__ import annotations

import re

try:
    from atlas.config import FORBIDDEN_SQL_ROOTS
except Exception:  # pragma: no cover - allow standalone hook import
    FORBIDDEN_SQL_ROOTS = frozenset({
        "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER",
        "MERGE", "TRUNCATE", "GRANT", "REVOKE", "COPY", "CALL",
        "REPLACE", "UPSERT", "VACUUM", "ATTACH", "DETACH", "SET",
    })

_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_ALLOWED_ROOTS = frozenset({"SELECT", "WITH", "EXPLAIN", "SHOW", "DESCRIBE", "DESC", "PRAGMA"})


class UnsafeSQLError(Exception):
    """Raised when a statement is not a read-only single query."""


def _strip_comments(sql: str) -> str:
    sql = _BLOCK_COMMENT.sub(" ", sql)
    sql = _LINE_COMMENT.sub(" ", sql)
    return sql.strip()


def _split_statements(sql: str) -> list[str]:
    """Naive but safe split on ';' that ignores semicolons inside quotes."""
    stmts, buf, quote = [], [], None
    for ch in sql:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            buf.append(ch)
        elif ch == ";":
            stmts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        stmts.append(tail)
    return [s for s in stmts if s]


def first_keyword(stmt: str) -> str:
    m = re.match(r"\s*([A-Za-z_]+)", stmt)
    return m.group(1).upper() if m else ""


def assert_read_only(sql: str) -> None:
    """Raise UnsafeSQLError unless `sql` is one or more read-only statements.

    Rules:
      * every statement's leading keyword must be in the allowed read-only set
      * no statement may lead with a forbidden (mutating/DDL) keyword
      * a trailing forbidden keyword anywhere (e.g. CTE hiding an INSERT) is caught
        because sqlglot parsing in the connector re-validates; here we scan tokens.
    """
    cleaned = _strip_comments(sql)
    if not cleaned:
        raise UnsafeSQLError("empty statement")

    statements = _split_statements(cleaned)
    if len(statements) > 1:
        # Multiple statements are refused outright — a classic injection vector.
        raise UnsafeSQLError(
            f"multiple statements not allowed (found {len(statements)}); "
            "run one read-only query at a time"
        )

    stmt = statements[0]
    root = first_keyword(stmt)
    if root in FORBIDDEN_SQL_ROOTS:
        raise UnsafeSQLError(f"forbidden statement type: {root}")
    if root not in _ALLOWED_ROOTS:
        raise UnsafeSQLError(f"only read-only statements allowed; got leading '{root or '?'}'")

    # Token scan for a mutating keyword hiding after a CTE / subquery.
    tokens = set(re.findall(r"[A-Za-z_]+", stmt.upper()))
    # These keywords, if present as statement roots elsewhere, indicate danger.
    dangerous = {"INSERT", "UPDATE", "DELETE", "DROP", "MERGE", "TRUNCATE", "ALTER", "GRANT"}
    hit = tokens & dangerous
    # Allow benign appearances (e.g. a column literally named "update") only when
    # not followed by typical DML syntax. Keep it strict: flag and let caller decide
    # via sqlglot in the connector. Here we only hard-fail on obvious DML patterns.
    if hit and re.search(
        r"\b(INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|DROP\s+(TABLE|VIEW|SCHEMA|DATABASE)|"
        r"MERGE\s+INTO|TRUNCATE\s+TABLE|ALTER\s+(TABLE|VIEW))\b",
        stmt.upper(),
    ):
        raise UnsafeSQLError(f"mutating pattern detected involving {sorted(hit)}")


def is_read_only(sql: str) -> bool:
    try:
        assert_read_only(sql)
        return True
    except UnsafeSQLError:
        return False
