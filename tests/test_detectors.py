"""Known-answer detection tests for the data-quality repair modules."""
from __future__ import annotations

from atlas.connectors.base import TableRef
from atlas.quality.detectors import critical_issues, detect_issues
from atlas.quality.modules.base import REGISTRY, all_modules


def _by_module(issues):
    out: dict[str, list] = {}
    for i in issues:
        out.setdefault(i.module_id, []).append(i)
    return out


def test_all_twelve_modules_registered():
    assert len(REGISTRY) == 12
    assert {m.id for m in all_modules()} == {
        "date_repair", "region_repair", "month_repair", "quarter_repair", "year_repair",
        "duplicate_detection", "country_standardisation", "numeric_type_repair",
        "boolean_repair", "whitespace_repair", "case_standardisation", "null_classification",
    }


def test_clean_source_has_no_issues(finance):
    """Backward-compat guard: the clean EMEA fixture trips nothing."""
    assert detect_issues(finance, TableRef("finance")) == []


def test_dirty_fixture_known_issue_set(dirty):
    issues = detect_issues(dirty, TableRef("dirty"))
    mods = _by_module(issues)

    # date: order_date is text but fully parses as DATE
    assert mods["date_repair"][0].column == "order_date"
    assert mods["date_repair"][0].severity == "HIGH"

    # region: NULL for the 3 USA/Canada rows, all recoverable from country
    reg = mods["region_repair"][0]
    assert reg.column == "region"
    assert reg.detail == {"null_rows": 3, "recoverable": 3, "country_col": "country"}

    # duplicate: exactly one full-duplicate row
    assert mods["duplicate_detection"][0].detail["duplicate_rows"] == 1

    # quarter mislabelled (fiscal) on 1 row; month is correct -> only quarter fires
    assert mods["quarter_repair"][0].detail["mismatch"] == 1
    assert mods["quarter_repair"][0].confidence == 0.70   # ambiguous -> needs approval
    assert "month_repair" not in mods
    assert "year_repair" not in mods

    # country standardisation: 'uk','usa' -> 2 non-canonical
    assert mods["country_standardisation"][0].detail["changed"] == 2

    # boolean-as-text
    assert mods["boolean_repair"][0].column == "active"

    # whitespace on the one 'Gold ' value
    assert mods["whitespace_repair"][0].detail["affected"] == 1

    # case collapse on category (Gold/gold) and country (USA/usa)
    case_cols = {i.column for i in mods["case_standardisation"]}
    assert "category" in case_cols

    # notes ~91% null -> structural (INFO), never a defect
    nc = mods["null_classification"][0]
    assert nc.column == "notes" and nc.structural and nc.severity == "INFO"


def test_critical_excludes_structural_and_low(dirty):
    issues = detect_issues(dirty, TableRef("dirty"))
    crit = critical_issues(issues)
    # HIGH, non-structural only: date, duplicate, quarter, region
    assert {c.module_id for c in crit} == {
        "date_repair", "duplicate_detection", "quarter_repair", "region_repair"}


def test_disabled_module_is_skipped(dirty, monkeypatch):
    from atlas.quality import rules_loader
    monkeypatch.setattr(rules_loader, "module_enabled",
                        lambda mid: mid != "date_repair")
    # detectors imports the symbol directly; patch there too
    import atlas.quality.detectors as det
    monkeypatch.setattr(det, "module_enabled", lambda mid: mid != "date_repair")
    issues = detect_issues(dirty, TableRef("dirty"))
    assert "date_repair" not in {i.module_id for i in issues}
