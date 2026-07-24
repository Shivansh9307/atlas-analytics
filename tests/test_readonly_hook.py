"""Tests for the read-only guard (shared lib) and the PreToolUse hook script."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from atlas.lib.sqlguard import assert_read_only, is_read_only, UnsafeSQLError

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / ".claude" / "hooks" / "pre_tool_use.py"


# ---- shared guard ----
@pytest.mark.parametrize("sql", [
    "SELECT 1",
    "select * from t where x = 1",
    "WITH a AS (SELECT 1) SELECT * FROM a",
    "EXPLAIN SELECT 1",
    "DESCRIBE finance",
])
def test_read_only_allows(sql):
    assert is_read_only(sql)


@pytest.mark.parametrize("sql", [
    "DELETE FROM t",
    "UPDATE t SET x = 1",
    "DROP TABLE t",
    "INSERT INTO t VALUES (1)",
    "TRUNCATE TABLE t",
    "MERGE INTO t USING s ON t.id=s.id WHEN MATCHED THEN UPDATE SET x=1",
    "ALTER TABLE t ADD COLUMN y int",
    "GRANT SELECT ON t TO u",
    "SELECT 1; DROP TABLE t",  # multi-statement
])
def test_read_only_blocks(sql):
    assert not is_read_only(sql)
    with pytest.raises(UnsafeSQLError):
        assert_read_only(sql)


# ---- hook script (end-to-end via subprocess, as Claude Code invokes it) ----
def _run_hook(command: str) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    return subprocess.run(
        [sys.executable, str(HOOK)], input=payload,
        capture_output=True, text=True,
    )


def test_hook_allows_select():
    r = _run_hook("uv run python -c \"con.run('SELECT count(*) FROM finance')\"")
    assert r.returncode == 0


def test_hook_blocks_delete():
    r = _run_hook("uv run python -c \"con.run('DELETE FROM finance')\"")
    assert r.returncode == 2
    assert "BLOCKED" in r.stderr


def test_hook_blocks_drop():
    r = _run_hook("psql -c 'DROP TABLE finance'")
    assert r.returncode == 2
