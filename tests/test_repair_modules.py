"""Per-module tests: every module's planned transformation actually repairs data.

Each test applies the module's generated SELECT-list expression against the real
fixture engine and asserts the resulting *_Clean column is correct — proving the
detector, plan, and SQL are consistent.
"""
from __future__ import annotations

import pytest

from atlas.connectors.base import TableRef
from atlas.quality.impact import impact_summary
from atlas.quality.modules.base import REGISTRY


def _plan(con, module_id, table="dirty"):
    t = TableRef(table)
    schema = con.get_schema(t)
    mod = REGISTRY[module_id]
    issues = mod.detect(con, t, schema)
    assert issues, f"{module_id} detected nothing"
    return mod.plan(con, t, schema, issues[0]), issues[0]


def _apply(con, repair, table="dirty"):
    """Run SELECT <expr> and return the clean column's values."""
    rows = con.run(f"SELECT {repair.sql_expression} FROM {table}").rows
    return [r[repair.clean_column] for r in rows]


def test_region_repair_recovers_all_nulls(dirty):
    repair, _ = _plan(dirty, "region_repair")
    vals = _apply(dirty, repair)
    assert None not in vals                       # every row now labelled
    assert vals[2] == "AMER" and vals[3] == "AMER"  # USA, Canada rows recovered
    assert repair.confidence == 1.0


def test_date_repair_produces_date(dirty):
    repair, _ = _plan(dirty, "date_repair")
    import datetime
    vals = _apply(dirty, repair)
    assert all(isinstance(v, datetime.date) for v in vals)


def test_quarter_repair_derives_calendar_quarter(dirty):
    repair, _ = _plan(dirty, "quarter_repair")
    vals = _apply(dirty, repair)
    # row index 8 is 2024-09-14 -> calendar Q3 (stored fiscal Q4)
    assert vals[8] == "Q3"
    assert repair.confidence == 0.70              # ambiguous -> approval required


def test_country_standardisation_canonicalises(dirty):
    repair, _ = _plan(dirty, "country_standardisation")
    vals = _apply(dirty, repair)
    assert vals[4] == "UK" and vals[6] == "USA"   # 'uk','usa' -> canonical


def test_boolean_repair_casts_to_bool(dirty):
    repair, _ = _plan(dirty, "boolean_repair")
    vals = _apply(dirty, repair)
    assert vals[0] is True and vals[1] is False    # yes/no
    assert vals[2] is True and vals[3] is False    # Y/N


def test_whitespace_repair_trims(dirty):
    repair, _ = _plan(dirty, "whitespace_repair")
    vals = _apply(dirty, repair)
    assert "Gold " not in vals and "Gold" in vals


def test_case_standardisation_uppercases(dirty):
    t = TableRef("dirty")
    mod = REGISTRY["case_standardisation"]
    issues = [i for i in mod.detect(dirty, t, dirty.get_schema(t)) if i.column == "category"]
    repair = mod.plan(dirty, t, dirty.get_schema(t), issues[0])
    vals = _apply(dirty, repair)
    assert set(vals) == {"GOLD", "SILVER", "BRONZE"}


def test_duplicate_detection_is_row_level(dirty):
    repair, issue = _plan(dirty, "duplicate_detection")
    assert repair.row_level and repair.sql_expression is None
    assert issue.detail["duplicate_rows"] == 1


def test_null_classification_is_annotation_only(dirty):
    repair, issue = _plan(dirty, "null_classification")
    assert repair.clean_column is None and repair.sql_expression is None
    assert issue.structural is True


def test_numeric_type_repair_on_varchar_numeric(dirty):
    """White-box: force a VARCHAR-numeric column (Excel/CSV auto-types numbers)."""
    dirty._con.execute(
        "CREATE VIEW numtxt AS SELECT CAST(id AS VARCHAR) AS amount FROM dirty")
    t = TableRef("numtxt")
    mod = REGISTRY["numeric_type_repair"]
    issues = mod.detect(dirty, t, dirty.get_schema(t))
    assert issues and issues[0].column == "amount"
    repair = mod.plan(dirty, t, dirty.get_schema(t), issues[0])
    vals = [r[repair.clean_column] for r in
            dirty.run(f"SELECT {repair.sql_expression} FROM numtxt").rows]
    assert all(isinstance(v, float) for v in vals)


def test_month_repair_fires_on_wrong_month(dirty):
    """White-box: a month label that disagrees with the date must be caught."""
    dirty._con.execute(
        "CREATE VIEW badmonth AS SELECT order_date, 'Jan' AS month FROM dirty")
    t = TableRef("badmonth")
    mod = REGISTRY["month_repair"]
    issues = mod.detect(dirty, t, dirty.get_schema(t))
    assert issues, "month_repair should fire when month != date"
    assert issues[0].detail["mismatch"] >= 1


def test_business_impact_summary_is_populated(dirty):
    issues = REGISTRY["region_repair"].detect(
        dirty, TableRef("dirty"), dirty.get_schema(TableRef("dirty")))
    summary = impact_summary(dirty, TableRef("dirty"), issues)
    assert summary and summary[0]["business_risk"]
    assert "North America" in summary[0]["business_risk"]
