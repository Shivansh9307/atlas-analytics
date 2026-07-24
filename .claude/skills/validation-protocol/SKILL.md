---
name: validation-protocol
description: The independent re-derivation procedure and veto criteria the red-team uses. Use to validate a headline number and attack a conclusion before it ships.
---

# Validation protocol

Held by `red-team-validator`. Gate 3. The validator must NOT read the analyst's
SQL — it re-derives independently and attacks.

## Step 1 — Independent re-derivation
Recompute the headline straight from raw source columns with your OWN query
(different SQL than the analyst). Compare:

    within_tolerance = |rederived - headline| <= |headline| * TOLERANCES.rederivation_rel

Default tolerance ±0.5% relative (`atlas/config.py`). Outside → FAIL, route
`failed_rederivation` → `sql-engineer`.

Helper: `uv run python .claude/skills/validation-protocol/scripts/rederive.py <source> <region> <p1> <p2> <headline_p1> <headline_p2>`

## Step 2 — Attack battery
- **filter leakage** — does a WHERE quietly drop rows that would flip the story?
- **survivorship** — entities in one period but not the other?
- **date boundaries** — inclusive/exclusive, timezone, quarter edges
- **Simpson's paradox** — aggregate vs segment directions (`simpsons_check`)
- **alternative explanations** the decomposition did not rule out

## Veto criteria
Output **PASS** only if re-derivation is within tolerance AND no fatal attack
survives. Any surviving attack routes `weak_causal_logic` → `root-cause-analyst`.
The deck build is blocked until PASS.
