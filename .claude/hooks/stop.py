#!/usr/bin/env python3
"""Stop hook — retrospective trigger.

Fires when the main agent finishes. If the most recent run directory has no
retro.md yet, it emits a reminder (via stdout JSON) that the retrospective-agent
should run. It never forces work; it flags the omission so full-auto runs close
the learning loop. Exit 0 always.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RUNS = ROOT / "runs"


def latest_run() -> Path | None:
    if not RUNS.exists():
        return None
    dirs = [d for d in RUNS.iterdir() if d.is_dir() and not d.name.startswith("_")]
    return max(dirs, key=lambda d: d.stat().st_mtime) if dirs else None


def main() -> int:
    run = latest_run()
    if run and not (run / "retro.md").exists() and (run / "findings.md").exists():
        # Surface a nudge; the orchestrator/agent decides whether to act.
        print(json.dumps({
            "systemMessage": (
                f"Atlas: run '{run.name}' completed without a retrospective. "
                f"Consider running /retro {run.name} to close the learning loop."
            )
        }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
