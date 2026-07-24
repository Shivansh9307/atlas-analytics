"""YAML theme loader + WCAG contrast checking.

Themes live in atlas/themes/*.yaml. The default ships the VALIDATED CVD-safe
categorical palette from the dataviz skill — do not eyeball palette safety, and if
you swap in brand colors, re-run the dataviz validator.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from atlas.config import PATHS

THEMES_DIR = PATHS.root / "atlas" / "themes"


@dataclass
class Theme:
    name: str
    surface: str
    text_primary: str
    text_secondary: str
    grid: str
    categorical: list[str]
    sequential: list[str]
    status: dict[str, str]
    highlight: str
    muted: str
    font_family: str = "DejaVu Sans"

    def color(self, i: int) -> str:
        """Categorical color by fixed slot; past the palette folds to muted (Other)."""
        return self.categorical[i] if i < len(self.categorical) else self.muted


@lru_cache(maxsize=8)
def load_theme(name: str = "default") -> Theme:
    path = THEMES_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"theme '{name}' not found at {path}")
    d = yaml.safe_load(path.read_text())
    return Theme(
        name=d.get("name", name), surface=d["surface"],
        text_primary=d["text_primary"], text_secondary=d["text_secondary"],
        grid=d["grid"], categorical=d["categorical"], sequential=d["sequential"],
        status=d.get("status", {}), highlight=d.get("highlight", d["categorical"][0]),
        muted=d.get("muted", "#c9c8c3"), font_family=d.get("font_family", "DejaVu Sans"),
    )


# ---- WCAG contrast ----
def _srgb_to_linear(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _srgb_to_linear(r) + 0.7152 * _srgb_to_linear(g) + 0.0722 * _srgb_to_linear(b)


def contrast_ratio(fg: str, bg: str) -> float:
    l1, l2 = relative_luminance(fg), relative_luminance(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return round((hi + 0.05) / (lo + 0.05), 2)


def passes_wcag(fg: str, bg: str, *, level: str = "AA", large: bool = False) -> bool:
    ratio = contrast_ratio(fg, bg)
    threshold = {"AA": 3.0 if large else 4.5, "AAA": 4.5 if large else 7.0}[level]
    return ratio >= threshold
