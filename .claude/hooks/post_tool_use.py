#!/usr/bin/env python3
"""PostToolUse hook — provenance logging.

Appends a lightweight audit line whenever a Bash tool call ran a query, so the
run log has an independent record of query activity alongside the QueryStore.
Never blocks (always exit 0). Best-effort; the authoritative provenance is the
per-run QueryStore + provenance.json written by the connector layer.
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
LOG = ROOT / "runs" / "_hook_audit.log"

_SQL_HINT = re.compile(r"\b(SELECT|WITH)\b", re.IGNORECASE)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    tin = payload.get("tool_input") or {}
    command = tin.get("command", "") if isinstance(tin, dict) else ""
    if command and _SQL_HINT.search(command):
        try:
            LOG.parent.mkdir(parents=True, exist_ok=True)
            with LOG.open("a") as f:
                f.write(json.dumps({
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "tool": payload.get("tool_name"),
                    "cmd_preview": command[:200],
                }) + "\n")
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
