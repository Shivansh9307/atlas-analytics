import pytest

from atlas.connectors.base import TableRef
from atlas.lib.sqlguard import UnsafeSQLError


def test_connection_ok(finance):
    check = finance.test_connection()
    assert check.ok
    assert "finance" in check.detail


def test_query_returns_hashed_result(finance):
    res = finance.run("SELECT count(*) AS n FROM finance")
    assert res.scalar() == 16
    assert res.query_hash and res.result_hash
    assert res.dialect == "duckdb"


def test_result_persisted_and_verifies(finance):
    res = finance.run(
        "SELECT region, sum(revenue) AS rev FROM finance GROUP BY region ORDER BY region"
    )
    # stored files exist and re-hash matches
    assert finance.store.verify(res.query_hash)
    meta = finance.store.load_query(res.query_hash)
    assert meta["result_hash"] == res.result_hash


def test_known_emea_margin_drop(finance):
    # The headline the whole pipeline exists to explain.
    sql = """
        SELECT quarter,
               sum(revenue) AS rev,
               sum(cogs)    AS cogs,
               (sum(revenue) - sum(cogs)) / sum(revenue) * 100 AS gm_pct
        FROM finance WHERE region = 'EMEA'
        GROUP BY quarter ORDER BY quarter
    """
    res = finance.run(sql)
    by_q = {r["quarter"]: r["gm_pct"] for r in res.rows}
    assert round(by_q["Q1"], 2) == 60.00
    assert round(by_q["Q2"], 2) == 56.00
    assert round(by_q["Q1"] - by_q["Q2"], 2) == 4.00


def test_schema_introspection(finance):
    schema = finance.get_schema(TableRef("finance"))
    names = {c.name for c in schema.columns}
    assert {"region", "quarter", "product_line", "segment", "revenue", "cogs"} <= names


def test_write_is_blocked_at_connector(finance):
    with pytest.raises(UnsafeSQLError):
        finance.run("DELETE FROM finance")
    with pytest.raises(UnsafeSQLError):
        finance.run("UPDATE finance SET revenue = 0")
    with pytest.raises(UnsafeSQLError):
        finance.run("DROP VIEW finance")


def test_multiple_statements_blocked(finance):
    with pytest.raises(UnsafeSQLError):
        finance.run("SELECT 1; DROP VIEW finance")
