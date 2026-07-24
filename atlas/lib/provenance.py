"""Provenance ledger.

Chain: run_id -> claim_id -> query_hash -> result_hash -> slide_number

Every number that appears in a finding, narrative, or deck must resolve to a
ledger entry. GATE 4 walks the deck's numbers against this ledger and blocks
export on any orphan. The ledger is persisted per-run as provenance.json.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Claim:
    """A single asserted number and where it comes from."""
    claim_id: str
    text: str                 # e.g. "EMEA Q2 gross margin = 56.0%"
    value: float | int | str  # the actual number
    query_hash: str           # -> query_store entry
    result_hash: str          # hash of the result set the number was read from
    evidence_tier: str = "decomposed"  # decomposed|tested|correlational|hypothesis
    slide_number: int | None = None    # filled by deck-builder
    notes: str = ""


class ProvenanceLedger:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self._claims: dict[str, Claim] = {}

    def add(self, claim: Claim) -> Claim:
        if claim.claim_id in self._claims:
            raise ValueError(f"duplicate claim_id: {claim.claim_id}")
        self._claims[claim.claim_id] = claim
        return claim

    def record(
        self,
        claim_id: str,
        text: str,
        value,
        query_hash: str,
        result_hash: str,
        evidence_tier: str = "decomposed",
        notes: str = "",
    ) -> Claim:
        return self.add(Claim(
            claim_id=claim_id, text=text, value=value,
            query_hash=query_hash, result_hash=result_hash,
            evidence_tier=evidence_tier, notes=notes,
        ))

    def get(self, claim_id: str) -> Claim | None:
        return self._claims.get(claim_id)

    def attach_slide(self, claim_id: str, slide_number: int) -> None:
        if claim_id not in self._claims:
            raise KeyError(f"unknown claim_id: {claim_id}")
        self._claims[claim_id].slide_number = slide_number

    def all(self) -> list[Claim]:
        return list(self._claims.values())

    def resolves(self, claim_id: str) -> bool:
        """True if the claim exists and carries both a query and result hash."""
        c = self._claims.get(claim_id)
        return bool(c and c.query_hash and c.result_hash)

    def orphans(self, claim_ids: list[str]) -> list[str]:
        """Return the subset of claim_ids that do NOT resolve in the ledger.

        Used by GATE 4: pass the claim_ids referenced by the deck.
        """
        return [cid for cid in claim_ids if not self.resolves(cid)]

    # --- persistence ---
    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "claims": [asdict(c) for c in self._claims.values()],
        }

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2))
        return path

    @classmethod
    def load(cls, path: str | Path) -> "ProvenanceLedger":
        data = json.loads(Path(path).read_text())
        ledger = cls(data["run_id"])
        for c in data["claims"]:
            ledger.add(Claim(**c))
        return ledger
