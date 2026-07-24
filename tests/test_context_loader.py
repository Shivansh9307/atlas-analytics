from atlas.knowledge import clear_cache
from atlas.lib.context_loader import load_context


def setup_function():
    clear_cache()


def test_context_includes_schema_when_connector_given(finance):
    ctx = load_context("emea_finance_csv", connector=finance)
    names = {c["name"] for c in ctx.schema}
    assert {"region", "quarter", "revenue", "cogs"} <= names


def test_context_render_has_key_sections(finance):
    md = load_context("emea_finance_csv", connector=finance).render()
    assert "Active context" in md
    assert "Metric dictionary" in md
    assert "gross_margin" in md
    assert "Glossary" in md
    assert "Source quirks" in md            # fixture has a quirks file


def test_context_without_connector_still_loads_knowledge():
    ctx = load_context("emea_finance_csv")
    assert ctx.schema == []                 # no connector -> no schema
    assert any(m["metric"] == "gross_margin" for m in ctx.metrics)
