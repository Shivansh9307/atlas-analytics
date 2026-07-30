"""PBIR report emission — pages and visuals as individual JSON files.

Field binding is the fiddly part and the shape is not guessable, so it is written
once here from a verified example:

    {"field": {"Measure": {"Expression": {"SourceRef": {"Entity": "<table>"}},
                           "Property": "<measure name>"}},
     "queryRef": "<table>.<name>", "nativeQueryRef": "<name>"}

`Column` replaces `Measure` for a column binding. Visual object names must be word
characters or hyphens and at most 50 chars, so they are derived deterministically
rather than randomly — a stable name means a re-export produces a clean diff.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from atlas.exporters.pbip.schemas import (
    DISPLAY_FIT_TO_PAGE, PAGE_SCHEMA, PAGES_SCHEMA, REPORT_SCHEMA, VISUAL_SCHEMA,
)

__all__ = ["Field", "Visual", "Page", "measure_field", "column_field",
           "render_visual", "render_page", "render_pages_metadata", "render_report",
           "object_name"]


def object_name(*parts: str) -> str:
    """A stable 20-char id from the visual's identity.

    PBIR requires word characters or hyphens, max 50. Deriving it from content rather
    than a random GUID keeps re-exports diff-clean, which is the entire point of the
    format.
    """
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return h[:20]


@dataclass
class Field:
    """One field binding inside a visual's query."""
    entity: str
    prop: str
    kind: str = "Measure"          # "Measure" | "Column"
    native_ref: str = ""

    def as_projection(self) -> dict:
        native = self.native_ref or self.prop
        return {
            "field": {self.kind: {"Expression": {"SourceRef": {"Entity": self.entity}},
                                  "Property": self.prop}},
            "queryRef": f"{self.entity}.{self.prop}",
            "nativeQueryRef": native,
        }


def measure_field(entity: str, name: str) -> Field:
    return Field(entity=entity, prop=name, kind="Measure")


def column_field(entity: str, name: str) -> Field:
    return Field(entity=entity, prop=name, kind="Column")


@dataclass
class Visual:
    visual_type: str
    x: int
    y: int
    width: int
    height: int
    roles: dict[str, list[Field]] = field(default_factory=dict)
    title: str = ""
    z: int = 0
    name: str = ""

    def resolved_name(self, page: str, index: int) -> str:
        return self.name or object_name(page, self.visual_type, self.title, index)


def render_visual(v: Visual, *, page: str, index: int) -> dict:
    query_state = {
        role: {"projections": [f.as_projection() for f in fields]}
        for role, fields in v.roles.items() if fields
    }
    visual: dict = {"visualType": v.visual_type, "drillFilterOtherVisuals": True}
    if query_state:
        visual["query"] = {"queryState": query_state}
    if v.title:
        visual["objects"] = {
            "title": [{"properties": {
                "text": {"expr": {"Literal": {"Value": f"'{_esc(v.title)}'"}}},
                "show": {"expr": {"Literal": {"Value": "true"}}},
            }}]
        }
    return {
        "$schema": VISUAL_SCHEMA,
        "name": v.resolved_name(page, index),
        "position": {"x": v.x, "y": v.y, "z": v.z,
                     "width": v.width, "height": v.height, "tabOrder": index},
        "visual": visual,
    }


def _esc(text: str) -> str:
    return str(text).replace("'", "''")


@dataclass
class Page:
    name: str                  # folder + object name (word chars / hyphens)
    display_name: str
    visuals: list[Visual] = field(default_factory=list)
    width: int = 1280
    height: int = 720


def render_page(p: Page) -> dict:
    # Required by the schema: $schema, name, displayName, displayOption.
    return {
        "$schema": PAGE_SCHEMA,
        "name": p.name,
        "displayName": p.display_name,
        "displayOption": DISPLAY_FIT_TO_PAGE,
        "width": p.width,
        "height": p.height,
    }


def render_pages_metadata(pages: list[Page], active: str | None = None) -> dict:
    return {
        "$schema": PAGES_SCHEMA,
        "pageOrder": [p.name for p in pages],
        "activePageName": active or (pages[0].name if pages else ""),
    }


def render_report(*, annotations: dict[str, str] | None = None) -> dict:
    out: dict = {"$schema": REPORT_SCHEMA}
    if annotations:
        out["annotations"] = [{"name": k, "value": str(v)}
                              for k, v in annotations.items()]
    return out


def dumps(obj: dict) -> str:
    return json.dumps(obj, indent=2) + "\n"
