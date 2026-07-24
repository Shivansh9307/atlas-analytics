---
name: first-run-welcome
description: Adaptive first-run welcome — if no user profile exists yet, orient the analyst and offer /setup before diving in. Use when a session starts and Atlas has not been onboarded.
---

# First-run welcome

At session start, check whether Atlas has been onboarded:
```bash
uv run python -c "from atlas.lib.onboarding import first_run, load_profile; \
print('FIRST_RUN' if first_run() else 'PROFILE: ' + load_profile().role)"
```

**If FIRST_RUN** — welcome the analyst briefly and set expectations honestly:
- Atlas handles ~80% of an analysis; **they are the eval** — run it on data they know
  cold so they catch mistakes and correct them (`/log-correction`), and it won't
  repeat them.
- Offer `/setup` to teach it their data/metrics/context, or `/connect <source>` +
  `/analyze "<question>"` to jump straight in on a CSV.
- Point at `/route "<question>"` if they're unsure what to run.

**If a profile exists** — greet with their role, load context
(`atlas.lib.context_loader.load_context`), and get to work. Don't re-onboard.

Keep it short. The goal is momentum, not a tour.
