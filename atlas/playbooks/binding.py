"""Column binding — how a playbook declares what it needs and finds it in a table.

This is what replaces the hardcoded `region / quarter / revenue / cogs` schema the
engine was built around. A playbook declares `ColumnRequirement`s by *role* rather
than by name; `resolve_binding()` matches those roles against a real table.

Two design rules carry the constitution:

1. **Every inference is a declared assumption.** Anything resolved by name hint or
   data shape rather than an explicit user override appends to `ColumnBinding.notes`,
   which the framing node folds into the brief's Assumptions section. A guessed
   target column that nobody is told about is exactly the failure mode rule 2 exists
   to prevent.
2. **Failure names the fix.** An unbindable required role produces a BLOCK message
   listing each rejected candidate *and why it was rejected*, plus the override that
   would resolve it. Atlas does not guess a target column.

`resolve_binding()` is a pure function over an already-collected probe, so the whole
matcher is unit-testable with no database. `probe_columns()` is the one part that
touches SQL, and it does so in a single batched query.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from atlas.connectors.base import TableSchema
from atlas.lib.sqlident import quote_ident, quote_table

# Values that make a 2-distinct-value column a genuine boolean rather than a
# 2-level category. Compared case-insensitively against the string form.
_BINARY_VALUE_SETS = (
    {"0", "1"}, {"true", "false"}, {"t", "f"},
    {"yes", "no"}, {"y", "n"},
)

_NUMERIC_DTYPES = (
    "TINYINT", "SMALLINT", "INTEGER", "INT", "BIGINT", "HUGEINT",
    "FLOAT", "DOUBLE", "REAL", "DECIMAL", "NUMERIC",
)
_TEXT_DTYPES = ("VARCHAR", "CHAR", "TEXT", "STRING", "BPCHAR")

# A numeric column with no more distinct values than this is treated as a category
# (Support Calls 0-10 is a category, Total Spend is not). Declared as an assumption.
MAX_CATEGORICAL_LEVELS = 10


class ColumnRole(str, Enum):
    TARGET = "target"                       # the outcome being explained
    ENTITY = "entity"                       # row identity; ALWAYS excluded from features
    TIME = "time"
    VALUE = "value"                         # additive money measure
    COST = "cost"
    DIMENSION = "dimension"                 # grouping key
    FILTER = "filter"                       # scoping key
    NUMERIC_FEATURE = "numeric_feature"
    CATEGORICAL_FEATURE = "categorical_feature"


@dataclass(frozen=True)
class ColumnRequirement:
    """One role a playbook needs filled, and the evidence that would fill it."""
    role: ColumnRole
    required: bool = True
    multiple: bool = False                  # binds to a list rather than one column
    dtypes: tuple[str, ...] = ()            # dtype-prefix family; () = any
    name_hints: tuple[str, ...] = ()
    shape: str = ""                         # "binary" | "unique" | "numeric" | ""
    describe: str = ""                      # human text used in the BLOCK message


@dataclass
class ColumnProbe:
    """Measured facts about one column. Produced by SQL, consumed by pure matching."""
    name: str
    dtype: str
    row_count: int
    distinct: int
    non_null: int
    min_str: str | None = None
    max_str: str | None = None

    @property
    def is_numeric(self) -> bool:
        return self.dtype.upper().startswith(_NUMERIC_DTYPES)

    @property
    def is_text(self) -> bool:
        return self.dtype.upper().startswith(_TEXT_DTYPES)

    @property
    def is_unique(self) -> bool:
        return self.non_null > 0 and self.distinct == self.row_count

    @property
    def is_constant(self) -> bool:
        return self.distinct <= 1

    @property
    def binary_values(self) -> set[str] | None:
        """The two values if this is a 2-distinct column, else None."""
        if self.distinct != 2 or self.min_str is None or self.max_str is None:
            return None
        return {str(self.min_str).strip().lower(), str(self.max_str).strip().lower()}

    @property
    def is_binary(self) -> bool:
        vals = self.binary_values
        return vals is not None and any(vals == s for s in _BINARY_VALUE_SETS)

    @property
    def is_categorical(self) -> bool:
        """Text of any cardinality, or a low-cardinality numeric."""
        if self.is_constant:
            return False
        if self.is_text:
            return True
        return self.is_numeric and self.distinct <= MAX_CATEGORICAL_LEVELS


@dataclass
class ColumnBinding:
    table: str
    roles: dict[str, list[str]] = field(default_factory=dict)
    unbound: list[str] = field(default_factory=list)
    rejected: dict[str, list[str]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    overrides: dict[str, str] = field(default_factory=dict)

    def one(self, role: ColumnRole | str) -> str | None:
        got = self.roles.get(_role_value(role)) or []
        return got[0] if got else None

    def many(self, role: ColumnRole | str) -> list[str]:
        return list(self.roles.get(_role_value(role)) or [])

    @property
    def ok(self) -> bool:
        return not self.unbound

    def as_dict(self) -> dict:
        return {
            "table": self.table, "roles": {k: list(v) for k, v in self.roles.items()},
            "unbound": list(self.unbound),
            "rejected": {k: list(v) for k, v in self.rejected.items()},
            "notes": list(self.notes), "overrides": dict(self.overrides),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ColumnBinding":
        return cls(
            table=d.get("table", ""),
            roles={k: list(v) for k, v in (d.get("roles") or {}).items()},
            unbound=list(d.get("unbound") or []),
            rejected={k: list(v) for k, v in (d.get("rejected") or {}).items()},
            notes=list(d.get("notes") or []),
            overrides=dict(d.get("overrides") or {}),
        )

    def block_message(self, playbook_id: str, probes: dict[str, ColumnProbe]) -> str:
        """The BLOCK text: what failed, why each candidate lost, how to fix it."""
        lines = [f"playbook '{playbook_id}' cannot bind required role(s) "
                 f"{self.unbound} on table '{self.table}'.", ""]
        for role in self.unbound:
            lines.append(f"  Role '{role}':")
            for why in self.rejected.get(role, []) or ["  (no candidate columns)"]:
                lines.append(f"    - {why}")
            lines.append("")
        avail = ", ".join(f"{p.name} {p.dtype}" for p in probes.values())
        lines += [
            f"  Available columns: {avail}", "",
            "  Fix: re-run pinning the column explicitly, e.g. "
            f"bind={{'{self.unbound[0]}': '<column>'}}, or lock the definition in "
            "atlas/semantic/metrics.yaml. Atlas does not guess a target column.",
        ]
        return "\n".join(lines)


def _role_value(role: ColumnRole | str) -> str:
    return role.value if isinstance(role, ColumnRole) else str(role)


def _norm(name: str) -> str:
    return name.lower().replace(" ", "").replace("_", "").replace("-", "")


# --------------------------- probing (the only SQL) ---------------------------
def probe_columns(con, table: str, schema: TableSchema, *,
                  charge=None) -> dict[str, ColumnProbe]:
    """Measure every column in ONE batched query.

    Four aggregates per column (distinct, non-null, min, max as text) in a single
    SELECT keeps binding at a flat one-query cost regardless of table width, which
    matters because the run budget counts queries. `min`/`max` cast to VARCHAR give
    us both values of a 2-distinct column for free, which is what the binary shape
    probe needs.
    """
    cols = list(schema.columns)
    if not cols:
        return {}
    parts = ["count(*) AS n_rows"]
    for c in cols:
        q, alias = quote_ident(c.name), c.name.replace('"', "")
        parts += [
            f'count(DISTINCT {q}) AS {quote_ident(alias + "__d")}',
            f'count({q}) AS {quote_ident(alias + "__nn")}',
            f'min(CAST({q} AS VARCHAR)) AS {quote_ident(alias + "__lo")}',
            f'max(CAST({q} AS VARCHAR)) AS {quote_ident(alias + "__hi")}',
        ]
    res = con.run(f"SELECT {', '.join(parts)} FROM {quote_table(table)}",
                  purpose="column probe for playbook binding")
    if charge is not None:
        charge(res.bytes_scanned)
    row = res.rows[0]
    n_rows = int(row["n_rows"] or 0)
    out: dict[str, ColumnProbe] = {}
    for c in cols:
        a = c.name.replace('"', "")
        out[c.name] = ColumnProbe(
            name=c.name, dtype=c.dtype, row_count=n_rows,
            distinct=int(row.get(a + "__d") or 0),
            non_null=int(row.get(a + "__nn") or 0),
            min_str=row.get(a + "__lo"), max_str=row.get(a + "__hi"),
        )
    return out


# --------------------------- matching (pure) ---------------------------
def _shape_ok(p: ColumnProbe, shape: str) -> tuple[bool, str]:
    if not shape:
        return True, ""
    if shape == "binary":
        if p.is_binary:
            return True, ""
        if p.distinct != 2:
            return False, f"{p.distinct} distinct values, need exactly 2"
        return False, f"2 distinct values {sorted(p.binary_values or [])} are not boolean-like"
    if shape == "unique":
        if p.is_unique:
            return True, ""
        return False, f"distinct={p.distinct} != row_count={p.row_count}"
    if shape == "numeric":
        return (True, "") if p.is_numeric else (False, f"dtype {p.dtype} is not numeric")
    return True, ""


def _dtype_ok(p: ColumnProbe, dtypes: tuple[str, ...]) -> bool:
    return not dtypes or p.dtype.upper().startswith(tuple(d.upper() for d in dtypes))


def _hit_hint(p: ColumnProbe, hints: tuple[str, ...]) -> bool:
    if not hints:
        return False
    n = _norm(p.name)
    return any(n == _norm(h) or n.startswith(_norm(h)) or n.endswith(_norm(h))
               for h in hints)


def resolve_binding(schema: TableSchema, requirements, probes: dict[str, ColumnProbe],
                    *, table: str, overrides: dict[str, str] | None = None
                    ) -> ColumnBinding:
    """Match requirements to columns. Pure — no DB, fully unit-testable.

    Resolution order per requirement, most explicit first:
      1. an explicit override (recorded, never noted as an assumption)
      2. a name hint that also satisfies dtype + shape
      3. shape/dtype alone, when the requirement is unambiguous about it
    Anything from step 2 or 3 becomes a declared assumption.

    Single-column roles claim their column so a later multi-column role cannot
    re-consume it — that is what keeps the target and the entity out of the
    feature list without any playbook having to remember to exclude them.
    """
    overrides = dict(overrides or {})
    b = ColumnBinding(table=table)
    claimed: set[str] = set()

    for req in requirements:
        role = req.role.value
        rejected: list[str] = []

        # 1. explicit override
        pin = overrides.get(role)
        if pin:
            if pin not in probes:
                rejected.append(f"{pin}: pinned via override but not a column of '{table}'")
                b.rejected[role] = rejected
                if req.required:
                    b.unbound.append(role)
                continue
            b.roles[role] = [pin]
            b.overrides[role] = pin
            claimed.add(pin)
            continue

        # 2 + 3. candidates that pass dtype and shape, hint-matching first
        eligible: list[ColumnProbe] = []
        for p in probes.values():
            if p.name in claimed:
                rejected.append(f"{p.name}: already bound to another role")
                continue
            if not _dtype_ok(p, req.dtypes):
                rejected.append(f"{p.name}: dtype {p.dtype} not in {list(req.dtypes)}")
                continue
            ok, why = _shape_ok(p, req.shape)
            if not ok:
                rejected.append(f"{p.name}: {why}")
                continue
            if p.is_constant and req.role != ColumnRole.ENTITY:
                rejected.append(f"{p.name}: constant column ({p.distinct} distinct)")
                continue
            eligible.append(p)

        hinted = [p for p in eligible if _hit_hint(p, req.name_hints)]
        pool = hinted or eligible

        if not pool:
            b.rejected[role] = rejected
            if req.required:
                b.unbound.append(role)
            continue

        if req.multiple:
            names = sorted(p.name for p in pool)
            b.roles[role] = names
            claimed.update(names)
            b.notes.append(
                f"Role '{role}' inferred as {names} by column shape — not explicitly "
                f"specified.")
        else:
            # deterministic single pick: hint match wins, then declaration order
            chosen = pool[0]
            b.roles[role] = [chosen.name]
            claimed.add(chosen.name)
            how = "name hint" if hinted else "column shape"
            b.notes.append(
                f"Role '{role}' inferred as '{chosen.name}' by {how} — not explicitly "
                f"specified. Pin it with bind={{'{role}': '<column>'}} to be certain.")
            for p in pool[1:]:
                rejected.append(f"{p.name}: eligible but '{chosen.name}' matched first")

        if rejected:
            b.rejected[role] = rejected

    return b


def split_features(probes: dict[str, ColumnProbe], *, exclude: set[str]
                   ) -> tuple[list[str], list[str], dict[str, str]]:
    """Partition remaining columns into (numeric, categorical, dropped-with-reason).

    The rule is declared rather than clever: text is categorical; a numeric with
    <= MAX_CATEGORICAL_LEVELS distinct values is categorical; a constant is dropped.
    """
    numeric: list[str] = []
    categorical: list[str] = []
    dropped: dict[str, str] = {}
    for name in sorted(probes):
        if name in exclude:
            continue
        p = probes[name]
        if p.is_constant:
            dropped[name] = f"constant ({p.distinct} distinct value)"
        elif p.is_text:
            categorical.append(name)
        elif p.is_numeric and p.distinct <= MAX_CATEGORICAL_LEVELS:
            categorical.append(name)
        elif p.is_numeric:
            numeric.append(name)
        else:
            dropped[name] = f"unsupported dtype {p.dtype}"
    return numeric, categorical, dropped
