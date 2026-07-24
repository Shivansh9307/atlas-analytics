---
name: memory-protocol
description: How Atlas lessons are written, tagged, deduplicated, retrieved, and PROMOTED into hard artefacts. Use in the retrospective and before each wave when injecting matching lessons.
---

# Memory protocol

Honest framing first: **only promoted artefacts are guaranteed. Prompt-injected
lessons are best-effort.** Never claim "never makes the same mistake twice" for a
plain lesson — only for a lesson that has been promoted to code.

## Lesson schema (`memory/lessons.jsonl`)
`id, trigger, tags, what_went_wrong, rule, run_id, times_prevented, created,
last_fired`. Tags look like `source:snowflake`, `metric:gross_margin`,
`agent:sql-engineer`, `class:filter-leakage`.

## Failure fingerprint (`memory/failures.jsonl`)
`sha256(source | metric | failure_class)`. Before a wave, matching lessons are
retrieved by fingerprint and injected into the owning agent's prompt.

## The script
`uv run python .claude/skills/memory-protocol/scripts/lesson.py <cmd> …`
- `add '<json>'` — append with semantic-dedup (skips near-duplicates)
- `find <tag>` — retrieve matching lessons
- `retrieve <source> <metric> <class>` — by fingerprint
- `fire <id>` — increment `times_prevented`; tells you when to promote

## Promotion — "fires twice ⇒ becomes code"
When `times_prevented >= 2`, promote to ONE hard artefact and mark the lesson
promoted:
| Lesson class | Promote to | Guarantee |
|---|---|---|
| metric-definition | lock formula in `atlas/semantic/metrics.yaml` | mechanical |
| unsafe-write | rule in `.claude/hooks/pre_tool_use.py` | mechanical |
| source-quirk | assertion in `memory/quirks/<source>.md` | mechanical if asserted |
| fragile-query | assertion in a query template | mechanical if asserted |
| analytical | keep as prompt injection | best-effort |

## Pruning
Lessons with `times_prevented == 0` after 20 runs are archived to
`lessons.archive.jsonl`.
