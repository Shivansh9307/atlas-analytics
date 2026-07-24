---
name: guardrails-closeloop
description: Pair every success metric with a guardrail and give every recommendation an owner, success metric, follow-up date, and fallback. Use when writing recommendations or a so-what — a rec without these is a wish, not a plan.
---

# Guardrails & close-the-loop

## Guardrail rule
Every success metric is paired with a **guardrail metric** so a "win" that quietly
breaks something else is caught (a conversion lift that tanks revenue-per-session is
not a win). `atlas/lib/experiment.py::_default_guardrails` suggests defaults; override
with the real counterpart for your metric. Check positive findings for the trade-off
you're not measuring.

## Close-the-loop rule (`atlas/lib/close_the_loop.py`)
Every recommendation is a `Recommendation` with all of:
- **action** — the concrete move
- **decision_owner** — who will do it
- **success_metric** (+ its **guardrail_metric**)
- **follow_up** — a date to check back (defaults to +30 days)
- **fallback** — what we do if it doesn't work

`close_the_loop(recs)` flags any recommendation missing a field — those aren't a plan
yet. Render with `Recommendation.render()`; put them on the deck's recommendation
slide and in the comms.

## Tie-in
This is what makes the "so-what" and "recommendation" slides actionable rather than
decorative. Pairs with the deck-standards skill (recommendation slide) and
comms-drafter (the follow-up goes in the email).
