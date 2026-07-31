# Query template — pre-model redundancy assertion

**Promotion artefact for lessons L-0004, L-0005, L-0006, L-0007** (see
`memory/lessons.jsonl`). Cross-source: this is not a quirk of one table, it is a
property of any joined star-schema source handed to an interpretable model.

Runnable form (preferred — it encodes the design exactly the way
`atlas/lib/logit.py::build_design` does, so a pass here means the engine's own
rank check will pass):

```
uv run python .claude/skills/advanced-analytics/scripts/redundancy_check.py \
    --source <source_id> --table <table> --target <col> [--entity <col>]
# or re-check a plan a failed run already wrote:
uv run python .claude/skills/advanced-analytics/scripts/redundancy_check.py \
    --source <source_id> --plan runs/<run_id>/feature_plan.json
```

Exit 0 = safe to fit. Exit 1 = redundancy found, **do not spend a run on the fit**.

## The assertions, and why each exists

### 1. No feature functionally determines another (hierarchy redundancy)
For every pair of columns that get one-hot encoded (categoricals, plus numerics with
few distinct values — an ID-like numeric is a linear function of the dummies):

```sql
-- MUST return zero rows. If it returns rows, `finer` does NOT determine `coarser`.
-- If it returns ZERO rows, `coarser` is redundant: its dummies are an exact linear
-- combination of `finer`'s, and the design matrix is singular.
SELECT finer_col, count(DISTINCT coarser_col) AS n
FROM   <table>
GROUP  BY 1
HAVING count(DISTINCT coarser_col) > 1;
```

Run it for EVERY pair in one sweep, not one pair per failed fit. On
`returns_risk_orders` this is true of `store_name -> store_city / store_district /
store_region / store_type / store_opening_year / store_size_sqm`,
`dominant_subcategory -> dominant_category`, and `customer_city ->
customer_region` — three separate hierarchies that cost three separate runs
because they were found one at a time.

### 2. No duplicate / by-construction column
Mutual determinism (A determines B *and* B determines A) is a relabelling —
`store_id` vs `store_name`. Exact equality between two numerics is an accidental
duplicate that only exists in this extract — `num_distinct_products` equalled
`num_line_items` on all 12,000 rows. And any flag that is a `CASE` over an included
column (`is_single_line_order` = `num_line_items = 1`) is redundant by construction.
None of these are derivable from the schema; test them on the data.

### 3. The encoded design matrix has full column rank
Assertions 1-2 are **necessary but not sufficient**. A categorical that is only
*partially* nested inside another passes them and still breaks the fit: brands span
several subcategories in aggregate, but a brand confined to exactly one subcategory
makes that subcategory's dummy an exact linear combination.

```python
X = build_design(rows, plan, standardize=True, drop_first=True)   # atlas.lib.logit
assert numpy.linalg.matrix_rank(X_with_intercept) == X_with_intercept.shape[1]
```

When it is short, an unpivoted QR on the column-normalised design puts a ~0 on R's
diagonal exactly at each dependent column, which NAMES the offending dummies; a
least-squares solve against the preceding columns names what it is entangled with.
Guessing which column to drop is what turned one failure into four.

### 4. No categorical makes the target quasi-separable
A different symptom (`logistic fit did not converge`), same class of mistake:

```sql
-- Any status/lifecycle column on which the target never varies will diverge the MLE.
SELECT status_col, count(*) AS n, min(target) AS lo, max(target) AS hi
FROM   <table>
GROUP  BY 1
ORDER  BY n DESC;   -- lo = hi on levels covering most rows  =>  exclude the column
```

`order_status` is 'Returned' for every returned order and both return targets are
exactly 0 for all 10,442 Completed + 495 Cancelled orders — the model could
near-perfectly predict the majority class, so the fit diverged.

## Honest scope
The script is deterministic and mechanical **when it is run**. Nothing in the engine
runs it automatically today: `LogisticPlaybook` still discovers the same problems by
failing the fit (correctly — it refuses to report coefficients from a degenerate
design), it just cannot name the column. Wiring this check into the `model` node, or
using its QR diagnosis to enrich the `PlaybookBlocked` message, would make the
guarantee unconditional. Until then this artefact removes the *diagnosis* cost, not
the failure itself.
