"""Optional, provider-agnostic LLM shim.

IMPORTANT: This is NEVER used to produce numbers. Numbers come only from SQL
results. The shim exists for optional non-numeric sanity checks (e.g. an
LLM-as-judge "does this narrative overclaim?" pass). It is fully disable-able:
set ATLAS_LLM_PROVIDER=none (or leave keys unset) and `enabled` is False.

Default provider is OpenAI (per project config); Anthropic is an alternate.
"""
from __future__ import annotations

from atlas.config import LLM


def is_enabled() -> bool:
    return LLM.enabled


def judge(prompt: str, *, system: str = "", max_tokens: int = 512) -> str | None:
    """Return the model's text, or None if the shim is disabled/unavailable.

    Callers MUST treat a None as "skip the optional check", never as a failure,
    so the core pipeline runs identically with or without a key.
    """
    if not LLM.enabled:
        return None
    try:
        if LLM.provider == "anthropic":
            return _anthropic(prompt, system, max_tokens)
        return _openai(prompt, system, max_tokens)
    except Exception:
        # optional path: never let a judge call break the pipeline
        return None


def _openai(prompt: str, system: str, max_tokens: int) -> str | None:
    from openai import OpenAI  # requires the [llm] extra
    client = OpenAI(api_key=LLM.openai_key)
    msgs = ([{"role": "system", "content": system}] if system else []) + \
           [{"role": "user", "content": prompt}]
    resp = client.chat.completions.create(
        model="gpt-4o-mini", messages=msgs, max_tokens=max_tokens,
    )
    return resp.choices[0].message.content


def _anthropic(prompt: str, system: str, max_tokens: int) -> str | None:
    import anthropic  # requires the anthropic package
    client = anthropic.Anthropic(api_key=LLM.anthropic_key)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        system=system or None,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
