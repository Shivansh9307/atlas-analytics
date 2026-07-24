"""Google Slides export — DORMANT (Phase 8), best-effort.

The .pptx from deck_pptx.py is the source of truth. Slides export is optional and
needs a one-time OAuth consent (which interrupts a full-auto run the first time,
then caches a token). Requires the [deck] extra.

export_to_slides() returns a status dict; it NEVER raises into the pipeline — an
unavailable token just defers the export.
"""
from __future__ import annotations

from pathlib import Path

TOKEN = Path(__file__).resolve().parents[2] / ".gslides_token.json"


def export_to_slides(pptx_path: str | Path, title: str) -> dict:
    """Best-effort export. Returns {status, detail, url?}."""
    if not TOKEN.exists():
        return {
            "status": "deferred",
            "detail": "Google Slides export needs one-time OAuth. Run the interactive "
                      "auth once to cache .gslides_token.json, then re-run /deck.",
        }
    try:  # pragma: no cover - Phase 8
        return _do_export(pptx_path, title)
    except Exception as e:  # pragma: no cover
        return {"status": "error", "detail": str(e)}


def _do_export(pptx_path, title) -> dict:  # pragma: no cover - Phase 8
    # Phase 8: upload pptx to Drive with mimeType application/vnd.google-apps.presentation
    # (Drive converts to Slides), via google-api-python-client using the cached token.
    raise NotImplementedError("Phase 8: implement Drive->Slides conversion upload")
