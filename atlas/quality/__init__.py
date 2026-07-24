"""Atlas Data Quality Copilot subsystem.

The first specialist every dataset passes through: profile -> detect issues ->
score quality -> plan/preview/apply safe repairs to a semantic clean layer (raw
stays sacred) -> gate analysis on readiness. Pluggable and config-driven; the
core reasoning backbone (orchestrator/gates/provenance) is untouched.
"""
from __future__ import annotations

from atlas.quality.detectors import critical_issues, detect_issues
from atlas.quality.score import QualityReport, score_table

__all__ = ["detect_issues", "critical_issues", "score_table", "QualityReport"]
