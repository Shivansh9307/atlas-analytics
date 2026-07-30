"""Logistic playbook — per-customer risk scoring with an auditable model.

Runs on top of the descriptive playbook's work: it reuses that stage's `FeaturePlan`,
including which columns were *measured* to be non-linear. A feature the descriptive
stage flagged as a cliff must arrive here binned, or the fit refuses to run — fitting
a straight line through a known staircase underfits, and the resulting coefficient
would be reported with exactly the same confidence as a sound one.

Provenance discipline (the reason this playbook is more than a wrapper):

  * The predictions are registered as a LOCAL DuckDB view via `materialize_scores()`,
    so every deck-facing number about the model (high-risk count, confusion matrix,
    rate by tier) is a genuine SQL result with real hashes.
  * Only two things stay genuinely derived: the coefficients, and the scored file.
    Each carries a `ModelFingerprint` / `ScoringFingerprint` written to disk, and
    `record_derived()` refuses to tag either above `correlational`.
  * Risk tiers come from `risk_tiers.yaml`, never a literal, so the CSV and any
    dashboard cut the same bands.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field

from atlas.lib.classify import (
    calibration_bins, confusion_at, majority_baseline, roc_auc, threshold_table,
)
from atlas.lib.deck_pptx import Chart, DeckSpec, Slide
from atlas.lib.logit import (
    SeparationError, build_design, fit_logit, phrase_odds_ratio, predict_proba,
    stratified_split,
)
from atlas.lib.model_provenance import (
    ModelFingerprint, ScoringFingerprint, sha256_file, write_fingerprint,
)
from atlas.lib.risk_tiers import load_policy
from atlas.lib.sqlident import quote_ident, quote_table
from atlas.lib.validation import (
    grade_layers, range_layer, sample_size_layer, structural_layer,
)
from atlas.lib.validation import LayerResult
from atlas.playbooks.base import (
    BriefFields, ClaimSpec, FeaturePlan, PlaybookBlocked, Rederivation,
    register_playbook,
)
from atlas.playbooks.binding import ColumnRequirement, ColumnRole
from atlas.playbooks.descriptive import DescriptivePlaybook, DescriptiveResult

SEED = 42
TEST_FRAC = 0.25
SCORES_VIEW = "atlas_scores"
SCORES_CSV = "risk_scores.csv"


@dataclass
class LogisticResult(DescriptiveResult):
    fit: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    model_digest: str = ""
    scoring_digest: str = ""
    tier_counts: dict = field(default_factory=dict)
    tier_refs: tuple[str, str] = ("", "")
    scored_rows: int = 0

    def as_dict(self) -> dict:
        d = super().as_dict()
        d.update({"fit": self.fit, "metrics": self.metrics,
                  "model_digest": self.model_digest,
                  "scoring_digest": self.scoring_digest,
                  "tier_counts": self.tier_counts,
                  "tier_refs": list(self.tier_refs),
                  "scored_rows": self.scored_rows})
        return d


@register_playbook
class LogisticPlaybook(DescriptivePlaybook):
    """Descriptive analysis, then an interpretable model over the same feature plan."""

    id = "logistic"
    description = ("Interpretable logistic regression: odds ratios with intervals "
                   "plus a per-entity risk-ranked list.")
    question_levels = (4,)
    # Not registered against any metrics.yaml `decomposition:` — this playbook is
    # opt-in via `playbook="logistic"`, because scoring individuals is a different
    # act from explaining an aggregate and should be chosen deliberately.
    supported_decompositions = frozenset()
    requirements = (
        ColumnRequirement(
            role=ColumnRole.TARGET, required=True, shape="binary",
            name_hints=("churn", "target", "label", "outcome", "converted",
                        "response", "is", "has", "flag"),
            describe="a binary outcome column to model"),
        ColumnRequirement(
            role=ColumnRole.ENTITY, required=True, shape="unique",
            name_hints=("id", "key", "customerid", "userid", "accountid"),
            describe="a unique identifier — required, since scores are per entity"),
    )

    def brief_fields(self, ctx) -> BriefFields:
        f = super().brief_fields(ctx)
        entity = ctx.binding.one(ColumnRole.ENTITY) if ctx.binding else "entity"
        f.decision_unblocked = f"Which {entity}s to prioritise for intervention."
        f.success_criteria = ("A risk-ranked list with calibrated probabilities, plus "
                              "odds ratios with confidence intervals for each driver.")
        f.non_goals = ("Causal attribution. A predictive model identifies who is at "
                       "risk, never why in a causal sense, and never what to do about it.")
        return f

    # ------------------------------ model ------------------------------
    def model(self, ctx, res: DescriptiveResult):
        plan = res.feature_plan
        if plan is None:
            raise PlaybookBlocked("no feature plan: the descriptive stage must run first")

        out = LogisticResult(
            binding=res.binding, row_count=res.row_count, target=res.target,
            base_rate=res.base_rate, base_refs=res.base_refs,
            column_summaries=res.column_summaries, findings=res.findings,
            thresholds=res.thresholds, feature_plan=plan)

        rows, train_refs = self._load_training_rows(ctx, plan)
        self._assert_binnings_honoured(plan, rows)

        dm = build_design(rows, plan, standardize=True, drop_first=True)
        self._assert_no_flagged_column_left_raw(plan, dm)

        train_idx, test_idx = stratified_split(
            dm.y, dm.entity_ids, test_frac=TEST_FRAC, seed=SEED)
        sds = (dm.standardizer.sds if dm.standardizer else {})
        try:
            fit = fit_logit(dm, train_idx, seed=SEED, sd_lookup=sds)
        except SeparationError as e:
            raise PlaybookBlocked(
                f"the model could not be fitted honestly: {e}\n\n"
                f"Atlas will not report coefficients from a fit that did not "
                f"converge or whose design is degenerate.") from e

        # --- metrics on the HELD-OUT split ---
        y_test = [dm.y[i] for i in test_idx]
        p_test = predict_proba(fit, dm, test_idx)
        policy = load_policy(plan.tier_policy_profile)
        cm = confusion_at(y_test, p_test, policy.flag_threshold)
        auc = roc_auc(y_test, p_test)
        base_cm = majority_baseline(y_test)
        metrics = {
            "auc": auc, "confusion": cm.as_dict(),
            "baseline": base_cm.as_dict(),
            "threshold_used": policy.flag_threshold,
            "threshold_table": threshold_table(
                y_test, p_test, [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]),
            "calibration": calibration_bins(y_test, p_test, k=10),
            "pseudo_r2": fit.pseudo_r2,
        }

        # --- fingerprint the recipe BEFORE anything downstream quotes a number ---
        mfp = ModelFingerprint(
            algorithm="statsmodels.Logit", algorithm_version=_sm_version(),
            seed=SEED, train_query_hash=train_refs[0], train_result_hash=train_refs[1],
            feature_names=tuple(dm.feature_names),
            preprocessing=tuple((a, b) for a, b in dm.preprocessing),
            split=("stratified", TEST_FRAC, True),
            hyperparams=(("method", "newton"), ("maxiter", "100"),
                         ("regularisation", "none")),
            coefficients=tuple((c.name, c.coef) for c in fit.coefficients),
            intercept=fit.intercept)
        out.model_digest = write_fingerprint(ctx.run_dir, mfp, kind="model")

        # --- score EVERY row, write the CSV, register it as a queryable view ---
        all_idx = list(range(dm.n))
        p_all = predict_proba(fit, dm, all_idx)
        scored = self._write_scores(ctx, dm, p_all, fit, policy, plan, test_idx)
        tier_counts, tier_refs = self._tier_counts(ctx, policy)

        sfp = ScoringFingerprint(
            model_digest=out.model_digest,
            score_query_hash=train_refs[0], score_result_hash=train_refs[1],
            tier_policy_digest=policy.digest(),
            flag_threshold=policy.flag_threshold,
            output_sha256=sha256_file(ctx.run_dir / SCORES_CSV),
            row_count=scored, entity_column=plan.entity)
        out.scoring_digest = write_fingerprint(ctx.run_dir, sfp, kind="scoring")

        out.fit = fit.as_dict()
        out.metrics = metrics
        out.tier_counts = tier_counts
        out.tier_refs = tier_refs
        out.scored_rows = scored
        out.query_refs = [train_refs]
        ctx.scratch["logit_fit"] = fit
        ctx.write("model_card.md", self._model_card(ctx, out, fit, policy, plan))
        return out

    def _load_training_rows(self, ctx, plan: FeaturePlan):
        """One query returns the whole training set; its hash is the parent of every
        derived number the model produces."""
        cols = [plan.target] + list(plan.numeric) + list(plan.categorical)
        if plan.entity:
            cols.insert(0, plan.entity)
        sel = ", ".join(quote_ident(c) for c in dict.fromkeys(cols))
        r = ctx.con.run(
            f"SELECT {sel} FROM {quote_table(plan.table)} "
            f"WHERE {quote_ident(plan.target)} IS NOT NULL",
            purpose="logistic training set")
        ctx.budget.charge_query(r.bytes_scanned)
        return r.rows, (r.query_hash, r.result_hash)

    @staticmethod
    def _assert_binnings_honoured(plan: FeaturePlan, rows: list[dict]) -> None:
        available = set(rows[0]) if rows else set()
        missing = [b.column for b in plan.binnings if b.column not in available]
        if missing:
            raise PlaybookBlocked(
                f"the feature plan requires binning {missing} (flagged non-linear by "
                f"the descriptive stage), but the column is not in the training set. "
                f"Atlas will not silently fit a linear term on a variable measured to "
                f"have a cliff.")

    @staticmethod
    def _assert_no_flagged_column_left_raw(plan: FeaturePlan, dm) -> None:
        """A flagged column must appear as bin dummies, never as a bare linear term."""
        for b in plan.binnings:
            if b.column in dm.feature_names:
                raise PlaybookBlocked(
                    f"'{b.column}' was measured to have a threshold effect "
                    f"({b.reason}) but entered the design matrix as a raw linear "
                    f"term. A linear coefficient on a staircase underfits and would "
                    f"be reported with unwarranted confidence.")
            if not any(n.startswith(f"{b.column}=") for n in dm.feature_names):
                raise PlaybookBlocked(
                    f"'{b.column}' is in the feature plan's binnings but produced no "
                    f"bin dummies; the encoding did not honour the plan.")

    def _write_scores(self, ctx, dm, probs, fit, policy, plan, test_idx) -> int:
        """risk_scores.csv, keyed on the same entity id used everywhere else.

        Carries `split` and `actual` as well as the score. That is what lets the
        red team recompute the held-out confusion matrix entirely in SQL and compare
        it against the Python one — the check that catches row/prediction
        misalignment, which is the most common way a scoring pipeline goes wrong
        while still looking healthy.
        """
        by_name = {c.name: c for c in fit.coefficients}
        test = set(test_idx)
        rows = []
        for i, p in enumerate(probs):
            contribs = []
            for j, fname in enumerate(dm.feature_names):
                c = by_name.get(fname)
                if c is None:
                    continue
                contribs.append((abs(c.coef * dm.X[i][j]), fname))
            contribs.sort(reverse=True)
            rows.append({
                plan.entity or "row_id": dm.entity_ids[i],
                policy.score_field: round(p, 6),
                "risk_tier": policy.tier_of(p),
                "flagged": int(p >= policy.flag_threshold),
                "split": "test" if i in test else "train",
                "actual": int(dm.y[i]),
                "top_factor_1": contribs[0][1] if contribs else "",
                "top_factor_2": contribs[1][1] if len(contribs) > 1 else "",
                "top_factor_3": contribs[2][1] if len(contribs) > 2 else "",
            })
        path = ctx.run_dir / SCORES_CSV
        with path.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        if SCORES_CSV not in ctx.artefacts:
            ctx.artefacts.append(SCORES_CSV)
        # Register locally so downstream counts are SQL, not Python sums.
        mat = getattr(ctx.con, "materialize_scores", None)
        if mat is not None:
            mat(SCORES_VIEW, rows)
        return len(rows)

    def _tier_counts(self, ctx, policy):
        """Counts per tier, measured in SQL against the registered scores view."""
        if not getattr(ctx.con, "has_table", lambda _n: False)(SCORES_VIEW):
            return {}, ("", "")
        r = ctx.con.run(
            f"SELECT risk_tier, count(*) AS n FROM {quote_table(SCORES_VIEW)} "
            f"GROUP BY 1 ORDER BY 1", purpose="risk tier distribution")
        ctx.budget.charge_query(r.bytes_scanned)
        return ({str(row["risk_tier"]): int(row["n"]) for row in r.rows},
                (r.query_hash, r.result_hash))

    # ------------------------------ claims ------------------------------
    def diagnose(self, ctx, res: LogisticResult) -> list[ClaimSpec]:
        claims = super().diagnose(ctx, res)          # base rate + top associations
        if not res.fit:
            return claims

        # Measured in SQL against the scores view -> ordinary claims.
        qh, rh = res.tier_refs
        if qh and rh:
            for tier, n in sorted(res.tier_counts.items()):
                claims.append(ClaimSpec(
                    f"c_tier_{tier.lower()}", f"{tier}-risk entities", n, qh, rh,
                    evidence_tier="decomposed",
                    notes="counted in SQL over the registered scores view"))

        # Derived from the fit -> recorded through record_derived() by the node.
        top = sorted(res.fit["coefficients"],
                     key=lambda c: -abs(c["coef"]))[:5]
        pq, pr = res.base_refs
        for c in top:
            claims.append(ClaimSpec(
                f"c_or_{_slug(c['name'])}",
                f"Odds ratio, {c['name']} ({c['unit']})",
                round(c["odds_ratio"], 4),
                pq, pr,
                evidence_tier="correlational",
                notes=f"95% CI {c['or_ci_low']:.3f}-{c['or_ci_high']:.3f}, "
                      f"p={c['p_value']:.3g}",
                derivation=f"model:{res.model_digest}",
                parent_claims=["c_base_rate"]))
        return claims

    # ------------------------------ red team ------------------------------
    def rederive(self, ctx, res: LogisticResult) -> Rederivation:
        rd = super().rederive(ctx, res)              # descriptive checks still apply
        if not res.fit:
            return rd

        comparisons, attacks = list(rd.comparisons), list(rd.attacks)
        m = res.metrics

        # 1. Confusion matrix recomputed ENTIRELY in SQL against the scores view.
        #    SQL-vs-Python over the same predictions is a genuinely independent path
        #    and is what catches row-misalignment, the most common real ML bug.
        if getattr(ctx.con, "has_table", lambda _n: False)(SCORES_VIEW):
            sql_cm = self._sql_confusion(ctx, res)
            py_cm = m["confusion"]
            for cell in ("tp", "fp", "tn", "fn"):
                match = sql_cm[cell] == py_cm[cell]
                comparisons.append({
                    "label": f"confusion {cell} (SQL vs Python)",
                    "analyst": float(py_cm[cell]), "redteam": float(sql_cm[cell]),
                    "tol": 0.0, "within": match})
            if any(sql_cm[c] != py_cm[c] for c in ("tp", "fp", "tn", "fn")):
                attacks.append(
                    f"the held-out confusion matrix recomputed in SQL {sql_cm} "
                    f"disagrees with the Python one "
                    f"{ {k: py_cm[k] for k in ('tp','fp','tn','fn')} } — rows and "
                    f"predictions are misaligned")

        # 2. Baseline dominance: must beat both the majority class and the single
        #    best one-rule cut the descriptive stage already found.
        auc = m.get("auc")
        if auc is not None:
            comparisons.append({"label": "AUC vs 0.5 coin flip", "analyst": auc,
                                "redteam": 0.5, "tol": 0.0, "within": auc > 0.6})
            if auc <= 0.6:
                attacks.append(
                    f"AUC {auc:.3f} is barely better than chance; the model does not "
                    f"earn its complexity")
        rule_auc = self._one_rule_auc(ctx, res)
        if rule_auc is not None and auc is not None:
            comparisons.append({"label": "AUC vs best single-rule cut",
                                "analyst": auc, "redteam": rule_auc, "tol": 0.0,
                                "within": auc >= rule_auc + 0.02})
            if auc < rule_auc + 0.02:
                attacks.append(
                    f"a single threshold rule scores AUC {rule_auc:.3f} against the "
                    f"model's {auc:.3f}. The model does not beat one rule by a "
                    f"meaningful margin — ship the rule, not the model")

        # 3. Sign agreement against the model-free univariate effect (continuous only).
        flips = self._sign_flips(res)
        if flips:
            attacks.append(
                f"coefficient sign disagrees with the univariate association for "
                f"{flips}. This can be legitimate confounding, but it must be "
                f"explained in the narrative, not shipped silently")

        # 3b. The binned analogue: does the model order the bins the way the data does?
        discordant = self._bin_order_discordance(res)
        if discordant:
            attacks.append(
                f"the model orders the bins of {discordant} differently from the "
                f"observed rates. A binned coefficient that contradicts its own "
                f"bucket rates is a fitting artefact, not a finding")

        # 4. Leakage probe.
        leaks = [f.column for f in res.findings
                 if f.effect_kind == "pearson_r" and abs(f.effect) > 0.95]
        if leaks:
            attacks.append(f"possible target leakage: {leaks} correlate > 0.95 with "
                           f"the outcome")

        return Rederivation(ok=rd.ok and not attacks, method=(
            rd.method + "; confusion matrix recomputed in SQL over the registered "
            "scores view; model benchmarked against the majority class and the best "
            "single-rule cut; coefficient signs checked against univariate effects"),
            comparisons=comparisons, attacks=attacks, query_refs=rd.query_refs)

    def _sql_confusion(self, ctx, res: LogisticResult) -> dict | None:
        """Recompute the held-out confusion matrix in pure SQL over the scores view."""
        r = ctx.con.run(
            "SELECT "
            "count(*) FILTER (WHERE flagged = 1 AND actual = 1) AS tp, "
            "count(*) FILTER (WHERE flagged = 1 AND actual = 0) AS fp, "
            "count(*) FILTER (WHERE flagged = 0 AND actual = 0) AS tn, "
            "count(*) FILTER (WHERE flagged = 0 AND actual = 1) AS fn "
            f"FROM {quote_table(SCORES_VIEW)} WHERE split = 'test'",
            purpose="red-team: held-out confusion matrix recomputed in SQL")
        ctx.budget.charge_query(r.bytes_scanned)
        row = r.rows[0]
        return {k: int(row[k] or 0) for k in ("tp", "fp", "tn", "fn")}

    def _one_rule_auc(self, ctx, res: LogisticResult) -> float | None:
        """AUC of the strongest single threshold rule the descriptive stage found."""
        thr = next((f for f in res.findings if f.kind == "threshold"), None)
        if thr is None or not thr.detail.get("cut_values"):
            return None
        cut = float(thr.detail["cut_values"][0])
        col = quote_ident(thr.column)
        y = quote_ident(res.target)
        r = ctx.con.run(
            f"SELECT CASE WHEN {col} >= {cut!r} THEN 1 ELSE 0 END AS rule, "
            f"CAST({y} AS INTEGER) AS y FROM {quote_table(res.feature_plan.table)} "
            f"WHERE {col} IS NOT NULL AND {y} IS NOT NULL",
            purpose="red-team: AUC of the best single-rule cut")
        ctx.budget.charge_query(r.bytes_scanned)
        return roc_auc([int(x["y"]) for x in r.rows], [float(x["rule"]) for x in r.rows])

    def _sign_flips(self, res: LogisticResult, alpha: float = 0.05) -> list[str]:
        """Continuous coefficients whose sign contradicts their univariate association.

        Scoped deliberately, because the naive version produces false positives that
        look alarming:

        * **Continuous features only.** A one-hot coefficient is a contrast against an
          arbitrary baseline level, so its sign carries no information about the
          feature's overall direction. Comparing `Tenure=6-23` (negative, vs the 0-5
          baseline) against Tenure's positive correlation flags a contradiction that
          does not exist. Binned features are checked by `_bin_order_discordance`.
        * **Both effects must be significant.** A "disagreement" between two estimates
          that are each indistinguishable from zero is noise, not confounding.
        """
        uni = {f.column: f for f in res.findings if f.effect_kind == "pearson_r"}
        flips = []
        for c in res.fit.get("coefficients", []):
            src = c.get("source_column")
            if c["name"] != src:            # one-hot contrast, not a continuous term
                continue
            f = uni.get(src)
            if f is None or not f.significant or not f.effect:
                continue
            if c.get("p_value", 1.0) >= alpha or not c["coef"]:
                continue
            if (f.effect > 0) != (c["coef"] > 0):
                flips.append(src)
        return sorted(set(flips))

    def _bin_order_discordance(self, res: LogisticResult) -> list[str]:
        """For a binned feature, does the model rank the bins as the data does?

        This is the valid analogue of a sign check for one-hot features: compare the
        ordering of the fitted bin coefficients (baseline = 0) against the ordering of
        the observed rate in each bin. A model that inverts its own bucket rates is
        reporting a fitting artefact.
        """
        plan = res.feature_plan
        if not plan:
            return []
        by_col = {t.column: t for t in res.thresholds}
        coefs = {c["name"]: c["coef"] for c in res.fit.get("coefficients", [])}
        bad = []
        for spec in plan.binnings:
            tf = by_col.get(spec.column)
            if tf is None or not tf.buckets:
                continue
            observed = self._observed_bin_rates(tf, spec)
            if len(observed) < 2:
                continue
            baseline = spec.labels[0]
            model = {lab: (0.0 if lab == baseline
                           else coefs.get(f"{spec.column}={lab}"))
                     for lab in spec.labels}
            if any(v is None for v in model.values()):
                continue
            obs_order = [lab for lab, _ in sorted(observed.items(), key=lambda kv: kv[1])]
            mdl_order = [lab for lab, _ in sorted(model.items(), key=lambda kv: kv[1])]
            if obs_order != mdl_order:
                bad.append(spec.column)
        return sorted(bad)

    @staticmethod
    def _observed_bin_rates(tf, spec) -> dict[str, float]:
        """Aggregate the threshold scan's buckets up into the plan's bins."""
        edges = sorted(spec.edges)
        agg: dict[str, list[int]] = {lab: [0, 0] for lab in spec.labels}
        for b in tf.buckets:
            idx = sum(1 for e in edges if b.lo >= e)
            lab = spec.labels[min(idx, len(spec.labels) - 1)]
            agg[lab][0] += b.n
            agg[lab][1] += b.x
        return {lab: (x / n) for lab, (n, x) in agg.items() if n}

    def validation_layers(self, ctx, res: LogisticResult):
        layers = list(super().validation_layers(ctx, res))
        if not res.fit:
            return layers
        m = res.metrics
        auc = m.get("auc") or 0.0
        layers.append(LayerResult("discrimination", auc >= 0.60, weight=1.5,
                                  detail=f"held-out AUC={auc:.4f} (floor 0.60)"))
        cal = m.get("calibration") or []
        worst = max((abs(b["gap"]) for b in cal), default=0.0)
        layers.append(LayerResult("calibration", worst <= 0.10, weight=1.0,
                                  detail=f"max |predicted-observed| = {worst:.4f}"))
        layers.append(LayerResult(
            "separation", not any("separation" in f for f in res.fit.get("flags", [])),
            weight=1.0, detail="; ".join(res.fit.get("flags", [])) or "no separation flags"))
        layers.append(sample_size_layer(res.fit.get("n_train", 0)))
        return layers

    # ------------------------------ output ------------------------------
    def narrate(self, ctx, res: LogisticResult) -> str:
        if not res.fit:
            return super().narrate(ctx, res)
        from atlas.lib.logit import Coefficient
        top = sorted(res.fit["coefficients"], key=lambda c: -abs(c["coef"]))[:5]
        lines = [phrase_odds_ratio(Coefficient(**c)) for c in top]
        m = res.metrics
        cm = m["confusion"]
        return (
            f"# Narrative — for {ctx.decision_owner}\n\n"
            f"## Answer (one sentence)\n"
            f"{res.scored_rows:,} entities are scored and ranked by modelled risk; "
            f"the model separates churners from non-churners with held-out "
            f"AUC {m['auc']:.3f} [c_base_rate].\n\n"
            f"## The strongest associations\n" +
            "\n".join(f"{i+1}. {t}" for i, t in enumerate(lines)) + "\n\n"
            f"## How good is it, honestly\n"
            f"- Held-out AUC **{m['auc']:.3f}**; majority-class baseline accuracy "
            f"{m['baseline']['accuracy']:.1%}\n"
            f"- At the {m['threshold_used']:.2f} cutoff: precision "
            f"{cm['precision']:.1%}, recall {cm['recall']:.1%}, F1 {cm['f1']:.3f}\n"
            f"- **The 0.50 cutoff is a modelling default, not a business decision.** "
            f"See the threshold table in `model_card.md` and set it from the relative "
            f"cost of a missed churner versus a wasted contact.\n\n"
            f"## What this does NOT say\n"
            f"Every coefficient is an association measured in one snapshot. A model "
            f"that predicts who will churn does not establish why, and does not imply "
            f"that changing a driver changes the outcome. Test before acting causally.\n")

    def deck_spec(self, ctx, res: LogisticResult) -> DeckSpec:
        spec = super().deck_spec(ctx, res)
        if not res.fit:
            return spec
        m = res.metrics
        tiers = res.tier_counts
        from atlas.lib.logit import Coefficient
        top = sorted(res.fit["coefficients"], key=lambda c: -abs(c["coef"]))[:5]

        spec.slides.insert(len(spec.slides) - 1, Slide(
            "evidence",
            f"{tiers.get('High', 0):,} entities sit in the High-risk band",
            bullets=[f"{k}: {v:,}" for k, v in sorted(tiers.items())] +
                    [f"Held-out AUC {m['auc']:.3f}"],
            chart=Chart("column", list(sorted(tiers)),
                        {"entities": [tiers[k] for k in sorted(tiers)]},
                        title="Risk tier distribution"),
            speaker_notes=(
                f"The model scores every entity and sorts them into bands defined in "
                f"risk_tiers.yaml — the same definition the exported file uses, so the "
                f"list and any dashboard cannot disagree. Held-out AUC is "
                f"{m['auc']:.3f}. These counts were recomputed in SQL against the "
                f"scored data rather than carried over from Python."),
            claim_ids=[f"c_tier_{k.lower()}" for k in sorted(tiers)]))

        spec.slides.insert(len(spec.slides) - 1, Slide(
            "evidence",
            "Odds ratios, with intervals — associations, not causes",
            bullets=[f"{c['name']}: OR {c['odds_ratio']:.2f} "
                     f"({c['or_ci_low']:.2f}-{c['or_ci_high']:.2f})" for c in top[:4]],
            chart=Chart("bar", [c["name"] for c in top],
                        {"odds ratio": [round(c["odds_ratio"], 3) for c in top]},
                        title="Odds ratio by feature"),
            speaker_notes=(
                "Each bar is an odds ratio with a 95% confidence interval in the "
                "appendix. Read these as associations: an entity with this "
                "characteristic shows these odds. None of it licenses the claim that "
                "changing the characteristic would change the outcome — that needs an "
                "experiment. The coefficients are model-derived, so they carry a "
                "fingerprint rather than a query hash, and they are capped at the "
                "correlational evidence tier by construction."),
            claim_ids=[f"c_or_{_slug(c['name'])}" for c in top[:3]]))
        return spec

    def exports(self, ctx, res) -> list[str]:
        """Compile the locked metrics into DAX alongside the scored list.

        Runs in the non-critical `emit` node, so a compiler refusal reports itself
        without discarding an already-validated deck.
        """
        return ["dax", "pbip"]

    def headline(self, ctx, res: LogisticResult) -> str:
        if not res.fit:
            return super().headline(ctx, res)
        m = res.metrics
        return (f"{res.scored_rows:,} entities scored and risk-ranked "
                f"(held-out AUC {m['auc']:.3f}); "
                f"{res.tier_counts.get('High', 0):,} are High-risk — "
                f"associations, not causes.")

    def _model_card(self, ctx, res: LogisticResult, fit, policy, plan) -> str:
        m, cm = res.metrics, res.metrics["confusion"]
        from atlas.lib.logit import Coefficient
        lines = [
            "# Model card", "",
            f"**Algorithm:** statsmodels Logit (unregularised MLE) | "
            f"**seed:** {SEED} | **split:** stratified {int(TEST_FRAC*100)}% held out",
            f"**Model fingerprint:** `{res.model_digest}` | "
            f"**Scoring fingerprint:** `{res.scoring_digest}` | "
            f"**Tier policy:** `{policy.digest()}`", "",
            "## Performance (held-out split)", "",
            f"| metric | value |", "|---|---|",
            f"| ROC-AUC | {m['auc']:.4f} |",
            f"| Precision @ {policy.flag_threshold} | {cm['precision']:.4f} |",
            f"| Recall @ {policy.flag_threshold} | {cm['recall']:.4f} |",
            f"| F1 | {cm['f1']:.4f} |",
            f"| Accuracy | {cm['accuracy']:.4f} |",
            f"| Majority-class accuracy | {m['baseline']['accuracy']:.4f} |",
            f"| McFadden pseudo-R² | {m['pseudo_r2']:.4f} |", "",
            "### Confusion matrix", "",
            "| | predicted 1 | predicted 0 |", "|---|---|---|",
            f"| **actual 1** | {cm['tp']} | {cm['fn']} |",
            f"| **actual 0** | {cm['fp']} | {cm['tn']} |", "",
            "> Accuracy is shown only beside the majority-class baseline. On an "
            "imbalanced target, accuracy alone flatters a model that predicts one "
            "class for everyone.", "",
            "## Choosing the cutoff", "",
            policy.flag_threshold_note.strip(), "",
            "| threshold | flagged | precision | recall | F1 |", "|---|---|---|---|---|",
        ]
        for r in m["threshold_table"]:
            lines.append(f"| {r['threshold']} | {r['flagged']} | {r['precision']:.4f} "
                         f"| {r['recall']:.4f} | {r['f1']:.4f} |")
        lines += ["", "## Odds ratios (associational)", "",
                  "| feature | OR | 95% CI | p | unit |", "|---|---|---|---|---|"]
        for c in sorted(fit.coefficients, key=lambda c: -abs(c.coef)):
            lines.append(f"| {c.name} | {c.odds_ratio:.3f} | "
                         f"{min(c.or_ci_low, c.or_ci_high):.3f}–"
                         f"{max(c.or_ci_low, c.or_ci_high):.3f} | "
                         f"{c.p_value:.3g} | {c.unit} |")
        lines += ["", "## Plain language", ""]
        lines += [f"- {phrase_odds_ratio(c)}"
                  for c in sorted(fit.coefficients, key=lambda c: -abs(c.coef))[:5]]
        binned = ", ".join(f"{b.column}{b.edges}" for b in plan.binnings) or "none"
        lines += ["", "## Preprocessing", "",
                  f"- Binned (measured non-linear, one-hot not ordinal): {binned}",
                  f"- Numerics standardised; coefficients are per 1 SD",
                  f"- Excluded: {plan.exclude}",
                  "", "## Limitations", "",
                  "- Observational fit: coefficients are associations, never causes.",
                  "- Trained and evaluated on one snapshot; no temporal validation.",
                  f"- Flags: {list(fit.flags) or 'none'}"]
        return "\n".join(lines) + "\n"

    def deserialize(self, d: dict) -> LogisticResult:
        base = super().deserialize(d)
        return LogisticResult(
            binding=base.binding, row_count=base.row_count, target=base.target,
            target_kind=base.target_kind, base_rate=base.base_rate,
            base_refs=base.base_refs, column_summaries=base.column_summaries,
            findings=base.findings, thresholds=base.thresholds,
            feature_plan=base.feature_plan,
            fit=d.get("fit", {}), metrics=d.get("metrics", {}),
            model_digest=d.get("model_digest", ""),
            scoring_digest=d.get("scoring_digest", ""),
            tier_counts=d.get("tier_counts", {}),
            tier_refs=tuple(d.get("tier_refs", ("", ""))),
            scored_rows=d.get("scored_rows", 0))


def _sm_version() -> str:
    try:
        import statsmodels
        return statsmodels.__version__
    except Exception:
        return "unknown"


def _slug(name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in name.lower()).strip("_")
