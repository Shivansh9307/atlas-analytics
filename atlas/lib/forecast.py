"""Time-series: trend, anomalies, seasonality, and a simple honest forecast.

Deterministic and dependency-light. Forecasting here is intentionally modest — a
trend (+ optional seasonal-naive) extrapolation with a residual-based interval — and
labelled as such. Atlas would rather ship a forecast it can defend than a black box.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class TrendFit:
    slope: float
    intercept: float
    direction: str          # "up" | "down" | "flat"
    r2: float

    def predict(self, x: float) -> float:
        return self.slope * x + self.intercept


def fit_trend(series: list[float]) -> TrendFit:
    """Ordinary least-squares line over 0..n-1."""
    n = len(series)
    if n < 2:
        return TrendFit(0.0, series[0] if series else 0.0, "flat", 0.0)
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(series) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, series))
    slope = sxy / sxx if sxx else 0.0
    intercept = my - slope * mx
    ss_tot = sum((y - my) ** 2 for y in series)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, series))
    r2 = (1 - ss_res / ss_tot) if ss_tot else 1.0
    direction = "up" if slope > 1e-9 else "down" if slope < -1e-9 else "flat"
    return TrendFit(slope, intercept, direction, r2)


def detect_anomalies(series: list[float], *, z: float = 3.0) -> list[int]:
    """Indices whose residual from trend exceeds z robust-MADs. Empty if none."""
    if len(series) < 3:
        return []
    fit = fit_trend(series)
    resid = [y - fit.predict(x) for x, y in enumerate(series)]
    med = _median(resid)
    mad = _median([abs(r - med) for r in resid]) or 1e-9
    # 1.4826 scales MAD to a std-equivalent for normal data
    return [i for i, r in enumerate(resid) if abs(r - med) / (1.4826 * mad) > z]


def seasonality_strength(series: list[float], period: int) -> float:
    """0..1 seasonal strength via STL (reuses stats.deseasonalize)."""
    from atlas.lib.stats import deseasonalize
    res = deseasonalize(series, period)
    return round(res.get("seasonal_strength", 0.0), 4) if "seasonal_strength" in res else 0.0


@dataclass
class Forecast:
    horizon: int
    points: list[float]
    lower: list[float]
    upper: list[float]
    method: str
    note: str = ""

    def as_dict(self) -> dict:
        return {"horizon": self.horizon, "method": self.method,
                "points": [round(p, 4) for p in self.points],
                "lower": [round(p, 4) for p in self.lower],
                "upper": [round(p, 4) for p in self.upper], "note": self.note}


def forecast(series: list[float], horizon: int, *, period: int | None = None,
             z: float = 1.96) -> Forecast:
    """Trend (+ optional seasonal-naive) extrapolation with a residual-based band."""
    if len(series) < 2:
        val = series[0] if series else 0.0
        return Forecast(horizon, [val] * horizon, [val] * horizon, [val] * horizon,
                        "naive", "series too short for a trend")
    fit = fit_trend(series)
    n = len(series)
    resid = [y - fit.predict(x) for x, y in enumerate(series)]
    sigma = _std(resid)

    seasonal = [0.0] * (period or 1)
    method = "linear-trend"
    if period and len(series) >= 2 * period:
        # average detrended value per seasonal position
        buckets: dict[int, list[float]] = {}
        for x, y in enumerate(series):
            buckets.setdefault(x % period, []).append(y - fit.predict(x))
        seasonal = [sum(buckets[i]) / len(buckets[i]) for i in range(period)]
        method = "trend+seasonal-naive"

    points, lower, upper = [], [], []
    for h in range(1, horizon + 1):
        x = n - 1 + h
        base = fit.predict(x)
        if period and method.startswith("trend+"):
            base += seasonal[x % period]
        points.append(base)
        lower.append(base - z * sigma)
        upper.append(base + z * sigma)
    return Forecast(horizon, points, lower, upper, method,
                    f"trend r²={fit.r2:.3f}, residual σ={sigma:.4f}")


# --- small helpers ---
def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return 0.0
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _std(xs: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
