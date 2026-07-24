"""Clean-layer tests: preview / apply / undo / history + raw-is-sacred guarantees."""
from __future__ import annotations

import datetime

import pytest

from atlas.connectors.base import TableRef
from atlas.quality import clean_layer as cl


@pytest.fixture
def isolate_manifest(tmp_path, monkeypatch):
    """Redirect the manifest AND repair-memory to a temp dir (no repo pollution)."""
    from atlas.quality import repair_memory
    monkeypatch.setattr(cl, "manifest_path", lambda source: tmp_path / f"{source}.json")
    monkeypatch.setattr(repair_memory, "_path", lambda source: tmp_path / f"{source}.repairs.jsonl")
    return tmp_path


def test_preview_improves_score(dirty):
    pv = cl.preview(dirty, TableRef("dirty"), source="dirty_src")
    assert pv.before.overall_score == 63.1
    assert pv.after.overall_score > pv.before.overall_score
    assert pv.after.business_readiness == "Excellent"
    assert pv.score_delta() > 30


def test_low_confidence_needs_approval(dirty):
    plan = cl.build_plan(dirty, TableRef("dirty"), source="dirty_src")
    assert [t.module_id for t in plan.needs_approval] == ["quarter_repair"]  # fiscal ambiguity


def test_apply_creates_clean_view_and_recovers_region(dirty, isolate_manifest):
    r = cl.apply(dirty, TableRef("dirty"), source="dirty_src")
    assert r.clean_table == "dirty_clean"
    # quarter_repair (conf 0.70) is NOT auto-applied
    assert "quarter_repair" in [t.module_id for t in r.skipped]
    # region_Clean fully recovers the USA/Canada nulls
    remaining = dirty.run(
        'SELECT count(*) AS n FROM dirty_clean WHERE "region_Clean" IS NULL').rows[0]["n"]
    assert remaining == 0
    # order_date_Clean is a real DATE
    v = dirty.run('SELECT "order_date_Clean" AS d FROM dirty_clean LIMIT 1').rows[0]["d"]
    assert isinstance(v, datetime.date)


def test_apply_does_not_touch_raw(dirty, isolate_manifest):
    before_rows = dirty.run("SELECT count(*) AS n FROM dirty").rows[0]["n"]
    before_nulls = dirty.run("SELECT count(*) AS n FROM dirty WHERE region IS NULL").rows[0]["n"]
    cl.apply(dirty, TableRef("dirty"), source="dirty_src")
    # raw view is byte-for-byte the same
    assert dirty.run("SELECT count(*) AS n FROM dirty").rows[0]["n"] == before_rows
    assert dirty.run("SELECT count(*) AS n FROM dirty WHERE region IS NULL").rows[0]["n"] == before_nulls


def test_clean_view_has_no_duplicate_columns(dirty, isolate_manifest):
    cl.apply(dirty, TableRef("dirty"), source="dirty_src")
    cols = [c.name for c in dirty.get_schema(TableRef("dirty_clean")).columns]
    assert len(cols) == len(set(cols))


def test_approve_applies_low_confidence(dirty, isolate_manifest):
    r = cl.apply(dirty, TableRef("dirty"), source="dirty_src", approve=True)
    assert "quarter_repair" in [t.module_id for t in r.applied]
    assert r.skipped == []


def test_manifest_and_history_written(dirty, isolate_manifest):
    cl.apply(dirty, TableRef("dirty"), source="dirty_src")
    man = cl.load_manifest("dirty_src")
    assert man["clean_table"] == "dirty_clean"
    assert man["transforms"]
    hist = cl.history("dirty_src")
    assert hist and hist[-1]["action"] == "apply"


def test_undo_pops_last_transform(dirty, isolate_manifest):
    cl.apply(dirty, TableRef("dirty"), source="dirty_src")
    before = len(cl.load_manifest("dirty_src")["transforms"])
    res = cl.undo(dirty, "dirty_src")
    assert res["remaining"] == before - 1
    assert cl.history("dirty_src")[-1]["action"] == "undo"


def test_materialize_from_manifest_reapplies(dirty, isolate_manifest):
    cl.apply(dirty, TableRef("dirty"), source="dirty_src")
    dirty.drop_clean("dirty_clean")
    assert not dirty.has_table("dirty_clean")
    name = cl.materialize_from_manifest(dirty, "dirty_src")
    assert name == "dirty_clean" and dirty.has_table("dirty_clean")


def test_audit_artefacts_written(dirty, isolate_manifest, tmp_path):
    run_dir = tmp_path / "run"
    r = cl.apply(dirty, TableRef("dirty"), source="dirty_src", run_dir=run_dir)
    for rel in ("repair/repair_plan.json", "repair/repair_log.json",
                "repair/transformations.sql", "repair/transformations.py",
                "repair/before_profile.md", "repair/after_profile.md",
                "repair/quality_score.json", "repair/before_after.md"):
        assert (run_dir / rel).exists(), rel
    assert r.after.overall_score > r.before.overall_score
