"""Phase 4: semantic guardrails, repair memory, schema drift, catalog, lineage."""
from __future__ import annotations

import pytest

from atlas.connectors.base import TableRef
from atlas.quality import catalog, clean_layer as cl, drift, guardrails, lineage, repair_memory


@pytest.fixture
def isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(cl, "manifest_path", lambda s: tmp_path / f"{s}.json")
    monkeypatch.setattr(repair_memory, "_path", lambda s: tmp_path / f"{s}.repairs.jsonl")
    monkeypatch.setattr(drift, "_snap_path", lambda s: tmp_path / "schema" / f"{s}.json")
    monkeypatch.setattr(catalog, "_catalog_dir", lambda: tmp_path / "catalog")
    return tmp_path


# ---- guardrails ----
def test_guardrails_flag_unsafe_on_raw(dirty):
    g = guardrails.column_guardrails(dirty, TableRef("dirty"))
    assert g["region"] == "Unsafe"        # HIGH defect, no clean sibling yet
    assert g["category"] == "Trusted"     # only a LOW issue


def test_guardrails_after_clean_layer(dirty, isolate):
    cl.apply(dirty, TableRef("dirty"), source="dirty_src", approve=True)
    g = guardrails.column_guardrails(dirty, TableRef("dirty_clean"))
    assert g["region"] == "Deprecated" and g["region_Clean"] == "Derived"
    assert "region" not in guardrails.safe_columns(dirty, TableRef("dirty_clean"))
    assert "region_Clean" in guardrails.safe_columns(dirty, TableRef("dirty_clean"))


def test_guardrails_blocked_list(dirty):
    g = guardrails.column_guardrails(dirty, TableRef("dirty"), blocked={"notes"})
    assert g["notes"] == "Blocked"


# ---- repair memory ----
def test_repair_memory_round_trip(dirty, isolate):
    r = cl.apply(dirty, TableRef("dirty"), source="dirty_src")
    recalled = repair_memory.recall_repairs("dirty_src")
    assert {x["module_id"] for x in recalled} == {t.module_id for t in r.applied}
    # idempotent: re-applying does not duplicate
    cl.apply(dirty, TableRef("dirty"), source="dirty_src")
    assert len(repair_memory.recall_repairs("dirty_src")) == len(recalled)


# ---- schema drift ----
def test_drift_detects_rename(dirty, isolate):
    drift.snapshot_schema(dirty, TableRef("dirty"), "dsrc")
    # a realistic single rename: region -> geo, all other columns preserved
    dirty._con.execute(
        'CREATE VIEW dirty2 AS SELECT id, order_date, region AS geo, country, '
        'active, category, month, quarter, notes FROM dirty')
    d = drift.detect_drift(dirty, TableRef("dirty2"), "dsrc")
    assert "region" in d.removed and "geo" in d.added
    assert {"from": "region", "to": "geo", "dtype": d.added["geo"]} in d.renamed_suggestions


def test_drift_first_snapshot_is_none(dirty, isolate):
    assert drift.detect_drift(dirty, TableRef("dirty"), "fresh", update=True) is None


# ---- catalog ----
def test_catalog_entry_and_listing(dirty, isolate):
    e = catalog.build_entry(dirty, TableRef("dirty"), "dirty_src",
                            owner="Data Eng", tags=["sales"])
    assert e["owner"] == "Data Eng" and e["quality_score"] == 63.1
    assert e["certification"] == "Uncertified"      # score < 75
    listing = catalog.list_catalog()
    assert any(x["source"] == "dirty_src" for x in listing)


def test_catalog_certifies_clean_source(finance, isolate):
    e = catalog.build_entry(finance, TableRef("finance"), "emea_finance_csv")
    assert e["quality_score"] == 100.0 and e["certification"].startswith("Certified")


# ---- lineage ----
def test_lineage_traces_layers(dirty, isolate):
    cl.apply(dirty, TableRef("dirty"), source="dirty_src", approve=True)
    lin = lineage.build_lineage("dirty_src", base_table="dirty",
                                provenance=[{"claim_id": "c1", "query_hash": "h1",
                                             "slide_number": 2}])
    stages = {s["stage"] for s in lin["stages"]}
    assert {"source", "transformation", "semantic_layer", "sql", "deliverable"} <= stages
    assert "# Lineage — dirty_src" in lineage.render_lineage(lin)
