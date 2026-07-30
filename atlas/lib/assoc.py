"""Association and effect-size maths for driver analysis.

The existing `stats.py` covers two-sample significance (`two_proportion_ztest`,
`welch_t_test`) and Wilson intervals. What was missing — and what ranking drivers
against an outcome needs — is the *effect size* half: how big is the association,
not merely whether it is distinguishable from zero. On 64k rows almost everything
is "significant"; only effect size separates a real driver from a rounding error.

Everything here takes summary counts or `list[dict]` with column names as keyword
arguments, matching the house style, so it is unit-testable against hand-computed
fixtures with no database and no dataframe.

Direction convention: a positive `gap_pp` / `lift_vs_base` above 1.0 means the group
churns MORE than the base. Every returned effect keeps its sign.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from atlas.config import TOLERANCES
from atlas.lib.stats import TestResult, proportion_ci

__all__ = [
    "GroupRate", "EffectSize", "group_rates", "chi_square_independence",
    "cramers_v", "cohens_d", "odds_ratio", "relative_risk",
    "point_biserial_from_summary",
]


@dataclass
class GroupRate:
    level: str
    n: int
    x: int                      # events in this level
    rate: float
    ci_low: float
    ci_high: float
    lift_vs_base: float         # rate / base_rate; 1.0 == exactly the base rate
    gap_pp: float               # (rate - base_rate) * 100, signed

    def as_dict(self) -> dict:
        return {"level": self.level, "n": self.n, "x": self.x, "rate": self.rate,
                "ci_low": self.ci_low, "ci_high": self.ci_high,
                "lift_vs_base": self.lift_vs_base, "gap_pp": self.gap_pp}


@dataclass
class EffectSize:
    name: str
    value: float
    ci_low: float | None = None
    ci_high: float | None = None
    detail: str = ""
    flags: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {"name": self.name, "value": self.value, "ci_low": self.ci_low,
                "ci_high": self.ci_high, "detail": self.detail,
                "flags": list(self.flags)}


def group_rates(rows: list[dict], *, level_key: str, n_key: str = "n",
                x_key: str = "x", base_rate: float | None = None) -> list[GroupRate]:
    """Per-level event rate with a Wilson CI, lift and signed gap vs the base.

    `base_rate` defaults to the pooled rate across the supplied rows, which is the
    right comparison when the rows are the complete partition of the table.
    """
    total_n = sum(int(r[n_key] or 0) for r in rows)
    total_x = sum(int(r[x_key] or 0) for r in rows)
    base = base_rate if base_rate is not None else (total_x / total_n if total_n else 0.0)
    out: list[GroupRate] = []
    for r in rows:
        n, x = int(r[n_key] or 0), int(r[x_key] or 0)
        rate = x / n if n else 0.0
        lo, hi = proportion_ci(x, n) if n else (0.0, 0.0)
        out.append(GroupRate(
            level=str(r[level_key]), n=n, x=x, rate=rate, ci_low=lo, ci_high=hi,
            lift_vs_base=(rate / base) if base else 0.0,
            gap_pp=(rate - base) * 100.0))
    return out


def chi_square_independence(table: list[list[int]], *,
                            alpha: float | None = None) -> TestResult:
    """Pearson chi-square test of independence over an r x c contingency table.

    Flags low expected cell counts rather than silently reporting a p-value the
    approximation does not support — the same discipline as `two_proportion_ztest`'s
    under-powered flag.
    """
    alpha = alpha or TOLERANCES.alpha
    rows = [r for r in table if sum(r) > 0]
    if len(rows) < 2 or len(rows[0]) < 2:
        return TestResult("chi_square", None, None, None,
                          "needs at least a 2x2 table", ("undefined",))
    n = sum(sum(r) for r in rows)
    if n == 0:
        return TestResult("chi_square", None, None, None, "empty table", ("undefined",))

    row_tot = [sum(r) for r in rows]
    col_tot = [sum(r[j] for r in rows) for j in range(len(rows[0]))]
    chi2 = 0.0
    min_expected = float("inf")
    for i, r in enumerate(rows):
        for j, obs in enumerate(r):
            exp = row_tot[i] * col_tot[j] / n
            if exp <= 0:
                continue
            min_expected = min(min_expected, exp)
            chi2 += (obs - exp) ** 2 / exp
    dof = (len(rows) - 1) * (len(col_tot) - 1)

    p = _chi2_sf(chi2, dof)
    flags: tuple[str, ...] = ()
    if min_expected < 5:
        flags += (f"low expected cell count ({min_expected:.1f} < 5); "
                  "chi-square approximation unreliable",)
    return TestResult("chi_square", chi2, p, (p < alpha) if p is not None else None,
                      f"dof={dof}, n={n}, min_expected={min_expected:.1f}", flags)


def cramers_v(table: list[list[int]]) -> float:
    """Cramér's V — chi-square normalised to [0, 1] so it is comparable across
    dimensions with different level counts."""
    res = chi_square_independence(table)
    if res.statistic is None:
        return 0.0
    rows = [r for r in table if sum(r) > 0]
    n = sum(sum(r) for r in rows)
    k = min(len(rows), len(rows[0]))
    if n == 0 or k < 2:
        return 0.0
    return math.sqrt(res.statistic / (n * (k - 1)))


def cohens_d(n1: int, mean1: float, sd1: float,
             n2: int, mean2: float, sd2: float) -> EffectSize:
    """Standardised mean difference, from summary statistics only.

    Computed from a grouped SQL result (`count`/`avg`/`stddev_samp` per class) so a
    64k-row table never has to be pulled into Python to size the effect.
    """
    if n1 < 2 or n2 < 2:
        return EffectSize("cohens_d", 0.0, detail="need n>=2 per group",
                          flags=("undefined",))
    pooled_var = (((n1 - 1) * sd1 ** 2) + ((n2 - 1) * sd2 ** 2)) / (n1 + n2 - 2)
    pooled = math.sqrt(pooled_var) if pooled_var > 0 else 0.0
    if pooled == 0:
        return EffectSize("cohens_d", 0.0, detail="zero pooled sd", flags=("undefined",))
    d = (mean1 - mean2) / pooled
    se = math.sqrt((n1 + n2) / (n1 * n2) + d ** 2 / (2 * (n1 + n2)))
    flags = () if min(n1, n2) >= 30 else ("small sample (<30 in a group)",)
    return EffectSize("cohens_d", d, d - 1.96 * se, d + 1.96 * se,
                      f"n1={n1}, n2={n2}, pooled_sd={pooled:.4f}", flags)


def odds_ratio(a: int, b: int, c: int, d: int, *, conf: float = 0.95) -> EffectSize:
    """Odds ratio for a 2x2 table [[a, b], [c, d]] with a Woolf log-SE interval.

    `a` = exposed & event, `b` = exposed & no event, `c` = unexposed & event,
    `d` = unexposed & no event. A Haldane-Anscombe 0.5 correction is applied when
    any cell is zero (and flagged, because it is an adjustment to the data).
    """
    flags: tuple[str, ...] = ()
    a_, b_, c_, d_ = float(a), float(b), float(c), float(d)
    if min(a_, b_, c_, d_) == 0:
        a_, b_, c_, d_ = a_ + 0.5, b_ + 0.5, c_ + 0.5, d_ + 0.5
        flags += ("zero cell; Haldane-Anscombe 0.5 correction applied",)
    if b_ == 0 or c_ == 0 or d_ == 0:
        return EffectSize("odds_ratio", 0.0, detail="degenerate table",
                          flags=flags + ("undefined",))
    or_ = (a_ * d_) / (b_ * c_)
    se = math.sqrt(1 / a_ + 1 / b_ + 1 / c_ + 1 / d_)
    z = 1.959963984540054 if abs(conf - 0.95) < 1e-9 else _z_for(conf)
    return EffectSize("odds_ratio", or_, math.exp(math.log(or_) - z * se),
                      math.exp(math.log(or_) + z * se),
                      f"2x2 [[{a},{b}],[{c},{d}]]", flags)


def relative_risk(a: int, b: int, c: int, d: int, *, conf: float = 0.95) -> EffectSize:
    """Risk ratio for [[a, b], [c, d]] — usually the more intuitive of the two.

    Unlike the odds ratio this is a ratio of *probabilities*, so "2x the risk" means
    what a reader expects it to mean.
    """
    flags: tuple[str, ...] = ()
    n1, n0 = a + b, c + d
    if n1 == 0 or n0 == 0 or a == 0 or c == 0:
        a_, b_, c_, d_ = a + 0.5, b + 0.5, c + 0.5, d + 0.5
        n1, n0 = a_ + b_, c_ + d_
        flags += ("zero cell; 0.5 correction applied",)
    else:
        a_, c_ = float(a), float(c)
    r1, r0 = a_ / n1, c_ / n0
    if r0 == 0:
        return EffectSize("relative_risk", 0.0, detail="zero baseline risk",
                          flags=flags + ("undefined",))
    rr = r1 / r0
    se = math.sqrt(1 / a_ - 1 / n1 + 1 / c_ - 1 / n0)
    z = 1.959963984540054 if abs(conf - 0.95) < 1e-9 else _z_for(conf)
    return EffectSize("relative_risk", rr, math.exp(math.log(rr) - z * se),
                      math.exp(math.log(rr) + z * se),
                      f"risk {r1:.4f} vs {r0:.4f}", flags)


def point_biserial_from_summary(n1: int, mean1: float, n0: int, mean0: float,
                                sd_all: float) -> float:
    """Point-biserial r from group means — a cross-check on DuckDB's `corr()`.

    Having a second, independently-coded route to the same number is what lets the
    red-team compare rather than trust.
    """
    n = n1 + n0
    if n == 0 or sd_all <= 0:
        return 0.0
    return (mean1 - mean0) / sd_all * math.sqrt(n1 * n0 / (n * n))


# --------------------------- small numeric helpers ---------------------------
def _z_for(conf: float) -> float:
    from atlas.lib.stats import _z_for_conf
    return _z_for_conf(1 - (1 - conf) / 2)


def _chi2_sf(x: float, dof: int) -> float | None:
    """Upper-tail chi-square probability.

    Uses scipy when available (same lazy-import idiom as `stats.welch_t_test`) and
    otherwise falls back to a closed form that is exact for even dof and uses the
    Wilson-Hilferty approximation for odd dof. Returning a slightly approximate p
    beats returning None and silently dropping the significance flag.
    """
    if x < 0 or dof <= 0:
        return None
    try:
        from scipy import stats as _sp
        return float(_sp.chi2.sf(x, dof))
    except Exception:
        pass
    if dof % 2 == 0:                      # exact: sum of Poisson terms
        k = dof // 2
        term = math.exp(-x / 2)
        total = term
        for i in range(1, k):
            term *= (x / 2) / i
            total += term
        return min(1.0, max(0.0, total))
    # Wilson-Hilferty: (X/dof)^(1/3) is approximately normal
    t = (x / dof) ** (1 / 3)
    mu = 1 - 2 / (9 * dof)
    sigma = math.sqrt(2 / (9 * dof))
    z = (t - mu) / sigma
    return 0.5 * math.erfc(z / math.sqrt(2))
