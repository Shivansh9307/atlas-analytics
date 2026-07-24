"""Shared export provenance gate.

Gate 4 is not just for the pptx: EVERY export format (HTML, PDF, Slack, email) must
pass the same check — every number it shows resolves in the provenance ledger.
This module is the single enforcement point all exporters call.
"""
from __future__ import annotations

from atlas.lib.provenance import ProvenanceLedger


class OrphanNumberError(Exception):
    """Raised when an export references a number with no ledger entry."""


def assert_no_orphans(ledger: ProvenanceLedger, claim_ids: list[str]) -> None:
    orphans = ledger.orphans(claim_ids)
    if orphans:
        raise OrphanNumberError(
            f"{len(orphans)} number(s) have no provenance and cannot be exported: "
            f"{orphans}. Fix the finding or remove the claim — Atlas does not ship "
            "unsourced numbers in any format."
        )
