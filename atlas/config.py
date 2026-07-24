"""Central configuration: paths, budgets, tolerances, secrets loading.

Secrets come only from a gitignored .env (loaded via python-dotenv). Nothing
here ever hard-codes a credential; sources.yaml references creds by env-var name.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*_a, **_k):  # type: ignore
        return False

# Repo root = parent of the atlas/ package dir.
ROOT = Path(__file__).resolve().parent.parent

# Load .env once at import (no-op if absent). override=False so real env wins.
load_dotenv(ROOT / ".env", override=False)


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Paths:
    root: Path = ROOT
    atlas: Path = ROOT / "atlas"
    connectors: Path = ROOT / "atlas" / "connectors"
    semantic: Path = ROOT / "atlas" / "semantic"
    quality: Path = ROOT / "atlas" / "quality"
    quality_rules: Path = ROOT / "atlas" / "quality" / "rules"
    sources_yaml: Path = ROOT / "atlas" / "connectors" / "sources.yaml"
    metrics_yaml: Path = ROOT / "atlas" / "semantic" / "metrics.yaml"
    memory: Path = ROOT / "memory"
    clean: Path = ROOT / "clean_layers"   # durable semantic-clean manifests (per source)
    lessons_jsonl: Path = ROOT / "memory" / "lessons.jsonl"
    failures_jsonl: Path = ROOT / "memory" / "failures.jsonl"
    quirks: Path = ROOT / "memory" / "quirks"
    runs: Path = ROOT / "runs"
    data: Path = ROOT / "data"

    def run_dir(self, run_id: str) -> Path:
        return self.runs / run_id


@dataclass(frozen=True)
class Budgets:
    """Hard caps for a single /analyze run. Warehouse-money guardrails."""
    max_queries: int = field(default_factory=lambda: _int_env("ATLAS_MAX_QUERIES", 60))
    max_bytes_scanned: int = field(
        default_factory=lambda: _int_env("ATLAS_MAX_BYTES_SCANNED", 5_000_000_000)
    )
    max_wallclock_s: int = field(
        default_factory=lambda: _int_env("ATLAS_MAX_WALLCLOCK_S", 1200)
    )
    # per-explorer-branch sub-budgets
    branch_max_queries: int = field(
        default_factory=lambda: _int_env("ATLAS_BRANCH_MAX_QUERIES", 12)
    )
    branch_max_wallclock_s: int = field(
        default_factory=lambda: _int_env("ATLAS_BRANCH_MAX_WALLCLOCK_S", 240)
    )


@dataclass(frozen=True)
class Tolerances:
    """Validation tolerances."""
    # red-team re-derivation must land within this RELATIVE tolerance of headline.
    rederivation_rel: float = 0.005  # ±0.5%
    # significance level for the statistician.
    alpha: float = 0.05


@dataclass(frozen=True)
class LLMConfig:
    """Optional in-script LLM shim. NEVER used to produce numbers."""
    provider: str = field(
        default_factory=lambda: os.environ.get("ATLAS_LLM_PROVIDER", "openai").lower()
    )
    openai_key: str | None = field(
        default_factory=lambda: os.environ.get("OPENAI_API_KEY") or None
    )
    anthropic_key: str | None = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY") or None
    )

    @property
    def enabled(self) -> bool:
        if self.provider == "none":
            return False
        if self.provider == "anthropic":
            return bool(self.anthropic_key)
        return bool(self.openai_key)


PATHS = Paths()
BUDGETS = Budgets()
TOLERANCES = Tolerances()
LLM = LLMConfig()

# Statements that must never reach any data source (read-only enforcement).
FORBIDDEN_SQL_ROOTS = frozenset({
    "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER",
    "MERGE", "TRUNCATE", "GRANT", "REVOKE", "COPY", "CALL",
    "REPLACE", "UPSERT", "VACUUM", "ATTACH", "DETACH", "SET",
})
