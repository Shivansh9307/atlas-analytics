"""Statistical testing helpers. Thin, honest wrappers over scipy/statsmodels.

Every function reports the number AND a plain flag (e.g. under-powered) so the
statistician agent never hand-waves. No function invents data.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from atlas.config import TOLERANCES


@dataclass
class TestResult:
    name: str
    statistic: float | None
    p_value: float | None
    significant: bool | None
    detail: str = ""
    flags: tuple[str, ...] = ()


def two_proportion_ztest(x1: int, n1: int, x2: int, n2: int,
                         alpha: float | None = None) -> TestResult:
    """Compare two proportions (e.g. conversion, defect rate)."""
    alpha = alpha or TOLERANCES.alpha
    if min(n1, n2) == 0:
        return TestResult("two_proportion_ztest", None, None, None,
                          "empty sample", ("undefined",))
    p1, p2 = x1 / n1, x2 / n2
    p = (x1 + x2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return TestResult("two_proportion_ztest", 0.0, 1.0, False, "zero variance")
    z = (p1 - p2) / se
    # normal two-sided p
    p_value = 2 * (1 - _norm_cdf(abs(z)))
    flags = []
    # rule-of-thumb power check: need >=10 successes & failures per arm
    if min(x1, n1 - x1, x2, n2 - x2) < 10:
        flags.append("under-powered: <10 events per cell")
    return TestResult("two_proportion_ztest", z, p_value, p_value < alpha,
                      f"p1={p1:.4f} p2={p2:.4f}", tuple(flags))


def welch_t_test(sample_a, sample_b, alpha: float | None = None) -> TestResult:
    alpha = alpha or TOLERANCES.alpha
    try:
        from scipy import stats
    except Exception:  # pragma: no cover
        return TestResult("welch_t", None, None, None, "scipy missing")
    a, b = list(sample_a), list(sample_b)
    if len(a) < 2 or len(b) < 2:
        return TestResult("welch_t", None, None, None, "n<2", ("undefined",))
    t, p = stats.ttest_ind(a, b, equal_var=False)
    flags = []
    if min(len(a), len(b)) < 30:
        flags.append("small sample (n<30): t-approx, check normality")
    return TestResult("welch_t", float(t), float(p), bool(p < alpha),
                      f"na={len(a)} nb={len(b)}", tuple(flags))


def proportion_ci(x: int, n: int, conf: float = 0.95) -> tuple[float, float]:
    """Wilson score interval — robust for small n."""
    if n == 0:
        return (0.0, 0.0)
    z = _z_for_conf(conf)
    phat = x / n
    denom = 1 + z**2 / n
    center = (phat + z**2 / (2 * n)) / denom
    half = (z * math.sqrt(phat * (1 - phat) / n + z**2 / (4 * n**2))) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def min_detectable_effect(n_per_arm: int, base_rate: float,
                          power: float = 0.8, alpha: float = 0.05) -> float | None:
    """Approx MDE (absolute pct points) for a two-proportion test at given n/arm."""
    if n_per_arm <= 0 or not (0 < base_rate < 1):
        return None
    z_a = _z_for_conf(1 - alpha)
    z_b = _z_for_conf(power)
    p = base_rate
    mde = (z_a + z_b) * math.sqrt(2 * p * (1 - p) / n_per_arm)
    return mde


def deseasonalize(series: list[float], period: int) -> dict:
    """Return a seasonally-adjusted series via statsmodels STL when feasible."""
    if len(series) < 2 * period:
        return {"adjusted": series, "note": f"insufficient length for STL (need >= {2*period})"}
    try:
        import numpy as np
        from statsmodels.tsa.seasonal import STL
        res = STL(np.asarray(series, dtype=float), period=period, robust=True).fit()
        adj = (np.asarray(series) - res.seasonal).tolist()
        return {"adjusted": adj, "seasonal_strength": float(_seasonal_strength(res))}
    except Exception as e:  # pragma: no cover
        return {"adjusted": series, "note": f"STL failed: {e}"}


# --- small numeric helpers (avoid importing scipy just for a normal CDF) ---
def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _z_for_conf(conf: float) -> float:
    # inverse normal via rational approximation (Acklam) — adequate here
    if conf <= 0 or conf >= 1:
        conf = min(max(conf, 1e-6), 1 - 1e-6)
    # for a one-sided tail prob p = conf, return z s.t. Phi(z)=conf
    return _inv_norm(conf)


def _inv_norm(p: float) -> float:
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def _seasonal_strength(res) -> float:
    import numpy as np
    var_resid = np.var(res.resid)
    var_sr = np.var(res.resid + res.seasonal)
    return max(0.0, 1 - var_resid / var_sr) if var_sr > 0 else 0.0
