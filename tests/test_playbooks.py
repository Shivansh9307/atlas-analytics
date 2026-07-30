"""Phase 1: the playbook abstraction — registry, selection, column binding.

Binding is deliberately a pure function over a pre-collected probe, so everything
here runs without a database.
"""
import json

import pytest

from atlas.connectors.base import ColumnSchema, TableRef, TableSchema
from atlas.lib.sqlident import quote_ident, quote_table
from atlas.playbooks import (
    PLAYBOOK_REGISTRY, ColumnProbe, ColumnRequirement, ColumnRole,
    all_playbooks, get_playbook, resolve_binding, select_playbook,
    split_features, supported_decompositions,
)
from atlas.playbooks.binding import ColumnBinding

# --- a churn-shaped table, described entirely by hand ---
N = 1000
PROBES = {
    "CustomerID":      ColumnProbe("CustomerID", "BIGINT", N, N, N, "1", "1000"),
    "Age":             ColumnProbe("Age", "BIGINT", N, 50, N, "18", "65"),
    "Gender":          ColumnProbe("Gender", "VARCHAR", N, 2, N, "Female", "Male"),
    "Contract Length": ColumnProbe("Contract Length", "VARCHAR", N, 3, N, "Annual", "Quarterly"),
    "Support Calls":   ColumnProbe("Support Calls", "BIGINT", N, 8, N, "0", "10"),
    "Total Spend":     ColumnProbe("Total Spend", "BIGINT", N, 900, N, "100", "999"),
    "Churn":           ColumnProbe("Churn", "BIGINT", N, 2, N, "0", "1"),
    "Country":         ColumnProbe("Country", "VARCHAR", N, 1, N, "USA", "USA"),
}
SCHEMA = TableSchema(table=TableRef("churn"),
                     columns=[ColumnSchema(p.name, p.dtype) for p in PROBES.values()])

TARGET_REQ = ColumnRequirement(
    role=ColumnRole.TARGET, shape="binary",
    name_hints=("churn", "target", "label", "outcome"),
    describe="a binary outcome column")
ENTITY_REQ = ColumnRequirement(
    role=ColumnRole.ENTITY, shape="unique", name_hints=("id", "key"),
    describe="a unique row identifier")


# --------------------------- identifier quoting ---------------------------
def test_quote_ident_handles_spaces_and_embedded_quotes():
    assert quote_ident("Payment Delay") == '"Payment Delay"'
    assert quote_ident('we"ird') == '"we""ird"'
    with pytest.raises(ValueError):
        quote_ident("")


def test_quote_table_qualifies_on_dots_and_passes_through_quoted():
    assert quote_table("finance") == '"finance"'
    assert quote_table("main.my tbl") == '"main"."my tbl"'
    assert quote_table('"already"') == '"already"'


# --------------------------- probe semantics ---------------------------
def test_probe_shape_classification():
    assert PROBES["CustomerID"].is_unique
    assert PROBES["Churn"].is_binary
    # two distinct values that are not boolean-like is a category, not a flag
    assert not PROBES["Gender"].is_binary
    assert PROBES["Gender"].is_categorical
    assert PROBES["Country"].is_constant
    assert not PROBES["Country"].is_categorical      # constants are dropped
    assert PROBES["Support Calls"].is_categorical    # low-cardinality numeric
    assert not PROBES["Total Spend"].is_categorical


# --------------------------- binding ---------------------------
def test_binding_resolves_target_and_entity_by_hint_and_shape():
    b = resolve_binding(SCHEMA, (TARGET_REQ, ENTITY_REQ), PROBES, table="churn")
    assert b.ok
    assert b.one(ColumnRole.TARGET) == "Churn"
    assert b.one(ColumnRole.ENTITY) == "CustomerID"
    # every inference is declared as an assumption
    assert any("target" in n for n in b.notes)
    assert any("entity" in n for n in b.notes)


def test_binding_override_wins_and_is_not_an_assumption():
    b = resolve_binding(SCHEMA, (TARGET_REQ,), PROBES, table="churn",
                        overrides={"target": "Gender"})
    assert b.one(ColumnRole.TARGET) == "Gender"
    assert b.overrides == {"target": "Gender"}
    assert b.notes == []          # explicitly pinned -> nothing was inferred


def test_binding_rejects_unknown_override_column():
    b = resolve_binding(SCHEMA, (TARGET_REQ,), PROBES, table="churn",
                        overrides={"target": "NoSuchColumn"})
    assert not b.ok
    assert "not a column" in " ".join(b.rejected["target"])


def test_binding_blocks_with_a_reason_per_rejected_candidate():
    probes = {k: v for k, v in PROBES.items() if k != "Churn"}   # no binary column
    b = resolve_binding(SCHEMA, (TARGET_REQ,), probes, table="churn")
    assert not b.ok and b.unbound == ["target"]
    msg = b.block_message("descriptive", probes)
    assert "cannot bind required role" in msg
    assert "Fix: re-run pinning the column" in msg
    # names the specific reason each candidate lost, not just that it lost
    assert "CustomerID: 1000 distinct values, need exactly 2" in msg
    assert "not boolean-like" in msg          # Gender had 2 distinct but wasn't a flag
    assert "Available columns:" in msg


def test_binding_claims_columns_so_target_cannot_also_be_a_feature():
    b = resolve_binding(SCHEMA, (TARGET_REQ, ENTITY_REQ), PROBES, table="churn")
    numeric, categorical, dropped = split_features(
        PROBES, exclude=set(b.many(ColumnRole.TARGET)) | set(b.many(ColumnRole.ENTITY)))
    assert "Churn" not in numeric + categorical        # the target is not a feature
    assert "CustomerID" not in numeric + categorical   # nor is the identifier
    assert set(numeric) == {"Age", "Total Spend"}
    assert set(categorical) == {"Contract Length", "Gender", "Support Calls"}
    assert "Country" in dropped and "constant" in dropped["Country"]


def test_binding_round_trips_through_json():
    b = resolve_binding(SCHEMA, (TARGET_REQ, ENTITY_REQ), PROBES, table="churn")
    again = ColumnBinding.from_dict(json.loads(json.dumps(b.as_dict())))
    assert again.as_dict() == b.as_dict()


# --------------------------- registry + selection ---------------------------
def test_margin_playbook_is_registered():
    assert "margin" in PLAYBOOK_REGISTRY
    assert get_playbook("margin") is not None
    assert [p.id for p in all_playbooks()] == sorted(PLAYBOOK_REGISTRY)


def test_supported_decompositions_is_the_registry_union():
    assert "mix_rate_interaction" in supported_decompositions()
    union = set()
    for pb in all_playbooks():
        union |= set(pb.supported_decompositions)
    assert supported_decompositions() == frozenset(union)


def test_select_playbook_routes_on_metric_decomposition():
    pb = select_playbook(metric_decomposition="mix_rate_interaction")
    assert pb is not None and pb.id == "margin"


def test_select_playbook_explicit_pin_wins():
    assert select_playbook(metric_decomposition=None, explicit="margin").id == "margin"
    assert select_playbook(metric_decomposition=None, explicit="nope") is None


def test_select_playbook_returns_none_when_nothing_can_execute():
    # This is what makes a resolvable-but-uncomputable metric BLOCK rather than
    # get silently handed to whichever maths the engine happens to implement.
    # 'survival_hazard' is a real decomposition shape that no registered playbook
    # implements; if one ever does, this test should switch to another unclaimed one.
    assert select_playbook(metric_decomposition="survival_hazard") is None


def test_descriptive_playbook_claims_the_previously_dead_decompositions():
    """`additive` and `non_decomposable` used to BLOCK every run that reached them.

    `revenue` and `cogs` declare `additive`; `customer_churn_rate` declares
    `non_decomposable`. Before the descriptive playbook existed, only `gross_margin`
    could complete a run at all.
    """
    for dec in ("additive", "non_decomposable"):
        pb = select_playbook(metric_decomposition=dec)
        assert pb is not None and pb.id == "descriptive", dec


def test_margin_result_serialize_round_trips_through_json():
    """The resume path depends on this pair; a mismatch only shows up on /resume."""
    from atlas.lib.decomposition import MarginDecomposition, SegmentContribution
    from atlas.playbooks.margin import MarginPlaybook, MarginResult

    dec = MarginDecomposition(
        m1=0.6, m2=0.56, delta=-0.04, mix_total=-0.04, rate_total=0.0,
        interaction_total=0.0,
        segments=[SegmentContribution("A", -0.04, 0.0, 0.0, 0.5, 0.4, 0.6, 0.6)])
    res = MarginResult(row_count=8, dec=dec, add=[], simp={"paradox": False},
                       r1=("q1", "r1"), r2=("q2", "r2"), rev_p1=900.0, rev_p2=1000.0)
    pb = MarginPlaybook()
    again = pb.deserialize(json.loads(json.dumps(pb.serialize(res))))
    assert again.dec.m1 == dec.m1 and again.dec.mix_total == dec.mix_total
    assert again.r1 == ("q1", "r1") and again.rev_p2 == 1000.0
    assert again.dec.segments[0].key == "A"


def test_explore_output_stays_flat_for_exporters():
    """`atlas/lib/exporters.py::_rebuild_spec` reads state.outputs['explore']['dec'].

    Keeping the serialized result flat (rather than nested under a 'result' key) is
    what lets the export path keep working unchanged across this refactor.
    """
    from atlas.playbooks.margin import MarginPlaybook, MarginResult
    from atlas.lib.decomposition import MarginDecomposition
    dec = MarginDecomposition(m1=0.6, m2=0.56, delta=-0.04, mix_total=-0.04,
                              rate_total=0.0, interaction_total=0.0, segments=[])
    out = MarginPlaybook().serialize(MarginResult(dec=dec, r1=("a", "b"), r2=("c", "d")))
    assert "dec" in out and "segments" in out["dec"]
