"""Question router — classify a business question L1–L5 and route it to the cheapest
path that answers it. Not every question needs the full 18-step pipeline; a lookup
should cost a lookup.

  L1 lookup      -> /quick        "what's our conversion rate?"
  L2 breakdown   -> /quick        "conversion by device"
  L3 root-cause  -> /analyze      "why did conversion drop?"    (full pipeline)
  L4 forecast    -> /forecast     "forecast Q4 revenue"
  L5 experiment  -> /experiment   "should we A/B test the new checkout?"

Deterministic keyword/pattern rules, checked most-specific first. Table-tested.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Routing:
    level: int              # 1..5
    label: str              # lookup | breakdown | root-cause | forecast | experiment
    command: str            # /quick | /analyze | /forecast | /experiment
    reason: str
    confidence: str = "medium"


_EXPERIMENT = re.compile(
    r"\b(a/?b test|ab test|experiment|randomi[sz]e|sample size|statistical power|"
    r"should we (test|try|roll ?out)|holdout|control group|treatment group)\b", re.I)
_FORECAST = re.compile(
    r"\b(forecast|predict|projection|project(ed)?|will .*(be|reach|hit)|next (quarter|month|year)|"
    r"expected .* (revenue|growth)|seasonalit|extrapolat)\b", re.I)
_ROOT_CAUSE = re.compile(
    r"\b(why|what'?s driving|what is driving|driver|root cause|caused|explain (the|this)|"
    r"reason for|attribut|decompos)\b", re.I)
_BREAKDOWN = re.compile(
    r"\b(by [a-z]+|per [a-z]+|breakdown|broken down|segment|compare|comparison|"
    r"top \d+|distribution|split by)\b", re.I)


def classify(question: str) -> Routing:
    q = question.strip()
    if _EXPERIMENT.search(q):
        return Routing(5, "experiment", "/experiment",
                       "asks to test/measure a change", "high")
    if _FORECAST.search(q):
        return Routing(4, "forecast", "/forecast",
                       "asks about a future value", "high")
    if _ROOT_CAUSE.search(q):
        return Routing(3, "root-cause", "/analyze",
                       "asks WHY — needs decomposition + validation", "high")
    if _BREAKDOWN.search(q):
        return Routing(2, "breakdown", "/quick",
                       "a segmentation/comparison lookup", "medium")
    # default: a plain lookup
    return Routing(1, "lookup", "/quick",
                   "a direct fact lookup", "low")


def route(question: str) -> dict:
    r = classify(question)
    return {"level": r.level, "label": r.label, "command": r.command,
            "reason": r.reason, "confidence": r.confidence}
