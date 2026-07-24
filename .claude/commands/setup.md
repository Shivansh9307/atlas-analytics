---
description: Interactive onboarding — learn the analyst's role, data, and business context.
argument-hint: ""
---

Run the Atlas setup interview.

Interview the user (one topic at a time, don't dump a form) and capture:
1. **Role** — who they are and what decisions they make.
2. **Data sources** — where the data lives. Offer to run `/connect <source>` for each;
   auto-profile with `/profile` and note quirks in `memory/quirks/<source>.md`.
3. **Primary metrics** — the 2–5 metrics they live by. For each, confirm the exact
   definition and lock it in `atlas/semantic/metrics.yaml`; add business context to
   `atlas/knowledge/business.yaml`.
4. **Business context** — glossary terms, product lines, teams/owners → `atlas/knowledge/`.

Then save the profile:
```bash
uv run python -c "
from atlas.lib.onboarding import UserProfile, save_profile
save_profile(UserProfile(role='<role>', primary_metrics=[...], data_sources=[...], business_context='<...>'))
print('profile saved')"
```

The point isn't a wizard for its own sake — you're teaching Atlas the context that
makes its answers trustworthy. The byproduct of the interview is your first real
analysis. End by suggesting a first `/analyze` on data they know cold, so they can
validate the output.
