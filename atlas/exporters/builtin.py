"""The formats that already existed, migrated onto the registry.

Output is byte-identical to the pre-registry if/elif ladder — `tests/test_export.py`
passes unchanged, which is the evidence the migration changed nothing. The behaviour
that *did* change is the failure mode: an unrecognised format now raises
`UnknownExportFormat` instead of silently producing nothing and reporting success.
"""
from __future__ import annotations

from atlas.lib import comms as comms_mod
from atlas.lib.comms import FindingBundle
from atlas.lib.deck_html import build_html, export_pdf
from atlas.lib.export_registry import ExportContext, Exporter, register_exporter

__all__ = ["HtmlExporter", "PdfExporter", "SlackExporter", "EmailExporter",
           "ExecExporter", "bundle_for"]


def bundle_for(ctx: ExportContext) -> FindingBundle:
    """The comms payload. Claim ids come from the deck spec rather than a hardcoded
    tuple, so this works for any playbook rather than only the margin one."""
    key = []
    for cid in ctx.spec.referenced_claim_ids():
        c = ctx.ledger.get(cid)
        if c and not any(k["claim_id"] == cid for k in key):
            key.append({"label": c.text, "value": c.value, "claim_id": cid})
    rec = next((s.title for s in ctx.spec.slides if s.kind == "recommendation"),
               "See recommendation.")
    headline = getattr(ctx.state, "headline", "") or ctx.spec.title
    return FindingBundle(headline=headline, decision_owner=ctx.spec.decision_owner,
                         key_numbers=key[:6], recommendation=rec)


@register_exporter
class HtmlExporter(Exporter):
    id = "html"
    description = "Self-contained HTML deck with base64-embedded charts."
    requires = ("spec", "ledger")

    def emit(self, ctx: ExportContext) -> list[str]:
        build_html(ctx.spec, ctx.ledger, ctx.run_dir / "deck.html")
        return ["deck.html"]


@register_exporter
class PdfExporter(Exporter):
    id = "pdf"
    description = "PDF via the HTML deck. Needs the optional [deck] extra."
    requires = ("spec", "ledger")

    def emit(self, ctx: ExportContext) -> list[str]:
        html_path = ctx.run_dir / "deck.html"
        if not html_path.exists():
            build_html(ctx.spec, ctx.ledger, html_path)
        res = export_pdf(html_path)
        ctx.options["pdf_status"] = res
        # A deferred PDF (weasyprint absent) is reported, never silently claimed.
        return ["deck.pdf"] if res.get("status") == "ok" else []


@register_exporter
class SlackExporter(Exporter):
    id = "slack"
    description = "Slack-ready summary; every number provenance-checked."
    requires = ("spec", "ledger")

    def emit(self, ctx: ExportContext) -> list[str]:
        (ctx.run_dir / "comms_slack.md").write_text(
            comms_mod.slack_summary(bundle_for(ctx), ctx.ledger))
        return ["comms_slack.md"]


@register_exporter
class EmailExporter(Exporter):
    id = "email"
    description = "Email brief with subject line."
    requires = ("spec", "ledger")

    def emit(self, ctx: ExportContext) -> list[str]:
        eb = comms_mod.email_brief(bundle_for(ctx), ctx.ledger)
        (ctx.run_dir / "comms_email.md").write_text(
            f"Subject: {eb['subject']}\n\n{eb['body']}")
        return ["comms_email.md"]


@register_exporter
class ExecExporter(Exporter):
    id = "exec"
    description = "One-paragraph executive summary."
    requires = ("spec", "ledger")

    def emit(self, ctx: ExportContext) -> list[str]:
        (ctx.run_dir / "comms_exec.md").write_text(
            comms_mod.exec_summary(bundle_for(ctx), ctx.ledger))
        return ["comms_exec.md"]
