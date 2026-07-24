"""Run state persistence for tracking + resume.

`pipeline_state.json` in each run dir records which nodes completed, their
JSON-serialisable outputs, gate results, the budget snapshot, and the headline.
`/resume` reloads it and re-enters the DAG at the first incomplete node, reusing
the artefacts already on disk (no re-query of completed work).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from atlas.config import PATHS

STATE_FILE = "pipeline_state.json"


@dataclass
class RunState:
    run_id: str
    question: str
    status: str = "RUNNING"                 # RUNNING | COMPLETE | BLOCKED | FAILED
    reason: str = ""
    headline: str = ""
    nodes: dict[str, str] = field(default_factory=dict)      # name -> status
    outputs: dict[str, dict] = field(default_factory=dict)   # name -> JSON output
    gates: dict[str, str] = field(default_factory=dict)
    budget: dict = field(default_factory=dict)
    created: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # ---- lifecycle ----
    def record_node(self, name: str, status: str, output: dict | None = None) -> None:
        self.nodes[name] = status
        if output is not None:
            self.outputs[name] = output
        self.updated = datetime.now(timezone.utc).isoformat()

    def completed_outputs(self) -> dict[str, dict]:
        """Nodes that finished OK, for seeding a resumed DAG run."""
        return {n: self.outputs.get(n, {}) for n, s in self.nodes.items() if s == "OK"}

    def is_complete(self) -> bool:
        return self.status == "COMPLETE"

    # ---- persistence ----
    def path(self, runs_root: Path | None = None) -> Path:
        root = runs_root or PATHS.runs
        return root / self.run_id / STATE_FILE

    def save(self, runs_root: Path | None = None) -> Path:
        p = self.path(runs_root)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(asdict(self), indent=2))
        return p

    @classmethod
    def load(cls, run_id: str, runs_root: Path | None = None) -> "RunState":
        root = runs_root or PATHS.runs
        p = root / run_id / STATE_FILE
        if not p.exists():
            raise FileNotFoundError(f"no run state for '{run_id}' at {p}")
        return cls(**json.loads(p.read_text()))


def list_runs(runs_root: Path | None = None) -> list[dict]:
    """Summaries of all runs, newest first — backs `/runs`."""
    root = runs_root or PATHS.runs
    if not root.exists():
        return []
    out = []
    for d in root.iterdir():
        if not d.is_dir() or d.name.startswith("_") or d.name.startswith("."):
            continue
        sp = d / STATE_FILE
        if sp.exists():
            s = json.loads(sp.read_text())
            out.append({
                "run_id": s["run_id"], "status": s["status"],
                "question": s.get("question", ""), "headline": s.get("headline", ""),
                "updated": s.get("updated", ""),
                "nodes_done": sum(1 for v in s.get("nodes", {}).values() if v == "OK"),
                "nodes_total": len(s.get("nodes", {})),
            })
        else:
            out.append({"run_id": d.name, "status": "UNKNOWN", "question": "",
                        "headline": "", "updated": "", "nodes_done": 0, "nodes_total": 0})
    return sorted(out, key=lambda r: r["updated"], reverse=True)
