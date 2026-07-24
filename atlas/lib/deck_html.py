"""Self-contained HTML deck export (+ best-effort PDF).

Renders the same DeckSpec the pptx builder uses into ONE portable .html file with
inline CSS and chart images embedded as base64 data URIs — no external requests, so
it opens anywhere and survives being emailed. Theme-aware (light/dark).

Gate 4 applies here too: every number shown must resolve in the ledger
(export_gate.assert_no_orphans), enforced before a byte is written.
"""
from __future__ import annotations

import base64
import html
from pathlib import Path

from atlas.lib.deck_pptx import Chart, DeckSpec
from atlas.lib.export_gate import assert_no_orphans
from atlas.lib.provenance import ProvenanceLedger
from atlas.lib.theme_loader import Theme, load_theme


def _png_data_uri(path: str | Path) -> str:
    data = Path(path).read_bytes()
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def _chart_png(chart: Chart, out_dir: Path, idx: int, theme: Theme) -> str | None:
    """Render a DeckSpec Chart to a PNG via the SWD chart module; return a data URI."""
    from atlas.lib import charts
    try:
        cats = chart.categories
        # one series -> highlight last; multi-series -> plain columns
        series_name, values = next(iter(chart.series.items()))
        p = out_dir / f"_chart_{idx}.png"
        charts.bar_chart(cats, values, p,
                         highlight_index=len(values) - 1 if len(values) > 1 else None,
                         title=chart.title or series_name, subtitle="", theme=theme,
                         orient="bar" if chart.kind == "bar" else "column")
        uri = _png_data_uri(p)
        p.unlink(missing_ok=True)
        return uri
    except Exception:
        return None


def build_html(
    spec: DeckSpec, ledger: ProvenanceLedger, out_path: str | Path,
    *, theme_name: str = "default",
) -> Path:
    # Gate 4 for this format
    assert_no_orphans(ledger, spec.referenced_claim_ids())

    theme = load_theme(theme_name)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    sections = [_cover(spec, theme)]
    for i, sl in enumerate(spec.slides):
        sections.append(_slide(sl, i, theme, out_path.parent))
    sections.append(_appendix(spec, theme))

    doc = _document(spec.title, "\n".join(sections), theme)
    out_path.write_text(doc)
    return out_path


def export_pdf(html_path: str | Path) -> dict:
    """Best-effort HTML->PDF. Needs the optional [deck] extra (weasyprint).

    Never raises into the pipeline; returns a status dict (mirrors the Slides stub).
    """
    html_path = Path(html_path)
    pdf_path = html_path.with_suffix(".pdf")
    try:
        from weasyprint import HTML  # optional
        HTML(string=html_path.read_text()).write_pdf(str(pdf_path))
        return {"status": "ok", "path": str(pdf_path)}
    except Exception as e:  # pragma: no cover - optional dep
        return {"status": "deferred",
                "detail": f"PDF export needs the [deck] extra (weasyprint): {e}. "
                          "The self-contained HTML is the portable source of truth."}


# --------------------- HTML fragments ---------------------
def _e(s) -> str:
    return html.escape(str(s))


def _document(title: str, body: str, theme: Theme) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(title)}</title>
<style>
:root {{ --surface:{theme.surface}; --ink:{theme.text_primary}; --muted:{theme.text_secondary};
        --grid:{theme.grid}; --accent:{theme.highlight}; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:var(--grid); color:var(--ink);
        font-family:'Helvetica Neue',Arial,sans-serif; line-height:1.5; }}
.slide {{ background:var(--surface); max-width:960px; margin:24px auto; padding:40px 48px;
          border-radius:10px; box-shadow:0 1px 4px rgba(0,0,0,.08); }}
.slide h1 {{ font-size:26px; margin:0 0 6px; }}
.slide h2 {{ font-size:20px; margin:0 0 14px; color:var(--ink); }}
.sub {{ color:var(--muted); font-size:14px; margin:0 0 18px; }}
.kicker {{ text-transform:uppercase; letter-spacing:.08em; font-size:11px; color:var(--accent);
           font-weight:700; }}
ul {{ margin:8px 0 16px; padding-left:20px; }} li {{ margin:4px 0; }}
img.chart {{ max-width:100%; height:auto; margin:8px 0; border-radius:6px; }}
table {{ border-collapse:collapse; width:100%; font-size:13px; }}
th,td {{ border:1px solid var(--grid); padding:6px 8px; text-align:left; }}
th {{ color:var(--muted); font-weight:600; }}
.notes {{ margin-top:14px; padding:12px 14px; background:var(--grid); border-radius:6px;
          font-size:13px; color:var(--muted); }}
@media (prefers-color-scheme: dark) {{
  body {{ background:#111; }} .slide {{ background:#1a1a19; box-shadow:none; }}
  :root {{ --ink:#fff; --muted:#c3c2b7; --grid:#333; }}
}}
</style></head><body>
{body}
</body></html>"""


def _cover(spec: DeckSpec, theme: Theme) -> str:
    return (f'<section class="slide"><div class="kicker">Atlas analysis</div>'
            f'<h1>{_e(spec.title)}</h1><p class="sub">{_e(spec.subtitle)} · '
            f'Prepared for {_e(spec.decision_owner)}</p></section>')


def _slide(sl, idx: int, theme: Theme, out_dir: Path) -> str:
    parts = [f'<section class="slide"><h2>{_e(sl.title)}</h2>']
    if sl.bullets:
        parts.append("<ul>" + "".join(f"<li>{_e(b)}</li>" for b in sl.bullets) + "</ul>")
    if sl.chart:
        uri = _chart_png(sl.chart, out_dir, idx, theme)
        if uri:
            parts.append(f'<img class="chart" alt="{_e(sl.chart.title)}" src="{uri}">')
    if sl.speaker_notes:
        parts.append(f'<div class="notes"><strong>Notes:</strong> {_e(sl.speaker_notes)}</div>')
    parts.append("</section>")
    return "".join(parts)


def _appendix(spec: DeckSpec, theme: Theme) -> str:
    rows = "".join(
        f"<tr><td>{_e(r.get('text',''))}</td><td>{_e(r.get('value',''))}</td>"
        f"<td><code>{_e(r.get('query_hash',''))}</code></td>"
        f"<td>{_e(r.get('tier',''))}</td></tr>"
        for r in spec.provenance)
    assumptions = "".join(f"<li>{_e(a)}</li>" for a in spec.assumptions)
    return (
        '<section class="slide"><h2>Appendix — Methodology &amp; Assumptions</h2>'
        f'<p class="sub">{_e(spec.methodology)}</p><ul>{assumptions}</ul>'
        '<h2>Provenance — every number is sourced</h2>'
        '<table><tr><th>Claim</th><th>Value</th><th>Query hash</th><th>Tier</th></tr>'
        f'{rows}</table></section>')
