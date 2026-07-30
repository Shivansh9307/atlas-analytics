"""SQL -> DAX transpiler for locked metric definitions.

`metrics.yaml` holds each metric as a SQL expression. Power BI needs DAX. Rewriting
those formulas by hand in a second language is exactly the drift `metrics.yaml`
exists to prevent, so this compiles them instead: `sqlglot` (already a declared
dependency, previously unused) parses the SQL to an AST and an explicit handler table
walks it.

The design rule is **escalate, never approximate**. Any node class absent from
`_HANDLERS` raises `DaxUnsupported` naming the offending fragment. A wrong DAX
measure is worse than a missing one — it silently produces a plausible number in a
dashboard nobody re-checks, which is precisely the failure this system exists to
prevent. Where a formula genuinely cannot be expressed, `dax_overrides.yaml` takes a
hand-written measure that is then labelled as hand-authored in the output.

Two correctness details that are not stylistic:
  * division always becomes `DIVIDE(a, b)`, never `a / b` — DAX raises on divide by
    zero, while `DIVIDE` returns BLANK, and a metric like churn rate over an empty
    filter context hits that constantly.
  * `COUNT(DISTINCT CASE WHEN p THEN id END)` — the conditional-count idiom, which is
    exactly `customer_churn_rate`'s numerator — becomes
    `CALCULATE(DISTINCTCOUNT(t[id]), p)`, not a nested IF, because the naive
    translation does not aggregate correctly in a filter context.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import sqlglot
from sqlglot import exp

from atlas.config import PATHS

__all__ = ["DaxUnsupported", "DaxMeasure", "transpile_expression", "transpile_metric",
           "load_overrides"]


class DaxUnsupported(Exception):
    def __init__(self, fragment: str, reason: str, suggestion: str = ""):
        self.fragment = fragment
        self.reason = reason
        self.suggestion = suggestion
        msg = f"cannot translate `{fragment}` to DAX: {reason}"
        if suggestion:
            msg += f"\n  -> {suggestion}"
        super().__init__(msg)


@dataclass
class DaxMeasure:
    name: str
    expression: str
    format_string: str = ""
    description: str = ""
    source_metric: str = ""
    source_sql: str = ""
    confidence: str = "exact"          # exact | override

    def as_tmdl(self, indent: str = "\t") -> str:
        body = self.expression.replace("\n", "\n" + indent + indent)
        out = [f"{indent}measure '{self.name}' = {body}"]
        if self.format_string:
            out.append(f"{indent}{indent}formatString: {self.format_string}")
        if self.description:
            for line in self.description.splitlines():
                out.append(f"{indent}{indent}/// {line}")
        return "\n".join(out)


def _col(table: str, name: str) -> str:
    return f"{table}[{name}]"


class _Translator:
    def __init__(self, table: str):
        self.table = table
        self.notes: list[str] = []

    # -- entry point --
    def walk(self, node) -> str:
        for cls, fn in _HANDLERS.items():
            if isinstance(node, cls):
                return fn(self, node)
        raise DaxUnsupported(
            node.sql(dialect="duckdb"),
            f"no handler for SQL node type {type(node).__name__}",
            "add a handler in atlas/exporters/dax.py, or supply a hand-written "
            "measure in atlas/exporters/dax_overrides.yaml")

    # -- leaves --
    def column(self, node: exp.Column) -> str:
        return _col(self.table, node.name)

    def literal(self, node: exp.Literal) -> str:
        return f"\"{node.this}\"" if node.is_string else str(node.this)

    def boolean(self, node: exp.Boolean) -> str:
        return "TRUE()" if node.this else "FALSE()"

    def null(self, node) -> str:
        return "BLANK()"

    def paren(self, node: exp.Paren) -> str:
        return f"({self.walk(node.this)})"

    def alias(self, node: exp.Alias) -> str:
        return self.walk(node.this)

    def cast(self, node: exp.Cast) -> str:
        # DAX is dynamically typed; a cast is a no-op but worth recording.
        self.notes.append(f"dropped CAST to {node.to.sql()} (DAX is dynamically typed)")
        return self.walk(node.this)

    # -- aggregates --
    def sum_(self, node: exp.Sum) -> str:
        return f"SUM({self.walk(node.this)})"

    def avg(self, node: exp.Avg) -> str:
        return f"AVERAGE({self.walk(node.this)})"

    def min_(self, node: exp.Min) -> str:
        return f"MIN({self.walk(node.this)})"

    def max_(self, node: exp.Max) -> str:
        return f"MAX({self.walk(node.this)})"

    def count(self, node: exp.Count) -> str:
        inner = node.this
        distinct = isinstance(inner, exp.Distinct)
        if distinct:
            targets = inner.expressions or [inner.this]
            inner = targets[0]

        if isinstance(inner, exp.Star) or inner is None:
            return f"COUNTROWS({self.table})"

        # COUNT(DISTINCT CASE WHEN p THEN id END) -> CALCULATE(DISTINCTCOUNT(id), p)
        if isinstance(inner, exp.Case):
            col, cond = self._conditional_count_parts(inner)
            agg = "DISTINCTCOUNT" if distinct else "COUNTA"
            return f"CALCULATE({agg}({col}), {cond})"

        target = self.walk(inner)
        return f"{'DISTINCTCOUNT' if distinct else 'COUNTA'}({target})"

    def _conditional_count_parts(self, case: exp.Case) -> tuple[str, str]:
        """Pull `CASE WHEN p THEN col END` apart into (col, predicate)."""
        ifs = case.args.get("ifs") or []
        if len(ifs) != 1 or case.args.get("default") is not None:
            raise DaxUnsupported(
                case.sql(dialect="duckdb"),
                "only a single-branch CASE with no ELSE is supported inside COUNT",
                "rewrite as COUNT(DISTINCT CASE WHEN <predicate> THEN <column> END)")
        branch = ifs[0]
        return self.walk(branch.args["true"]), self.walk(branch.this)

    # -- arithmetic --
    def add(self, node: exp.Add) -> str:
        return f"{self.walk(node.this)} + {self.walk(node.expression)}"

    def sub(self, node: exp.Sub) -> str:
        return f"{self.walk(node.this)} - {self.walk(node.expression)}"

    def mul(self, node: exp.Mul) -> str:
        return f"{self.walk(node.this)} * {self.walk(node.expression)}"

    def div(self, node: exp.Div) -> str:
        # DIVIDE, always: `/` errors on a zero denominator, DIVIDE returns BLANK.
        return f"DIVIDE(\n    {self.walk(node.this)},\n    {self.walk(node.expression)}\n)"

    def neg(self, node: exp.Neg) -> str:
        return f"-{self.walk(node.this)}"

    # -- predicates --
    def eq(self, node) -> str:
        return f"{self.walk(node.this)} = {self.walk(node.expression)}"

    def neq(self, node) -> str:
        return f"{self.walk(node.this)} <> {self.walk(node.expression)}"

    def gt(self, node) -> str:
        return f"{self.walk(node.this)} > {self.walk(node.expression)}"

    def gte(self, node) -> str:
        return f"{self.walk(node.this)} >= {self.walk(node.expression)}"

    def lt(self, node) -> str:
        return f"{self.walk(node.this)} < {self.walk(node.expression)}"

    def lte(self, node) -> str:
        return f"{self.walk(node.this)} <= {self.walk(node.expression)}"

    def and_(self, node: exp.And) -> str:
        return f"({self.walk(node.this)} && {self.walk(node.expression)})"

    def or_(self, node: exp.Or) -> str:
        return f"({self.walk(node.this)} || {self.walk(node.expression)})"

    def not_(self, node: exp.Not) -> str:
        return f"NOT({self.walk(node.this)})"

    def is_(self, node: exp.Is) -> str:
        target = self.walk(node.this)
        if isinstance(node.expression, exp.Null):
            return f"ISBLANK({target})"
        return f"{target} = {self.walk(node.expression)}"

    # -- conditionals --
    def case(self, node: exp.Case) -> str:
        ifs = node.args.get("ifs") or []
        default = node.args.get("default")
        if len(ifs) == 1 and default is not None:
            return (f"IF({self.walk(ifs[0].this)}, "
                    f"{self.walk(ifs[0].args['true'])}, {self.walk(default)})")
        parts = [f"    {self.walk(b.this)}, {self.walk(b.args['true'])}" for b in ifs]
        tail = f",\n    {self.walk(default)}" if default is not None else ""
        return "SWITCH(\n    TRUE(),\n" + ",\n".join(parts) + tail + "\n)"

    def if_(self, node: exp.If) -> str:
        return (f"IF({self.walk(node.this)}, {self.walk(node.args['true'])}, "
                f"{self.walk(node.args.get('false')) if node.args.get('false') else 'BLANK()'})")

    def coalesce(self, node: exp.Coalesce) -> str:
        args = [self.walk(node.this)] + [self.walk(e) for e in node.expressions]
        return f"COALESCE({', '.join(args)})"

    def nullif(self, node: exp.Nullif) -> str:
        # NULLIF(x, 0) exists to dodge divide-by-zero; DIVIDE already handles that.
        if isinstance(node.expression, exp.Literal) and str(node.expression.this) == "0":
            self.notes.append("folded NULLIF(x, 0) away — DIVIDE() handles zero denominators")
            return self.walk(node.this)
        return (f"IF({self.walk(node.this)} = {self.walk(node.expression)}, BLANK(), "
                f"{self.walk(node.this)})")


_HANDLERS = {
    exp.Column: _Translator.column,
    exp.Literal: _Translator.literal,
    exp.Boolean: _Translator.boolean,
    exp.Null: _Translator.null,
    exp.Paren: _Translator.paren,
    exp.Alias: _Translator.alias,
    exp.Cast: _Translator.cast,
    exp.Sum: _Translator.sum_,
    exp.Avg: _Translator.avg,
    exp.Min: _Translator.min_,
    exp.Max: _Translator.max_,
    exp.Count: _Translator.count,
    exp.Add: _Translator.add,
    exp.Sub: _Translator.sub,
    exp.Mul: _Translator.mul,
    exp.Div: _Translator.div,
    exp.Neg: _Translator.neg,
    exp.EQ: _Translator.eq,
    exp.NEQ: _Translator.neq,
    exp.GT: _Translator.gt,
    exp.GTE: _Translator.gte,
    exp.LT: _Translator.lt,
    exp.LTE: _Translator.lte,
    exp.And: _Translator.and_,
    exp.Or: _Translator.or_,
    exp.Not: _Translator.not_,
    exp.Is: _Translator.is_,
    exp.Case: _Translator.case,
    exp.If: _Translator.if_,
    exp.Coalesce: _Translator.coalesce,
    exp.Nullif: _Translator.nullif,
}

# Constructs that are deliberately refused, with a specific reason each. Checked
# before the generic handler lookup so the message is useful rather than "no handler".
_REFUSED = {
    exp.Window: ("window functions have no direct DAX equivalent",
                 "express the ranking as a measure using RANKX, by hand, in "
                 "dax_overrides.yaml"),
    exp.Select: ("a full SELECT is not a measure expression",
                 "metrics.yaml should hold a scalar aggregate expression, not a query"),
    exp.Subquery: ("subqueries are not supported",
                   "flatten the metric, or hand-write it in dax_overrides.yaml"),
    exp.Join: ("joins belong in the model's relationships, not a measure",
               "model the relationship in the semantic model instead"),
    exp.Union: ("set operations are not supported", ""),
}


def _check_refused(tree) -> None:
    for cls, (reason, suggestion) in _REFUSED.items():
        found = list(tree.find_all(cls))
        if found:
            raise DaxUnsupported(found[0].sql(dialect="duckdb"), reason, suggestion)


def referenced_columns(sql_expr: str, *, dialect: str = "duckdb") -> set[str]:
    """Every column name a metric expression reads."""
    try:
        tree = sqlglot.parse_one(" ".join(str(sql_expr).split()), read=dialect)
    except Exception:
        return set()
    return {c.name for c in tree.find_all(exp.Column)} if tree is not None else set()


def transpile_expression(sql_expr: str, table: str, *, dialect: str = "duckdb",
                         available_columns: set[str] | None = None
                         ) -> tuple[str, list[str]]:
    """Translate one SQL scalar expression into DAX. Returns (dax, notes).

    When `available_columns` is supplied, a metric referencing a column the bound
    table does not have is refused. Without that check the compiler happily emits
    `SUM(Churn[revenue])` for a table with no revenue column — syntactically valid
    DAX that silently breaks in the report, which is exactly the "plausible but
    wrong" output this module exists to avoid.
    """
    cleaned = " ".join(str(sql_expr).split())
    try:
        tree = sqlglot.parse_one(cleaned, read=dialect)
    except Exception as e:
        raise DaxUnsupported(cleaned, f"SQL did not parse ({e})",
                             "check the expression in metrics.yaml") from e
    if tree is None:
        raise DaxUnsupported(cleaned, "SQL parsed to nothing", "")
    _check_refused(tree)

    if available_columns is not None:
        have = {c.lower() for c in available_columns}
        missing = sorted({c.name for c in tree.find_all(exp.Column)
                          if c.name.lower() not in have})
        if missing:
            raise DaxUnsupported(
                cleaned,
                f"references column(s) {missing} that table '{table}' does not have",
                f"this metric does not apply to '{table}'; bind it to the source that "
                f"has those columns, or remove it from this export")

    t = _Translator(table)
    return t.walk(tree), t.notes


def load_overrides() -> dict[str, str]:
    """metric name -> hand-written DAX, for formulas the transpiler refuses."""
    import yaml
    path = Path(__file__).resolve().parent / "dax_overrides.yaml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    return dict(data.get("measures") or {})


_FORMAT_BY_UNIT = {
    "ratio": '"0.0%"',
    "currency": '"\\$#,0.00"',
    "count": '"#,0"',
}


def transpile_metric(metric_name: str, mdef, table: str, *,
                     dialect: str = "duckdb",
                     available_columns: set[str] | None = None) -> DaxMeasure:
    """Compile one locked metric definition into a DAX measure.

    An override wins over the transpiler and is labelled `override`, so a
    hand-written formula is always visibly distinguishable from a compiled one.
    """
    overrides = load_overrides()
    display = metric_name.replace("_", " ").title()
    if metric_name in overrides:
        return DaxMeasure(
            name=display, expression=overrides[metric_name].strip(),
            format_string=_FORMAT_BY_UNIT.get(getattr(mdef, "unit", ""), ""),
            description=("Hand-written override from dax_overrides.yaml — the "
                         "transpiler could not compile the SQL definition."),
            source_metric=metric_name, source_sql=getattr(mdef, "expression", ""),
            confidence="override")

    dax, notes = transpile_expression(mdef.expression, table, dialect=dialect,
                                      available_columns=available_columns)
    desc = [f"Compiled from metrics.yaml: {' '.join(str(mdef.expression).split())}"]
    desc += notes
    return DaxMeasure(
        name=display, expression=dax,
        format_string=_FORMAT_BY_UNIT.get(getattr(mdef, "unit", ""), ""),
        description="\n".join(desc), source_metric=metric_name,
        source_sql=mdef.expression, confidence="exact")
