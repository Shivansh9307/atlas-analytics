"""Integration test for the /clean command lifecycle (plan -> preview -> apply ->
undo -> history), plus a sanity check that the command file is registered."""
from __future__ import annotations

from pathlib import Path

import pytest

from atlas.config import PATHS
from atlas.connectors.base import TableRef
from atlas.quality import clean_layer as cl
from atlas.quality.score import score_table


@pytest.fixture
def isolate_manifest(tmp_path, monkeypatch):
    from atlas.quality import repair_memory
    monkeypatch.setattr(cl, "manifest_path", lambda source: tmp_path / f"{source}.json")
    monkeypatch.setattr(repair_memory, "_path", lambda source: tmp_path / f"{source}.repairs.jsonl")
    return tmp_path


def test_clean_command_file_exists():
    p = PATHS.root / ".claude" / "commands" / "clean.md"
    assert p.exists()
    body = p.read_text()
    for flag in ("--preview", "--apply", "--undo", "--history"):
        assert flag in body


def test_full_lifecycle(dirty, isolate_manifest):
    t = TableRef("dirty")

    # plan
    plan = cl.build_plan(dirty, t, source="dirty_src")
    assert plan.transforms and plan.clean_table == "dirty_clean"

    # preview (no persistence)
    pv = cl.preview(dirty, t, source="dirty_src")
    assert pv.score_delta() > 0
    assert not (isolate_manifest / "dirty_src.json").exists()

    # apply (persists manifest + clean view)
    r = cl.apply(dirty, t, source="dirty_src")
    assert dirty.has_table("dirty_clean")
    assert (isolate_manifest / "dirty_src.json").exists()
    after = score_table(dirty, TableRef("dirty_clean"))
    assert after.overall_score == r.after.overall_score

    # history records the apply
    assert cl.history("dirty_src")[-1]["action"] == "apply"

    # undo rolls one back
    res = cl.undo(dirty, "dirty_src")
    assert res["remaining"] == len(r.applied) - 1
