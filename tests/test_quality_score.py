"""Known-answer tests for the 10-dimension quality score + score-band verdict."""
from __future__ import annotations

from atlas.connectors.base import TableRef
from atlas.lib.profiling import profile_table, verdict_from_score
from atlas.quality.score import score_table

TEN_DIMENSIONS = {
    "completeness", "consistency", "validity", "freshness", "uniqueness",
    "semantic_accuracy", "referential_integrity", "business_readiness",
    "type_safety", "documentation",
}


def test_score_reports_all_ten_dimensions(dirty):
    rep = score_table(dirty, TableRef("dirty"))
    assert set(rep.dimensions) == TEN_DIMENSIONS
    for v in rep.dimensions.values():
        assert 0.0 <= v <= 100.0


def test_clean_source_scores_perfect(finance):
    rep = score_table(finance, TableRef("finance"))
    assert rep.overall_score == 100.0
    assert rep.business_readiness == "Excellent"
    assert rep.critical_count == 0
    assert verdict_from_score(rep).decision == "GO"


def test_dirty_source_known_score(dirty):
    rep = score_table(dirty, TableRef("dirty"))
    # Deterministic known answer for the engineered fixture.
    assert rep.overall_score == 63.1
    assert rep.business_readiness == "Fair"
    assert rep.critical_count == 4
    assert rep.dimensions["semantic_accuracy"] == 20.0   # region + quarter penalised
    assert rep.dimensions["uniqueness"] == 90.91         # one duplicate row
    assert rep.dimensions["business_readiness"] == 0.0   # 4 critical issues
    # 4 critical issues -> NO-GO under the default readiness thresholds
    assert verdict_from_score(rep).decision == "NO-GO"


def test_freshness_is_real_max_date(dirty):
    rep = score_table(dirty, TableRef("dirty"))
    assert rep.freshness == "2024-10-25"
    # profiling exposes the same freshness (self-contained, no quality import)
    pr = profile_table(dirty, TableRef("dirty"))
    assert pr.freshness is not None and "2024-10-25" in pr.freshness


def test_empty_table_scores_zero(dirty):
    dirty._con.execute("CREATE VIEW empty_dirty AS SELECT * FROM dirty WHERE 1=0")
    rep = score_table(dirty, TableRef("empty_dirty"))
    assert rep.overall_score == 0.0
    assert rep.business_readiness == "Poor"
