"""Data Quality Score — 10 dimensions, each 0-100, rolled into an overall 0-100.

Deterministic and explicitly rounded (known-answer testable). Every probe runs
through the guarded `Connector.run()`. Completeness/Uniqueness/Freshness are
measured directly from the data; the issue-driven dimensions are penalised from
the detector output so scoring and detection never disagree.

Dimensions (spec "Data Quality Score"): Completeness, Consistency, Validity,
Freshness, Uniqueness, Semantic Accuracy, Referential Integrity, Business
Readiness, Type Safety, Documentation.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from atlas.config import PATHS
from atlas.connectors.base import Connector, TableRef
from atlas.quality.detectors import critical_issues, detect_issues, superseded_columns
from atlas.quality.modules._shared import find_date_column
from atlas.quality.modules.base import Issue, col_stats

# Which module's issues penalise which score dimension. Completeness, Uniqueness
# and Freshness are measured directly, so their modules are not listed here (no
# double counting).
_ISSUE_DIM = {
    "date_repair": "type_safety",
    "numeric_type_repair": "type_safety",
    "boolean_repair": "type_safety",
    "country_standardisation": "consistency",
    "whitespace_repair": "consistency",
    "case_standardisation": "consistency",
    "month_repair": "semantic_accuracy",
    "quarter_repair": "semantic_accuracy",
    "year_repair": "semantic_accuracy",
    "region_repair": "semantic_accuracy",
}
_SEVERITY_PENALTY = {"HIGH": 40, "MED": 20, "LOW": 8, "INFO": 0}

# Overall weights (sum = 1.0).
_WEIGHTS = {
    "completeness": 0.15,
    "uniqueness": 0.10,
    "validity": 0.10,
    "freshness": 0.08,
    "consistency": 0.12,
    "semantic_accuracy": 0.12,
    "type_safety": 0.10,
    "referential_integrity": 0.05,
    "business_readiness": 0.13,
    "documentation": 0.05,
}
_ISSUE_DIMS = {"consistency", "validity", "semantic_accuracy", "type_safety"}

_BANDS = [(90, "Excellent"), (75, "Good"), (60, "Fair")]


@dataclass
class QualityReport:
    table: TableRef
    row_count: int
    dimensions: dict[str, float]              # dimension -> 0..100
    overall_score: float                      # 0..100
    business_readiness: str                   # Excellent | Good | Fair | Poor
    issues: list[Issue] = field(default_factory=list)
    freshness: str | None = None              # max date (ISO) when a date column exists
    detail: dict = field(default_factory=dict)

    @property
    def critical_count(self) -> int:
        return len(critical_issues(self.issues))

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity in ("MED", "LOW") and not i.structural)

    def as_dict(self) -> dict:
        return {
            "table": self.table.qualified(),
            "row_count": self.row_count,
            "overall_score": self.overall_score,
            "business_readiness": self.business_readiness,
            "dimensions": self.dimensions,
            "critical_issues": self.critical_count,
            "warnings": self.warning_count,
            "freshness": self.freshness,
            "issues": [i.as_dict() for i in self.issues],
        }


def _band(score: float) -> str:
    for cut, label in _BANDS:
        if score >= cut:
            return label
    return "Poor"


def _clamp(x: float) -> float:
    return max(0.0, min(100.0, x))


def score_table(con: Connector, table: TableRef,
                issues: list[Issue] | None = None) -> QualityReport:
    tname = table.qualified()
    schema = con.get_schema(table)
    row_count = con.run(f"SELECT count(*) AS n FROM {tname}").rows[0]["n"] or 0
    if issues is None:
        issues = detect_issues(con, table)

    if row_count == 0:
        dims = {d: 0.0 for d in _WEIGHTS}
        return QualityReport(table, 0, dims, 0.0, "Poor", issues,
                             detail={"note": "empty table"})

    # Structural (by-design) columns are excluded from completeness; so are raw
    # columns superseded by a *_Clean sibling (the clean layer improves the score).
    structural_cols = {i.column for i in issues
                       if i.module_id == "null_classification" and i.column}
    excluded = structural_cols | superseded_columns(schema)

    # --- directly-measured dimensions ---
    null_rates = []
    for c in schema.columns:
        if c.name in excluded:
            continue
        null_rates.append(col_stats(con, tname, c.name)["null_rate"])
    completeness = _clamp(100.0 * (1 - (sum(null_rates) / len(null_rates) if null_rates else 0.0)))

    distinct_rows = con.run(
        f"SELECT count(*) AS n FROM (SELECT DISTINCT * FROM {tname})"
    ).rows[0]["n"] or 0
    dup_frac = (row_count - distinct_rows) / row_count
    uniqueness = _clamp(100.0 * (1 - dup_frac))

    dc = find_date_column(con, tname, schema)
    freshness_str: str | None = None
    if dc is None:
        freshness = 100.0            # no time dimension to assess (neutral)
        freshness_assessed = False
    else:
        col, needs_cast = dc
        expr = f"TRY_CAST({_qq(col)} AS DATE)" if needs_cast else _qq(col)
        mx = con.run(f"SELECT CAST(max({expr}) AS VARCHAR) AS mx FROM {tname}").rows[0]["mx"]
        freshness_str = mx
        freshness = 90.0 if needs_cast else 100.0   # castable-but-text costs a little
        freshness_assessed = True

    # --- issue-driven dimensions (start at 100, subtract penalties) ---
    issue_dims = {d: 100.0 for d in _ISSUE_DIMS}
    for i in issues:
        dim = _ISSUE_DIM.get(i.module_id)
        if dim in issue_dims:
            issue_dims[dim] -= _SEVERITY_PENALTY.get(i.severity, 0)
    issue_dims = {d: _clamp(v) for d, v in issue_dims.items()}

    # --- derived dimensions ---
    n_critical = len(critical_issues(issues))
    business_readiness_score = _clamp(100.0 - 25.0 * n_critical)
    referential = 100.0            # no cross-table FKs declared yet (assessed=False)
    documentation = 100.0 if (PATHS.quirks / f"{con.name}.md").exists() else 60.0

    dims = {
        "completeness": round(completeness, 2),
        "uniqueness": round(uniqueness, 2),
        "validity": round(issue_dims["validity"], 2),
        "freshness": round(freshness, 2),
        "consistency": round(issue_dims["consistency"], 2),
        "semantic_accuracy": round(issue_dims["semantic_accuracy"], 2),
        "type_safety": round(issue_dims["type_safety"], 2),
        "referential_integrity": round(referential, 2),
        "business_readiness": round(business_readiness_score, 2),
        "documentation": round(documentation, 2),
    }
    overall = round(sum(dims[d] * w for d, w in _WEIGHTS.items()), 2)

    return QualityReport(
        table=table, row_count=row_count, dimensions=dims, overall_score=overall,
        business_readiness=_band(overall), issues=issues, freshness=freshness_str,
        detail={
            "structural_columns": sorted(structural_cols),
            "referential_assessed": False,
            "freshness_assessed": freshness_assessed,
            "duplicate_rows": row_count - distinct_rows,
        },
    )


def _qq(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'
