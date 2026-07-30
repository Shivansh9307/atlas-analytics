"""The Playbook abstraction — one analysis *shape*, pluggable.

The engine used to hardcode a single analysis (gross-margin mix/rate decomposition
over two quarters) across six node bodies. A playbook factors that shape out: the
orchestrator keeps the fixed spine (profile -> frame -> semantics -> quality ->
readiness -> explore -> model -> diagnose ‖ redteam -> sizing -> narrative -> deck ->
emit -> stakeholder -> retro) and the gates, and delegates *what to compute* to a
registered playbook.

Deliberate boundaries:

* **Gates are not pluggable.** A playbook supplies evidence (`rederive()`,
  `validation_layers()`); the node still calls the same gate function. Letting a
  playbook place its own gates would make the one safety property that must be
  uniform depend on the plugin.
* **The orchestrator records provenance, not the playbook.** `diagnose()` returns
  declarative `ClaimSpec`s and the node writes them to the ledger, so a playbook
  cannot accidentally skip a hash.
* **Results must round-trip through JSON.** `RunState` persists every node output
  so `/resume` can skip completed work; `serialize()`/`deserialize()` generalise the
  old `_ser_dec`/`_deser_dec` pair.

Registration mirrors `@register` for repair modules and `@register_copilot`: define
the class, decorate it, import it in this package's `__init__`. Nothing else changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from atlas.lib.validation import LayerResult
from atlas.playbooks.binding import ColumnBinding, ColumnRequirement


class PlaybookBlocked(Exception):
    """A playbook cannot proceed. The node turns this into NodeStatus.BLOCKED.

    Raised for capability and contract failures — an unbindable column, a feature
    plan the model cannot honour. Never for a gate decision: gates return, not raise.
    """


@dataclass
class BriefFields:
    """The framing wave's per-playbook prose. Keeps `_render_brief` generic."""
    decision_unblocked: str
    primary_metric: str
    comparison_window: str
    grain: str
    success_criteria: str = "A ranked, provenance-stamped answer."
    non_goals: str = "Anything outside the stated question."


@dataclass
class PlaybookResult:
    """Base findings payload. MUST be JSON round-trippable."""
    binding: ColumnBinding | None = None
    row_count: int = 0
    query_refs: list[tuple[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "binding": self.binding.as_dict() if self.binding else None,
            "row_count": self.row_count,
            "query_refs": [list(q) for q in self.query_refs],
        }


@dataclass
class ClaimSpec:
    """A request to record a ledger claim. The ORCHESTRATOR performs the record,
    so provenance enforcement stays central rather than per-playbook.

    A non-empty `derivation` marks a number computed FROM a stored SQL result by a
    fingerprinted recipe (a model coefficient) rather than read directly from one.
    """
    claim_id: str
    text: str
    value: float | int | str
    query_hash: str
    result_hash: str
    evidence_tier: str = "correlational"
    notes: str = ""
    derivation: str = ""
    parent_claims: list[str] = field(default_factory=list)


@dataclass
class Rederivation:
    """The red-team's independent recomputation. Feeds GATE 3 unchanged."""
    ok: bool
    method: str = ""
    comparisons: list[dict] = field(default_factory=list)
    attacks: list[str] = field(default_factory=list)
    query_refs: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class BinningSpec:
    """A numeric column the descriptive stage found to be non-linear, and its cuts.

    `edges` are inclusive lower bounds of the bin above, matching
    `binning.edges_to_sql_case` and `edges_to_dax_switch` exactly, so the same bin
    definition renders identically in the analysis, the clean layer and a dashboard.
    """
    column: str
    edges: list[float]
    labels: list[str]
    reason: str = ""
    source_finding_id: str = ""
    ordinal: bool = True

    def as_dict(self) -> dict:
        return {"column": self.column, "edges": list(self.edges),
                "labels": list(self.labels), "reason": self.reason,
                "source_finding_id": self.source_finding_id, "ordinal": self.ordinal}

    @classmethod
    def from_dict(cls, d: dict) -> "BinningSpec":
        return cls(column=d["column"], edges=[float(e) for e in d["edges"]],
                   labels=list(d["labels"]), reason=d.get("reason", ""),
                   source_finding_id=d.get("source_finding_id", ""),
                   ordinal=bool(d.get("ordinal", True)))


@dataclass
class FeaturePlan:
    """The contract from the descriptive stage to any modelling stage.

    It carries not just *which* columns are features but which ones were measured to
    be non-linear. A model that ignores `binnings` and fits a raw linear term on a
    column known to have a cliff is underfitting silently — so the modelling stage
    treats a missing binning as a hard error rather than a preference.
    """
    table: str
    target: str
    target_kind: str = "binary"
    entity: str = ""
    numeric: list[str] = field(default_factory=list)
    categorical: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    exclude_reasons: dict[str, str] = field(default_factory=dict)
    binnings: list[BinningSpec] = field(default_factory=list)
    tier_policy_profile: str = "default"
    notes: list[str] = field(default_factory=list)

    def binning_for(self, column: str) -> BinningSpec | None:
        return next((b for b in self.binnings if b.column == column), None)

    def as_dict(self) -> dict:
        return {
            "table": self.table, "target": self.target,
            "target_kind": self.target_kind, "entity": self.entity,
            "numeric": list(self.numeric), "categorical": list(self.categorical),
            "exclude": list(self.exclude),
            "exclude_reasons": dict(self.exclude_reasons),
            "binnings": [b.as_dict() for b in self.binnings],
            "tier_policy_profile": self.tier_policy_profile,
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FeaturePlan":
        return cls(
            table=d.get("table", ""), target=d.get("target", ""),
            target_kind=d.get("target_kind", "binary"), entity=d.get("entity", ""),
            numeric=list(d.get("numeric", [])),
            categorical=list(d.get("categorical", [])),
            exclude=list(d.get("exclude", [])),
            exclude_reasons=dict(d.get("exclude_reasons", {})),
            binnings=[BinningSpec.from_dict(b) for b in d.get("binnings", [])],
            tier_policy_profile=d.get("tier_policy_profile", "default"),
            notes=list(d.get("notes", [])),
        )


@dataclass
class SizingOutcome:
    """Result of the sizing step. `None` from `size()` makes that node a clean no-op.

    The playbook runs `size_opportunity()` itself rather than handing the node an
    input to execute: sizing emits *several* claims whose text depends on the
    computed value, which a declarative input cannot express without the node
    knowing the analysis shape again.
    """
    output: dict = field(default_factory=dict)
    claims: list[ClaimSpec] = field(default_factory=list)
    doc: tuple[str, str] | None = None      # (relative_path, text)


class Playbook(ABC):
    """One analysis shape. Subclass, decorate with @register_playbook, import."""

    id: str = ""
    description: str = ""
    question_levels: tuple[int, ...] = (3,)
    supported_decompositions: frozenset[str] = frozenset()
    requirements: tuple[ColumnRequirement, ...] = ()

    # ---- framing ----
    def parse_hints(self, question: str) -> dict:
        return {}

    def bind(self, ctx) -> ColumnBinding:
        """Resolve required columns against the bound table. Default: probe + match."""
        from atlas.connectors.base import TableRef
        from atlas.playbooks.binding import probe_columns, resolve_binding
        table = ctx.analysis_table()
        schema = ctx.con.get_schema(TableRef(table))
        probes = probe_columns(ctx.con, table, schema,
                               charge=ctx.budget.charge_query)
        ctx.scratch["probes"] = probes
        return resolve_binding(schema, self.requirements, probes, table=table,
                               overrides=ctx.bind_overrides)

    @abstractmethod
    def brief_fields(self, ctx) -> BriefFields: ...

    # ---- analysis ----
    @abstractmethod
    def explore(self, ctx) -> PlaybookResult:
        """All SQL through ctx.con.run(), charging ctx.budget for every result."""

    def model(self, ctx, res: PlaybookResult) -> PlaybookResult:
        """Optional fitting step. Default: passthrough, so the node is a clean no-op."""
        return res

    @abstractmethod
    def diagnose(self, ctx, res: PlaybookResult) -> list[ClaimSpec]: ...

    # ---- validation ----
    def rederive(self, ctx, res: PlaybookResult) -> Rederivation:
        return Rederivation(ok=True, method="no independent re-derivation defined")

    def validation_layers(self, ctx, res: PlaybookResult) -> list[LayerResult]:
        return []

    # ---- downstream ----
    def size(self, ctx, res: PlaybookResult) -> SizingOutcome | None:
        return None

    @abstractmethod
    def narrate(self, ctx, res: PlaybookResult) -> str: ...

    @abstractmethod
    def deck_spec(self, ctx, res: PlaybookResult): ...

    def stakeholder_questions(self, ctx, res: PlaybookResult, spec) -> dict[str, bool]:
        return {}

    def exports(self, ctx, res: PlaybookResult) -> list[str]:
        return []

    # ---- markdown artefacts: (relative_path, text) ----
    @abstractmethod
    def hypotheses_doc(self, ctx, res: PlaybookResult) -> tuple[str, str]: ...

    @abstractmethod
    def findings_doc(self, ctx, res: PlaybookResult) -> tuple[str, str]: ...

    @abstractmethod
    def validation_doc(self, ctx, res, rd: Rederivation, report) -> tuple[str, str]: ...

    # ---- RunState round-trip ----
    def serialize(self, res: PlaybookResult) -> dict:
        return res.as_dict()

    @abstractmethod
    def deserialize(self, d: dict) -> PlaybookResult: ...


# --------------------------- registry ---------------------------
PLAYBOOK_REGISTRY: dict[str, Playbook] = {}


def register_playbook(cls):
    inst = cls()
    if not inst.id:
        raise ValueError(f"{cls.__name__} must define a non-empty id")
    if inst.id in PLAYBOOK_REGISTRY:
        raise ValueError(f"duplicate playbook id '{inst.id}'")
    PLAYBOOK_REGISTRY[inst.id] = inst
    return cls


def all_playbooks() -> list[Playbook]:
    return [PLAYBOOK_REGISTRY[k] for k in sorted(PLAYBOOK_REGISTRY)]


def get_playbook(pid: str) -> Playbook | None:
    return PLAYBOOK_REGISTRY.get(pid)


def supported_decompositions() -> frozenset[str]:
    """Union over the registry — replaces the old module-level constant.

    A metric whose `decomposition:` is not in this set resolves fine at GATE 2 but
    has no execution path, so the run blocks on capability rather than silently
    being handed to whichever maths the engine happens to implement.
    """
    out: set[str] = set()
    for pb in PLAYBOOK_REGISTRY.values():
        out |= set(pb.supported_decompositions)
    return frozenset(out)


def select_playbook(*, metric_decomposition: str | None, explicit: str | None = None,
                    question: str = "") -> Playbook | None:
    """Pick the playbook for this run. Deterministic; never a coin-flip.

    1. an explicit pin (`run_analysis(playbook=...)`) — used by every new test
    2. the metric's `decomposition:` — preserves today's routing exactly
    3. the router's L1-L5 level, as a tiebreak among the remainder
    """
    if explicit:
        return PLAYBOOK_REGISTRY.get(explicit)

    if metric_decomposition:
        matches = [pb for pb in all_playbooks()
                   if metric_decomposition in pb.supported_decompositions]
        if len(matches) == 1:
            return matches[0]
        if matches:
            level = _question_level(question)
            ranked = sorted(matches,
                            key=lambda pb: (0 if level in pb.question_levels else 1, pb.id))
            return ranked[0]
    return None


def _question_level(question: str) -> int:
    try:
        from atlas.lib.router import classify
        return classify(question).level
    except Exception:
        return 3
