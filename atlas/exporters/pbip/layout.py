"""Explicit report layout — coordinates, not "arrange it yourself".

Every visual's x/y/width/height is fixed here and tabulated in LAYOUT_GUIDE.md, so
the emitted report is a finished dashboard rather than a pile of visuals at the
origin. Canvas is the Power BI default 1280x720.

Three pages, matching how the analysis actually reads:
  Overview  — the KPI row plus the two biggest segment splits
  Drivers   — what moves the outcome, with the measured threshold bands first
  Risk List — the per-entity ranked table, only when scores exist
"""
from __future__ import annotations

from atlas.exporters.pbip.pbir import Page, Visual, column_field, measure_field
from atlas.exporters.pbip.schemas import (
    CANVAS_H, CANVAS_W, VISUAL_BAR, VISUAL_CARD, VISUAL_COLUMN, VISUAL_SLICER,
    VISUAL_TABLE,
)

__all__ = ["build_pages", "render_guide"]

PAD = 20
KPI_H = 120
KPI_Y = 20


def _kpi_row(table: str, names: list[str]) -> list[Visual]:
    """Up to four KPI cards across the top, evenly divided."""
    wanted = [n for n in ("Churn Rate", "Revenue at Risk", "Total Customers",
                          "High Risk Customer Count") if n in names][:4]
    if not wanted:
        return []
    gap = PAD
    total = CANVAS_W - PAD * 2 - gap * (len(wanted) - 1)
    w = total // len(wanted)
    out = []
    for i, n in enumerate(wanted):
        out.append(Visual(visual_type=VISUAL_CARD, x=PAD + i * (w + gap), y=KPI_Y,
                          width=w, height=KPI_H, title=n,
                          roles={"Values": [measure_field("_Measures", n)]}))
    return out


def build_pages(*, table: str, scores_table: str, entity: str,
                measure_names: list[str], plan, has_scores: bool) -> list[Page]:
    categorical = list(getattr(plan, "categorical", []) or [])
    binnings = list(getattr(plan, "binnings", []) or [])
    rate = "Churn Rate" if "Churn Rate" in measure_names else (
        measure_names[0] if measure_names else "")

    pages: list[Page] = []

    # ---------------- Overview ----------------
    top = KPI_Y + KPI_H + PAD
    h = CANVAS_H - top - PAD
    half = (CANVAS_W - PAD * 3) // 2
    overview = _kpi_row(table, measure_names)
    for i, col in enumerate(categorical[:2]):
        overview.append(Visual(
            visual_type=VISUAL_COLUMN, x=PAD + i * (half + PAD), y=top,
            width=half, height=h, title=f"{rate} by {col}",
            roles={"Category": [column_field(table, col)],
                   "Y": [measure_field("_Measures", rate)] if rate else []}))
    pages.append(Page(name="overview", display_name="Overview", visuals=overview))

    # ---------------- Drivers ----------------
    drivers: list[Visual] = []
    row_h = (CANVAS_H - PAD * 3) // 2
    # Measured threshold bands lead, because a cliff is the finding a mean hides.
    band_cols = [f"{b.column} Bucket" for b in binnings][:2]
    for i, col in enumerate(band_cols):
        drivers.append(Visual(
            visual_type=VISUAL_BAR, x=PAD + i * (half + PAD), y=PAD,
            width=half, height=row_h, title=f"{rate} by {col}",
            roles={"Category": [column_field(table, col)],
                   "Y": [measure_field("_Measures", rate)] if rate else []}))
    y2 = PAD + row_h + PAD
    third = (CANVAS_W - PAD * 4) // 3
    for i, col in enumerate(categorical[:3]):
        drivers.append(Visual(
            visual_type=VISUAL_COLUMN, x=PAD + i * (third + PAD), y=y2,
            width=third, height=row_h, title=f"{rate} by {col}",
            roles={"Category": [column_field(table, col)],
                   "Y": [measure_field("_Measures", rate)] if rate else []}))
    if drivers:
        pages.append(Page(name="drivers", display_name="Drivers", visuals=drivers))

    # ---------------- Risk List ----------------
    if has_scores:
        sl_w, sl_h = 240, 160
        risk: list[Visual] = []
        slicer_cols = (categorical[:2] + ["risk_tier"])[:3]
        for i, col in enumerate(slicer_cols):
            src = scores_table if col == "risk_tier" else table
            risk.append(Visual(
                visual_type=VISUAL_SLICER, x=PAD, y=PAD + i * (sl_h + PAD),
                width=sl_w, height=sl_h, title=col,
                roles={"Values": [column_field(src, col)]}))
        tx = PAD + sl_w + PAD
        risk.append(Visual(
            visual_type=VISUAL_TABLE, x=tx, y=PAD,
            width=CANVAS_W - tx - PAD, height=CANVAS_H - PAD * 2 - 80,
            title="Entities by modelled risk",
            roles={"Values": [
                column_field(scores_table, entity),
                column_field(scores_table, "risk_tier"),
                column_field(scores_table, "churn_probability"),
                column_field(scores_table, "top_factor_1"),
            ]}))
        # The self-check card: it must read 0, or the CSV and the report disagree.
        if "Tier Mismatch Count" in measure_names:
            risk.append(Visual(
                visual_type=VISUAL_CARD, x=tx, y=CANVAS_H - 80 + PAD - PAD,
                width=260, height=60, title="Tier Mismatch Count (must be 0)",
                roles={"Values": [measure_field("_Measures", "Tier Mismatch Count")]}))
        pages.append(Page(name="risk-list", display_name="Risk List", visuals=risk))

    return pages


def render_guide(name, pages, measures, policy, table, has_scores) -> str:
    lines = [
        f"# {name} — layout guide", "",
        f"Canvas {CANVAS_W}x{CANVAS_H}. Every visual below is emitted at the exact "
        f"coordinates listed, so the report opens laid out rather than as a blank "
        f"canvas you have to arrange.", "",
        f"Risk-tier policy digest: `{policy.digest()}` — the same value stamped into "
        f"the semantic model and `risk_tier_policy.json`. If these three ever differ, "
        f"the export and the dashboard are cutting different bands.", "",
    ]
    for p in pages:
        lines += [f"## Page: {p.display_name} (`{p.name}`)", "",
                  "| visual | type | x | y | w | h |", "|---|---|---|---|---|---|"]
        for i, v in enumerate(p.visuals):
            lines.append(f"| {v.title or '(untitled)'} | `{v.visual_type}` | "
                         f"{v.x} | {v.y} | {v.width} | {v.height} |")
        lines.append("")

    lines += ["## Measures", "", "| measure | origin |", "|---|---|"]
    for m in measures:
        lines.append(f"| {m.name} | {m.source_metric} ({m.confidence}) |")
    lines += ["",
              "Measures live on a dedicated `_Measures` table so they are not buried "
              "among columns.", ""]

    if has_scores:
        lines += [
            "## The Risk List page", "",
            f"`{table}` and `RiskScores` are two tables joined 1:1 on the entity id, "
            "not one merged table. That keeps `risk_scores.csv` independently "
            "refreshable and makes the join explicit in the model rather than buried "
            "in Power Query.", "",
            "**`Tier Mismatch Count` must read 0.** It recomputes each row's tier from "
            "the locked policy and counts disagreements with the tier stored in the "
            "CSV. Any non-zero value means the two have drifted apart.", ""]

    lines += [
        "## Getting a single-file deliverable", "",
        f"Open `{name}.pbip` in Power BI Desktop -> **File -> Save As** -> choose "
        "`.pbix`.", "",
        "Atlas cannot perform this step: `.pbix` is a compiled binary produced only by "
        "Power BI Desktop (Windows). This run generated **PBIP project source only** — "
        "see `PBIP_LIMITATIONS.md`.", ""]
    return "\n".join(lines)
