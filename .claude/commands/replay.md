---
description: Re-execute a past run's stored queries against current data to check if the finding still holds.
argument-hint: <run_id>
---

Replay run **$ARGUMENTS** against current data.

For each stored query in `runs/$ARGUMENTS/queries/*.sql`, re-run it via the
connector and re-hash the result. Compare each new `result_hash` to the stored one
(`QueryStore.verify` shows whether the stored result still reproduces).

Report, per headline number: unchanged / drifted (old → new value). If the
headline drifted beyond the re-derivation tolerance, say the past finding **no
longer holds** and recommend a fresh `/analyze`.
