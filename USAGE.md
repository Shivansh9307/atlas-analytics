# Atlas — How to use it (operator guide)

This is the hands-on guide for the person **driving** Atlas (usually an analyst): how to
add your data, ask a question, get a PowerPoint deck, run individual commands, and get
other formats. For the *why it can be trusted* / stakeholder view, see
[README.md](README.md).

Everything here is copy-paste. Anywhere you see `<...>`, substitute your own value.

---

## 1. Before you start

You need:

- **[Claude Code](https://claude.com/claude-code)** — Atlas runs inside it.
- **Python 3.13** and **[`uv`](https://github.com/astral-sh/uv)**.

Set up the environment once:

```bash
uv venv --python 3.13.9
uv pip install -e ".[dev]"        # the core engine + tests

# optional, only if you need them later:
uv pip install -e ".[warehouse]"  # Postgres / Snowflake / BigQuery / Databricks drivers
uv pip install -e ".[deck]"       # PDF export
uv pip install -e ".[llm]"        # optional in-script LLM checks
```

The core pipeline (files → deck) needs **no API key and no credentials**.

---

## 2. 60-second demo — get a PowerPoint from the bundled example

Atlas ships with a small example dataset so you can see a real deck immediately:

```bash
uv run python -c "from atlas.orchestrator import run_analysis; \
r = run_analysis('Why did EMEA gross margin drop 4pts in Q2?'); \
print(r.status, '|', r.headline); print('deck:', r.run_dir / 'deck.pptx')"
```

You'll get something like:

```
COMPLETE | EMEA gross margin fell 4.0pts (60.0% -> 56.0%), driven by mix.
deck: runs/r-20260724-100237/deck.pptx
```

Open that `deck.pptx` — a full, provenance-stamped slide deck. Everything else in
`runs/<run_id>/` is the audit trail (see §4).

---

## 3. Add your own data source

There's no hidden database — you register sources in one file:
**`atlas/connectors/sources.yaml`**. Adding a source means adding a block there, then
testing it. Atlas is **read-only** to every source.

### 3a. A CSV or Excel file (works immediately, no credentials)

1. Put your file somewhere in the project, e.g. `data/sales.csv`.
2. Add a block to `atlas/connectors/sources.yaml`:

   ```yaml
   sources:
     my_sales:                      # <- your name for it
       dialect: duckdb
       kind: file
       path: ./data/sales.csv       # .csv, .tsv, .xlsx, or .parquet
       table_name: sales            # the name you'll query it by
       row_limit: 5000000
   ```
   Excel is handled too — for a multi-sheet workbook add `sheet: "Sheet1"`.

3. Test and profile it (in Claude Code):

   ```
   /connect my_sales
   /profile my_sales
   ```
   `/connect` confirms it's reachable and read-only; `/profile` runs the data-quality
   battery and gives a **GO / NO-GO** verdict (row counts, nulls, duplicates, grain).

You can also test it from the shell without Claude Code:
```bash
uv run python .claude/skills/data-connectors/scripts/conn_test.py my_sales
```

### 3b. A data warehouse (Postgres / Snowflake / BigQuery / Databricks)

1. In `sources.yaml`, uncomment the template for your warehouse and give it a name. The
   templates reference credentials **by environment-variable name only** — never put a
   secret in this file.
2. Copy `.env.example` to `.env` (which is gitignored) and fill in the values it names,
   e.g. for Postgres: `PG_HOST`, `PG_USER`, `PG_PASSWORD`, `PG_DATABASE`. **Use a
   read-only database role.**
3. Install the drivers: `uv pip install -e ".[warehouse]"`.
4. Test it:
   ```
   /connect my_warehouse
   ```

Notes:
- **MCP-first:** where a mature official connector exists (Snowflake, Databricks,
  BigQuery), Atlas prefers it; otherwise it uses the documented Python driver.
- **Fallback chain:** you can give a source a `fallback:` (a local CSV/DuckDB copy) so a
  warehouse outage doesn't stop you — Atlas will use it and **tell you which source
  actually answered**.

---

## 4. Ask a question → get a deck

There are two ways to run an analysis. Pick based on your data.

### Path A — In Claude Code (the general path, any data shape)

Just ask:

```
/analyze "Why did conversion drop for mobile users last month?"
```

Claude orchestrates the 17 specialist agents: they profile your source, lock the metric
definition, explore hypotheses, decompose the cause, red-team it, write the story, and
build the deck — **adapting the queries to your schema**. When it finishes you get the
one-sentence answer, the gate results, and the path to the deck.

Use this for **your own data**, whatever its shape.

### Path B — The deterministic runner (margin-shaped data, demos, CI)

```bash
uv run python -c "from atlas.orchestrator import run_analysis; \
r = run_analysis('<your question>', source='my_sales', table='sales'); \
print(r.status, r.headline, r.run_dir)"
```

⚠️ **Honest limitation:** this built-in runner implements the *margin-decomposition
playbook* and expects columns shaped like the bundled example —
`region, quarter, product_line, segment, revenue, cogs`. It's perfect for the demo, for
margin questions on similarly-shaped data, and for automated testing. For **any other
schema or question type, use Path A**, where the agents write the right queries for your
data.

### Where your outputs land: `runs/<run_id>/`

| File | What it is |
|---|---|
| `deck.pptx` | **Your PowerPoint** |
| `speaker_notes.md` | ~1 minute of talking track per slide |
| `brief.md` | The framed question + declared assumptions |
| `profile/` | The data-quality verdict |
| `findings.md` | The ranked cause with evidence tiers |
| `validation.md` | The red-team's re-derivation + A–F confidence grade |
| `narrative.md` | The written story |
| `sizing.md` | The opportunity size + tornado |
| `provenance.json` | The receipts — every number → its query |
| `queries/`, `evidence/` | Every query run and the exact rows it returned |

---

## 5. Run a single command (you rarely need the whole pipeline)

In Claude Code, type the command. A few you'll use often:

```
/quick "What was EMEA revenue in Q2?"        # one number + a chart, no deck
/rca gross_margin "Q2 vs Q1"                 # root-cause only
/forecast revenue 4                          # forecast the next 4 periods
/profile my_sales                            # data-quality check only
/route "Why is churn up?"                     # tells you which command fits
```

**Redo just one part** after feedback, without paying for the whole run — pass the
`run_id` (find it with `/runs`):

```
/diagnose <run_id>     # re-run the root-cause + stats
/narrative <run_id>    # rewrite the story
/deck <run_id>         # rebuild the deck
/validate <run_id>     # re-run the red-team
```

The full menu of all 25 commands is in the
[README](README.md#under-the-hood--the-team-the-playbooks-and-the-menu).

---

## 6. Get other formats (HTML, PDF, Slack, email)

The `.pptx` is produced automatically. To render the *same validated findings* in other
formats, export a finished run:

```
/export html,slack,email <run_id>
```

or from the shell:

```bash
uv run python -c "from atlas.lib.exporters import export_run; \
import json; print(json.dumps(export_run('<run_id>', formats=['html','slack','email']), indent=2))"
```

- **HTML** — a single self-contained web page (charts embedded, no internet needed);
  great for sharing a link or emailing.
- **Slack / email / exec** — ready-to-send text summaries.
- **PDF** — best-effort; needs `uv pip install -e ".[deck]"` (weasyprint). Without it,
  Atlas reports `deferred` and the HTML is the portable source of truth.

Every format re-checks that **every number resolves in the provenance ledger** before it
writes — no unsourced number ships in any format.

---

## 7. How skills work

You don't invoke skills manually — they **load automatically** when your task matches
(ask for a chart and the charting standards load; start an analysis and the profiling
checks load). You *can* call one explicitly with `/<skill-name>`.

Four skills also ship command-line tools:

```bash
# break a metric change into mix / rate / interaction
uv run python .claude/skills/metric-decomposition/scripts/decompose.py my_sales <region> Q1 Q2

# test a source connection
uv run python .claude/skills/data-connectors/scripts/conn_test.py my_sales

# independently re-derive a headline number (what the red-team does)
uv run python .claude/skills/validation-protocol/scripts/rederive.py my_sales <region> Q1 Q2 60.0 56.0

# search / record what Atlas has learned
uv run python .claude/skills/memory-protocol/scripts/lesson.py find metric:gross_margin
```

The full list of 15 skills is in the
[README](README.md#under-the-hood--the-team-the-playbooks-and-the-menu).

---

## 8. Re-run, resume, and revisit

```
/runs                  # list past analyses with their status
/runs <run_id>         # inspect one in detail
/resume <run_id>       # continue an interrupted run where it left off (no re-query)
/replay <run_id>       # re-run a past analysis against today's data — does it still hold?
```

Nothing is thrown away — every run is a folder under `runs/` you can revisit or rebuild.

---

## 9. Teach Atlas your business (this is what makes it trustworthy over time)

The more context Atlas has, the sharper and more trustworthy it gets:

```
/setup                 # a short interview: your role, your data, your key metrics
/business              # browse the glossary, products, teams, metric ownership
/metrics conversion    # see a metric's exact definition and who owns it
```

- **Lock a metric definition** so it's never guessed: add it to
  `atlas/semantic/metrics.yaml` (Atlas resolves against these and escalates rather than
  inventing a formula).
- **Log a correction** when it gets something wrong:
  ```
  /log-correction "used net margin -> should be gross margin"
  ```
  Promotable corrections (a wrong metric, a source quirk) become permanent guardrails,
  not just notes — so the mistake can't recur.

---

## 10. Troubleshooting

| You see… | What it means / what to do |
|---|---|
| **Profile says NO-GO** | The data is too incomplete or messy to answer honestly. The verdict names the reason (e.g. duplicate rows, empty column). Fix the data or pick a cleaner table. |
| **Run comes back BLOCKED** | A quality gate refused to pass. Atlas writes a `BLOCKED.md` saying exactly what's blocking and what it needs — fix that, then re-run (or `/resume <run_id>`). It will not ship a degraded deck. |
| **PDF export says `deferred`** | The optional PDF engine isn't installed. Run `uv pip install -e ".[deck]"`, or just use the self-contained HTML. |
| **Warehouse source is "dormant"** | Its credentials aren't set. Add the env-var values to `.env` and re-run `/connect`. |
| **The metric meaning looks wrong** | It resolved "margin" to the wrong definition. Fix it in `atlas/semantic/metrics.yaml` and `/log-correction` so it sticks. |
| **`/analyze` on your own data doesn't fit the built-in runner** | Use Path A (`/analyze` inside Claude Code), not the deterministic `run_analysis` — the agents adapt to your schema. |

---

## Quick reference

| I want to… | Do this |
|---|---|
| See a deck right now | The 60-second demo (§2) |
| Add a spreadsheet | Edit `sources.yaml` → `/connect` → `/profile` (§3a) |
| Add a warehouse | Uncomment template + `.env` + `[warehouse]` → `/connect` (§3b) |
| Full analysis on my data | `/analyze "<question>"` (§4, Path A) |
| A quick number | `/quick "<question>"` (§5) |
| The PowerPoint | `runs/<run_id>/deck.pptx` (§4) |
| HTML / Slack / email | `/export <formats> <run_id>` (§6) |
| Redo one stage | `/diagnose` / `/narrative` / `/deck <run_id>` (§5) |
| Teach it a definition | `atlas/semantic/metrics.yaml` + `/log-correction` (§9) |
