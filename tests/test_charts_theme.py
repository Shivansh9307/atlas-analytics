from atlas.lib import charts
from atlas.lib.theme_loader import (
    contrast_ratio, load_theme, passes_wcag, relative_luminance,
)


# ---- theme + WCAG ----
def test_theme_loads_validated_palette():
    t = load_theme("default")
    assert len(t.categorical) == 8
    assert t.categorical[0] == "#2a78d6"       # validated blue, slot 1
    assert t.color(99) == t.muted               # past palette -> Other/muted


def test_contrast_ratio_known_values():
    assert contrast_ratio("#000000", "#ffffff") == 21.0
    assert contrast_ratio("#ffffff", "#ffffff") == 1.0
    # primary ink on the surface must be readable
    t = load_theme()
    assert passes_wcag(t.text_primary, t.surface, level="AA")


def test_relative_luminance_bounds():
    assert relative_luminance("#000000") == 0.0
    assert round(relative_luminance("#ffffff"), 4) == 1.0


# ---- pure chart helpers ----
def test_collision_detection():
    a = (0, 0, 10, 10)
    b = (5, 5, 15, 15)      # overlaps a
    c = (100, 100, 110, 110)  # separate
    pairs = charts.check_label_collisions([a, b, c])
    assert (0, 1) in pairs
    assert (0, 2) not in pairs


def test_collision_resolution_separates_or_drops():
    a = (0, 0, 10, 10)
    b = (0, 0, 10, 10)       # identical -> must be resolved
    new, actions = charts.resolve_collisions([a, b])
    live = [x for x in new if x is not None]
    # after resolution, no two live boxes overlap
    assert charts.check_label_collisions(live) == []
    assert "offset" in actions or "drop" in actions


def test_funnel_dropoffs_finds_biggest():
    info = charts.funnel_dropoffs([1000, 900, 300, 280])
    assert info["biggest_drop_index"] == 2      # 900 -> 300 is the biggest drop
    assert info["stages"][1]["conversion"] == 0.9


def test_tornado_order_by_swing():
    bars = [{"name": "a", "low": 0, "high": 1}, {"name": "b", "low": 0, "high": 5}]
    assert charts.tornado_order(bars)[0]["name"] == "b"


# ---- rendering produces real files ----
def test_bar_chart_renders(tmp_path):
    p = charts.bar_chart(["Q1", "Q2"], [60.0, 56.0], tmp_path / "bar.png",
                         highlight_index=1, title="Margin fell 4pts", subtitle="EMEA")
    assert p.exists() and p.stat().st_size > 500


def test_funnel_and_tornado_render(tmp_path):
    f = charts.funnel_waterfall(["View", "Cart", "Buy"], [1000, 400, 350],
                                tmp_path / "funnel.png", title="Checkout leak")
    t = charts.tornado_chart([{"name": "vol", "low": 1, "high": 9},
                              {"name": "rate", "low": 3, "high": 5}],
                             tmp_path / "tornado.png", title="Sensitivity")
    assert f.exists() and t.exists()


def test_retention_heatmap_renders(tmp_path):
    matrix = {"Jan": {0: 1.0, 1: 0.8}, "Feb": {0: 1.0, 1: 0.5}}
    p = charts.retention_heatmap(matrix, [0, 1], tmp_path / "heat.png", title="Retention")
    assert p.exists()
