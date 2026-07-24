"""Stakeholder communications: Slack summary, email brief, exec summary.

Generated from a structured finding bundle — every number carries a provenance
claim_id and is checked against the ledger before anything is drafted (Gate 4 for
comms). Atlas will not put an unsourced number into a Slack message either.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from atlas.lib.export_gate import assert_no_orphans
from atlas.lib.provenance import ProvenanceLedger


@dataclass
class FindingBundle:
    headline: str                       # one-sentence answer
    decision_owner: str
    key_numbers: list[dict]             # [{label, value, claim_id}]
    recommendation: str
    claim_ids: list[str] = field(default_factory=list)

    def all_claim_ids(self) -> list[str]:
        return list({*(self.claim_ids), *(k["claim_id"] for k in self.key_numbers
                                          if k.get("claim_id"))})


def _gate(bundle: FindingBundle, ledger: ProvenanceLedger) -> None:
    assert_no_orphans(ledger, bundle.all_claim_ids())


def slack_summary(bundle: FindingBundle, ledger: ProvenanceLedger) -> str:
    _gate(bundle, ledger)
    nums = "  ".join(f"*{k['label']}:* {k['value']}" for k in bundle.key_numbers)
    return (f":bar_chart: *{bundle.headline}*\n{nums}\n"
            f":dart: _Recommendation:_ {bundle.recommendation}\n"
            f"_For {bundle.decision_owner} · every number is query-sourced._")


def email_brief(bundle: FindingBundle, ledger: ProvenanceLedger) -> dict:
    _gate(bundle, ledger)
    body = [f"Hi {bundle.decision_owner.split(',')[0]},", "",
            bundle.headline, "", "Key numbers:"]
    body += [f"  • {k['label']}: {k['value']}" for k in bundle.key_numbers]
    body += ["", f"Recommendation: {bundle.recommendation}", "",
             "Every figure traces to a stored query (provenance available on request).",
             "", "— Atlas"]
    return {"subject": f"[Analysis] {bundle.headline}", "body": "\n".join(body)}


def exec_summary(bundle: FindingBundle, ledger: ProvenanceLedger) -> str:
    _gate(bundle, ledger)
    kn = "; ".join(f"{k['label']} {k['value']}" for k in bundle.key_numbers)
    return (f"{bundle.headline} ({kn}). Recommendation: {bundle.recommendation}. "
            f"All figures are provenance-stamped.")
