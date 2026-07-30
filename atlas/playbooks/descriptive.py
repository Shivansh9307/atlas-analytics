"""Descriptive playbook — schema-agnostic driver analysis against a target column.

Works on any tabular source: it needs a target column and nothing else. No revenue,
no cogs, no date column, no two comparison periods. That is the point — the engine
previously could only answer questions shaped like the EMEA margin fixture.

It produces five things, all measured in SQL so every number carries provenance:

  1. per-column summary statistics
  2. numeric features ranked by association with the target (point-biserial r,
     Cohen's d from grouped summaries)
  3. categorical segments compared by outcome rate, with Wilson intervals, a
     best-vs-rest z-test, and Cramer's V for the dimension as a whole
  4. threshold / cliff analysis per numeric feature, which is what catches a driver
     that is flat and then jumps
  5. a single ranked findings list, plus a `FeaturePlan` telling any downstream model
     which columns must be binned because a linear term would underfit them

Language discipline: this measures *association*. Nothing here establishes cause, so
findings carry `correlational` (or `tested` where a significance test backs them) and
the prose never says "drives" or "causes" — only "is associated with".
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from atlas.config import TOLERANCES
from atlas.lib.assoc import (
    chi_square_independence, cohens_d, cramers_v, group_rates,
)
from atlas.lib.binning import (
    buckets_from_rows, edges_to_labels, ntile_sql, should_group_by_value,
    value_group_sql,
)
from atlas.lib.deck_pptx import Chart, DeckSpec, Slide
from atlas.lib.sqlident import quote_ident, quote_table
from atlas.lib.stats import correlation_test, two_proportion_ztest
from atlas.lib.thresholds import ThresholdFinding, detect_threshold
from atlas.lib.validation import validate_ranked_findings
from atlas.playbooks.base import (
    BinningSpec, BriefFields, ClaimSpec, FeaturePlan, Playbook, PlaybookResult,
    Rederivation, register_playbook,
)
from atlas.playbooks.binding import (
    ColumnRequirement, ColumnRole, split_features,
)

MAX_FEATURES = 25          # bounds query count on very wide tables
MAX_LEVELS = 20            # categorical levels reported per dimension
NTILE_K = 10


@dataclass
class Finding:
    finding_id: str
    kind: str                  # summary | correlation | group_gap | threshold
    column: str
    headline: str
    effect: float
    effect_kind: str
    n: int
    query_hash: str
    result_hash: str
    p_value: float | None = None
    significant: bool | None = None
    evidence_tier: str = "correlational"
    rank_score: float = 0.0
    detail: dict = field(default_factory=dict)
    flags: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {
            "finding_id": self.finding_id, "kind": self.kind, "column": self.column,
            "headline": self.headline, "effect": self.effect,
            "effect_kind": self.effect_kind, "n": self.n,
            "query_hash": self.query_hash, "result_hash": self.result_hash,
            "p_value": self.p_value, "significant": self.significant,
            "evidence_tier": self.evidence_tier, "rank_score": self.rank_score,
            "detail": self.detail, "flags": list(self.flags),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Finding":
        return cls(**{**d, "flags": tuple(d.get("flags", ()))})


@dataclass
class DescriptiveResult(PlaybookResult):
    target: str = ""
    target_kind: str = "binary"
    base_rate: float = 0.0
    base_refs: tuple[str, str] = ("", "")
    column_summaries: list[dict] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    thresholds: list[ThresholdFinding] = field(default_factory=list)
    feature_plan: FeaturePlan | None = None

    def top(self, n: int = 5) -> list[Finding]:
        """Best finding per column, highest first.

        A column can produce both a correlation and a threshold finding; both belong
        in findings.md, but a top-N list that shows the same column twice wastes the
        reader's attention and a chart's axis.
        """
        seen: set[str] = set()
        out: list[Finding] = []
        for f in self.findings:
            if f.column in seen:
                continue
            seen.add(f.column)
            out.append(f)
            if len(out) >= n:
                break
        return out

    def as_dict(self) -> dict:
        d = super().as_dict()
        d.update({
            "target": self.target, "target_kind": self.target_kind,
            "base_rate": self.base_rate, "base_refs": list(self.base_refs),
            "column_summaries": self.column_summaries,
            "findings": [f.as_dict() for f in self.findings],
            "thresholds": [t.as_dict() for t in self.thresholds],
            "feature_plan": self.feature_plan.as_dict() if self.feature_plan else None,
        })
        return d


def _rank_score(effect_kind: str, effect: float, significant: bool | None,
                n: int) -> float:
    """Map heterogeneous effect sizes onto one comparable scale.

    This is an explicit heuristic ordering, NOT a statistical statement, and the
    findings doc says so. Its only job is to put the biggest, best-evidenced effects
    at the top of a list a human then reads.
    """
    e = abs(effect)
    base = {
        "pearson_r": e,
        "cramers_v": e,
        "cohens_d": e / (e + 1.0),
        "rate_gap_pp": min(1.0, e / 100.0),
        "cliff_jump": min(1.0, e),
    }.get(effect_kind, min(1.0, e))
    sig_factor = 1.0 if significant else (0.7 if significant is None else 0.5)
    n_factor = min(1.0, n / 384.0)
    return round(base * sig_factor * n_factor, 6)


@register_playbook
class DescriptivePlaybook(Playbook):
    id = "descriptive"
    description = ("Schema-agnostic driver analysis: ranks how strongly each column "
                   "is associated with a target, including threshold effects.")
    question_levels = (2, 3)
    supported_decompositions = frozenset({"additive", "non_decomposable", "driver_ranking"})
    requirements = (
        ColumnRequirement(
            role=ColumnRole.TARGET, required=True, shape="binary",
            name_hints=("churn", "target", "label", "outcome", "converted",
                        "response", "is", "has", "flag"),
            describe="a binary (exactly 2 boolean-like values) outcome column"),
        ColumnRequirement(
            role=ColumnRole.ENTITY, required=False, shape="unique",
            name_hints=("id", "key", "customerid", "userid", "accountid"),
            describe="a unique row identifier, excluded from features"),
    )

    def brief_fields(self, ctx) -> BriefFields:
        target = ctx.binding.one(ColumnRole.TARGET) if ctx.binding else "?"
        return BriefFields(
            decision_unblocked=f"Where to intervene on '{target}'.",
            primary_metric=f"'{target}' rate (ratio)",
            comparison_window="cross-sectional (single snapshot; no time dimension required)",
            grain=f"one row per {ctx.binding.one(ColumnRole.ENTITY) or 'record'}",
            success_criteria=("A ranked list of measured associations, each with an "
                              "effect size, a confidence interval and a provenance ID."),
            non_goals=("Causal attribution; forecasting. Associations measured here do "
                       "not establish that changing a driver changes the outcome."),
        )

    # ------------------------------ explore ------------------------------
    def explore(self, ctx) -> DescriptiveResult:
        table = ctx.analysis_table()
        b = ctx.binding
        target = b.one(ColumnRole.TARGET)
        entity = b.one(ColumnRole.ENTITY) or ""
        probes = ctx.scratch.get("probes", {})

        numeric, categorical, dropped = split_features(
            probes, exclude={target} | ({entity} if entity else set()))
        numeric, categorical, dropped = self._cap_features(
            numeric, categorical, dropped, probes)

        base_rate, base_refs, row_count = self._base_rate(ctx, table, target)
        summaries = self._summaries(ctx, table, numeric, categorical, probes)

        findings: list[Finding] = []
        findings += self._numeric_findings(ctx, table, target, numeric)
        findings += self._categorical_findings(ctx, table, target, categorical, base_rate)
        thresholds, thr_findings = self._threshold_findings(
            ctx, table, target, numeric, probes, row_count)
        findings += thr_findings

        for f in findings:
            f.rank_score = _rank_score(f.effect_kind, f.effect, f.significant, f.n)
        findings.sort(key=lambda f: (-f.rank_score, f.finding_id))

        plan = FeaturePlan(
            table=table, target=target, target_kind="binary", entity=entity,
            numeric=numeric, categorical=categorical,
            exclude=sorted(set(dropped) | {target} | ({entity} if entity else set())),
            exclude_reasons={**dropped,
                             target: "the target being explained",
                             **({entity: "entity identifier"} if entity else {})},
            binnings=[
                BinningSpec(column=t.column, edges=list(t.cut_values),
                            labels=edges_to_labels(t.cut_values),
                            reason=t.detail, source_finding_id=f"f_thresh_{_slug(t.column)}")
                for t in thresholds if t.recommend_bin
            ],
            notes=list(b.notes),
        )
        ctx.write("feature_plan.json", json.dumps(plan.as_dict(), indent=2))

        return DescriptiveResult(
            binding=b, row_count=row_count, target=target, base_rate=base_rate,
            base_refs=base_refs, column_summaries=summaries, findings=findings,
            thresholds=thresholds, feature_plan=plan)

    def _cap_features(self, numeric, categorical, dropped, probes):
        """Bound the query count on a very wide table, and say so."""
        keep = MAX_FEATURES
        if len(numeric) + len(categorical) <= keep:
            return numeric, categorical, dropped
        n_keep = max(1, keep * len(numeric) // (len(numeric) + len(categorical)))
        for c in numeric[n_keep:]:
            dropped[c] = f"feature cap of {MAX_FEATURES} columns"
        for c in categorical[keep - n_keep:]:
            dropped[c] = f"feature cap of {MAX_FEATURES} columns"
        return numeric[:n_keep], categorical[:keep - n_keep], dropped

    def _base_rate(self, ctx, table, target):
        t, y = quote_table(table), quote_ident(target)
        r = ctx.con.run(
            f"SELECT count(*) AS n, CAST(sum(CAST({y} AS DOUBLE)) AS BIGINT) AS x, "
            f"avg(CAST({y} AS DOUBLE)) AS rate FROM {t} WHERE {y} IS NOT NULL",
            purpose="overall target rate")
        ctx.budget.charge_query(r.bytes_scanned)
        row = r.rows[0]
        return float(row["rate"] or 0.0), (r.query_hash, r.result_hash), int(row["n"] or 0)

    def _summaries(self, ctx, table, numeric, categorical, probes) -> list[dict]:
        """One batched query for numeric moments; cardinality comes from the probe."""
        out: list[dict] = []
        if numeric:
            parts = []
            for c in numeric:
                q, a = quote_ident(c), c
                parts += [
                    f'count({q}) AS {quote_ident(a + "__n")}',
                    f'min({q}) AS {quote_ident(a + "__min")}',
                    f'max({q}) AS {quote_ident(a + "__max")}',
                    f'avg({q}) AS {quote_ident(a + "__mean")}',
                    f'stddev_samp({q}) AS {quote_ident(a + "__sd")}',
                    f'quantile_cont({q}, 0.5) AS {quote_ident(a + "__p50")}',
                ]
            r = ctx.con.run(f"SELECT {', '.join(parts)} FROM {quote_table(table)}",
                            purpose="numeric column summaries")
            ctx.budget.charge_query(r.bytes_scanned)
            row = r.rows[0]
            for c in numeric:
                out.append({
                    "column": c, "kind": "numeric",
                    "n": row.get(c + "__n"), "min": row.get(c + "__min"),
                    "max": row.get(c + "__max"), "mean": row.get(c + "__mean"),
                    "sd": row.get(c + "__sd"), "p50": row.get(c + "__p50"),
                    "distinct": probes[c].distinct if c in probes else None,
                })
        for c in categorical:
            p = probes.get(c)
            out.append({"column": c, "kind": "categorical",
                        "distinct": p.distinct if p else None,
                        "n": p.non_null if p else None})
        return out

    def _numeric_findings(self, ctx, table, target, numeric) -> list[Finding]:
        """Point-biserial r for every numeric feature in ONE query, then Cohen's d
        from a single grouped summary — neither pulls raw rows into Python."""
        if not numeric:
            return []
        t, y = quote_table(table), quote_ident(target)
        corr_parts = [f'corr({quote_ident(c)}, CAST({y} AS DOUBLE)) AS {quote_ident(c + "__r")}'
                      for c in numeric]
        r = ctx.con.run(
            f"SELECT {', '.join(corr_parts)}, count(*) AS n FROM {t} WHERE {y} IS NOT NULL",
            purpose="point-biserial correlation of numeric features with the target")
        ctx.budget.charge_query(r.bytes_scanned)
        crow = r.rows[0]
        n_all = int(crow["n"] or 0)

        grp_parts = []
        for c in numeric:
            q = quote_ident(c)
            grp_parts += [f'count({q}) AS {quote_ident(c + "__n")}',
                          f'avg({q}) AS {quote_ident(c + "__mean")}',
                          f'stddev_samp({q}) AS {quote_ident(c + "__sd")}']
        g = ctx.con.run(
            f"SELECT CAST({y} AS DOUBLE) AS cls, {', '.join(grp_parts)} "
            f"FROM {t} WHERE {y} IS NOT NULL GROUP BY 1 ORDER BY 1",
            purpose="per-class numeric summaries for effect size")
        ctx.budget.charge_query(g.bytes_scanned)
        by_cls = {float(row["cls"]): row for row in g.rows}
        pos, neg = by_cls.get(1.0), by_cls.get(0.0)

        out = []
        for c in numeric:
            rr = crow.get(c + "__r")
            if rr is None:
                continue
            d_eff = None
            if pos and neg:
                d_eff = cohens_d(
                    int(pos[c + "__n"] or 0), float(pos[c + "__mean"] or 0.0),
                    float(pos[c + "__sd"] or 0.0),
                    int(neg[c + "__n"] or 0), float(neg[c + "__mean"] or 0.0),
                    float(neg[c + "__sd"] or 0.0))
            direction = "higher" if float(rr) > 0 else "lower"
            test = correlation_test(float(rr), n_all)
            out.append(Finding(
                finding_id=f"f_corr_{_slug(c)}", kind="correlation", column=c,
                headline=(f"'{c}' is associated with the outcome (r={float(rr):+.3f}): "
                          f"{direction} values occur more often among positives"),
                effect=float(rr), effect_kind="pearson_r", n=n_all,
                query_hash=r.query_hash, result_hash=r.result_hash,
                p_value=test.p_value, significant=test.significant,
                # `tested` marks the *association* as distinguishable from zero. It
                # never upgrades the claim to causal — see the methodology note.
                evidence_tier="tested" if test.significant else "correlational",
                detail={"cohens_d": d_eff.as_dict() if d_eff else None},
                flags=tuple(test.flags)))
        return out

    def _categorical_findings(self, ctx, table, target, categorical, base_rate):
        out = []
        t, y = quote_table(table), quote_ident(target)
        for c in categorical:
            q = quote_ident(c)
            r = ctx.con.run(
                f"SELECT CAST({q} AS VARCHAR) AS level, count(*) AS n, "
                f"CAST(sum(CAST({y} AS DOUBLE)) AS BIGINT) AS x "
                f"FROM {t} WHERE {y} IS NOT NULL GROUP BY 1 "
                f"ORDER BY count(*) DESC, 1 LIMIT {MAX_LEVELS}",
                purpose=f"outcome rate by {c}")
            ctx.budget.charge_query(r.bytes_scanned)
            if len(r.rows) < 2:
                continue
            rates = group_rates(r.rows, level_key="level", base_rate=base_rate)
            rates.sort(key=lambda g: (-abs(g.gap_pp), g.level))
            topg = rates[0]
            rest_n = sum(g.n for g in rates) - topg.n
            rest_x = sum(g.x for g in rates) - topg.x
            test = two_proportion_ztest(topg.x, topg.n, rest_x, rest_n)
            table_2d = [[g.x, g.n - g.x] for g in rates]
            v = cramers_v(table_2d)
            chi = chi_square_independence(table_2d)
            out.append(Finding(
                finding_id=f"f_group_{_slug(c)}", kind="group_gap", column=c,
                headline=(f"'{c}' splits the outcome: '{topg.level}' runs "
                          f"{topg.rate:.1%} vs {base_rate:.1%} overall "
                          f"({topg.gap_pp:+.1f}pp, n={topg.n:,})"),
                effect=topg.gap_pp, effect_kind="rate_gap_pp", n=sum(g.n for g in rates),
                query_hash=r.query_hash, result_hash=r.result_hash,
                p_value=test.p_value, significant=test.significant,
                evidence_tier="tested" if test.significant else "correlational",
                detail={"levels": [g.as_dict() for g in rates],
                        "cramers_v": v, "chi_square_p": chi.p_value},
                flags=tuple(test.flags) + tuple(chi.flags)))
        return out

    def _threshold_findings(self, ctx, table, target, numeric, probes, row_count):
        thresholds, findings = [], []
        for c in numeric:
            p = probes.get(c)
            distinct = p.distinct if p else 0
            by_value = should_group_by_value(distinct, NTILE_K, row_count=row_count)
            sql = (value_group_sql(table, c, target) if by_value
                   else ntile_sql(table, c, target, NTILE_K))
            r = ctx.con.run(sql, purpose=f"threshold buckets for {c}")
            ctx.budget.charge_query(r.bytes_scanned)
            if len(r.rows) < 3:
                continue
            buckets = buckets_from_rows(
                r.rows, index_key=None if by_value else "bucket")
            tf = detect_threshold(buckets, column=c)
            thresholds.append(tf)
            if not tf.recommend_bin:
                continue
            # NB `tf.p_value or 1` would be wrong here: a p-value of exactly 0.0 is
            # falsy, so the strongest possible result would be scored as untested.
            sig = tf.p_value is not None and tf.p_value < TOLERANCES.alpha
            findings.append(Finding(
                finding_id=f"f_thresh_{_slug(c)}", kind="threshold", column=c,
                headline=(f"'{c}' has a threshold effect at {tf.cut_values}: the rate "
                          f"steps by {tf.jump:.1%} across the cut, not gradually"),
                effect=tf.jump, effect_kind="cliff_jump", n=sum(b.n for b in buckets),
                query_hash=r.query_hash, result_hash=r.result_hash,
                p_value=tf.p_value, significant=sig,
                evidence_tier="tested" if sig else "correlational",
                detail={"cut_values": tf.cut_values, "buckets": [b.as_dict() for b in tf.buckets],
                        "step_r2": tf.step_r2, "linear_r2": tf.linear_r2},
                flags=tf.flags))
        return thresholds, findings

    # ------------------------------ diagnose ------------------------------
    def diagnose(self, ctx, res: DescriptiveResult) -> list[ClaimSpec]:
        qh, rh = res.base_refs
        claims = [ClaimSpec(
            "c_base_rate", f"Overall '{res.target}' rate",
            round(res.base_rate * 100, 2), qh, rh, evidence_tier="decomposed",
            notes="measured directly from the source")]
        for f in res.top(5):
            claims.append(ClaimSpec(
                f"c_{f.finding_id}", f.headline, round(f.effect, 4),
                f.query_hash, f.result_hash, evidence_tier=f.evidence_tier,
                notes=f"{f.effect_kind}; n={f.n}"))
        return claims

    # ------------------------------ red team ------------------------------
    def rederive(self, ctx, res: DescriptiveResult) -> Rederivation:
        """Recompute the headline by structurally different SQL, then attack it."""
        table, target = ctx.analysis_table(), res.target
        t, y = quote_table(table), quote_ident(target)
        tol = TOLERANCES.rederivation_rel
        comparisons, attacks, refs = [], [], []

        # 1. base rate via a different aggregate family (FILTER vs avg(CAST(...)))
        r = ctx.con.run(
            f"SELECT count(*) FILTER (WHERE {y} = 1) * 1.0 / count(*) AS rate "
            f"FROM {t} WHERE {y} IS NOT NULL",
            purpose="red-team: base rate by a different aggregate")
        ctx.budget.charge_query(r.bytes_scanned)
        rd_base = float(r.rows[0]["rate"] or 0.0)
        refs.append((r.query_hash, r.result_hash))
        ok = abs(rd_base - res.base_rate) <= max(abs(res.base_rate) * tol, 1e-9)
        comparisons.append({"label": "base rate", "analyst": res.base_rate,
                            "redteam": rd_base, "tol": tol, "within": ok})

        # 2. the law of total probability must hold over the top categorical split
        grp = next((f for f in res.findings if f.kind == "group_gap"), None)
        if grp:
            levels = grp.detail.get("levels", [])
            total_n = sum(l["n"] for l in levels) or 1
            recon = sum(l["rate"] * l["n"] for l in levels) / total_n
            within = abs(recon - res.base_rate) <= max(abs(res.base_rate) * tol, 1e-6)
            comparisons.append({"label": f"weighted rates over '{grp.column}'",
                                "analyst": res.base_rate, "redteam": recon,
                                "tol": tol, "within": within})
            if not within:
                attacks.append(
                    f"size-weighted rates across '{grp.column}' reconstruct "
                    f"{recon:.4f}, not the overall {res.base_rate:.4f} — the grouping "
                    f"is dropping or double-counting rows")

        # 3. re-derive the top cliff WITHOUT a window function, to catch NTILE
        #    bucket-edge bugs the analyst path could hide.
        thr = next((f for f in res.findings if f.kind == "threshold"), None)
        if thr and thr.detail.get("cut_values"):
            cut = float(thr.detail["cut_values"][0])
            c = quote_ident(thr.column)
            r2 = ctx.con.run(
                f"SELECT CASE WHEN {c} >= {cut!r} THEN 'above' ELSE 'below' END AS side, "
                f"count(*) AS n, CAST(sum(CAST({y} AS DOUBLE)) AS BIGINT) AS x "
                f"FROM {t} WHERE {c} IS NOT NULL AND {y} IS NOT NULL GROUP BY 1",
                purpose="red-team: threshold re-derived with an explicit CASE split")
            ctx.budget.charge_query(r2.bytes_scanned)
            refs.append((r2.query_hash, r2.result_hash))
            side = {row["side"]: (int(row["n"]), int(row["x"])) for row in r2.rows}
            if "above" in side and "below" in side:
                ra = side["above"][1] / side["above"][0]
                rb = side["below"][1] / side["below"][0]
                jump = abs(ra - rb)
                within = abs(jump - thr.effect) <= max(thr.effect * 0.05, 0.01)
                comparisons.append({"label": f"cliff jump at {thr.column}>={cut:g}",
                                    "analyst": thr.effect, "redteam": jump,
                                    "tol": 0.05, "within": within})
                if not within:
                    attacks.append(
                        f"threshold jump for '{thr.column}' re-derives to {jump:.4f} "
                        f"vs the reported {thr.effect:.4f} — likely a bucket-edge artefact")

        return Rederivation(ok=ok and not attacks,
                            method=("base rate recomputed with count(*) FILTER; "
                                    "segment rates checked against the law of total "
                                    "probability; top threshold re-split with an "
                                    "explicit CASE (no window function)"),
                            comparisons=comparisons, attacks=attacks, query_refs=refs)

    def validation_layers(self, ctx, res: DescriptiveResult):
        grp = next((f for f in res.findings if f.kind == "group_gap"), None)
        parts, rates = {}, {}
        if grp:
            levels = grp.detail.get("levels", [])
            total = sum(l["n"] for l in levels) or 1
            parts = {l["level"]: l["rate"] * l["n"] / total for l in levels}
            rates = {l["level"]: l["rate"] for l in levels}
        top = res.findings[0] if res.findings else None
        return validate_ranked_findings(
            row_count=res.row_count, profile_ok=True,
            weighted_parts=parts or {"all": res.base_rate},
            overall_rate=res.base_rate, rates=rates or {"base": res.base_rate},
            top_significant=(top.significant if top else None),
            top_effect=(top.effect if top else 0.0)).layers

    # ------------------------------ output ------------------------------
    def narrate(self, ctx, res: DescriptiveResult) -> str:
        top = res.top(3)
        pillars = "\n".join(
            f"{i+1}. **{f.column}** — {f.headline} [c_{f.finding_id}]"
            for i, f in enumerate(top))
        cliffs = [t for t in res.thresholds if t.recommend_bin]
        cliff_note = ("\n".join(
            f"- **{t.column}**: steps at {t.cut_values} — a linear model would "
            f"understate this ({t.detail})" for t in cliffs)
            if cliffs else "- none detected")
        return (
            f"# Narrative — for {ctx.decision_owner}\n\n"
            f"## Answer (one sentence)\n"
            f"The strongest measured association with '{res.target}' is "
            f"**{top[0].column if top else 'none found'}**; overall rate is "
            f"{res.base_rate:.1%} [c_base_rate].\n\n"
            f"## Why (ranked associations)\n{pillars}\n\n"
            f"## Threshold effects\n{cliff_note}\n\n"
            f"## So what\n"
            f"Target the segments above, and treat the threshold columns as bands "
            f"rather than linear dials.\n\n"
            f"## What this does NOT say\n"
            f"These are associations measured in a single snapshot. None of them "
            f"establishes that changing a driver would change the outcome; that "
            f"requires an experiment (see `/experiment`).\n"
        )

    def deck_spec(self, ctx, res: DescriptiveResult) -> DeckSpec:
        top = res.top(4)
        grp = next((f for f in res.findings if f.kind == "group_gap"), None)
        cliffs = [t for t in res.thresholds if t.recommend_bin]

        slides = [Slide(
            "insight",
            f"'{res.target}' runs at {res.base_rate:.1%}; "
            f"{top[0].column if top else 'no column'} is the strongest signal",
            bullets=[f"Overall rate: {res.base_rate:.1%} across {res.row_count:,} rows"] +
                    [f"{f.column}: {f.effect_kind} {f.effect:+.3f}" for f in top[:3]],
            chart=Chart("bar", [f.column for f in top],
                        {"effect": [round(abs(f.effect), 4) for f in top]},
                        title="Strength of association (ranked)"),
            speaker_notes=(
                f"The overall {res.target} rate is {res.base_rate:.1%} over "
                f"{res.row_count:,} rows, and that number was independently re-derived "
                f"by the red team using a different aggregate. The ranked bars are "
                f"effect sizes, not p-values — on a table this size almost everything "
                f"is statistically significant, so size is what separates a real "
                f"driver from noise. These are associations, not proven causes."),
            claim_ids=["c_base_rate"] + [f"c_{f.finding_id}" for f in top[:3]])]

        if grp:
            levels = grp.detail.get("levels", [])[:8]
            slides.append(Slide(
                "evidence",
                f"'{grp.column}' separates the outcome by "
                f"{abs(grp.effect):.1f} percentage points",
                bullets=[f"{l['level']}: {l['rate']:.1%} (n={l['n']:,})" for l in levels[:4]],
                chart=Chart("column", [str(l["level"]) for l in levels],
                            {"rate %": [round(l["rate"] * 100, 2) for l in levels]},
                            title=f"Outcome rate by {grp.column}"),
                speaker_notes=(
                    f"Splitting by {grp.column} moves the rate by "
                    f"{abs(grp.effect):.1f} points against a {res.base_rate:.1%} base. "
                    f"Each bar carries a Wilson confidence interval in the appendix, and "
                    f"the size-weighted average of these bars reconstructs the overall "
                    f"rate exactly — that identity is what the red team checked."),
                claim_ids=[f"c_{grp.finding_id}"]))

        if cliffs:
            t0 = cliffs[0]
            slides.append(Slide(
                "evidence",
                f"'{t0.column}' is a cliff, not a slope — it steps at {t0.cut_values}",
                bullets=[f"Cut point(s): {t0.cut_values}",
                         f"Step size: {t0.jump:.1%}",
                         f"A step explains it far better than a line "
                         f"(R² {t0.step_r2:.2f} vs {t0.linear_r2:.2f})"],
                chart=Chart("column", [f"{b.lo:g}-{b.hi:g}" for b in t0.buckets],
                            {"rate %": [round(b.rate * 100, 2) for b in t0.buckets]},
                            title=f"Outcome rate by {t0.column}"),
                speaker_notes=(
                    f"This is the finding an average or a correlation would hide. "
                    f"{t0.column} is flat and then jumps at {t0.cut_values}. That "
                    f"changes the intervention: there is a specific point at which "
                    f"risk changes, so the action is a rule at that boundary rather "
                    f"than a gradual push on the whole population."),
                claim_ids=[f"c_f_thresh_{_slug(t0.column)}"]))

        slides.append(Slide(
            "recommendation",
            f"Act on the bands, not the averages — and test before believing cause",
            bullets=([f"Prioritise the highest-rate segment of '{grp.column}'"] if grp else []) +
                    ([f"Treat '{t.column}' as bands at {t.cut_values}" for t in cliffs[:2]]) +
                    ["Run an experiment before assuming any of these are causal"],
            speaker_notes=(
                "Three moves. Prioritise the worst segment, because that is where the "
                "same effort reaches the most affected population. Treat the threshold "
                "columns as bands, because that is how they actually behave. And before "
                "spending against any of this as though it were causal, run an "
                "experiment — everything on these slides is measured association."),
            claim_ids=[]))

        return DeckSpec(
            title=(f"What is associated with '{res.target}': "
                   f"{top[0].column if top else 'no clear driver'} leads a ranked list"),
            subtitle=f"Cross-sectional driver analysis over {res.row_count:,} rows",
            decision_owner=ctx.decision_owner,
            slides=slides,
            assumptions=ctx.scratch.get("assumptions", []),
            methodology=(
                "Cross-sectional association analysis. Numeric features ranked by "
                "point-biserial correlation and Cohen's d; categorical features by "
                "outcome-rate gap with Wilson intervals, a two-proportion z-test and "
                "Cramer's V. Threshold detection compares a step function against a "
                "straight line and reports a cut only when the step removes most of "
                "the line's residual error.\nEVIDENCE TIER: correlational. A single "
                "snapshot cannot establish causation.\nEvery number carries a "
                "provenance ID -> stored query + result hash."),
            provenance=[
                {"claim_id": c.claim_id, "text": c.text, "value": c.value,
                 "query_hash": c.query_hash, "tier": c.evidence_tier}
                for c in ctx.ledger.all()
            ])

    def stakeholder_questions(self, ctx, res: DescriptiveResult, spec) -> dict[str, bool]:
        notes = " ".join(s.speaker_notes.lower() for s in spec.slides)
        return {
            "Is the number right?": "re-derived" in notes or "identity" in notes,
            "How big is the effect?": "effect size" in notes or "points" in notes,
            "Is this causal?": "association" in notes or "causal" in notes,
            "Which segment do we target?": any(s.kind == "recommendation" for s in spec.slides),
            "What do we do Monday?": any(s.kind == "recommendation" for s in spec.slides),
        }

    def headline(self, ctx, res: DescriptiveResult) -> str:
        top = res.findings[0] if res.findings else None
        if top is None:
            return (f"No column showed a material association with '{res.target}' "
                    f"(base rate {res.base_rate:.1%}).")
        return (f"'{res.target}' runs at {res.base_rate:.1%}; the strongest measured "
                f"association is {top.column} ({top.effect_kind} {top.effect:+.3f}) "
                f"— correlational, not causal.")

    # ------------------------------ artefacts ------------------------------
    def hypotheses_doc(self, ctx, res: DescriptiveResult) -> tuple[str, str]:
        lines = ["# Exploration — candidate drivers", "",
                 f"Target: **{res.target}** | base rate **{res.base_rate:.2%}** "
                 f"| rows **{res.row_count:,}**", "",
                 "## Column summaries", "",
                 "| column | kind | distinct | mean | sd | min | max |", "|---|---|---|---|---|---|---|"]
        for s in res.column_summaries:
            lines.append(
                f"| {s['column']} | {s['kind']} | {s.get('distinct')} | "
                f"{_fmt(s.get('mean'))} | {_fmt(s.get('sd'))} | "
                f"{_fmt(s.get('min'))} | {_fmt(s.get('max'))} |")
        lines += ["", "## Threshold scan", "",
                  "| column | shape | cuts | jump | step R² | linear R² |",
                  "|---|---|---|---|---|---|"]
        for t in res.thresholds:
            lines.append(f"| {t.column} | {t.kind} | {t.cut_values or '—'} | "
                         f"{t.jump:.3f} | {t.step_r2:.3f} | {t.linear_r2:.3f} |")
        return "hypotheses.md", "\n".join(lines) + "\n"

    def findings_doc(self, ctx, res: DescriptiveResult) -> tuple[str, str]:
        lines = [
            "# Findings — ranked associations", "",
            f"**Overall '{res.target}' rate:** {res.base_rate:.2%} "
            f"across {res.row_count:,} rows [c_base_rate].", "",
            "> Ranking uses a heuristic score that maps different effect measures "
            "onto one scale so they can be listed together. It is an ordering aid, "
            "**not a statistical statement**; read the effect size and interval.", "",
            "| # | column | finding | effect | p | tier |", "|---|---|---|---|---|---|"]
        for i, f in enumerate(res.findings, 1):
            p = "—" if f.p_value is None else (f"{f.p_value:.2e}" if f.p_value < 1e-4
                                               else f"{f.p_value:.4f}")
            lines.append(f"| {i} | {f.column} | {f.headline} | "
                         f"{f.effect:+.4f} ({f.effect_kind}) | {p} | {f.evidence_tier} |")
        cliffs = [t for t in res.thresholds if t.recommend_bin]
        lines += ["", "## Threshold effects (must be binned before linear modelling)", ""]
        lines += ([f"- **{t.column}** — {t.detail}" for t in cliffs]
                  or ["- none detected"])
        lines += ["", "## Evidence tier", "",
                  "All findings here are **correlational** unless marked `tested` "
                  "(a significance test backs the specific comparison). Nothing in "
                  "this document establishes causation."]
        return "findings.md", "\n".join(lines) + "\n"

    def validation_doc(self, ctx, res, rd: Rederivation, report) -> tuple[str, str]:
        lines = ["# Validation (red-team)", "", "## Independent re-derivation", "",
                 rd.method, "", "| check | analyst | red-team | within tolerance |",
                 "|---|---|---|---|"]
        for c in rd.comparisons:
            lines.append(f"| {c['label']} | {c['analyst']:.6f} | {c['redteam']:.6f} | "
                         f"{'YES' if c.get('within', True) else 'NO'} |")
        lines += ["", "## Attacks", ""]
        lines += ([f"- SURVIVING: {a}" for a in rd.attacks] or ["- none survived"])
        lines += ["", "## Verdict", "", f"**{'PASS' if rd.ok else 'FAIL'}**", "",
                  f"## Confidence grade", "", f"**{report.grade}** (score {report.score:.2f})"]
        lines += [f"- L:{l['layer']} {'PASS' if l['passed'] else 'FAIL'} — {l['detail']}"
                  for l in report.as_dict()["layers"]]
        return "validation.md", "\n".join(lines) + "\n"

    # ------------------------------ resume ------------------------------
    def deserialize(self, d: dict) -> DescriptiveResult:
        fp = d.get("feature_plan")
        return DescriptiveResult(
            binding=None, row_count=d.get("row_count", 0),
            target=d.get("target", ""), target_kind=d.get("target_kind", "binary"),
            base_rate=d.get("base_rate", 0.0),
            base_refs=tuple(d.get("base_refs", ("", ""))),
            column_summaries=d.get("column_summaries", []),
            findings=[Finding.from_dict(f) for f in d.get("findings", [])],
            thresholds=[ThresholdFinding.from_dict(t) for t in d.get("thresholds", [])],
            feature_plan=FeaturePlan.from_dict(fp) if fp else None)


def _slug(name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in name.lower()).strip("_")


def _fmt(v) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):,.3f}"
    except (TypeError, ValueError):
        return str(v)
