# Validation (red-team)

## Independent re-derivation

base rate recomputed with count(*) FILTER; segment rates checked against the law of total probability; top threshold re-split with an explicit CASE (no window function)

| check | analyst | red-team | within tolerance |
|---|---|---|---|
| base rate | 0.473685 | 0.473685 | YES |
| weighted rates over 'Gender' | 0.473685 | 0.473685 | YES |
| cliff jump at Payment Delay>=16 | 0.611904 | 0.611904 | YES |

## Attacks

- none survived

## Verdict

**PASS**

## Confidence grade

**A** (score 1.00)
- L:structural PASS — rows=64374, profile_ok=True
- L:rate_identity PASS — sum(parts)=0.473685 vs total=0.473685 (tol 1e-06)
- L:business_range PASS — all in range
- L:sample_size PASS — n=64374 (minimum 384)
- L:top_effect PASS — significant=True, |effect|=0.6119
