"""Tests for CsvDuckDBConnector features with no prior coverage:
derived_columns (sources.yaml-declared computed columns) and the non-UTF-8
CSV fallback (cp1252 / latin-1 re-read).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atlas.connectors.base import TableRef
from atlas.connectors.csv_duckdb import CsvDuckDBConnector
from atlas.lib.sqlguard import UnsafeSQLError

FIXTURES = Path(__file__).parent / "fixtures"
EMEA_MARGIN = FIXTURES / "emea_margin.csv"
CP1252_CSV = FIXTURES / "cp1252.csv"
LATIN1_ONLY_CSV = FIXTURES / "latin1_only.csv"


# ---------------------------------------------------------------------------
# derived_columns
# ---------------------------------------------------------------------------

@pytest.fixture
def margin_with_derived(store):
    con = CsvDuckDBConnector(
        "margin_derived",
        str(EMEA_MARGIN),
        table_name="margin",
        store=store,
        derived_columns={
            "gm_dollars": "revenue - cogs",
            "rev_x2": "revenue * 2",
        },
    )
    yield con
    con.close()


def test_derived_columns_appear_in_schema(margin_with_derived):
    schema = margin_with_derived.get_schema(TableRef("margin"))
    names = {c.name for c in schema.columns}
    assert {"region", "quarter", "revenue", "cogs", "gm_dollars", "rev_x2"} <= names


def test_derived_columns_compute_correct_known_answer(margin_with_derived):
    # EMEA Q1 known-answer from make_fixture.py: rev=1000.00, cogs=400.00, GM=60%.
    res = margin_with_derived.run(
        "SELECT sum(gm_dollars) AS gm_sum, sum(rev_x2) AS rev_x2_sum "
        "FROM margin WHERE region = 'EMEA' AND quarter = 'Q1'"
    )
    row = res.rows[0]
    assert round(row["gm_sum"], 2) == 600.00          # 1000 - 400
    assert round(row["rev_x2_sum"], 2) == 2000.00     # 1000 * 2


def test_derived_columns_recorded_as_warning(margin_with_derived):
    joined = " ".join(margin_with_derived.warnings)
    assert "derived column(s) declared in sources.yaml" in joined
    assert "gm_dollars = revenue - cogs" in joined
    assert "rev_x2 = revenue * 2" in joined


def test_no_derived_columns_means_no_warning_and_unchanged_schema(store):
    plain = CsvDuckDBConnector("margin_plain", str(EMEA_MARGIN), table_name="margin", store=store)
    try:
        assert plain.warnings == []
        names = {c.name for c in plain.get_schema(TableRef("margin")).columns}
        assert "gm_dollars" not in names
    finally:
        plain.close()


def test_derived_column_projection_is_read_only(margin_with_derived):
    # The projection is a VIEW rebuilt over the private base view, not a mutation
    # of the source — the read-only guard must still hold for it.
    with pytest.raises(UnsafeSQLError):
        margin_with_derived.run("DELETE FROM margin")


# ---------------------------------------------------------------------------
# non-UTF-8 CSV fallback
# ---------------------------------------------------------------------------

@pytest.fixture
def cp1252_con(store):
    con = CsvDuckDBConnector("cp1252_src", str(CP1252_CSV), table_name="cp1252_t", store=store)
    yield con
    con.close()


@pytest.fixture
def latin1_only_con(store):
    con = CsvDuckDBConnector("latin1_src", str(LATIN1_ONLY_CSV), table_name="latin1_t", store=store)
    yield con
    con.close()


def test_cp1252_fixture_registers_despite_non_utf8_bytes(cp1252_con):
    check = cp1252_con.test_connection()
    assert check.ok
    res = cp1252_con.run("SELECT count(*) AS n FROM cp1252_t")
    assert res.scalar() == 3


def test_cp1252_fallback_decodes_accented_and_smart_quote_text(cp1252_con):
    res = cp1252_con.run("SELECT id, name, city FROM cp1252_t ORDER BY id")
    by_id = {r["id"]: r for r in res.rows}
    assert by_id[1]["name"] == "François Müller"
    assert by_id[1]["city"] == "Zürich"
    assert by_id[2]["name"] == "O’Brien"           # curly quote decoded, not mojibake
    assert by_id[2]["city"] == "São Paulo"
    assert by_id[3]["name"] == "Jane Doe"          # unaffected ASCII row untouched


def test_cp1252_fallback_recorded_as_warning_naming_the_encoding(cp1252_con):
    joined = " ".join(cp1252_con.warnings)
    assert "not UTF-8 encoded" in joined
    assert "cp1252" in joined


def test_cp1252_fallback_result_still_carries_provenance(cp1252_con):
    res = cp1252_con.run("SELECT count(*) AS n FROM cp1252_t")
    assert res.query_hash and res.result_hash
    assert cp1252_con.store.verify(res.query_hash)


def test_latin1_only_fixture_falls_back_past_cp1252(latin1_only_con):
    # Byte 0x81 is undefined in cp1252 (raises UnicodeDecodeError on that attempt)
    # but valid in latin-1 — this exercises the second loop iteration specifically.
    check = latin1_only_con.test_connection()
    assert check.ok
    res = latin1_only_con.run("SELECT id, tag FROM latin1_t ORDER BY id")
    by_id = {r["id"]: r["tag"] for r in res.rows}
    assert by_id[1] == "x\x81y"
    assert by_id[2] == "plain"


def test_latin1_only_fallback_names_latin1_not_cp1252(latin1_only_con):
    joined = " ".join(latin1_only_con.warnings)
    assert "re-read as latin-1" in joined
