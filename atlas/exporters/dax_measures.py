"""`DAX_MEASURES.md` — the locked metric definitions compiled into Power BI measures.

Emitted on its own so the DAX compiler is usable and reviewable before the full
Power BI project exists. Each measure records which metric it came from, the exact
SQL it was compiled from, and whether it was compiled or hand-written — so a reviewer
can check the translation rather than trust it.
"""
from __future__ import annotations

from atlas.exporters.dax import DaxMeasure, DaxUnsupported, transpile_metric
from atlas.lib.export_registry import ExportContext, Exporter, register_exporter
from atlas.lib.risk_tiers import load_policy
from atlas.semantic import known_metrics, resolve_metric

__all__ = ["DaxMeasuresExporter", "build_measures"]


def build_measures(table: str, metrics: list[str] | None = None,
                   available_columns: set[str] | None = None):
    """Compile the named metrics (default: all locked ones).

    Returns `(measures, failures)`. A metric that references a column this table does
    not have lands in `failures` rather than being emitted — the metric dictionary is
    global, but any one export is bound to one table, and most locked metrics will not
    apply to it.
    """
    names = metrics if metrics is not None else list(known_metrics())
    out, failures = [], []
    for name in names:
        try:
            out.append(transpile_metric(name, resolve_metric(name), table,
                                        available_columns=available_columns))
        except DaxUnsupported as e:
            failures.append((name, e))
        except Exception as e:                       # a malformed metrics.yaml entry
            failures.append((name, e))
    return out, failures


def stakeholder_measures(table: str, *, target: str, entity: str,
                         numeric: list[str] | None = None,
                         value_column: str | None = None,
                         tier_table: str = "RiskScores") -> list[DaxMeasure]:
    """The measures a stakeholder dashboard needs, built from the BOUND columns.

    `metrics.yaml` holds definitions locked against the sources they were written
    for; most will not apply to whatever table this run bound. These are generated
    from the columns actually present, so a churn dataset gets a churn rate on its
    real target column rather than nothing at all.

    Derived from the same binding the analysis used, so the dashboard counts the same
    population the deck does.
    """
    ent, tgt = f"{table}[{entity}]", f"{table}[{target}]"
    out = [
        DaxMeasure(name="Total Customers", expression=f"DISTINCTCOUNT({ent})",
                   format_string='"#,0"', source_metric="(binding)",
                   description=f"Distinct {entity} in {table}."),
        DaxMeasure(name="Churned Customers",
                   expression=f"CALCULATE([Total Customers], {tgt} = 1)",
                   format_string='"#,0"', source_metric="(binding)",
                   description=f"Entities where {target} = 1."),
        DaxMeasure(name="Churn Rate",
                   expression="DIVIDE([Churned Customers], [Total Customers])",
                   format_string='"0.0%"', source_metric="(binding)",
                   description="DIVIDE, not '/', so an empty filter context returns "
                               "BLANK rather than an error."),
    ]
    for col in (numeric or [])[:4]:
        safe = col.replace("[", "").replace("]", "")
        out.append(DaxMeasure(
            name=f"Avg {safe} (Churned)",
            expression=f"CALCULATE(AVERAGE({table}[{col}]), {tgt} = 1)",
            format_string='"0.0"', source_metric="(binding)"))
        out.append(DaxMeasure(
            name=f"Avg {safe} (Retained)",
            expression=f"CALCULATE(AVERAGE({table}[{col}]), {tgt} = 0)",
            format_string='"0.0"', source_metric="(binding)"))

    policy = load_policy()
    high = policy.band_names()[-1]
    out.append(DaxMeasure(
        name="High Risk Customer Count",
        expression=(f"CALCULATE([Total Customers], "
                    f"{tier_table}[risk_tier] = \"{high}\")"),
        format_string='"#,0"', source_metric="(risk_tiers.yaml)",
        description=f"Tier policy digest {policy.digest()}."))
    if value_column:
        out.append(DaxMeasure(
            name="Revenue at Risk",
            expression=(f"CALCULATE(SUM({table}[{value_column}]), "
                        f"{tier_table}[risk_tier] = \"{high}\")"),
            format_string='"\\$#,0"', source_metric="(binding)",
            description=(f"ASSUMPTION: '{value_column}' is used as the revenue proxy "
                         f"— this dataset has no ARR/MRR column. Declared here, in "
                         f"the deck's assumptions appendix, and in the model.")))
    out.append(DaxMeasure(
        name="Risk Tier Recomputed",
        expression=policy.dax_switch(f"{tier_table}[churn_probability]"),
        source_metric="(risk_tiers.yaml)",
        description="Recomputes the tier from the same locked policy the CSV used."))
    out.append(DaxMeasure(
        name="Tier Mismatch Count",
        expression=(f"COUNTROWS(FILTER({tier_table}, "
                    f"{tier_table}[risk_tier] <> [Risk Tier Recomputed]))"),
        format_string='"#,0"', source_metric="(self-check)",
        description=("Must read 0. If it does not, the exported scores and the "
                     "dashboard disagree about who is High risk.")))
    return out


def _stakeholder_for(ctx: ExportContext, table: str) -> list[DaxMeasure]:
    """Build the bound-column measures, when this run has a target and an entity."""
    from atlas.playbooks.binding import ColumnRole
    b = getattr(ctx, "binding", None)
    if b is None:
        return []
    target = b.one(ColumnRole.TARGET)
    entity = b.one(ColumnRole.ENTITY)
    if not target or not entity:
        return []
    plan = getattr(ctx.result, "feature_plan", None)
    numeric = list(getattr(plan, "numeric", []) or [])
    # A "revenue at risk" proxy only if a spend-like column was bound; never invented.
    value_col = next((c for c in numeric
                      if any(k in c.lower() for k in ("spend", "revenue", "value",
                                                      "amount", "arr", "mrr"))), None)
    return stakeholder_measures(table, target=target, entity=entity,
                                numeric=numeric, value_column=value_col)


def _columns(ctx: ExportContext, table: str) -> set[str] | None:
    """Columns of the bound table, when a live connector is available.

    Returns None (skip the check) rather than an empty set when there is no
    connector — an empty set would refuse every metric and look like a compiler bug.
    """
    con = getattr(ctx, "con", None)
    if con is None:
        return None
    try:
        from atlas.connectors.base import TableRef
        return {c.name for c in con.get_schema(TableRef(table)).columns}
    except Exception:
        return None


@register_exporter
class DaxMeasuresExporter(Exporter):
    id = "dax"
    description = "Compile metrics.yaml into Power BI DAX measures (markdown)."

    def emit(self, ctx: ExportContext) -> list[str]:
        table = (ctx.options.get("dax_table")
                 or getattr(ctx.binding, "table", None)
                 or "Data")
        table = str(table).split(".")[-1]
        measures, failures = build_measures(table, available_columns=_columns(ctx, table))
        measures += _stakeholder_for(ctx, table)

        lines = [
            "# DAX measures", "",
            f"Compiled against table `{table}`.", "",
            "Measures come from two places: locked definitions in "
            "`atlas/semantic/metrics.yaml`, compiled by the SQL->DAX transpiler so the "
            "dashboard and the deck cannot drift apart; and stakeholder measures "
            "generated from the columns this run actually bound. Ratios use `DIVIDE()` "
            "rather than `/` because DAX errors on a zero denominator while `DIVIDE` "
            "returns BLANK.", "",
            "| measure | source metric | origin |", "|---|---|---|",
        ]
        for m in measures:
            lines.append(f"| {m.name} | `{m.source_metric}` | {m.confidence} |")
        lines.append("")

        for m in measures:
            lines += [f"## {m.name}", ""]
            if m.confidence == "override":
                lines += ["> **Hand-written override.** The transpiler could not "
                          "compile this metric's SQL, so the formula below was "
                          "authored by hand and has not been machine-verified against "
                          "the SQL definition.", ""]
            lines += ["```dax", f"{m.name} =", m.expression, "```", ""]
            if m.format_string:
                lines.append(f"*Format string:* `{m.format_string}`")
            lines += [f"*Compiled from:* `{' '.join(str(m.source_sql).split())}`", ""]
            if m.description:
                lines += [f"> {ln}" for ln in m.description.splitlines() if ln]
                lines.append("")

        if failures:
            lines += ["## Not translated", "",
                      "These metrics were **refused rather than approximated**. A DAX "
                      "measure that looks plausible and computes something else is "
                      "worse than a missing one.", ""]
            for name, err in failures:
                lines += [f"- **{name}** — {err}"]
            lines += ["", "Supply a hand-written measure in "
                      "`atlas/exporters/dax_overrides.yaml` to resolve these.", ""]

        ctx.write("DAX_MEASURES.md", "\n".join(lines))
        return ["DAX_MEASURES.md"]
