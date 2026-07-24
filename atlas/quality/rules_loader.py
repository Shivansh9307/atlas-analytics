"""Loaders for the quality/repair config YAMLs (config over code).

Follows the canonical Atlas idiom: `yaml.safe_load(...) or {}`, resolved via
PATHS, wrapped in lru_cache with an explicit clear for tests. Nothing here
hardcodes a business rule — every mapping/threshold lives in rules/*.yaml.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from atlas.config import PATHS


def _load(path: Path) -> dict:
    return (yaml.safe_load(path.read_text()) or {}) if path.exists() else {}


@lru_cache(maxsize=1)
def repair_rules() -> dict:
    return _load(PATHS.quality_rules / "repair_rules.yaml")


@lru_cache(maxsize=1)
def country_region_mapping() -> dict:
    """Return {'regions': [...], 'country_to_region': {country_lower: REGION}}."""
    data = _load(PATHS.quality_rules / "country_region_mapping.yaml")
    return {
        "regions": [str(r) for r in data.get("regions", [])],
        "country_to_region": {
            str(k).strip().lower(): str(v)
            for k, v in (data.get("country_to_region") or {}).items()
        },
    }


@lru_cache(maxsize=1)
def country_standardisation() -> dict[str, str]:
    data = _load(PATHS.quality_rules / "country_standardisation.yaml")
    return {
        str(k).strip().lower(): str(v)
        for k, v in (data.get("canonical") or {}).items()
    }


def module_config(module_id: str) -> dict:
    return (repair_rules().get("modules", {}) or {}).get(module_id, {}) or {}


def module_enabled(module_id: str) -> bool:
    cfg = module_config(module_id)
    return bool(cfg.get("enabled", True))


def auto_apply_confidence() -> float:
    return float(repair_rules().get("auto_apply_confidence", 0.95))


def readiness_thresholds() -> dict:
    r = repair_rules().get("readiness", {}) or {}
    return {
        "min_overall_score": float(r.get("min_overall_score", 60)),
        "caveats_below": float(r.get("caveats_below", 90)),
        "max_critical_issues": int(r.get("max_critical_issues", 0)),
    }


def clear_cache() -> None:
    repair_rules.cache_clear()
    country_region_mapping.cache_clear()
    country_standardisation.cache_clear()
