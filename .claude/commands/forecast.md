---
description: Forecast a metric's time series with trend, anomaly, and seasonality analysis.
argument-hint: <metric> [horizon] [period]
---

Forecast: **$ARGUMENTS**

Delegate to the `forecaster` agent, or use `atlas/lib/forecast.py`. Pull the metric's
time series (via `Connector.run()`), then:
- `detect_anomalies(series)` first (spikes distort the trend)
- `fit_trend(series)` for direction + r²
- `seasonality_strength(series, period)` if a period is given
- `forecast(series, horizon, period=)` for point forecasts + an uncertainty band

Report the method used, the trend, any anomalies, and the forecast **with its band** —
never a bare point. If the series is too short/noisy, give a range and say why.
