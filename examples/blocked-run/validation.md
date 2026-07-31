# Validation (red-team)

## Independent re-derivation

base rate recomputed with count(*) FILTER; segment rates checked against the law of total probability; top threshold re-split with an explicit CASE (no window function); confusion matrix recomputed in SQL over the registered scores view; model benchmarked against the majority class and the best single-rule cut; coefficient signs checked against univariate effects

| check | analyst | red-team | within tolerance |
|---|---|---|---|
| base rate | 0.059750 | 0.059750 | YES |
| weighted rates over 'employee_role' | 0.059750 | 0.059750 | YES |
| confusion tp (SQL vs Python) | 0.000000 | 0.000000 | YES |
| confusion fp (SQL vs Python) | 0.000000 | 0.000000 | YES |
| confusion tn (SQL vs Python) | 2821.000000 | 2821.000000 | YES |
| confusion fn (SQL vs Python) | 179.000000 | 179.000000 | YES |
| AUC vs 0.5 coin flip | 0.495440 | 0.500000 | NO |

## Attacks

- SURVIVING: AUC 0.495 is barely better than chance; the model does not earn its complexity

## Verdict

**FAIL**

## Confidence grade

**B** (score 0.85)
- L:structural PASS — rows=12000, profile_ok=True
- L:rate_identity PASS — sum(parts)=0.059750 vs total=0.059750 (tol 1e-06)
- L:business_range PASS — all in range
- L:sample_size PASS — n=12000 (minimum 384)
- L:top_effect PASS — significant=True, |effect|=2.3358
- L:discrimination FAIL — held-out AUC=0.4954 (floor 0.60)
- L:calibration PASS — max |predicted-observed| = 0.0419
- L:separation PASS — no separation flags
- L:sample_size PASS — n=9000 (minimum 384)
