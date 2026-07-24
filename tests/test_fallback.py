"""Connection fallback chain: primary -> local DuckDB/CSV, active source reported."""
from pathlib import Path

import pytest

from atlas.connectors.registry import Registry

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "emea_margin.csv"


def _yaml(body: str, tmp_path) -> Path:
    p = tmp_path / "sources.yaml"
    p.write_text(body)
    return p


def test_primary_file_source_resolves_directly(tmp_path):
    y = _yaml(f"""
sources:
  main_csv:
    dialect: duckdb
    kind: file
    path: {FIXTURE}
    table_name: finance
""", tmp_path)
    res = Registry(y).resolve("main_csv")
    assert res.active == "main_csv"
    assert not res.used_fallback
    assert res.connector.run("SELECT count(*) AS n FROM finance").scalar() == 16
    res.connector.close()


def test_dormant_warehouse_falls_back_to_csv(tmp_path):
    # postgres with no creds -> dormant; fallback CSV should answer, reported as active
    y = _yaml(f"""
sources:
  prod_pg:
    dialect: postgres
    kind: warehouse
    host_env: NONEXISTENT_PG_HOST
    user_env: NONEXISTENT_PG_USER
    fallback:
      csv_path: {FIXTURE}
      table_name: finance
""", tmp_path)
    res = Registry(y).resolve("prod_pg")
    assert res.used_fallback
    assert res.active == "prod_pg:fallback"
    assert res.chain == ["prod_pg", "prod_pg:fallback"]
    assert res.connector.run("SELECT count(*) AS n FROM finance").scalar() == 16
    res.connector.close()


def test_no_fallback_raises_clearly(tmp_path):
    y = _yaml("""
sources:
  prod_pg:
    dialect: postgres
    kind: warehouse
    host_env: NONEXISTENT_PG_HOST
    user_env: NONEXISTENT_PG_USER
""", tmp_path)
    with pytest.raises(RuntimeError) as e:
        Registry(y).resolve("prod_pg")
    assert "fallback" in str(e.value).lower()
