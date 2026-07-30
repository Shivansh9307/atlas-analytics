"""Playbook registry — one analysis shape per plugin.

Importing a concrete playbook here is what registers it (the `@register_playbook`
decorator runs at import time). Adding a new analysis shape means adding a module
and one import line below; no core edit.
"""
from __future__ import annotations

from atlas.playbooks.base import (  # noqa: F401
    BinningSpec, BriefFields, ClaimSpec, FeaturePlan, Playbook, PlaybookBlocked,
    PlaybookResult, Rederivation, SizingOutcome, all_playbooks, get_playbook,
    register_playbook, select_playbook, supported_decompositions, PLAYBOOK_REGISTRY,
)
from atlas.playbooks.binding import (  # noqa: F401
    ColumnBinding, ColumnProbe, ColumnRequirement, ColumnRole,
    probe_columns, resolve_binding, split_features,
)

# Concrete playbooks — import to register.
from atlas.playbooks import margin       # noqa: F401,E402
from atlas.playbooks import descriptive  # noqa: F401,E402
from atlas.playbooks import logistic     # noqa: F401,E402

__all__ = [
    "Playbook", "PlaybookResult", "PlaybookBlocked", "ClaimSpec", "Rederivation",
    "SizingOutcome", "BriefFields", "BinningSpec", "FeaturePlan",
    "register_playbook", "select_playbook", "all_playbooks", "get_playbook",
    "supported_decompositions", "PLAYBOOK_REGISTRY",
    "ColumnRole", "ColumnRequirement", "ColumnBinding", "ColumnProbe",
    "resolve_binding", "probe_columns", "split_features",
]
