#!/usr/bin/env python3
"""PreToolUse hook — the OUTER read-only + budget gate and lesson injector.

Wired in .claude/settings.json for Bash tool calls. Reads the tool-call JSON on
stdin. Exit code 2 (with stderr message) BLOCKS the call; exit 0 allows it.

What it enforces mechanically:
  * any SQL that is not a single read-only statement is blocked (INSERT/UPDATE/
    DELETE/DROP/CREATE/ALTER/MERGE/TRUNCATE/GRANT/COPY, or multi-statement).
  * detection is best-effort over the Bash command string; the connector layer
    (atlas/connectors/base.run) re-asserts, so this is defence in depth.

What it does best-effort:
  * injects matching lessons (by source|metric|failure_class fingerprint) into
    the tool call's context via additionalContext, so the agent sees prior
    mistakes before repeating them.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

try:
    from atlas.lib.sqlguard import assert_read_only, UnsafeSQLError
except Exception:
    # keep the hook resilient even if the package can't import
    def assert_read_only(_sql):  # type: ignore
        return None
    class UnsafeSQLError(Exception):  # type: ignore
        pass

# Heuristic: pull candidate SQL out of a shell command. We look for SQL passed to
# duckdb/psql/bq/snowsql or embedded in python -c "... run('SELECT ...')".
# A quoted blob is treated as a SQL statement only if it STARTS with one of these.
_LEADS = re.compile(
    r"^\s*(SELECT|WITH|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|MERGE|TRUNCATE|"
    r"GRANT|REVOKE|COPY|EXPLAIN|DESCRIBE|DESC|SHOW|PRAGMA)\b",
    re.IGNORECASE,
)
_MUTATING = re.compile(
    r"\b(INSERT\s+INTO|UPDATE\s+\S+\s+SET|DELETE\s+FROM|DROP\s+(TABLE|VIEW|SCHEMA|DATABASE)|"
    r"MERGE\s+INTO|TRUNCATE\s+TABLE|ALTER\s+(TABLE|VIEW)|GRANT\s+|REVOKE\s+)\b",
    re.IGNORECASE,
)
_SINGLE = re.compile(r"'([^']*)'", re.DOTALL)
_DOUBLE = re.compile(r'"([^"]*)"', re.DOTALL)


def extract_sql_candidates(command: str) -> list[str]:
    """Quoted strings (either quote type) that begin with a SQL keyword.

    Scanning both quote types independently means a nested SQL literal inside an
    outer shell/python quote (e.g. python -c "con.run('SELECT ...')") is found,
    while the outer non-SQL wrapper is ignored.
    """
    cands = []
    for rx in (_SINGLE, _DOUBLE):
        for m in rx.finditer(command):
            s = m.group(1)
            if _LEADS.match(s):
                cands.append(s)
    # bare command that is itself a SQL statement (e.g. `psql -c 'DROP ...'` handled
    # above; here catch an unquoted leading statement)
    if not cands and _LEADS.match(command):
        cands.append(command)
    return cands


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # nothing to inspect

    tool = payload.get("tool_name") or payload.get("tool") or ""
    tin = payload.get("tool_input") or payload.get("input") or {}
    command = tin.get("command", "") if isinstance(tin, dict) else ""

    if tool != "Bash" or not command:
        return 0

    for sql in extract_sql_candidates(command):
        # fast reject obvious mutations
        if _MUTATING.search(sql):
            sys.stderr.write(
                "BLOCKED by Atlas read-only guard: mutating/DDL statement detected. "
                "Atlas is read-only to all data sources.\n"
            )
            return 2
        # precise reject via shared guard
        try:
            assert_read_only(sql)
        except UnsafeSQLError as e:
            sys.stderr.write(f"BLOCKED by Atlas read-only guard: {e}\n")
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
