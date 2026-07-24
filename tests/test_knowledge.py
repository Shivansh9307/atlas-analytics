from atlas.knowledge import (
    clear_cache, decision_owner_for, load_glossary, metric_dictionary,
    metric_owner, resolve_term,
)


def setup_function():
    clear_cache()


def test_resolve_term_by_name_and_alias():
    assert resolve_term("EMEA").category == "region"
    assert resolve_term("gm").metric == "gross_margin"          # alias -> term
    assert resolve_term("gross margin").metric == "gross_margin"
    assert resolve_term("nonexistent-term") is None


def test_glossary_definitions_are_flattened():
    t = resolve_term("mix shift")
    assert "blend" in t.definition.lower()
    assert "\n" not in t.definition


def test_metric_dictionary_merges_formula_and_context():
    d = {m["metric"]: m for m in metric_dictionary()}
    gm = d["gross_margin"]
    assert gm["expression"] == "(sum(revenue) - sum(cogs)) / sum(revenue)"
    assert gm["owner_team"] == "Finance"
    assert gm["decision_owner"] == "VP Finance, EMEA"
    assert gm["decomposition"] == "mix_rate_interaction"
    assert gm["definition"]                                     # pulled from glossary


def test_metric_ownership():
    assert metric_owner("gross_margin") == "Finance"
    assert decision_owner_for("gross_margin") == "VP Finance, EMEA"
    assert metric_owner("unknown_metric") is None
