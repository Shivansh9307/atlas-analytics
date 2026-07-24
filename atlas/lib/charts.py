"""Storytelling-with-Data charts (matplotlib -> PNG).

Follows the dataviz method: form first, decluttered marks, ONE highlight color with
everything else muted, categorical hues in fixed order (never cycled), one axis,
recessive grid/axes, action titles (a claim, not a label), direct labels over
legends where possible. Palette comes from the validated theme (theme_loader).

Rendering functions save a PNG and return its path. Pure helpers (collision math,
funnel drop-offs, tornado ordering) are separated so they are unit-testable without
inspecting pixels.
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")  # headless; no display needed
import matplotlib.pyplot as plt  # noqa: E402

from pathlib import Path  # noqa: E402

from atlas.lib.theme_loader import Theme, load_theme  # noqa: E402


# --------------------- pure helpers (unit-testable) ---------------------
Box = tuple[float, float, float, float]  # (x0, y0, x1, y1)


def _overlap(a: Box, b: Box) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def check_label_collisions(boxes: list[Box]) -> list[tuple[int, int]]:
    """Return index pairs of overlapping label boxes."""
    pairs = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if _overlap(boxes[i], boxes[j]):
                pairs.append((i, j))
    return pairs


def resolve_collisions(boxes: list[Box], *, max_shift_steps: int = 20):
    """Offset-then-drop strategy. Returns (new_boxes, actions).

    Each colliding label is shifted down by its own height until clear; if it can't
    be cleared within the step budget it is dropped (None) — the dataviz rule: drop
    the least-important label rather than ship an overlap.
    """
    boxes = [tuple(b) for b in boxes]
    actions = ["keep"] * len(boxes)
    for i in range(len(boxes)):
        if boxes[i] is None:
            continue
        h = boxes[i][3] - boxes[i][1]
        steps = 0
        while any(boxes[j] is not None and j != i and _overlap(boxes[i], boxes[j])
                  for j in range(len(boxes))):
            if steps >= max_shift_steps:
                boxes[i] = None
                actions[i] = "drop"
                break
            x0, y0, x1, y1 = boxes[i]
            boxes[i] = (x0, y0 - h, x1, y1 - h)   # shift down
            actions[i] = "offset"
            steps += 1
    return boxes, actions


def funnel_dropoffs(values: list[float]) -> dict:
    """Per-stage conversion + the biggest drop-off. Pure math for a funnel."""
    out = []
    biggest = {"index": None, "drop": -1.0}
    for i, v in enumerate(values):
        prev = values[i - 1] if i > 0 else None
        conv = (v / prev) if (prev not in (None, 0)) else 1.0
        drop = (prev - v) if prev is not None else 0.0
        out.append({"stage": i, "value": v, "conversion": round(conv, 4), "drop": drop})
        if prev is not None and drop > biggest["drop"]:
            biggest = {"index": i, "drop": drop}
    return {"stages": out, "biggest_drop_index": biggest["index"]}


def tornado_order(bars: list[dict]) -> list[dict]:
    """Sort tornado bars by swing desc (bars: {name, low, high})."""
    return sorted(bars, key=lambda b: abs(b["high"] - b["low"]), reverse=True)


# --------------------- rendering ---------------------
def _style(ax, theme: Theme) -> None:
    ax.set_facecolor(theme.surface)
    ax.figure.set_facecolor(theme.surface)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(theme.text_secondary)
        ax.spines[spine].set_linewidth(0.8)
    ax.tick_params(colors=theme.text_secondary, labelsize=9, length=0)
    ax.grid(axis="y", color=theme.grid, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)


def _action_title(ax, title: str, subtitle: str, theme: Theme) -> None:
    ax.set_title(title, loc="left", fontsize=13, fontweight="bold",
                 color=theme.text_primary, pad=18)
    if subtitle:
        ax.text(0.0, 1.02, subtitle, transform=ax.transAxes, fontsize=9,
                color=theme.text_secondary, va="bottom")


def save_chart(fig, path: str | Path, dpi: int = 150) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


def bar_chart(categories, values, path, *, highlight_index: int | None = None,
              title: str = "", subtitle: str = "", theme: Theme | None = None,
              orient: str = "column", value_fmt: str = "{:.1f}") -> Path:
    """Column/bar chart. One highlighted bar (theme.highlight); rest muted. Direct
    value labels; no legend (single series)."""
    theme = theme or load_theme()
    fig, ax = plt.subplots(figsize=(6.5, 4))
    _style(ax, theme)
    colors = [theme.highlight if i == highlight_index else theme.muted
              for i in range(len(values))]
    if highlight_index is None:
        colors = [theme.highlight] * len(values)
    if orient == "bar":
        ax.barh(categories, values, color=colors, zorder=3)
        for i, v in enumerate(values):
            ax.text(v, i, " " + value_fmt.format(v), va="center",
                    color=theme.text_primary, fontsize=9)
        ax.grid(axis="x", color=theme.grid, linewidth=0.8)
        ax.grid(axis="y", visible=False)
    else:
        ax.bar(categories, values, color=colors, zorder=3)
        for i, v in enumerate(values):
            ax.text(i, v, value_fmt.format(v), ha="center", va="bottom",
                    color=theme.text_primary, fontsize=9)
    _action_title(ax, title, subtitle, theme)
    return save_chart(fig, path)


def funnel_waterfall(stages, values, path, *, title: str = "", subtitle: str = "",
                     theme: Theme | None = None) -> Path:
    """Funnel as descending bars; the biggest drop-off stage is highlighted."""
    theme = theme or load_theme()
    info = funnel_dropoffs(values)
    big = info["biggest_drop_index"]
    fig, ax = plt.subplots(figsize=(6.5, 4))
    _style(ax, theme)
    colors = [theme.status["critical"] if i == big else theme.muted
              for i in range(len(values))]
    ax.bar(stages, values, color=colors, zorder=3)
    for s in info["stages"]:
        ax.text(s["stage"], s["value"], f"{s['value']:.0f}\n{s['conversion']*100:.0f}%",
                ha="center", va="bottom", color=theme.text_primary, fontsize=8)
    _action_title(ax, title, subtitle, theme)
    return save_chart(fig, path)


def tornado_chart(bars, path, *, title: str = "", subtitle: str = "",
                  theme: Theme | None = None) -> Path:
    """Sensitivity tornado: horizontal low/high spans, widest swing on top."""
    theme = theme or load_theme()
    ordered = tornado_order(bars)
    fig, ax = plt.subplots(figsize=(6.5, 4))
    _style(ax, theme)
    ax.grid(axis="x", color=theme.grid, linewidth=0.8)
    ax.grid(axis="y", visible=False)
    names = [b["name"] for b in ordered][::-1]      # widest at top
    for y, b in enumerate(ordered[::-1]):
        lo, hi = sorted((b["low"], b["high"]))
        ax.barh(y, hi - lo, left=lo, color=theme.highlight, zorder=3, height=0.6)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names)
    _action_title(ax, title, subtitle, theme)
    return save_chart(fig, path)


def retention_heatmap(matrix, offsets, path, *, title: str = "", subtitle: str = "",
                      theme: Theme | None = None) -> Path:
    """Cohort × offset retention as a sequential-blue heatmap.

    `matrix`: dict cohort -> {offset -> rate}. Uses the theme's sequential ramp.
    """
    from matplotlib.colors import LinearSegmentedColormap
    theme = theme or load_theme()
    cohorts = list(matrix)
    grid = [[matrix[c].get(o, float("nan")) for o in offsets] for c in cohorts]
    cmap = LinearSegmentedColormap.from_list("seq", theme.sequential)
    fig, ax = plt.subplots(figsize=(6.5, 0.5 * len(cohorts) + 2))
    ax.set_facecolor(theme.surface)
    fig.set_facecolor(theme.surface)
    im = ax.imshow(grid, cmap=cmap, aspect="auto", vmin=0, vmax=1)
    ax.set_xticks(range(len(offsets)), [str(o) for o in offsets])
    ax.set_yticks(range(len(cohorts)), cohorts)
    for i in range(len(cohorts)):
        for j in range(len(offsets)):
            v = grid[i][j]
            if v == v:  # not NaN
                ax.text(j, i, f"{v*100:.0f}", ha="center", va="center",
                        color=theme.text_primary, fontsize=8)
    fig.colorbar(im, ax=ax, shrink=0.8)
    _action_title(ax, title, subtitle, theme)
    return save_chart(fig, path)


def kpi_card(value: str, label: str, path, *, delta: str = "", good: bool = True,
             theme: Theme | None = None) -> Path:
    """A hero-number card — sometimes the right 'chart' is one big number."""
    theme = theme or load_theme()
    fig, ax = plt.subplots(figsize=(3.2, 2))
    ax.set_facecolor(theme.surface)
    fig.set_facecolor(theme.surface)
    ax.axis("off")
    ax.text(0.5, 0.62, value, ha="center", va="center", fontsize=34,
            fontweight="bold", color=theme.text_primary)
    ax.text(0.5, 0.22, label, ha="center", va="center", fontsize=11,
            color=theme.text_secondary)
    if delta:
        c = theme.status["good"] if good else theme.status["critical"]
        ax.text(0.5, 0.02, delta, ha="center", va="center", fontsize=11, color=c)
    return save_chart(fig, path)
