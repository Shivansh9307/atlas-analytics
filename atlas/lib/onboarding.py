"""Onboarding state — user profile + first-run detection.

The `/setup` interview writes a profile here (role, primary metrics, data sources,
business context). `first_run()` lets the first-run-welcome skill adapt to whether a
user has been onboarded. Profile is per-deployment and gitignored.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from atlas.config import PATHS

PROFILE = PATHS.memory / "user_profile.json"


@dataclass
class UserProfile:
    role: str = ""
    primary_metrics: list[str] = field(default_factory=list)
    data_sources: list[str] = field(default_factory=list)
    business_context: str = ""
    created: str = field(default_factory=lambda: date.today().isoformat())

    def is_complete(self) -> bool:
        return bool(self.role and self.data_sources)


def profile_path(runs_root: Path | None = None) -> Path:
    return PROFILE if runs_root is None else runs_root / "user_profile.json"


def has_profile(path: Path | None = None) -> bool:
    return (path or PROFILE).exists()


def first_run(path: Path | None = None) -> bool:
    return not has_profile(path)


def save_profile(profile: UserProfile, path: Path | None = None) -> Path:
    p = path or PROFILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(profile), indent=2))
    return p


def load_profile(path: Path | None = None) -> UserProfile:
    p = path or PROFILE
    if not p.exists():
        return UserProfile()
    return UserProfile(**json.loads(p.read_text()))
