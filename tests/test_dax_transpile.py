"""SQL -> DAX translation, and the export registry it plugs into.

The transpiler's contract is "escalate, never approximate": a DAX measure that looks
plausible and computes something else is worse than a missing one, because nobody
re-checks a number that appears in a dashboard. Roughly half these tests assert a
refusal.
"""
import pytest

from atlas.exporters.dax import (
    DaxUnsupported, referenced_columns, transpile_expression, transpile_metric,
)
from atlas.lib.export_registry import (
    EXPORTER_REGISTRY, ExportContext, Exporter, UnknownExportFormat, all_exporters,
    get_exporter, register_exporter,
)
from atlas.semantic import resolve_metric

T = "Sales"


def dax(sql, table=T, **kw):
    return transpile_expression(sql, table, **kw)[0]


# --------------------------- aggregates ---------------------------
def test_basic_aggregates():
    assert dax("sum(revenue)") == "SUM(Sales[revenue])"
    assert dax("avg(price)") == "AVERAGE(Sales[price])"
    assert dax("min(age)") == "MIN(Sales[age])"
    assert dax("max(age)") == "MAX(Sales[age])"


def test_count_variants():
    assert dax("count(*)") == "COUNTROWS(Sales)"
    assert dax("count(id)") == "COUNTA(Sales[id])"
    assert dax("count(distinct id)") == "DISTINCTCOUNT(Sales[id])"


def test_division_always_uses_DIVIDE_never_a_bare_slash():
    """Not stylistic: DAX errors on a zero denominator, DIVIDE returns BLANK. A rate
    over an empty filter context hits that constantly."""
    out = dax("sum(a) / sum(b)")
    assert "DIVIDE(" in out
    assert "/" not in out


def test_conditional_distinct_count_idiom():
    """`customer_churn_rate`'s numerator. The naive translation (a nested IF) does not
    aggregate correctly in a filter context, so this needs its own handler."""
    out = dax("count(distinct case when status = 'Churned' then customer_id end)")
    assert out == 'CALCULATE(DISTINCTCOUNT(Sales[customer_id]), Sales[status] = "Churned")'


def test_case_becomes_switch_and_single_branch_becomes_if():
    multi = dax("case when a < 1 then 'x' when a < 2 then 'y' else 'z' end")
    assert multi.startswith("SWITCH(\n    TRUE(),")
    single = dax("case when a < 1 then 'x' else 'z' end")
    assert single.startswith("IF(")


def test_boolean_and_comparison_operators():
    out = dax("case when a > 1 and b <= 2 then 1 else 0 end")
    assert "&&" in out and ">" in out and "<=" in out


def test_cast_is_dropped_with_a_recorded_note():
    out, notes = transpile_expression("sum(cast(x as double))", T)
    assert out == "SUM(Sales[x])"
    assert any("CAST" in n for n in notes)


def test_nullif_zero_is_folded_because_DIVIDE_already_handles_it():
    out, notes = transpile_expression("sum(a) / nullif(sum(b), 0)", T)
    assert "NULLIF" not in out.upper()
    assert any("NULLIF" in n for n in notes)


# --------------------------- refusals ---------------------------
@pytest.mark.parametrize("sql,fragment", [
    ("sum(x) over (partition by y)", "window"),
    ("(select sum(x) from t)", "SELECT"),
])
def test_unsupported_constructs_raise_rather_than_guess(sql, fragment):
    with pytest.raises(DaxUnsupported):
        dax(sql)


def test_refusal_names_the_fragment_and_suggests_a_fix():
    with pytest.raises(DaxUnsupported) as e:
        dax("sum(x) over (partition by y)")
    assert e.value.fragment
    assert e.value.reason
    assert "dax_overrides.yaml" in str(e.value)


def test_unparseable_sql_is_refused_not_silently_emitted():
    with pytest.raises(DaxUnsupported):
        dax("sum(((((")


def test_missing_column_is_refused():
    """Emitting SUM(Churn[revenue]) for a table with no revenue column is valid DAX
    that silently breaks in the report — the worst possible failure mode."""
    with pytest.raises(DaxUnsupported, match="does not have"):
        transpile_expression("sum(revenue)", "Churn",
                             available_columns={"CustomerID", "Churn"})
    # present columns are fine
    transpile_expression("sum(revenue)", "Churn",
                         available_columns={"revenue", "Churn"})


def test_referenced_columns_extraction():
    assert referenced_columns("(sum(revenue) - sum(cogs)) / sum(revenue)") == {
        "revenue", "cogs"}


# --------------------------- real metrics.yaml ---------------------------
def test_every_locked_metric_compiles_against_its_own_schema():
    gm = transpile_metric("gross_margin", resolve_metric("gross_margin"), "Sales")
    assert gm.expression == ("DIVIDE(\n    (SUM(Sales[revenue]) - SUM(Sales[cogs])),"
                             "\n    SUM(Sales[revenue])\n)")
    assert gm.format_string == '"0.0%"'
    assert gm.confidence == "exact"

    churn = transpile_metric("customer_churn_rate",
                             resolve_metric("customer_churn_rate"), "Sales")
    assert "CALCULATE(DISTINCTCOUNT(Sales[customer_id])" in churn.expression
    assert 'Sales[customer_status] = "Churned"' in churn.expression
    assert churn.expression.startswith("DIVIDE(")


def test_measure_records_the_sql_it_came_from():
    m = transpile_metric("revenue", resolve_metric("revenue"), "Sales")
    assert m.source_metric == "revenue"
    assert "sum(revenue)" in " ".join(str(m.source_sql).split())
    assert "Compiled from metrics.yaml" in m.description


def test_override_wins_and_is_labelled_as_hand_written(monkeypatch):
    monkeypatch.setattr("atlas.exporters.dax.load_overrides",
                        lambda: {"revenue": "SUM(Other[amount])"})
    m = transpile_metric("revenue", resolve_metric("revenue"), "Sales")
    assert m.expression == "SUM(Other[amount])"
    assert m.confidence == "override"
    assert "could not compile" in m.description


# --------------------------- stakeholder measures ---------------------------
def test_stakeholder_measures_are_built_from_bound_columns():
    from atlas.exporters.dax_measures import stakeholder_measures
    ms = {m.name: m.expression for m in stakeholder_measures(
        "Churn", target="Churn", entity="CustomerID",
        numeric=["Payment Delay"], value_column="Total Spend")}
    assert ms["Total Customers"] == "DISTINCTCOUNT(Churn[CustomerID])"
    assert ms["Churn Rate"] == "DIVIDE([Churned Customers], [Total Customers])"
    assert "Avg Payment Delay (Churned)" in ms
    assert "Avg Payment Delay (Retained)" in ms
    assert 'RiskScores[risk_tier] = "High"' in ms["High Risk Customer Count"]
    assert "SUM(Churn[Total Spend])" in ms["Revenue at Risk"]


def test_revenue_at_risk_declares_the_proxy_assumption():
    """churn.csv has no ARR column, so using Total Spend is a substitution — the kind
    the constitution forbids making silently."""
    from atlas.exporters.dax_measures import stakeholder_measures
    m = next(m for m in stakeholder_measures(
        "Churn", target="Churn", entity="CustomerID", value_column="Total Spend")
        if m.name == "Revenue at Risk")
    assert "ASSUMPTION" in m.description
    assert "revenue proxy" in m.description


def test_no_revenue_at_risk_measure_when_nothing_spend_like_was_bound():
    from atlas.exporters.dax_measures import stakeholder_measures
    names = {m.name for m in stakeholder_measures(
        "T", target="y", entity="id", value_column=None)}
    assert "Revenue at Risk" not in names       # never invented


def test_tier_mismatch_self_check_is_emitted():
    from atlas.exporters.dax_measures import stakeholder_measures
    m = next(m for m in stakeholder_measures("T", target="y", entity="id")
             if m.name == "Tier Mismatch Count")
    assert "Must read 0" in m.description


# --------------------------- registry ---------------------------
def test_builtin_exporters_are_registered():
    import atlas.exporters  # noqa: F401
    ids = {e.id for e in all_exporters()}
    assert {"html", "pdf", "slack", "email", "exec", "dax"} <= ids


def test_unknown_format_raises_instead_of_silently_doing_nothing():
    """The old if/elif ladder ignored unrecognised formats and reported success."""
    import atlas.exporters  # noqa: F401
    with pytest.raises(UnknownExportFormat, match="unknown export format"):
        get_exporter("does_not_exist")


def test_export_run_rejects_an_unknown_format(tmp_path):
    from atlas.lib.exporters import export_run
    from atlas.orchestrator import run_analysis
    res = run_analysis("Why did EMEA gross margin drop 4pts in Q2?", runs_root=tmp_path)
    with pytest.raises(UnknownExportFormat):
        export_run(res.run_id, formats=["html", "nope"], runs_root=tmp_path)


def test_duplicate_exporter_id_is_refused():
    class _Dup(Exporter):
        id = "html"
        def emit(self, ctx):
            return []
    with pytest.raises(ValueError, match="duplicate exporter id"):
        register_exporter(_Dup)


def test_exporter_reports_missing_context_rather_than_crashing():
    import atlas.exporters  # noqa: F401
    ctx = ExportContext(run_id="r", run_dir=__import__("pathlib").Path("/tmp"))
    ok, why = get_exporter("html").available(ctx)
    assert not ok and "needs" in why
