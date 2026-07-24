"""Semantic clean layer: plan -> preview -> apply -> undo -> history.

Raw data is sacred: repairs only ever ADD `<col>_Clean` columns (and optionally
dedup rows) in a derived DuckDB view. The applied set is persisted as a per-source
manifest (+ transformations.sql/.py) and re-materialised on connect, so the clean
layer is deterministic and reproducible without a persisted database.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from atlas.config import PATHS
from atlas.connectors.base import Connector, TableRef
from atlas.quality import sql_engine
from atlas.quality.detectors import detect_issues
from atlas.quality.impact import impact_summary
from atlas.quality.modules.base import REGISTRY, Transform
from atlas.quality.pandas_engine import build_pandas_script
from atlas.quality.rules_loader import auto_apply_confidence
from atlas.quality.score import QualityReport, score_table


# When several modules target the SAME <col>_Clean, keep the single most
# semantically-complete repair (lower rank wins). e.g. case_standardisation
# (upper(trim)) subsumes whitespace_repair (trim); boolean/type repairs beat a
# spurious case-fold; country_standardisation (canonical map) beats case-folding.
_PRECEDENCE = {
    "date_repair": 0, "numeric_type_repair": 1, "boolean_repair": 2,
    "country_standardisation": 3, "region_repair": 4,
    "month_repair": 5, "quarter_repair": 5, "year_repair": 5,
    "case_standardisation": 6, "whitespace_repair": 7,
}


def clean_table_name(table: str) -> str:
    return f"{table}_clean"


def manifest_path(source: str) -> Path:
    return PATHS.clean / f"{source}.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
@dataclass
class CleanPlan:
    source: str
    base_table: str
    clean_table: str
    transforms: list[Transform]           # column-producing + row-level (dedup)
    annotations: list[dict] = field(default_factory=list)  # structural notes (no transform)

    @property
    def column_transforms(self) -> list[Transform]:
        return [t for t in self.transforms if t.enabled and t.sql_expression]

    @property
    def dedup(self) -> bool:
        return any(t.enabled and t.row_level for t in self.transforms)

    @property
    def auto(self) -> list[Transform]:
        thr = auto_apply_confidence()
        return [t for t in self.transforms if t.confidence >= thr]

    @property
    def needs_approval(self) -> list[Transform]:
        thr = auto_apply_confidence()
        return [t for t in self.transforms if t.confidence < thr]

    def select_sql(self) -> str:
        return sql_engine.build_clean_select(self.base_table, self.column_transforms,
                                             dedup=self.dedup)

    def as_dict(self) -> dict:
        return {
            "source": self.source, "base_table": self.base_table,
            "clean_table": self.clean_table,
            "transforms": [t.as_dict() for t in self.transforms],
            "annotations": self.annotations,
        }


def build_plan(con: Connector, table: TableRef, source: str | None = None) -> CleanPlan:
    """Detect issues and turn each into a sequenced, approvable Transform."""
    source = source or con.name
    base = table.name
    issues = detect_issues(con, table)
    schema = con.get_schema(table)
    thr = auto_apply_confidence()
    transforms: list[Transform] = []
    annotations: list[dict] = []
    seq = 0
    ts = _now()
    for issue in issues:
        mod = REGISTRY.get(issue.module_id)
        repair = mod.plan(con, table, schema, issue) if mod else None
        if repair is None:
            continue
        # Structural annotation-only (no column, no dedup): record, don't transform.
        if repair.clean_column is None and not repair.row_level:
            annotations.append({"module_id": repair.module_id, "column": repair.column,
                                "note": repair.notes,
                                "business_impact": repair.business_impact.as_dict()})
            continue
        seq += 1
        transforms.append(Transform.from_repair(
            repair, seq, approved_by="auto" if repair.confidence >= thr else "user", ts=ts))
    transforms = _collapse_collisions(transforms)
    return CleanPlan(source=source, base_table=base,
                     clean_table=clean_table_name(base),
                     transforms=transforms, annotations=annotations)


def _collapse_collisions(transforms: list[Transform]) -> list[Transform]:
    """One transform per <col>_Clean target (keep highest precedence); row-level
    transforms (dedup) are always kept. Re-sequences deterministically."""
    best: dict[str, Transform] = {}
    row_level: list[Transform] = []
    for t in transforms:
        if t.clean_column is None:
            row_level.append(t)
            continue
        cur = best.get(t.clean_column)
        if cur is None or _PRECEDENCE.get(t.module_id, 99) < _PRECEDENCE.get(cur.module_id, 99):
            best[t.clean_column] = t
    kept = row_level + list(best.values())
    kept.sort(key=lambda t: (0 if t.row_level else 1, _PRECEDENCE.get(t.module_id, 99),
                             t.clean_column or ""))
    for i, t in enumerate(kept, 1):
        t.seq = i
    return kept


# --------------------------------------------------------------------------- #
@dataclass
class PreviewResult:
    plan: CleanPlan
    before: QualityReport
    after: QualityReport
    samples: list[dict]
    ddl: dict[str, str]

    def score_delta(self) -> float:
        return round(self.after.overall_score - self.before.overall_score, 2)


def preview(con: Connector, table: TableRef, source: str | None = None,
            *, include: list[Transform] | None = None, sample_rows: int = 5) -> PreviewResult:
    """Before/after: quality-score delta, rows affected, and per-column samples.

    Materialises a temporary clean view (in-memory only) to score the 'after'
    state honestly. Does NOT persist a manifest."""
    plan = build_plan(con, table, source)
    if include is not None:
        keep = {t.seq for t in include}
        for t in plan.transforms:
            t.enabled = t.seq in keep
    before = score_table(con, table)

    tmp = f"{plan.clean_table}__preview"
    select = sql_engine.build_clean_select(plan.base_table, plan.column_transforms, dedup=plan.dedup)
    _materialize(con, tmp, select)
    after = score_table(con, TableRef(tmp))

    samples = _samples(con, plan, table, tmp, sample_rows)
    if hasattr(con, "drop_clean"):
        con.drop_clean(tmp)

    ddl = sql_engine.emit_all_dialects(plan.clean_table, plan.base_table,
                                       plan.column_transforms, dedup=plan.dedup)
    return PreviewResult(plan=plan, before=before, after=after, samples=samples, ddl=ddl)


def _samples(con, plan, base_ref, clean_view, n) -> list[dict]:
    out = []
    for t in plan.column_transforms:
        if not t.column or not t.clean_column:
            continue
        rows = con.run(
            f'SELECT "{t.column}" AS before, "{t.clean_column}" AS after '
            f'FROM {clean_view} WHERE CAST("{t.column}" AS VARCHAR) IS DISTINCT FROM '
            f'CAST("{t.clean_column}" AS VARCHAR) LIMIT {int(n)}'
        ).rows
        out.append({"module_id": t.module_id, "column": t.column,
                    "clean_column": t.clean_column, "rows_affected": t.rows_affected,
                    "examples": [{"before": r["before"], "after": r["after"]} for r in rows]})
    return out


# --------------------------------------------------------------------------- #
@dataclass
class ApplyResult:
    plan: CleanPlan
    applied: list[Transform]
    skipped: list[Transform]
    clean_table: str
    before: QualityReport
    after: QualityReport
    manifest_path: str
    artefacts: list[str] = field(default_factory=list)


def apply(con: Connector, table: TableRef, source: str | None = None, *,
          approve: bool = False, user: str = "operator",
          run_dir: Path | None = None, persist: bool = True) -> ApplyResult:
    """Materialise the clean layer, persist the manifest, write the audit trail.

    Auto-applies transforms at/above the confidence floor; those below apply only
    when `approve=True` (the human-approval path). `persist=False` materialises the
    clean layer and writes the run-dir audit but does NOT write the durable
    per-source manifest (used inside /analyze, where the clean layer is per-run)."""
    source = source or con.name
    plan = build_plan(con, table, source)
    thr = auto_apply_confidence()

    applied, skipped = [], []
    for t in plan.transforms:
        if t.confidence >= thr or approve:
            t.approved_by = "user" if (t.confidence < thr and approve) else t.approved_by
            applied.append(t)
        else:
            t.enabled = False
            skipped.append(t)

    before = score_table(con, table)
    active = CleanPlan(source, plan.base_table, plan.clean_table, applied, plan.annotations)
    select = active.select_sql()
    _materialize(con, plan.clean_table, select)
    after = score_table(con, TableRef(plan.clean_table))

    mpath = ""
    if persist:
        _write_manifest(con, source, active, applied, user, action="apply")
        mpath = str(manifest_path(source))
        from atlas.quality.repair_memory import remember_repairs
        remember_repairs(source, applied, user=user)   # reuse on future connects
    artefacts = _write_audit(run_dir, source, plan, applied, before, after, select) if run_dir else []

    return ApplyResult(plan=plan, applied=applied, skipped=skipped,
                       clean_table=plan.clean_table, before=before, after=after,
                       manifest_path=mpath, artefacts=artefacts)


def undo(con: Connector, source: str, *, user: str = "operator") -> dict:
    """Roll back the most recently applied transform (LIFO); re-materialise."""
    man = load_manifest(source)
    if not man or not man.get("transforms"):
        return {"undone": None, "remaining": 0, "note": "no clean layer to undo"}
    transforms = [Transform.from_dict(d) for d in man["transforms"]]
    removed = transforms.pop()
    active = CleanPlan(source, man["base_table"], man["clean_table"], transforms)
    if transforms:
        _materialize(con, man["clean_table"], active.select_sql())
    elif hasattr(con, "drop_clean"):
        con.drop_clean(man["clean_table"])
    _write_manifest(con, source, active, transforms, user, action="undo",
                    extra_history={"undone_module": removed.module_id,
                                   "undone_column": removed.column})
    return {"undone": removed.module_id, "column": removed.column,
            "remaining": len(transforms)}


def history(source: str) -> list[dict]:
    man = load_manifest(source)
    return man.get("history", []) if man else []


# --------------------------------------------------------------------------- #
def load_manifest(source: str) -> dict | None:
    p = manifest_path(source)
    return json.loads(p.read_text()) if p.exists() else None


def materialize_from_manifest(con: Connector, source: str) -> str | None:
    """Re-apply a persisted clean layer on connect. Returns the clean table name."""
    man = load_manifest(source)
    if not man or not man.get("transforms") or not hasattr(con, "materialize_clean"):
        return None
    transforms = [Transform.from_dict(d) for d in man["transforms"] if d.get("enabled", True)]
    if not transforms:
        return None
    active = CleanPlan(source, man["base_table"], man["clean_table"], transforms)
    _materialize(con, man["clean_table"], active.select_sql())
    return man["clean_table"]


def _materialize(con: Connector, clean_table: str, select_sql: str) -> None:
    if not hasattr(con, "materialize_clean"):
        raise RuntimeError(
            f"connector '{con.name}' cannot materialise a local clean layer; "
            f"emit warehouse DDL instead (sql_engine.build_ddl).")
    con.materialize_clean(clean_table, select_sql)


def _write_manifest(con, source, active_plan, applied, user, *, action, extra_history=None) -> Path:
    p = manifest_path(source)
    p.parent.mkdir(parents=True, exist_ok=True)
    prior = load_manifest(source) or {}
    hist = prior.get("history", [])
    entry = {"ts": _now(), "action": action, "user": user,
             "transforms_applied": [t.module_id for t in applied],
             "rows_affected": sum(t.rows_affected for t in applied)}
    if extra_history:
        entry.update(extra_history)
    hist.append(entry)
    man = {
        "source": source, "base_table": active_plan.base_table,
        "clean_table": active_plan.clean_table,
        "created": prior.get("created", _now()), "updated": _now(),
        "transforms": [t.as_dict() for t in active_plan.transforms],
        "annotations": active_plan.annotations, "history": hist,
    }
    p.write_text(json.dumps(man, indent=2))
    return p


def _write_audit(run_dir, source, plan, applied, before, after, select) -> list[str]:
    run_dir = Path(run_dir)
    (run_dir / "repair").mkdir(parents=True, exist_ok=True)
    files: list[dict] = [
        ("repair/repair_plan.json", json.dumps(plan.as_dict(), indent=2)),
        ("repair/repair_log.json", json.dumps(
            {"applied": [t.as_dict() for t in applied],
             "score_before": before.overall_score, "score_after": after.overall_score}, indent=2)),
        ("repair/transformations.sql",
         f"-- Semantic clean layer for {source}\n"
         + sql_engine.build_ddl(plan.clean_table, plan.base_table, plan.column_transforms,
                                dedup=plan.dedup) + "\n"),
        ("repair/before_profile.md", _score_md("Before", before)),
        ("repair/after_profile.md", _score_md("After", after)),
        ("repair/quality_score.json", json.dumps(
            {"before": before.as_dict(), "after": after.as_dict()}, indent=2)),
        ("repair/before_after.md", _before_after_md(source, before, after, applied)),
    ]
    # pandas equivalent (needs the source path for the read step)
    py = build_pandas_script(str(_src_path(source)), plan.base_table, plan.clean_table,
                             plan.column_transforms, dedup=plan.dedup)
    files.append(("repair/transformations.py", py))
    written = []
    for rel, text in files:
        (run_dir / rel).write_text(text)
        written.append(rel)
    return written


def _src_path(source: str):
    try:
        from atlas.connectors.registry import Registry
        spec = Registry().get_spec(source)
        return PATHS.root / spec.raw.get("path", source)
    except Exception:
        return Path(source)


def _score_md(label: str, rep: QualityReport) -> str:
    lines = [f"# {label} — quality score {rep.overall_score:.1f}/100 ({rep.business_readiness})",
             "", "| dimension | score |", "|---|---|"]
    for d, v in rep.dimensions.items():
        lines.append(f"| {d} | {v} |")
    lines += ["", f"Critical issues: {rep.critical_count} · warnings: {rep.warning_count} · "
              f"freshness: {rep.freshness}"]
    return "\n".join(lines)


def _before_after_md(source, before, after, applied) -> str:
    delta = round(after.overall_score - before.overall_score, 2)
    lines = [f"# Before & After — {source}", "",
             f"**Quality score:** {before.overall_score:.1f} → {after.overall_score:.1f} "
             f"(**{delta:+.1f}**)", "",
             f"**Business readiness:** {before.business_readiness} → {after.business_readiness}", "",
             "## Repairs applied", ""]
    for t in applied:
        lines.append(f"- **{t.module_id}** on `{t.column or '(rows)'}` → "
                     f"`{t.clean_column or 'DISTINCT'}` "
                     f"(conf {t.confidence:.2f}, {t.rows_affected} rows, by {t.approved_by})")
    lines += ["", "## Remaining warnings", ""]
    remaining = [i for i in after.issues if not i.structural]
    lines += [f"- {i.severity} {i.module_id}:{i.column}" for i in remaining] or ["- none"]
    return "\n".join(lines)
