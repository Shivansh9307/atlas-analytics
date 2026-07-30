"""Interpretable logistic regression over a FeaturePlan.

statsmodels, not scikit-learn, for two reasons that matter to this system:
`Logit` is unregularised MLE (sklearn shrinks coefficients by default at `C=1.0`,
which would quietly bias every odds ratio reported), and it returns standard errors,
z-statistics, p-values and confidence intervals natively — the interval is what makes
an odds ratio honest rather than a point estimate presented as fact.

Three deliberate constraints:

* **Identifiers are never features.** They are excluded at the FeaturePlan level.
* **Numerics are standardised**, so a coefficient on Payment Delay (days) and one on
  Total Spend (currency) are comparable. The scaling is recorded in the fingerprint,
  because "per 1 SD" is meaningless without knowing the SD.
* **A column the descriptive stage flagged non-linear is binned, or the fit refuses
  to run.** Fitting a straight line through a known staircase is underfitting, and
  the resulting coefficient would be reported with the same confidence as a valid
  one. That is a hard error, not a preference.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field

__all__ = [
    "Standardizer", "DesignMatrix", "Coefficient", "LogitFit",
    "build_design", "stratified_split", "fit_logit", "predict_proba",
    "phrase_odds_ratio", "SeparationError",
]

# Verbs that would turn a measured association into a causal claim. The single
# phrasing function refuses to emit any of them.
_CAUSAL_VERBS = ("causes", "drives", "leads to", "results in", "because of",
                 "makes", "produces")


class SeparationError(Exception):
    """The fit did not converge, or a feature perfectly separates the outcome."""


@dataclass
class Standardizer:
    means: dict[str, float] = field(default_factory=dict)
    sds: dict[str, float] = field(default_factory=dict)

    def fit(self, rows: list[dict], cols: list[str]) -> "Standardizer":
        for c in cols:
            vals = [float(r[c]) for r in rows if r.get(c) is not None]
            n = len(vals)
            mu = sum(vals) / n if n else 0.0
            var = sum((v - mu) ** 2 for v in vals) / (n - 1) if n > 1 else 0.0
            self.means[c] = mu
            self.sds[c] = math.sqrt(var) if var > 0 else 1.0     # constant -> no-op
        return self

    def z(self, col: str, value: float) -> float:
        return (float(value) - self.means.get(col, 0.0)) / (self.sds.get(col) or 1.0)

    def as_dict(self) -> dict:
        return {"means": dict(self.means), "sds": dict(self.sds)}


@dataclass
class DesignMatrix:
    feature_names: list[str]
    X: list[list[float]]
    y: list[int]
    entity_ids: list
    preprocessing: list[tuple[str, str]] = field(default_factory=list)
    standardizer: Standardizer | None = None
    # feature name -> the source column it came from, for attributing a score back
    source_of: dict[str, str] = field(default_factory=dict)

    @property
    def n(self) -> int:
        return len(self.y)


def build_design(rows: list[dict], plan, *, standardize: bool = True,
                 drop_first: bool = True) -> DesignMatrix:
    """Encode rows into a numeric design matrix according to the feature plan.

    Binned features are one-hot encoded on their bins, NOT ordinal-coded. An ordinal
    code re-imposes a linear relationship *across* the bins, which is precisely the
    assumption the binning exists to escape.
    """
    from atlas.lib.binning import edges_to_labels

    target, entity = plan.target, plan.entity
    binned = {b.column: b for b in plan.binnings}

    # Which raw numerics stay continuous vs become bins
    cont = [c for c in plan.numeric if c not in binned]
    std = Standardizer().fit(rows, cont) if standardize and cont else Standardizer()

    names: list[str] = []
    source_of: dict[str, str] = {}
    prep: list[tuple[str, str]] = []

    for c in cont:
        names.append(c)
        source_of[c] = c
        if standardize:
            prep.append((c, f"zscore:mu={std.means[c]:.6g},sd={std.sds[c]:.6g}"))

    # binned numerics -> one-hot over bin labels, drop-first
    bin_levels: dict[str, list[str]] = {}
    for col, spec in binned.items():
        labels = spec.labels or edges_to_labels(spec.edges)
        bin_levels[col] = labels
        keep = labels[1:] if drop_first else labels
        for lab in keep:
            fn = f"{col}={lab}"
            names.append(fn)
            source_of[fn] = col
        prep.append((col, f"bin:{spec.edges} labels={labels} "
                          f"onehot drop_first={drop_first}"))

    # categoricals -> one-hot, drop-first, levels sorted for determinism
    cat_levels: dict[str, list[str]] = {}
    for c in plan.categorical:
        levels = sorted({str(r[c]) for r in rows if r.get(c) is not None})
        cat_levels[c] = levels
        keep = levels[1:] if drop_first else levels
        for lv in keep:
            fn = f"{c}={lv}"
            names.append(fn)
            source_of[fn] = c
        base = levels[0] if (drop_first and levels) else None
        prep.append((c, f"onehot:{'|'.join(levels)} drop={base}"))

    X, y, ids = [], [], []
    for r in rows:
        if r.get(target) is None:
            continue
        row: list[float] = []
        for c in cont:
            v = r.get(c)
            row.append(std.z(c, v) if (standardize and v is not None) else float(v or 0.0))
        for col, labels in bin_levels.items():
            lab = _bin_label(float(r.get(col) or 0.0), binned[col].edges, labels)
            for candidate in (labels[1:] if drop_first else labels):
                row.append(1.0 if lab == candidate else 0.0)
        for c, levels in cat_levels.items():
            val = str(r.get(c))
            for lv in (levels[1:] if drop_first else levels):
                row.append(1.0 if val == lv else 0.0)
        X.append(row)
        y.append(int(float(r[target])))
        ids.append(r.get(entity) if entity else len(ids))

    return DesignMatrix(feature_names=names, X=X, y=y, entity_ids=ids,
                        preprocessing=prep, standardizer=std, source_of=source_of)


def _bin_label(value: float, edges: list[float], labels: list[str]) -> str:
    for i, cut in enumerate(sorted(edges)):
        if value < cut:
            return labels[i]
    return labels[-1]


def stratified_split(y: list[int], entity_ids: list, *, test_frac: float = 0.25,
                     seed: int = 42) -> tuple[list[int], list[int]]:
    """Deterministic stratified split, keyed on a hash of the entity id.

    Hashing the id rather than shuffling an RNG makes the split reproducible across
    platforms, Python versions and numpy RNG stream changes — which matters because
    the whole provenance story depends on the fit being re-derivable. Stratifying
    preserves the class balance, so a test-set metric is comparable to a train one.
    """
    by_class: dict[int, list[int]] = {}
    for i, cls in enumerate(y):
        by_class.setdefault(int(cls), []).append(i)

    train, test = [], []
    for cls, idxs in sorted(by_class.items()):
        scored = sorted(
            idxs,
            key=lambda i: hashlib.sha256(
                f"{seed}:{entity_ids[i]}:{i}".encode()).hexdigest())
        n_test = int(round(len(scored) * test_frac))
        test += scored[:n_test]
        train += scored[n_test:]
    return sorted(train), sorted(test)


@dataclass
class Coefficient:
    name: str
    coef: float
    std_err: float
    z: float
    p_value: float
    odds_ratio: float
    or_ci_low: float
    or_ci_high: float
    unit: str = ""
    source_column: str = ""

    def as_dict(self) -> dict:
        return {"name": self.name, "coef": self.coef, "std_err": self.std_err,
                "z": self.z, "p_value": self.p_value, "odds_ratio": self.odds_ratio,
                "or_ci_low": self.or_ci_low, "or_ci_high": self.or_ci_high,
                "unit": self.unit, "source_column": self.source_column}


@dataclass
class LogitFit:
    coefficients: list[Coefficient]
    intercept: float
    n_train: int
    n_test: int
    converged: bool
    pseudo_r2: float
    flags: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {"coefficients": [c.as_dict() for c in self.coefficients],
                "intercept": self.intercept, "n_train": self.n_train,
                "n_test": self.n_test, "converged": self.converged,
                "pseudo_r2": self.pseudo_r2, "flags": list(self.flags)}


def fit_logit(dm: DesignMatrix, train_idx: list[int], *, seed: int = 42,
              maxiter: int = 100, sd_lookup: dict[str, float] | None = None
              ) -> LogitFit:
    """Fit unregularised logistic regression and return interpretable coefficients.

    Raises `SeparationError` rather than returning quietly-garbage numbers: statsmodels
    can emit a ConvergenceWarning and still hand back coefficients, and a rank-deficient
    design (a one-hot set that was not drop-first) yields meaningless standard errors.
    """
    import numpy as np
    import statsmodels.api as sm

    X = np.array([dm.X[i] for i in train_idx], dtype=float)
    y = np.array([dm.y[i] for i in train_idx], dtype=float)
    if X.size == 0:
        raise SeparationError("empty training set")
    if len(set(y.tolist())) < 2:
        raise SeparationError("training set contains only one class")

    Xc = sm.add_constant(X, has_constant="add")
    rank = int(np.linalg.matrix_rank(Xc))
    if rank < Xc.shape[1]:
        raise SeparationError(
            f"design matrix is rank-deficient ({rank} < {Xc.shape[1]} columns): "
            f"the encoded features are collinear. Check that one-hot encoding used "
            f"drop-first and that no constant column survived.")

    flags: list[str] = []
    try:
        import warnings
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            model = sm.Logit(y, Xc)
            res = model.fit(disp=0, maxiter=maxiter, method="newton")
        for w in caught:
            if "converge" in str(w.message).lower():
                flags.append(f"convergence warning: {w.message}")
    except Exception as e:                      # PerfectSeparationError et al.
        raise SeparationError(f"logistic fit failed: {type(e).__name__}: {e}") from e

    if not bool(getattr(res.mle_retvals, "get", lambda *_: True)("converged", True)):
        raise SeparationError("logistic fit did not converge")

    params, bse, pvals = res.params, res.bse, res.pvalues
    ci = res.conf_int()
    coefs: list[Coefficient] = []
    for j, name in enumerate(dm.feature_names):
        k = j + 1                                # 0 is the intercept
        b, se = float(params[k]), float(bse[k])
        lo, hi = float(ci[k][0]), float(ci[k][1])
        src = dm.source_of.get(name, name)
        if "=" in name:
            unit = f"vs baseline of '{src}'"
        elif sd_lookup and src in sd_lookup:
            unit = f"per 1 SD ({sd_lookup[src]:.4g}) of {src}"
        else:
            unit = f"per 1 unit of {src}"
        coefs.append(Coefficient(
            name=name, coef=b, std_err=se, z=float(params[k] / se) if se else 0.0,
            p_value=float(pvals[k]), odds_ratio=math.exp(b),
            or_ci_low=math.exp(lo), or_ci_high=math.exp(hi),
            unit=unit, source_column=src))

    max_abs = max((abs(c.coef) for c in coefs), default=0.0)
    if max_abs > 10:
        flags.append(
            f"|coefficient| up to {max_abs:.1f} — near-separation; the odds ratio and "
            f"its interval are unstable and should not be quoted precisely")

    return LogitFit(coefficients=coefs, intercept=float(params[0]),
                    n_train=len(train_idx), n_test=dm.n - len(train_idx),
                    converged=True, pseudo_r2=float(res.prsquared),
                    flags=tuple(flags))


def predict_proba(fit: LogitFit, dm: DesignMatrix, idx: list[int]) -> list[float]:
    by_name = {c.name: c.coef for c in fit.coefficients}
    weights = [by_name.get(n, 0.0) for n in dm.feature_names]
    out = []
    for i in idx:
        z = fit.intercept + sum(w * v for w, v in zip(weights, dm.X[i]))
        out.append(1.0 / (1.0 + math.exp(-max(-500.0, min(500.0, z)))))
    return out


def phrase_odds_ratio(c: Coefficient, *, causal: bool = False) -> str:
    """The ONE place model prose is generated, so the framing cannot drift.

    Always associational. "Customers with X show N times the odds" — never
    "X increases churn by N%", which asserts a causal mechanism an observational fit
    cannot support no matter how small the p-value.
    """
    if causal:
        raise ValueError(
            "causal phrasing is not available: this is an observational fit, and no "
            "coefficient from it licenses a causal claim")
    direction = "higher" if c.odds_ratio >= 1 else "lower"
    factor = c.odds_ratio if c.odds_ratio >= 1 else (1 / c.odds_ratio if c.odds_ratio else 0)
    lo, hi = sorted((c.or_ci_low, c.or_ci_high))
    return (f"Customers {c.unit} show **{factor:.2f}x {direction} odds** of the "
            f"outcome (95% CI {lo:.2f}-{hi:.2f}, p={c.p_value:.3g}). This is an "
            f"association measured in this dataset, not a demonstrated cause.")
