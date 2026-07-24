"""Repair-module package. Importing it registers every module in REGISTRY.

New modules: add a file that defines a @register-decorated RepairModule and import
it here. Nothing else in the codebase needs to change (plugin architecture).
"""
from __future__ import annotations

from atlas.quality.modules.base import REGISTRY, all_modules, register  # noqa: F401

# Import each module for its @register side effect. Order is irrelevant —
# all_modules() sorts by id for deterministic execution.
from atlas.quality.modules import (  # noqa: F401,E402
    boolean_repair,
    case_standardisation,
    country_standardisation,
    date_repair,
    duplicate_detection,
    month_repair,
    null_classification,
    numeric_type_repair,
    quarter_repair,
    region_repair,
    whitespace_repair,
    year_repair,
)
