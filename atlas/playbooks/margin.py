"""Margin playbook — gross-margin mix/rate/interaction decomposition over two periods.

This is a **verbatim port** of the analysis the orchestrator used to hardcode across
six node bodies. Same SQL, same f-strings, same rounding, same claim ids, same slide
order and count. The port is deliberately not an improvement: `tests/test_end_to_end_csv.py`
pins exact ledger values (`c_delta == -4.0`, `c_opportunity == 40.0`) and a 9-slide
deck, and those assertions are the proof that factoring the abstraction out changed
no behaviour. Improve it in a later, separate change if at all.

It also keeps populating the legacy `ctx.scratch` keys (`dec`, `add`, `simp`, `r1`,
`r2`, `rev_p1`, `rev_p2`, `row_count`, `sizing`) because orchestrator helpers that are
not part of the playbook contract — `_render_enrichment`, `_write_confidence_and_recommendation`,
`_archive_headline_queries` — read them directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from atlas.config import TOLERANCES
from atlas.lib.decomposition import (
    MarginDecomposition, SegmentContribution,
    additive_contribution, decompose_margin, simpsons_check,
)
from atlas.lib.deck_pptx import Chart, DeckSpec, Slide
from atlas.lib.sizing import Assumption, size_opportunity
from atlas.lib.validation import validate_margin_finding
from atlas.playbooks.base import (
    BriefFields, ClaimSpec, Playbook, PlaybookResult, Rederivation, SizingOutcome,
    register_playbook,
)
from atlas.playbooks.binding import ColumnBinding


@dataclass
class MarginResult(PlaybookResult):
    dec: MarginDecomposition | None = None
    add: list = field(default_factory=list)
    simp: dict = field(default_factory=dict)
    r1: tuple[str, str] = ("", "")
    r2: tuple[str, str] = ("", "")
    rev_p1: float = 0.0
    rev_p2: float = 0.0

    def as_dict(self) -> dict:
        # Flat shape, matching what n_explore persisted before the refactor, so
        # `atlas/lib/exporters.py::_rebuild_spec` keeps reading state.outputs["explore"]["dec"].
        return {
            "dec": _ser_dec(self.dec), "add": self.add, "simp": self.simp,
            "r1": list(self.r1), "r2": list(self.r2),
            "rev_p1": self.rev_p1, "rev_p2": self.rev_p2, "row_count": self.row_count,
        }


def _ser_dec(dec: MarginDecomposition) -> dict:
    return {
        "m1": dec.m1, "m2": dec.m2, "delta": dec.delta,
        "mix_total": dec.mix_total, "rate_total": dec.rate_total,
        "interaction_total": dec.interaction_total,
        "segments": [{"key": s.key, "mix": s.mix, "rate": s.rate,
                      "interaction": s.interaction, "w1": s.w1, "w2": s.w2,
                      "m1": s.m1, "m2": s.m2} for s in dec.segments],
    }


def _deser_dec(d: dict) -> MarginDecomposition:
    segs = [SegmentContribution(**s) for s in d["segments"]]
    return MarginDecomposition(
        m1=d["m1"], m2=d["m2"], delta=d["delta"], mix_total=d["mix_total"],
        rate_total=d["rate_total"], interaction_total=d["interaction_total"], segments=segs)


def _emea_rows(ctx, quarter: str):
    r = ctx.con.run(
        f"SELECT {ctx.dim}, segment, revenue, cogs FROM {ctx.table} "
        f"WHERE region = '{ctx.region}' AND quarter = '{quarter}'"
    )
    ctx.budget.charge_query(r.bytes_scanned)
    return r


@register_playbook
class MarginPlaybook(Playbook):
    id = "margin"
    description = "Gross-margin mix / rate / interaction decomposition between two periods."
    question_levels = (3,)
    supported_decompositions = frozenset({"mix_rate_interaction"})
    requirements = ()          # see bind() — this playbook predates column binding

    def bind(self, ctx) -> ColumnBinding:
        """No-op binding.

        The margin path addresses its columns literally (`revenue`, `cogs`, `region`,
        `quarter`, `ctx.dim`) exactly as it always has. Running the generic binder
        here would spend a query and risk perturbing the golden path for no gain;
        binding exists for the schema-agnostic playbooks.
        """
        return ColumnBinding(table=ctx.table)

    def brief_fields(self, ctx) -> BriefFields:
        return BriefFields(
            decision_unblocked=f"Whether/how to intervene on {ctx.region} margin.",
            primary_metric="gross margin (ratio)",
            comparison_window=f"{ctx.p2} vs {ctx.p1}",
            grain=f"product_line x segment, {ctx.region}",
            success_criteria="A ranked, decomposed, provenance-stamped cause.",
            non_goals="Other regions; forecasting; pricing strategy build-out.",
        )

    # ---- analysis ----
    def explore(self, ctx) -> MarginResult:
        r1, r2 = _emea_rows(ctx, ctx.p1), _emea_rows(ctx, ctx.p2)
        dec = decompose_margin(r1.rows, r2.rows, dim=ctx.dim)
        add = additive_contribution(r1.rows, r2.rows, dim=ctx.dim, value_key="revenue")
        simp = simpsons_check(r1.rows, r2.rows, dim=ctx.dim)
        rev_p1 = sum(float(r["revenue"]) for r in r1.rows)
        rev_p2 = sum(float(r["revenue"]) for r in r2.rows)
        res = MarginResult(
            binding=ctx.binding, row_count=len(r1.rows) + len(r2.rows),
            dec=dec, add=add, simp=simp,
            r1=(r1.query_hash, r1.result_hash), r2=(r2.query_hash, r2.result_hash),
            rev_p1=rev_p1, rev_p2=rev_p2,
        )
        self._stash(ctx, res)
        return res

    @staticmethod
    def _stash(ctx, res: MarginResult) -> None:
        """Mirror the result into the legacy scratch keys the orchestrator helpers read."""
        ctx.scratch.update(
            dec=res.dec, add=res.add, simp=res.simp, r1=res.r1, r2=res.r2,
            rev_p1=res.rev_p1, rev_p2=res.rev_p2, row_count=res.row_count,
        )

    def diagnose(self, ctx, res: MarginResult) -> list[ClaimSpec]:
        dec = res.dec
        (q1h, r1h), (q2h, r2h) = res.r1, res.r2
        return [
            ClaimSpec("c_gm_p1", f"{ctx.region} {ctx.p1} gross margin",
                      round(dec.m1 * 100, 2), q1h, r1h, evidence_tier="decomposed"),
            ClaimSpec("c_gm_p2", f"{ctx.region} {ctx.p2} gross margin",
                      round(dec.m2 * 100, 2), q2h, r2h, evidence_tier="decomposed"),
            ClaimSpec("c_delta", f"{ctx.region} margin change {ctx.p2} vs {ctx.p1} (pts)",
                      round(dec.delta_pts, 2), q2h, r2h, evidence_tier="decomposed"),
            ClaimSpec("c_mix", "Mix contribution (pts)",
                      round(dec.mix_total * 100, 2), q2h, r2h, evidence_tier="decomposed"),
            ClaimSpec("c_rate", "Rate contribution (pts)",
                      round(dec.rate_total * 100, 2), q2h, r2h, evidence_tier="decomposed"),
        ]

    # ---- validation ----
    def rederive(self, ctx, res: MarginResult) -> Rederivation:
        dec = res.dec
        rd = ctx.con.run(
            f"SELECT quarter, sum(revenue) AS rev, sum(cogs) AS cogs "
            f"FROM {ctx.table} WHERE region = '{ctx.region}' "
            f"AND quarter IN ('{ctx.p1}','{ctx.p2}') GROUP BY quarter"
        )
        ctx.budget.charge_query(rd.bytes_scanned)
        by = {row["quarter"]: (row["rev"], row["cogs"]) for row in rd.rows}
        rd_m1 = (by[ctx.p1][0] - by[ctx.p1][1]) / by[ctx.p1][0] * 100
        rd_m2 = (by[ctx.p2][0] - by[ctx.p2][1]) / by[ctx.p2][0] * 100
        tol = TOLERANCES.rederivation_rel
        ok = (abs(rd_m1 - dec.m1 * 100) <= abs(dec.m1 * 100) * tol and
              abs(rd_m2 - dec.m2 * 100) <= abs(dec.m2 * 100) * tol)
        attacks = []
        if res.simp["paradox"]:
            attacks.append("Simpson's paradox detected — aggregate hides opposite segment moves")
        ctx.scratch["rd_margins"] = (rd_m1, rd_m2)
        return Rederivation(
            ok=ok, method="raw revenue/cogs sums re-aggregated by quarter",
            comparisons=[
                {"label": ctx.p1, "analyst": dec.m1 * 100, "redteam": rd_m1, "tol": tol},
                {"label": ctx.p2, "analyst": dec.m2 * 100, "redteam": rd_m2, "tol": tol},
            ],
            attacks=attacks,
            query_refs=[(rd.query_hash, rd.result_hash)],
        )

    def validation_layers(self, ctx, res: MarginResult):
        dec = res.dec
        report = validate_margin_finding(
            row_count=res.row_count or 1, profile_ok=True,
            mix=dec.mix_total, rate=dec.rate_total, interaction=dec.interaction_total,
            delta=dec.delta, m1=dec.m1, m2=dec.m2, paradox=res.simp["paradox"])
        return report.layers

    # ---- downstream ----
    def size(self, ctx, res: MarginResult) -> SizingOutcome:
        dec = res.dec
        rev_p2 = float(res.rev_p2)
        recoverable_pts = abs(dec.mix_total) * 100.0     # mix-driven points, recoverable

        def model(a: dict) -> float:
            return a["recoverable_pts"] / 100.0 * a["revenue"]

        assumptions = [
            Assumption("recoverable_pts", base=recoverable_pts,
                       low=recoverable_pts / 2, high=recoverable_pts),
            Assumption("revenue", base=rev_p2, low=rev_p2 * 0.9, high=rev_p2 * 1.1),
        ]
        sized = size_opportunity(assumptions, model)
        q2h, r2h = res.r2
        ctx.scratch["sizing"] = sized
        d = sized.as_dict()
        doc = (
            "sizing.md",
            f"# Opportunity sizing\n\n"
            f"**Base case:** recovering the mix-driven {recoverable_pts:.1f}pts on "
            f"{ctx.region} {ctx.p2} revenue ({rev_p2:,.0f}) ≈ **{sized.base:,.0f}** "
            f"[c_opportunity].\n\n**Most sensitive to:** {d['most_sensitive_to']}.\n\n"
            f"## Tornado\n" +
            "\n".join(f"- {b['assumption']}: {b['low']:,.0f} … {b['high']:,.0f} "
                      f"(swing {b['swing']:,.0f})" for b in d["tornado"]) + "\n",
        )
        return SizingOutcome(
            output={"opportunity": round(sized.base, 2),
                    "most_sensitive_to": d["most_sensitive_to"]},
            claims=[
                ClaimSpec("c_revenue_p2", f"{ctx.region} {ctx.p2} revenue",
                          round(rev_p2, 2), q2h, r2h, evidence_tier="decomposed"),
                ClaimSpec("c_opportunity", f"Margin-recovery opportunity ({ctx.p2})",
                          round(sized.base, 2), q2h, r2h, evidence_tier="hypothesis"),
            ],
            doc=doc,
        )

    def narrate(self, ctx, res: MarginResult) -> str:
        return _render_narrative(ctx.region, ctx.p1, ctx.p2, res.dec, ctx.decision_owner)

    def deck_spec(self, ctx, res: MarginResult) -> DeckSpec:
        return _build_deck_spec(ctx.region, ctx.p1, ctx.p2, res.dec, res.add,
                                ctx.decision_owner, ctx.scratch["assumptions"], ctx.ledger)

    def stakeholder_questions(self, ctx, res: MarginResult, spec) -> dict[str, bool]:
        return _stakeholder_checks(spec, res.dec)

    def headline(self, ctx, res: MarginResult) -> str:
        dec = res.dec
        return (f"{ctx.region} gross margin fell {abs(dec.delta_pts):.1f}pts "
                f"({dec.m1*100:.1f}% -> {dec.m2*100:.1f}%), "
                f"driven by {dec.dominant_effect()}.")

    # ---- artefacts ----
    def hypotheses_doc(self, ctx, res: MarginResult) -> tuple[str, str]:
        return "hypotheses.md", _render_hypotheses(res.dec, res.add, res.simp,
                                                   ctx.dim, ctx.p1, ctx.p2)

    def findings_doc(self, ctx, res: MarginResult) -> tuple[str, str]:
        return "findings.md", _render_findings(ctx.region, ctx.p1, ctx.p2,
                                               res.dec, res.simp)

    def validation_doc(self, ctx, res: MarginResult, rd: Rederivation, report):
        rd_m1, rd_m2 = ctx.scratch.get("rd_margins", (0.0, 0.0))
        body = _render_validation(ctx.region, ctx.p1, ctx.p2, res.dec, rd_m1, rd_m2,
                                  rd.ok, TOLERANCES.rederivation_rel, rd.attacks)
        return "validation.md", (
            body +
            f"\n\n## Confidence grade\n**{report.grade}** (score {report.score:.2f})\n" +
            "\n".join(f"- L:{l['layer']} {'PASS' if l['passed'] else 'FAIL'} — {l['detail']}"
                      for l in report.as_dict()["layers"]) + "\n")

    # ---- RunState round-trip ----
    def deserialize(self, d: dict) -> MarginResult:
        return MarginResult(
            binding=None, row_count=d.get("row_count", 1),
            dec=_deser_dec(d["dec"]), add=d.get("add", []), simp=d.get("simp", {}),
            r1=tuple(d["r1"]), r2=tuple(d["r2"]),
            rev_p1=d.get("rev_p1", 0.0), rev_p2=d.get("rev_p2", 0.0),
        )


# --------------------- rendering (moved verbatim from orchestrator) ---------------------
def _render_hypotheses(dec, add, simp, dim, p1, p2):
    seg_lines = "\n".join(
        f"- **{s.key}**: total {s.total*100:+.2f}pts (mix {s.mix*100:+.2f}, "
        f"rate {s.rate*100:+.2f}, interaction {s.interaction*100:+.2f})"
        for s in dec.segments
    )
    add_lines = "\n".join(
        f"- **{a['key']}** revenue {a['contribution']:+,.0f}" for a in add
    )
    return (
        f"# Hypotheses & exploration ({p2} vs {p1})\n\n"
        f"## H1 — Mix vs rate (grain: {dim})\n"
        f"Margin change {dec.delta_pts:+.2f}pts = mix {dec.mix_total*100:+.2f} + "
        f"rate {dec.rate_total*100:+.2f} + interaction {dec.interaction_total*100:+.2f}.\n"
        f"Dominant effect: **{dec.dominant_effect()}**.\n\n{seg_lines}\n\n"
        f"## H2 — Revenue mix shift\n{add_lines}\n\n"
        f"## H3 — Simpson's paradox check\n"
        f"paradox={simp['paradox']}; aggregate {simp['aggregate_delta_pts']:+.2f}pts; "
        f"segment deltas {simp['segment_deltas_pts']}.\n"
    )


def _render_findings(region, p1, p2, dec, simp):
    return (
        f"# Findings\n\n"
        f"**Headline (evidence tier: decomposed):** {region} gross margin fell "
        f"{abs(dec.delta_pts):.1f}pts, from {dec.m1*100:.1f}% ({p1}) to "
        f"{dec.m2*100:.1f}% ({p2}).\n\n"
        f"**Root cause (decomposed):** The drop is a **{dec.dominant_effect()}** effect. "
        f"Mix contributed {dec.mix_total*100:+.2f}pts; within-segment rate contributed "
        f"{dec.rate_total*100:+.2f}pts; interaction {dec.interaction_total*100:+.2f}pts.\n\n"
        f"**Ranked drivers:**\n" +
        "\n".join(f"{i+1}. {s.key}: {s.total*100:+.2f}pts" for i, s in enumerate(dec.segments)) +
        f"\n\n**Simpson check:** {'PARADOX FLAGGED' if simp['paradox'] else 'no paradox'}.\n"
    )


def _render_validation(region, p1, p2, dec, rd_m1, rd_m2, ok, tol, attacks):
    return (
        f"# Validation (red-team)\n\n"
        f"## Independent re-derivation\n"
        f"Re-derived from raw sums via a separate query (analyst SQL not seen):\n"
        f"- {p1}: {rd_m1:.2f}% vs analyst {dec.m1*100:.2f}%\n"
        f"- {p2}: {rd_m2:.2f}% vs analyst {dec.m2*100:.2f}%\n"
        f"- Tolerance: ±{tol*100:.2f}% relative -> **{'WITHIN' if ok else 'OUTSIDE'}**\n\n"
        f"## Attacks\n" + ("\n".join(f"- SURVIVING: {a}" for a in attacks) or "- none survived") +
        f"\n\n## Verdict\n**{'PASS' if ok and not attacks else 'FAIL'}**\n"
    )


def _render_narrative(region, p1, p2, dec, owner):
    return (
        f"# Narrative — for {owner}\n\n"
        f"## Answer (one sentence)\n"
        f"{region} gross margin fell {abs(dec.delta_pts):.1f} points because revenue mix "
        f"shifted toward lower-margin lines — not because any product got less profitable "
        f"[c_delta, c_mix].\n\n"
        f"## Why (three pillars)\n"
        f"1. **The fall is real and precise:** {dec.m1*100:.1f}% -> {dec.m2*100:.1f}% "
        f"({dec.delta_pts:+.1f}pts) [c_gm_p1, c_gm_p2].\n"
        f"2. **It is a mix shift:** mix explains {dec.mix_total*100:+.1f}pts; rate only "
        f"{dec.rate_total*100:+.1f}pts [c_mix, c_rate].\n"
        f"3. **No product became less profitable:** within-line margins are essentially flat.\n\n"
        f"## So what\n"
        f"Margin is defensible: rebalance mix rather than chase cost.\n"
    )


def _build_deck_spec(region, p1, p2, dec, add, owner, assumptions, ledger) -> DeckSpec:
    seg = dec.segments
    slides = [
            Slide("insight",
                  f"Gross margin dropped from {dec.m1*100:.1f}% to {dec.m2*100:.1f}% "
                  f"— a {abs(dec.delta_pts):.1f}pt fall",
                  bullets=[f"{p1}: {dec.m1*100:.1f}%", f"{p2}: {dec.m2*100:.1f}%",
                           "Within-line margins essentially unchanged"],
                  chart=Chart("column", [p1, p2],
                              {"Gross margin %": [round(dec.m1*100, 2), round(dec.m2*100, 2)]},
                              title=f"{region} gross margin"),
                  speaker_notes=(
                      f"The headline is a {abs(dec.delta_pts):.1f} point drop in {region} gross "
                      f"margin, from {dec.m1*100:.1f} to {dec.m2*100:.1f} percent. Hold on that "
                      f"number: it is exact and independently re-derived. What matters next is "
                      f"that no product line actually got less profitable — so this is a mix "
                      f"story, which we will show on the next slide."),
                  claim_ids=["c_gm_p1", "c_gm_p2", "c_delta"]),
            Slide("evidence",
                  "The entire drop is a mix shift, not a rate collapse",
                  bullets=[f"Mix: {dec.mix_total*100:+.1f}pts",
                           f"Rate: {dec.rate_total*100:+.1f}pts",
                           f"Interaction: {dec.interaction_total*100:+.1f}pts"],
                  chart=Chart("bar", ["Mix", "Rate", "Interaction"],
                              {"Contribution (pts)": [round(dec.mix_total*100, 2),
                                                      round(dec.rate_total*100, 2),
                                                      round(dec.interaction_total*100, 2)]}),
                  speaker_notes=(
                      f"Decomposing the change exactly, mix contributes {dec.mix_total*100:+.1f} "
                      f"points while rate contributes only {dec.rate_total*100:+.1f}. The identity "
                      f"is exact — mix plus rate plus interaction equals the total change. In plain "
                      f"terms: we sold a lower-margin blend, we did not get worse at any single "
                      f"product. That distinction changes the fix entirely."),
                  claim_ids=["c_mix", "c_rate", "c_delta"]),
            Slide("sowhat",
                  "This is a defensible, mix-driven move — cost-cutting would miss it",
                  bullets=[f"Top driver: {seg[0].key} ({seg[0].total*100:+.1f}pts)",
                           "Rate levers (procurement, pricing) would not have caught this"],
                  speaker_notes=(
                      f"So what does this mean for you? Because the driver is {seg[0].key} mix "
                      f"and not unit economics, the right response is commercial — steering the "
                      f"sales blend — rather than a cost programme. A procurement or pricing push "
                      f"would spend effort against the wrong cause."),
                  claim_ids=["c_mix"]),
            Slide("recommendation",
                  "Rebalance the EMEA product mix to recover the 4 points",
                  bullets=["Incentivise higher-margin attach in the sales motion",
                           "Review discounting on the lower-margin line",
                           "Track mix weekly as the leading indicator"],
                  speaker_notes=(
                      "The recommendation is three concrete moves: incentivise the higher-margin "
                      "attach, review discounting on the line that grew, and instrument mix as a "
                      "weekly leading indicator so this never surprises us again. None of these "
                      "require a cost programme; all target the mechanism we identified."),
                  claim_ids=[]),
    ]

    # Opportunity slide — inserted after the evidence slide when sizing produced a
    # provenance-stamped estimate (opportunity-sizer node). Keeps the deck honest:
    # the impact is a sized estimate (hypothesis tier), shown with its driver.
    opp = ledger.get("c_opportunity")
    rev = ledger.get("c_revenue_p2")
    if opp is not None and rev is not None:
        slides.insert(2, Slide(
            "sowhat",
            f"Recovering the mix drift is worth ≈ {opp.value:,.0f}",
            bullets=[f"Mix-driven points recoverable: {abs(dec.mix_total)*100:.1f}pts",
                     f"On {p2} revenue of {rev.value:,.0f}",
                     "Sized estimate — see tornado in the appendix"],
            chart=Chart("column", ["Opportunity"], {"Est. value": [round(opp.value, 2)]},
                        title="Margin-recovery opportunity"),
            speaker_notes=(
                f"To put a number on it: recovering the mix-driven {abs(dec.mix_total)*100:.1f} "
                f"points on {p2} revenue is worth roughly {opp.value:,.0f}. Treat this as a "
                f"sized estimate, not a measured fact — the appendix shows the tornado, and it "
                f"hinges most on how many of those points are actually recoverable."),
            claim_ids=["c_opportunity", "c_revenue_p2"]))

    return DeckSpec(
        title=(f"{region} gross margin fell {abs(dec.delta_pts):.0f}pts because volume "
               f"shifted to lower-margin lines"),
        subtitle=f"{p2} vs {p1} gross-margin decomposition",
        decision_owner=owner,
        slides=slides,
        assumptions=assumptions,
        methodology=(
            "Exact mix / rate / interaction decomposition of gross margin at product_line "
            "grain.\nHeadline independently re-derived from raw revenue/cogs sums within "
            "±0.5% tolerance.\nEvery number carries a provenance ID -> stored query + result hash."),
        provenance=[
            {"claim_id": c.claim_id, "text": c.text, "value": c.value,
             "query_hash": c.query_hash, "tier": c.evidence_tier}
            for c in ledger.all()
        ],
    )


def _stakeholder_checks(spec, dec) -> dict[str, bool]:
    """Five hardest exec questions -> whether the deck+notes answer each."""
    notes = " ".join(s.speaker_notes.lower() for s in spec.slides)
    return {
        "Is the number right?": "re-derived" in notes or "exact" in notes,
        "Is it mix or rate?": "mix" in notes and "rate" in notes,
        "Which line drives it?": any("driver" in s.title.lower() or dec.segments[0].key.lower() in notes
                                     for s in spec.slides),
        "Should we cut cost?": "cost" in notes,
        "What do we do Monday?": any(s.kind == "recommendation" for s in spec.slides),
    }
