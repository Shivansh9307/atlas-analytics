# Atlas — your on-demand analytics team

**Ask a business question in plain English. Get back a boardroom-ready slide deck —
with the story, the recommendation, and every number traceable to where it came from —
in minutes instead of weeks.**

You don't write formulas or SQL. You ask the kind of question you'd bring to your data
team:

> *"Why did EMEA gross margin drop 4 points in Q2?"*

Atlas frames the question, digs through the data, finds the real cause, argues with
itself to make sure it's right, writes the narrative, and hands you a deck with speaker
notes. This guide is written for the people who **read and act on** those decks — not
for engineers. (There's a short technical appendix at the end for your data team.)

---

## The one thing that makes Atlas different

Most "AI analytics" tools give you a confident answer and no way to check it. Atlas does
the opposite:

> **Every single number in the deck can be traced back to the exact query that
> produced it.** No number appears unless Atlas can show its work.

That one rule changes everything about how much you can trust what you're looking at.
The rest of this page explains how that promise is kept, what you get, and how to read
it.

---

## Quickstart — how to use it

Want to *drive* Atlas rather than just read about it? Here's the whole loop in five
steps:

1. **Install it** (one time): `uv venv --python 3.13.9 && uv pip install -e ".[dev]"`
2. **See a deck immediately** — run the bundled example and open the resulting
   `runs/<run_id>/deck.pptx`.
3. **Add your data** — drop a CSV in `data/`, register it in
   `atlas/connectors/sources.yaml`, then `/connect` and `/profile` it. (Warehouses:
   fill in `.env` and install the `[warehouse]` extra.)
4. **Ask your question** — in Claude Code, `/analyze "Why did <metric> change?"`. The
   specialist agents adapt to your data and build the deck.
5. **Get other formats** — `/export html,slack,email <run_id>` for a web page and
   ready-to-send summaries.

> **📘 Full step-by-step operator guide, with copy-paste commands for every step →
> [USAGE.md](USAGE.md)** — adding data sources, running commands and skills, getting the
> PowerPoint, exporting, and troubleshooting.

---

## Why you can trust the numbers

Think of Atlas as a very careful analyst who refuses to cut corners. Here's what that
means for you, in plain terms:

| The safeguard | What it means for your decision |
|---|---|
| **Everything is sourced** | Every figure links to the query behind it. If someone asks "where did 56% come from?", the answer is in the appendix. |
| **It checks its own work** | A separate "red-team" step re-calculates the headline number a second way, from the raw data, without looking at the first calculation. The two must agree within a hair (0.5%) or the deck is blocked. |
| **It says what it assumed** | If your question was ambiguous ("margin" could mean three things), Atlas picks the most likely meaning, **tells you it did**, and lists it in an Assumptions page — never buried. |
| **It refuses rather than guesses** | If the data is too messy or incomplete to answer honestly, Atlas stops and tells you what it would need. It will **not** produce a confident-looking deck over bad data. |
| **It never changes your data** | Atlas only ever *reads*. It cannot edit, delete, or overwrite anything in your systems. |
| **It labels a hunch as a hunch** | Every claim is tagged with how strong the evidence is — from "proven by the math" down to "a plausible hypothesis." You always know how much weight a statement can bear. |

If any of these checks fail, **you never see a polished deck** — you get a clear note
about what's blocking and what's needed. That's on purpose.

---

## What you receive

For a full analysis, Atlas produces a complete, self-contained package. The headline
deliverable is a slide deck that follows the same trustworthy shape every time:

1. **A title that makes a claim, not a label.** Not *"EMEA Margin Analysis"* but
   *"EMEA margin fell 4 points because sales shifted toward lower-margin products."*
   You know the answer from slide one.
2. **The key insight** — the single most important finding.
3. **The evidence** — one clean chart per point, no clutter.
4. **What it's worth** — the size of the opportunity or the cost, in dollars, with a
   range (more on this below).
5. **So what** — why it matters for the decision in front of you.
6. **The recommendation** — concrete next steps, each with an owner, a success measure,
   a safety measure, and a follow-up date.
7. **An appendix** — the assumptions made, the method used, and the full source table
   linking every number to its query.

Alongside the deck you also get **speaker notes** for each slide (about a minute of
talking track), a **web page version** you can open in any browser or email to anyone,
and ready-to-send **Slack, email, and one-paragraph executive summaries** — all drawn
from the same validated numbers.

---

## How to brief a good question

Atlas does best with the same brief you'd give a sharp analyst. The more specific you
are, the sharper the answer:

- **Name the metric** — "gross margin," "conversion rate," "revenue."
- **Name the time window** — "Q2 vs Q1," "last month vs the month before."
- **Say what decision it unblocks** — "we're deciding whether to cut costs or change the
  sales mix."

**Strong question:** *"Why did EMEA gross margin drop 4 points in Q2 versus Q1, and is
it something we should fix with pricing or with sales mix?"*

**Weaker question:** *"How's margin doing?"* — Atlas will still answer, but it will have
to make more assumptions (which it will declare) to fill in the blanks.

You don't need to phrase it perfectly. If something's ambiguous, Atlas resolves it the
most sensible way and shows you that choice — it won't stall waiting for a perfect brief.

---

## How Atlas works — the journey of your question

Here's what actually happens between your question and the finished deck. Each stage is
a checkpoint that protects you from a common way analyses go wrong. We'll follow the
EMEA margin question the whole way through.

**Step 1 — Frame the question.**
Atlas turns your plain-English ask into a precise brief: who the decision-maker is, the
exact metric, the comparison window, and — importantly — what's *out of scope*. This is
where it writes down any assumptions.
*Protects you from:* answering the wrong question precisely.

**Step 2 — Check the data is trustworthy.**
Before calculating anything, Atlas profiles the data: Is it complete? Are there
duplicates? Gaps? It issues a plain **GO / NO-GO** verdict.
*Protects you from:* a beautiful analysis built on broken data. (If it's NO-GO, Atlas
stops here and tells you what's wrong.)

**Step 3 — Explore the possibilities.**
Atlas considers several explanations at once — was it a time trend? a particular
segment? a shift in the product mix? — rather than latching onto the first idea.
*Protects you from:* tunnel vision and cherry-picking.

**Step 4 — Find the true cause by breaking the number down.**
This is the heart of it. Instead of guessing, Atlas does the math that splits the change
into its real drivers. For EMEA, it separates *"did each product get less profitable?"*
(no) from *"did we sell a different mix of products?"* (yes) — and finds the entire
4-point drop came from **selling more low-margin Hardware and less high-margin
Software**, not from any product getting worse.
*Protects you from:* confusing correlation with cause, and from "vibes-based" answers.

**Step 5 — Stress-test the finding.**
An independent red-team re-derives the headline from scratch and actively tries to break
the conclusion — checking for filtering mistakes, missing data, and date-boundary
errors. It also assigns an **A–F confidence grade**.
*Protects you from:* a single mistake sailing through unquestioned.

**Step 6 — Write the story.**
Atlas writes for your named decision-maker: the answer in one sentence first, then the
supporting points, then the evidence. Every number carries its source tag.
*Protects you from:* a data dump with no clear "so what."

**Step 7 — Build the deck and pressure-test it.**
Atlas assembles the slides, then role-plays your toughest stakeholder and generates the
five hardest questions they'd ask — checking the deck can answer every one before you
ever present it.
*Protects you from:* getting caught flat-footed in the room.

Throughout, the deck must clear **five quality checkpoints** (good data, clear
definitions, the red-team's approval, every number sourced, and every hard question
answerable). Miss any one, and the deck doesn't ship.

---

## How to read the result

A few things on an Atlas deck are worth knowing how to read:

- **The confidence grade (A–F).** A quick verdict on how solid the finding is. **A**
  means every internal check passed cleanly. Anything lower comes with a visible reason.
  Treat it like a credit rating for the analysis.
- **Evidence tiers.** Each claim is labelled by strength:
  **decomposed** (proven by the math) → **tested** (statistically significant) →
  **correlational** (moves together, cause unproven) → **hypothesis** (plausible, not
  yet shown). A recommendation resting on a "hypothesis" deserves more caution than one
  resting on "decomposed."
- **"What it's worth" and the tornado.** When Atlas sizes an opportunity, it never gives
  a single false-precision number. It gives a base estimate *and* a "tornado" chart
  showing which assumption the number depends on most — so you know where the risk sits.
  (E.g. *"worth about $40 on the fixture data, and it hinges most on how many of those
  margin points are truly recoverable."*)
- **The Assumptions page.** Read it. It's where Atlas tells you the judgment calls it
  made. If you disagree with one, that's a quick correction — not a reason to distrust
  the whole deck.
- **The Provenance page.** The receipts. Every number, its value, and a code linking it
  to the exact query. You'll rarely need it — but it's there, and that's the point.

---

## What you can ask Atlas for

You don't need the full pipeline every time. Atlas matches the effort to the question:

- **A full analysis** — "Why did X change?" → the complete deck described above.
- **A quick number** — "What was EMEA revenue in Q2?" → a straight answer with a chart,
  in under a couple of minutes.
- **A single chart** — "Make a clean chart of the checkout funnel." → one publication-
  quality visual.
- **A forecast** — "Where is this metric heading?" → a projection **with an honest
  uncertainty range** (only when there's enough history; otherwise Atlas says so).
- **An experiment design** — "How should we A/B test the new checkout?" → sample size,
  how long to run, and the safety metrics to watch.
- **"Redo just one part"** — after feedback, Atlas can re-run a single stage (say, just
  the narrative) without repeating the whole analysis.

Not sure which you need? Just ask your question in plain English — Atlas figures out the
right path.

---

## Under the hood — the team, the playbooks, and the menu

Atlas isn't one big black box. It's organised the way a good analytics *team* is, and
that structure is exactly what makes it careful. Three ideas:

- **Agents** — a team of **specialists**, each with one job (framing the question,
  checking the data, breaking the number down, red-teaming the result, building the
  deck). Each works in its own isolated workspace, so they stay focused and act as
  checks on one another — the red-team literally re-does the headline without seeing
  the first analyst's work.
- **Skills** — the **playbooks and standards** each specialist follows: how to break a
  metric into its drivers, how to design an honest chart, how to validate a number,
  how to write for an executive.
- **Commands** — the **menu** an analyst types to drive Atlas (you saw the plain-English
  versions above; these are the exact shortcuts).

The full reference is below — expand what you're curious about.

<details>
<summary><strong>The analytics team — 17 specialist agents</strong></summary>

| Agent | What it does | When |
|---|---|---|
| requirements-analyst | Turns your plain-English ask into a precise brief and writes down any assumptions | Framing |
| source-profiler | Checks the data is complete and trustworthy; issues a GO / NO-GO | Framing |
| semantic-architect | Pins down exactly what each metric means, from the locked definitions | Framing |
| sql-engineer | Writes the careful, read-only, cost-aware queries and stores every one | Throughout |
| explorer | Chases several possible explanations at once, each in isolation | Exploration |
| root-cause-analyst | Breaks the number down into its true drivers (mix vs. rate, Simpson's check) | Diagnosis |
| statistician | Tests whether a finding is real or noise; flags anything under-powered | Diagnosis |
| red-team-validator | Independently re-derives the headline and attacks the conclusion; can veto | Validation |
| opportunity-sizer | Puts a dollar figure on the finding, with a sensitivity range | Diagnosis |
| forecaster | Projects a metric forward with an honest uncertainty band *(when there's enough history)* | Diagnosis |
| cohort-analyst | Retention, vintage, and lifetime-value analysis *(when the data has customers)* | Diagnosis |
| narrative-writer | Writes the answer-first story for your named decision-maker | Story |
| deck-builder | Assembles the branded slide deck with speaker notes | Deck |
| stakeholder-simulator | Role-plays your toughest stakeholder and checks the deck answers their 5 hardest questions | Deck |
| comms-drafter | Drafts the Slack / email / one-paragraph exec summaries | Deck |
| experiment-designer | Designs A/B tests — sample size, guardrails, decision rule *(on demand, not in every run)* | On demand |
| retrospective-agent | After each run, records what was corrected so the mistake isn't repeated | Learning |

</details>

<details>
<summary><strong>The full menu — 25 commands</strong></summary>

**Ask & answer**
| Command | What it does |
|---|---|
| `/analyze "<question>"` | The full analysis → validated deck |
| `/quick "<question>"` | A fast, single-number answer with a chart |
| `/rca <metric> <window>` | Root-cause only (skips the framing stage) |
| `/route "<question>"` | Suggests the cheapest path that answers your question |

**Analytical tools**
| Command | What it does |
|---|---|
| `/forecast <metric>` | Trend, anomalies, seasonality, and a forecast |
| `/cohort <source>` | Retention / vintage / lifetime-value |
| `/size "<finding>"` | Size the opportunity with a sensitivity range |
| `/experiment <base> <mde>` | Design an A/B test |
| `/profile <source>` | Data-quality check with a GO / NO-GO |

**Redo just one part** (after feedback, without repeating everything)
| Command | What it does |
|---|---|
| `/explore <run_id>` | Re-run the exploration stage |
| `/diagnose <run_id>` | Re-run the root-cause + stats stage |
| `/narrative <run_id>` | Rewrite the story |
| `/deck <run_id>` | Rebuild the deck |
| `/validate <run_id>` | Re-run the red-team check |

**Share & revisit**
| Command | What it does |
|---|---|
| `/export <format> <run_id>` | Export to HTML / PDF / Slack / email / exec summary |
| `/runs [run_id]` | List, inspect, and compare past analyses |
| `/resume <run_id>` | Resume an interrupted run where it left off |
| `/replay <run_id>` | Re-run a past analysis against today's data to see if it still holds |

**Knowledge & learning**
| Command | What it does |
|---|---|
| `/business [term]` | Browse the glossary, products, teams, and metric ownership |
| `/metrics [metric]` | Browse the metric dictionary (definition + owner) |
| `/lessons [tag]` | Search what Atlas has learned |
| `/log-correction "<wrong> -> <right>"` | Log a correction so it isn't repeated |
| `/retro <run_id>` | Force a post-run retrospective |

**Setup**
| Command | What it does |
|---|---|
| `/connect <source>` | Register and test a data source (read-only) |
| `/setup` | Onboarding interview — teach Atlas your role, data, and context |

</details>

<details>
<summary><strong>The playbooks it follows — 15 skills</strong></summary>

| Skill | What it covers |
|---|---|
| metric-decomposition | Breaking a metric change into mix vs. rate and per-segment drivers |
| statistical-testing | Which test to use, statistical power, confidence intervals, seasonality |
| root-cause-playbooks | Named recipes: revenue drop, margin compression, churn spike, funnel leak… |
| advanced-analytics | Cohorts, forecasting, opportunity sizing, experiments, the A–F confidence grade |
| data-profiling | The standard data-quality checks and how to read them |
| data-connectors | Connecting to files and warehouses, safely and read-only |
| sql-dialects | The differences between Snowflake / BigQuery / Postgres / Databricks / DuckDB |
| validation-protocol | The independent re-derivation and veto rules the red-team uses |
| narrative-craft | Answer-first executive writing; titles that make a claim, not a label |
| deck-standards | Slide layout, chart choice, speaker notes, and appendix requirements |
| guardrails-closeloop | Pairing every goal with a safety metric; owner + follow-up on every recommendation |
| business-knowledge | The glossary, metric dictionary, ownership, and reusing proven queries |
| memory-protocol | How lessons are recorded, de-duplicated, and promoted so mistakes stick fixed |
| question-router | Classifying a question so a quick lookup doesn't trigger the full pipeline |
| first-run-welcome | Orienting a new user and offering setup on first use |

</details>

---

## What Atlas can and can't do

Honesty is part of the product, so here are the limits stated plainly:

- **It's a power tool for an analyst, not a replacement for one.** It handles roughly
  the 80% of an analysis that eats all the time. **You (or your analyst) are the final
  check** — run it first on questions you already know the answer to, so you can catch
  and correct it.
- **It needs your business context.** The more you teach it your metrics, your product
  names, and your definitions, the better it gets. It learns from your corrections and
  won't make the same mistake twice.
- **Some capabilities need the right data.** Forecasting needs enough history;
  retention/cohort analysis needs a customer identifier in the data. When the data can't
  support something, Atlas tells you — it doesn't fake it.
- **Connecting live systems is a setup step.** Spreadsheets and files work immediately.
  Data warehouses (Snowflake, BigQuery, Postgres, Databricks) need a one-time, read-only
  connection set up by your technical team.

---

## Getting your first analysis

The best way to build trust is to start where you can check the answer:

1. **Pick a question you already know the answer to** — a report you were going to run
   anyway this week.
2. **Have your analyst point Atlas at the data and ask it.** The first run takes a little
   longer because you're teaching it your context; by the third, it's faster than doing
   it by hand.
3. **Read the deck critically.** Look at the headline, the confidence grade, and the
   Assumptions page. Because you know this data, you'll spot anything off immediately.
4. **Correct anything wrong.** Atlas records the correction and applies it from then on.
   That's the whole loop — look, check, correct, move on.

Do that a few times and you'll trust it on the questions you *don't* already know the
answer to.

---

## Appendix — for your technical team

Atlas runs inside [Claude Code](https://claude.com/claude-code). It's a Python project
managed with [`uv`](https://github.com/astral-sh/uv); the analytical engine is
deterministic and fully tested, separate from the AI layer.

```bash
# setup
uv venv --python 3.13.9
uv pip install -e ".[dev]"          # core; add ".[warehouse]" to connect a warehouse

# run the full pipeline on the bundled example, no API key needed
uv run python -c "from atlas.orchestrator import run_analysis; \
r = run_analysis('Why did EMEA gross margin drop 4pts in Q2?'); \
print(r.status, '|', r.headline); print(r.run_dir)"

# the test suite (140 tests)
uv run pytest -q
```

Every run writes a complete audit trail to `runs/<run_id>/` — the brief, the data
profile, the queries and their results, the findings, the red-team validation, the
narrative, the deck (`.pptx` + `.html`), the comms drafts, and `provenance.json` (the
number-to-query ledger). Analysts drive Atlas through the **25 slash commands, 17
specialist agents, and 15 skills** listed in
[*Under the hood*](#under-the-hood--the-team-the-playbooks-and-the-menu) above; each
agent, command, and skill is a plain markdown file in `.claude/` that you can read and
edit. Data sources are registered read-only in `atlas/connectors/sources.yaml`.

- **The rules Atlas operates under:** `CLAUDE.md` (the project constitution — the
  non-negotiables described above, in full).
- **The analytical engine:** `atlas/` (connectors, the provenance ledger, the
  decomposition/forecast/sizing math, the quality gates, the deck builders).
- **The specialist agents, commands, and skills:** the `.claude/` folder.

Atlas is read-only to every data source, enforced in two independent places, and no
figure reaches any output — deck, web page, or Slack message — without resolving in the
provenance ledger first.
