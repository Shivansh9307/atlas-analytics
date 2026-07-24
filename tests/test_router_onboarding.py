import pytest

from atlas.lib.onboarding import (
    UserProfile, first_run, has_profile, load_profile, save_profile,
)
from atlas.lib.router import classify


# ---- router classification table ----
@pytest.mark.parametrize("question,level,command", [
    ("What's our conversion rate?", 1, "/quick"),
    ("How many active users do we have?", 1, "/quick"),
    ("Conversion rate by device", 2, "/quick"),
    ("Show me revenue broken down by region", 2, "/quick"),
    ("Why did EMEA gross margin drop 4pts in Q2?", 3, "/analyze"),
    ("What's driving the churn increase?", 3, "/analyze"),
    ("Forecast Q4 revenue", 4, "/forecast"),
    ("Will we hit our target next quarter?", 4, "/forecast"),
    ("Should we A/B test the new checkout?", 5, "/experiment"),
    ("Design an experiment for the new onboarding", 5, "/experiment"),
])
def test_router_table(question, level, command):
    r = classify(question)
    assert r.level == level, f"{question!r} -> L{r.level} ({r.label})"
    assert r.command == command


def test_root_cause_beats_breakdown():
    # "why ... by segment" should route to root-cause, not a breakdown lookup
    r = classify("Why did revenue fall, broken down by segment?")
    assert r.level == 3 and r.command == "/analyze"


def test_experiment_beats_forecast_keyword():
    r = classify("Should we test whether the new flow will improve signups?")
    assert r.level == 5           # experiment intent wins over 'will'


# ---- onboarding ----
def test_first_run_and_profile_roundtrip(tmp_path):
    p = tmp_path / "user_profile.json"
    assert first_run(p) is True
    assert has_profile(p) is False

    prof = UserProfile(role="Product Analyst", primary_metrics=["conversion"],
                       data_sources=["emea_finance_csv"], business_context="SaaS")
    save_profile(prof, p)

    assert has_profile(p) is True
    assert first_run(p) is False
    back = load_profile(p)
    assert back.role == "Product Analyst"
    assert back.data_sources == ["emea_finance_csv"]
    assert back.is_complete()


def test_incomplete_profile():
    assert not UserProfile(role="", data_sources=[]).is_complete()
