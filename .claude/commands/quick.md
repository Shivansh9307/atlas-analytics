---
description: Single-agent fast path for a simple lookup — one query, one number, no deck.
argument-hint: "\"<simple question>\""
---

Fast path for: **$ARGUMENTS**

This is a simple lookup, not a full investigation. Do NOT spawn the pipeline.
Author one read-only query (via `Connector.run()` so it is still hashed and
stored), read the number, and answer in 1–3 sentences.

Still non-negotiable: the number must come from a real query result (no memory,
no estimate), and you state the source + `query_hash`. If the question actually
needs decomposition or validation, say so and suggest `/analyze` instead.
