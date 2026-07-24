from atlas.lib.forecast import (
    detect_anomalies, fit_trend, forecast, seasonality_strength,
)


def test_perfect_line_fit_and_forecast():
    series = [2, 4, 6, 8, 10]          # slope 2, intercept 2
    fit = fit_trend(series)
    assert round(fit.slope, 6) == 2.0
    assert round(fit.intercept, 6) == 2.0
    assert fit.direction == "up"
    assert round(fit.r2, 6) == 1.0
    fc = forecast(series, horizon=2)
    assert round(fc.points[0], 6) == 12.0    # next in the line
    assert round(fc.points[1], 6) == 14.0
    # perfect fit -> zero residual -> band collapses to the point
    assert round(fc.upper[0] - fc.lower[0], 6) == 0.0


def test_downward_trend_direction():
    assert fit_trend([10, 8, 6, 4]).direction == "down"


def test_anomaly_detection_flags_the_spike():
    series = [1, 2, 3, 4, 5, 6, 7, 8, 9, 50, 11, 12]   # index 9 is the spike
    idx = detect_anomalies(series, z=3.0)
    assert 9 in idx


def test_no_anomaly_on_clean_line():
    assert detect_anomalies([1, 2, 3, 4, 5, 6, 7, 8], z=3.0) == []


def test_seasonal_forecast_repeats_pattern():
    # period-2 seasonal signal; the series ends "high" so the next point is the "low"
    series = [10, 20, 10, 20, 10, 20, 10, 20]
    fc = forecast(series, horizon=2, period=2)
    assert fc.method == "trend+seasonal-naive"
    # the low/high alternation is carried forward
    assert fc.points[0] < fc.points[1]
    assert 5 < fc.points[0] < 16 and 15 < fc.points[1] < 26


def test_seasonality_strength_high_for_strong_signal():
    series = [10, 20, 10, 20, 10, 20, 10, 20, 10, 20, 10, 20]
    assert seasonality_strength(series, period=2) > 0.5
