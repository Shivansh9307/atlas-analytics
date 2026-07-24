"""Standard data-profiling battery + GO/NO-GO verdict logic.

Runs entirely through connector.run() so every profiling query is itself
provenance-stamped. Produces a ProfileReport the source-profiler agent renders
into a one-page verdict.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from atlas.connectors.base import Connector, ProfileReport, TableRef


@dataclass
class Verdict:
    decision: str            # "GO" | "GO-WITH-CAVEATS" | "NO-GO"
    reasons: list[str] = field(default_factory=list)

    def line(self) -> str:
        return f"{self.decision}: " + ("; ".join(self.reasons) if self.reasons else "clean")


def profile_table(con: Connector, table: TableRef, sample: int | None = None) -> ProfileReport:
    tname = table.qualified()
    schema = con.get_schema(table)
    col_names = [c.name for c in schema.columns]

    row_count = con.run(f"SELECT count(*) AS n FROM {tname}").scalar() or 0

    columns_stats = []
    warnings: list[str] = []
    for col in schema.columns:
        q = (
            f"SELECT count(*) AS n, count({_q(col.name)}) AS non_null, "
            f"count(DISTINCT {_q(col.name)}) AS distinct_ct FROM {tname}"
        )
        r = con.run(q).rows[0]
        n = r["n"] or 0
        non_null = r["non_null"] or 0
        distinct = r["distinct_ct"] or 0
        null_rate = (n - non_null) / n if n else 0.0
        cardinality = distinct / non_null if non_null else 0.0
        stat = {
            "column": col.name,
            "dtype": col.dtype,
            "null_rate": round(null_rate, 4),
            "distinct": distinct,
            "cardinality_ratio": round(cardinality, 4),
        }
        columns_stats.append(stat)
        if null_rate > 0.5:
            warnings.append(f"{col.name}: {null_rate:.0%} null")

    # duplicate-key / grain probe: is the full row set unique on all columns?
    distinct_rows = con.run(
        f"SELECT count(*) AS n FROM (SELECT DISTINCT * FROM {tname})"
    ).scalar() or 0
    dup_candidates: list[list[str]] = []
    grain: list[str] | None = None
    if distinct_rows < row_count:
        warnings.append(
            f"{row_count - distinct_rows} fully-duplicate row(s) — grain not unique on all cols"
        )
    else:
        grain = col_names  # unique at all-columns grain (coarse but honest)

    freshness = _freshness(con, tname, schema)

    return ProfileReport(
        table=table,
        row_count=row_count,
        columns=columns_stats,
        duplicate_key_candidates=dup_candidates,
        grain=grain,
        freshness=freshness,
        warnings=warnings,
    )


def _freshness(con: Connector, tname: str, schema) -> str | None:
    """Max date in the table's best date column, as an ISO string, or None.

    Handles a real DATE/TIMESTAMP column or a text column that TRY_CASTs to DATE
    (the Sales `Order_Date`-as-VARCHAR case). Self-contained so profiling stays
    decoupled from the quality package. Data-derived, hence deterministic.
    """
    real, textual = [], []
    for c in schema.columns:
        u = c.dtype.upper()
        if u.startswith(("DATE", "TIMESTAMP")):
            real.append(c.name)
        elif u.startswith(("VARCHAR", "CHAR", "TEXT", "STRING")):
            textual.append(c.name)

    def _pick(names):
        return sorted(names, key=lambda n: (0 if "date" in n.lower() else 1, n))[0] if names else None

    col = _pick(real)
    if col:
        expr = _q(col)
    else:
        col = _pick(textual)
        if not col:
            return None
        # only accept a text column that overwhelmingly parses as a date
        r = con.run(
            f"SELECT count({_q(col)}) AS nn, count(TRY_CAST({_q(col)} AS DATE)) AS ok FROM {tname}"
        ).rows[0]
        nn = r["nn"] or 0
        if nn == 0 or (r["ok"] or 0) / nn < 0.99:
            return None
        expr = f"TRY_CAST({_q(col)} AS DATE)"
    mx = con.run(f"SELECT CAST(max({expr}) AS VARCHAR) AS mx FROM {tname}").rows[0]["mx"]
    return f"{mx} (max {col})" if mx else None


def verdict_for(report: ProfileReport) -> Verdict:
    """Turn a ProfileReport into a GO / GO-WITH-CAVEATS / NO-GO decision."""
    reasons: list[str] = []
    decision = "GO"
    if report.row_count == 0:
        return Verdict("NO-GO", ["table is empty"])
    high_null = [c["column"] for c in report.columns if c["null_rate"] > 0.5]
    if high_null:
        decision = "GO-WITH-CAVEATS"
        reasons.append(f"high null columns: {high_null}")
    if any("duplicate" in w for w in report.warnings):
        decision = "GO-WITH-CAVEATS"
        reasons.append("duplicate rows present; confirm grain before aggregating")
    # a totally-null key metric column would be NO-GO; caller passes metric cols
    return Verdict(decision, reasons)


def verdict_from_score(report) -> Verdict:
    """Map a quality.score.QualityReport onto the GO / GO-WITH-CAVEATS / NO-GO band.

    Thresholds are config-driven (rules/repair_rules.yaml::readiness). Kept
    separate from verdict_for() so the existing ProfileReport path is unchanged.
    """
    from atlas.quality.rules_loader import readiness_thresholds
    t = readiness_thresholds()
    reasons: list[str] = []
    if report.row_count == 0:
        return Verdict("NO-GO", ["table is empty"])
    if report.critical_count > t["max_critical_issues"] or report.overall_score < t["min_overall_score"]:
        crit = [f"{i.severity} {i.module_id}:{i.column}" for i in report.issues
                if i.severity == "HIGH" and not i.structural]
        return Verdict("NO-GO",
                       [f"quality score {report.overall_score:.0f} below "
                        f"{t['min_overall_score']:.0f} or unresolved critical issues: {crit}"])
    if report.overall_score < t["caveats_below"]:
        reasons.append(f"quality score {report.overall_score:.0f} "
                       f"({report.warning_count} warning(s)); clean layer recommended")
        return Verdict("GO-WITH-CAVEATS", reasons)
    return Verdict("GO", [])


def _q(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'
