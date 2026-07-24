from atlas.lib.validation import (
    LayerResult, grade_layers, validate_margin_finding,
)


def test_all_pass_is_grade_a():
    r = validate_margin_finding(
        row_count=16, profile_ok=True,
        mix=-0.04, rate=0.0, interaction=0.0, delta=-0.04,
        m1=0.60, m2=0.56, paradox=False)
    assert r.grade == "A"
    assert r.confident


def test_broken_identity_downgrades():
    # logical layer (weight 1.5) fails -> score drops below A
    r = validate_margin_finding(
        row_count=16, profile_ok=True,
        mix=-0.04, rate=0.0, interaction=0.0, delta=-0.10,   # identity broken
        m1=0.60, m2=0.56, paradox=False)
    assert r.grade != "A"
    assert any(l.layer == "logical" and not l.passed for l in r.layers)


def test_implausible_margin_fails_business_layer():
    r = validate_margin_finding(
        row_count=16, profile_ok=True,
        mix=-0.04, rate=0.0, interaction=0.0, delta=-0.04,
        m1=1.8, m2=0.56, paradox=False)                       # 180% margin
    assert any(l.layer == "business" and not l.passed for l in r.layers)


def test_grade_thresholds():
    assert grade_layers([LayerResult("a", True)]).grade == "A"
    assert grade_layers([LayerResult("a", False)]).grade == "F"
    # half weight passing -> D/F range
    r = grade_layers([LayerResult("a", True, 1.0), LayerResult("b", False, 1.0)])
    assert r.grade in ("D", "F")


def test_no_rows_fails_structural():
    r = validate_margin_finding(
        row_count=0, profile_ok=True,
        mix=-0.04, rate=0.0, interaction=0.0, delta=-0.04,
        m1=0.60, m2=0.56, paradox=False)
    assert any(l.layer == "structural" and not l.passed for l in r.layers)
