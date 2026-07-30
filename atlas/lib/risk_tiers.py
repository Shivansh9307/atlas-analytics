"""Risk-tier policy — one definition, three renderers.

The scoring CSV, the SQL scores view and the Power BI measure must agree on what
"High risk" means. Three hand-written copies of `0.40 / 0.70` is the same class of
bug as three hand-written copies of a metric formula, so there is one YAML source
and three renderers over it: `tier_of()` (Python), `sql_case()` (DuckDB) and
`dax_switch()` (Power BI).

Agreement is *proved*, not asserted: `digest()` is stamped into the model card, the
emitted semantic model and the claim notes, and a test parses the generated DAX back
into intervals and checks it against `tier_of()` across the whole probability range.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from atlas.config import PATHS

__all__ = ["Band", "TierPolicy", "load_policy", "policy_path"]


def policy_path() -> Path:
    return PATHS.semantic / "risk_tiers.yaml"


@dataclass(frozen=True)
class Band:
    name: str
    min: float
    max: float                      # exclusive upper bound

    def contains(self, p: float) -> bool:
        return self.min <= p < self.max


@dataclass(frozen=True)
class TierPolicy:
    profile: str
    score_field: str
    method: str
    bands: tuple[Band, ...]
    flag_threshold: float
    flag_threshold_note: str = ""
    notes: str = ""

    # ---- renderer 1: Python (risk_scores.csv) ----
    def tier_of(self, p: float) -> str:
        for b in self.bands:
            if b.contains(p):
                return b.name
        # Only reachable if the bands leave a gap; name it rather than guess.
        return self.bands[-1].name if p >= self.bands[-1].max else self.bands[0].name

    # ---- renderer 2: SQL (the local scores view / red-team checks) ----
    def sql_case(self, expr: str) -> str:
        parts = [f"WHEN {expr} < {b.max!r} THEN '{b.name}'" for b in self.bands[:-1]]
        return "CASE " + " ".join(parts) + f" ELSE '{self.bands[-1].name}' END"

    # ---- renderer 3: DAX (the Power BI semantic model) ----
    def dax_switch(self, col_ref: str) -> str:
        lines = [f"    {col_ref} < {b.max!r}, \"{b.name}\"" for b in self.bands[:-1]]
        return ("SWITCH(\n    TRUE(),\n" + ",\n".join(lines) +
                f",\n    \"{self.bands[-1].name}\"\n)")

    def band_names(self) -> list[str]:
        return [b.name for b in self.bands]

    def as_dict(self) -> dict:
        return {
            "profile": self.profile, "score_field": self.score_field,
            "method": self.method,
            "bands": [{"name": b.name, "min": b.min, "max": b.max} for b in self.bands],
            "flag_threshold": self.flag_threshold,
            "flag_threshold_note": self.flag_threshold_note.strip(),
        }

    def digest(self) -> str:
        canon = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]

    def validate(self) -> None:
        """Bands must be ordered, contiguous and cover [0, 1]."""
        if not self.bands:
            raise ValueError("risk tier policy has no bands")
        lo = self.bands[0].min
        if lo > 0.0:
            raise ValueError(f"bands start at {lo}, leaving [0,{lo}) unassigned")
        for a, b in zip(self.bands, self.bands[1:]):
            if abs(a.max - b.min) > 1e-9:
                raise ValueError(
                    f"gap or overlap between band '{a.name}' (max {a.max}) and "
                    f"'{b.name}' (min {b.min}); every probability must map to exactly "
                    f"one tier")
        if self.bands[-1].max <= 1.0:
            raise ValueError(
                f"top band ends at {self.bands[-1].max}; it must exceed 1.0 so a "
                f"predicted probability of exactly 1.0 still has a tier")


@lru_cache(maxsize=8)
def load_policy(profile: str = "default") -> TierPolicy:
    path = policy_path()
    if not path.exists():
        raise FileNotFoundError(f"no risk-tier policy at {path}")
    data = yaml.safe_load(path.read_text()) or {}
    spec = (data.get("tiers") or {}).get(profile)
    if spec is None:
        raise KeyError(f"risk-tier profile '{profile}' not in {path}. "
                       f"Known: {sorted((data.get('tiers') or {}))}")
    policy = TierPolicy(
        profile=profile,
        score_field=spec.get("score_field", "probability"),
        method=spec.get("method", "fixed_probability"),
        bands=tuple(Band(name=b["name"], min=float(b["min"]), max=float(b["max"]))
                    for b in spec["bands"]),
        flag_threshold=float(spec.get("flag_threshold", 0.5)),
        flag_threshold_note=spec.get("flag_threshold_note", ""),
        notes=spec.get("notes", ""),
    )
    policy.validate()
    return policy
