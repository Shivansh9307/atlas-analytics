"""SQL + pandas repair-engine tests: DDL generation and pandas parity."""
from __future__ import annotations

from atlas.connectors.base import TableRef
from atlas.quality import clean_layer as cl
from atlas.quality import sql_engine
from atlas.quality.pandas_engine import build_pandas_script


def _plan(dirty):
    return cl.build_plan(dirty, TableRef("dirty"), source="dirty_src")


def test_clean_select_lists_star_plus_clean_columns(dirty):
    plan = _plan(dirty)
    sql = plan.select_sql()
    assert sql.startswith("SELECT DISTINCT *")   # dedup + derived columns
    for t in plan.column_transforms:
        assert t.clean_column in sql


def test_ddl_emitted_for_every_dialect(dirty):
    plan = _plan(dirty)
    ddl = sql_engine.emit_all_dialects(plan.clean_table, plan.base_table,
                                       plan.column_transforms, dedup=plan.dedup)
    assert set(ddl) == set(sql_engine.DIALECTS)
    assert ddl["duckdb"].startswith("CREATE OR REPLACE VIEW")
    assert ddl["snowflake"].startswith("CREATE VIEW")
    for sql in ddl.values():
        assert "dirty_clean" in sql


def test_dedup_only_when_duplicates_present(dirty, finance):
    # dirty has a duplicate row -> DISTINCT
    assert "DISTINCT" in _plan(dirty).select_sql()
    # emea fixture is clean -> no transforms, no DISTINCT
    fplan = cl.build_plan(finance, TableRef("finance"), source="emea_finance_csv")
    assert fplan.transforms == []


def test_pandas_script_is_runnable_text(dirty):
    plan = _plan(dirty)
    script = build_pandas_script("data/x.xlsx", plan.base_table, plan.clean_table,
                                 plan.column_transforms, dedup=plan.dedup)
    assert "import pandas as pd" in script
    assert "drop_duplicates()" in script          # dedup present
    assert "COUNTRY_TO_REGION" in script           # config-driven mapping referenced
