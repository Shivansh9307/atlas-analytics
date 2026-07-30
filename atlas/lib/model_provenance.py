"""Provenance for numbers a model produced rather than a query returned.

Constitution rule 1 says every figure carries a provenance ID resolving to a stored
query hash and result hash, and `ProvenanceLedger.resolves()` enforces both being
non-empty. A logistic coefficient satisfies neither on its face: no SQL returned it.

Pushing the fit into SQL is not an option — MLE needs iteration, `CREATE TEMP TABLE`
is forbidden by the read-only guard, and Newton-Raphson in recursive CTEs would be
unauditable. Fabricating a hash violates the rule outright. Leaving the field blank
fails GATE 4.

The resolution: a coefficient is a **deterministic pure function of an exact result
set plus a fully specified recipe**. So both fields are real, just not both from SQL:

    query_hash  = the REAL hash of the training query (stored, replayable via /replay)
    result_hash = a derivation digest: sha256 over the canonical recipe, which
                  INCLUDES the parent result_hash

Nothing is invented — both are computed from bytes that exist on disk. Anyone with
the stored evidence JSON and the recorded fingerprint can re-fit and get the same
digest; a different seed, feature set or coefficient produces a different one.

These files live in `runs/<id>/model/`, deliberately NOT in `evidence/`, because
`QueryStore.verify()` re-hashes stored rows against `result_hash` and a derivation
digest is not a row hash — putting it there would make verification report a false
mismatch.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["ModelFingerprint", "ScoringFingerprint", "write_fingerprint"]

_ROUND = 10          # coefficients rounded before hashing, so the digest is stable
                     # across platform-level float noise while still changing on any
                     # difference that could matter to a reported odds ratio.


def _digest(payload: dict) -> str:
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class ModelFingerprint:
    """Everything needed to reproduce a fit, hashed into one id."""
    algorithm: str
    algorithm_version: str
    seed: int
    train_query_hash: str
    train_result_hash: str
    feature_names: tuple[str, ...]
    preprocessing: tuple[tuple[str, str], ...]
    split: tuple[str, float, bool]              # (method, test_fraction, stratified)
    hyperparams: tuple[tuple[str, str], ...]
    coefficients: tuple[tuple[str, float], ...]
    intercept: float

    def as_dict(self) -> dict:
        return {
            "algorithm": self.algorithm,
            "algorithm_version": self.algorithm_version,
            "seed": self.seed,
            "train_query_hash": self.train_query_hash,
            "train_result_hash": self.train_result_hash,
            "feature_names": list(self.feature_names),
            "preprocessing": [list(p) for p in self.preprocessing],
            "split": list(self.split),
            "hyperparams": [list(h) for h in self.hyperparams],
            "coefficients": [[n, round(float(v), _ROUND)] for n, v in self.coefficients],
            "intercept": round(float(self.intercept), _ROUND),
        }

    def digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True)
class ScoringFingerprint:
    """The scored output file, tied to the model and the tier policy that made it."""
    model_digest: str
    score_query_hash: str
    score_result_hash: str
    tier_policy_digest: str
    flag_threshold: float
    output_sha256: str
    row_count: int
    entity_column: str = ""

    def as_dict(self) -> dict:
        return {
            "model_digest": self.model_digest,
            "score_query_hash": self.score_query_hash,
            "score_result_hash": self.score_result_hash,
            "tier_policy_digest": self.tier_policy_digest,
            "flag_threshold": self.flag_threshold,
            "output_sha256": self.output_sha256,
            "row_count": self.row_count,
            "entity_column": self.entity_column,
        }

    def digest(self) -> str:
        return _digest(self.as_dict())


def write_fingerprint(run_dir: Path, fp, *, kind: str = "model") -> str:
    """Persist a fingerprint under runs/<id>/model/ and return its digest.

    A derived claim whose recipe was never written down is exactly as unsourced as a
    fabricated one, so GATE 4 checks that this file exists for every derived claim.
    """
    d = fp.digest()
    out = Path(run_dir) / "model"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{kind}_{d}.json").write_text(
        json.dumps({"kind": kind, "digest": d, **fp.as_dict()}, indent=2))
    return d


def fingerprint_exists(run_dir: Path, digest: str) -> bool:
    out = Path(run_dir) / "model"
    return any(p.name.endswith(f"_{digest}.json") for p in out.glob("*.json")) \
        if out.exists() else False


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(Path(path).read_bytes())
    return h.hexdigest()[:16]
