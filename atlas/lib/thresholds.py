"""Threshold ("cliff") detection for a numeric feature against a binary outcome.

Why this exists: a driver can be flat and then jump. On the churn dataset the event
rate by `Payment Delay` is ~0.10 for values 0-15, ~0.58 for 16-20 and ~0.77 for 21+.
Summarising that with a correlation coefficient understates it, and feeding the raw
column to a logistic regression fits a straight line through a staircase — it will
underfit, and nothing in the output would say so.

So the detector answers a sharper question than "is there an association?":

    **Does a step function explain this materially better than a straight line?**

That is the `step_r2 - linear_r2` term in `recommend_bin`. Only when a step wins by a
real margin do we tell the modelling stage to bin the feature. Everything is closed
form and deterministic — no fitting library, no randomness, ties broken by lowest
index — so the same data always yields the same cut and the unit tests can assert an
exact answer.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from atlas.config import TOLERANCES
from atlas.lib.stats import two_proportion_ztest

__all__ = ["Bucket", "ThresholdFinding", "detect_threshold"]


@dataclass
class Bucket:
    """One bin of a numeric column: its value range and the outcome rate inside it."""
    index: int
    lo: float
    hi: float
    n: int
    x: int                      # events in this bucket

    @property
    def rate(self) -> float:
        return self.x / self.n if self.n else 0.0

    @property
    def mid(self) -> float:
        return (self.lo + self.hi) / 2.0

    def as_dict(self) -> dict:
        return {"index": self.index, "lo": self.lo, "hi": self.hi,
                "n": self.n, "x": self.x, "rate": self.rate}

    @classmethod
    def from_dict(cls, d: dict) -> "Bucket":
        return cls(index=int(d["index"]), lo=float(d["lo"]), hi=float(d["hi"]),
                   n=int(d["n"]), x=int(d["x"]))


@dataclass
class ThresholdFinding:
    column: str
    kind: str                   # cliff | monotone | non_monotone | flat | insufficient
    cut_values: list[float] = field(default_factory=list)
    jump: float = 0.0           # |rate_above - rate_below| at the best cut
    ratio: float = 0.0          # rate_above / rate_below
    z: float | None = None
    p_value: float | None = None
    monotonicity: float = 0.0   # fraction of adjacent pairs that increase
    linear_r2: float = 0.0
    step_r2: float = 0.0
    recommend_bin: bool = False
    buckets: list[Bucket] = field(default_factory=list)
    detail: str = ""
    flags: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {
            "column": self.column, "kind": self.kind,
            "cut_values": list(self.cut_values), "jump": self.jump,
            "ratio": self.ratio, "z": self.z, "p_value": self.p_value,
            "monotonicity": self.monotonicity, "linear_r2": self.linear_r2,
            "step_r2": self.step_r2, "recommend_bin": self.recommend_bin,
            "buckets": [b.as_dict() for b in self.buckets],
            "detail": self.detail, "flags": list(self.flags),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ThresholdFinding":
        return cls(
            column=d["column"], kind=d["kind"],
            cut_values=[float(c) for c in d.get("cut_values", [])],
            jump=float(d.get("jump", 0.0)), ratio=float(d.get("ratio", 0.0)),
            z=d.get("z"), p_value=d.get("p_value"),
            monotonicity=float(d.get("monotonicity", 0.0)),
            linear_r2=float(d.get("linear_r2", 0.0)),
            step_r2=float(d.get("step_r2", 0.0)),
            recommend_bin=bool(d.get("recommend_bin", False)),
            buckets=[Bucket.from_dict(b) for b in d.get("buckets", [])],
            detail=d.get("detail", ""), flags=tuple(d.get("flags", ())),
        )


def _weighted_r2(buckets: list[Bucket], fitted: list[float]) -> float:
    """n-weighted R^2 of `fitted` against the observed bucket rates."""
    tot_n = sum(b.n for b in buckets)
    if tot_n == 0:
        return 0.0
    mean = sum(b.rate * b.n for b in buckets) / tot_n
    ss_tot = sum(b.n * (b.rate - mean) ** 2 for b in buckets)
    ss_res = sum(b.n * (b.rate - f) ** 2 for b, f in zip(buckets, fitted))
    if ss_tot <= 0:
        return 1.0 if ss_res <= 0 else 0.0
    return max(0.0, 1.0 - ss_res / ss_tot)


def _linear_r2(buckets: list[Bucket]) -> float:
    """Weighted least-squares line through (bucket midpoint, rate)."""
    tot_n = sum(b.n for b in buckets)
    if tot_n == 0 or len(buckets) < 2:
        return 0.0
    mx = sum(b.mid * b.n for b in buckets) / tot_n
    my = sum(b.rate * b.n for b in buckets) / tot_n
    sxx = sum(b.n * (b.mid - mx) ** 2 for b in buckets)
    sxy = sum(b.n * (b.mid - mx) * (b.rate - my) for b in buckets)
    if sxx <= 0:
        return 0.0
    slope = sxy / sxx
    intercept = my - slope * mx
    return _weighted_r2(buckets, [slope * b.mid + intercept for b in buckets])


def _piecewise_r2(buckets: list[Bucket], splits: list[int]) -> float:
    """R^2 of the piecewise-constant fit defined by `splits`.

    Each split is the bucket index at which a new segment begins. With no splits
    this is the grand mean; with one it is the classic two-level step.
    """
    bounds = [0] + sorted(splits) + [len(buckets)]
    fitted: list[float] = []
    for s, e in zip(bounds, bounds[1:]):
        seg = buckets[s:e]
        if not seg:
            continue
        n = sum(b.n for b in seg) or 1
        fitted += [sum(b.x for b in seg) / n] * len(seg)
    return _weighted_r2(buckets, fitted)


def _greedy_splits(buckets: list[Bucket], max_splits: int, *,
                   min_gain: float = 0.01) -> tuple[list[int], float]:
    """Greedily add the cut that most improves the piecewise fit.

    Comparing a *staircase* against the line — rather than a single step against it
    — is what lets a genuine multi-step shape be recognised. The real churn data
    steps twice (0.10 -> 0.58 -> 0.77); against a line that is monotone enough to
    score R^2 0.84, one step gains only 0.11 while two gain 0.16.

    A cut is only kept if it improves R^2 by `min_gain`, so a smooth ramp does not
    accumulate spurious cuts. Ties keep the lowest index, so the result is stable.
    """
    splits: list[int] = []
    current = _piecewise_r2(buckets, splits)
    for _ in range(max(0, max_splits)):
        best_i, best_val = None, None
        for i in range(1, len(buckets)):
            if i in splits:
                continue
            cand = _piecewise_r2(buckets, splits + [i])
            if best_val is None or cand > best_val + 1e-12:
                best_i, best_val = i, cand
        if best_i is None or best_val is None or best_val < current + min_gain:
            break
        splits.append(best_i)
        current = best_val
    return sorted(splits), current


def _best_split(buckets: list[Bucket], alpha: float):
    """Split maximising |rate_above - rate_below|. Lowest index wins a tie."""
    best = None
    for i in range(1, len(buckets)):
        below, above = buckets[:i], buckets[i:]
        n_b, x_b = sum(b.n for b in below), sum(b.x for b in below)
        n_a, x_a = sum(b.n for b in above), sum(b.x for b in above)
        if n_b == 0 or n_a == 0:
            continue
        r_b, r_a = x_b / n_b, x_a / n_a
        gap = abs(r_a - r_b)
        if best is None or gap > best["jump"] + 1e-12:
            test = two_proportion_ztest(x_a, n_a, x_b, n_b, alpha=alpha)
            hi, lo = max(r_a, r_b), min(r_a, r_b)
            best = {
                "index": i, "jump": gap, "rate_below": r_b, "rate_above": r_a,
                # Symmetric: a cliff DOWN is as real as a cliff up. Usage Frequency
                # falls 0.68 -> 0.43; a directional ratio scores that 0.67 and
                # silently discards it.
                "ratio": (hi / lo) if lo > 0 else float("inf"),
                "direction": "up" if r_a >= r_b else "down",
                "z": test.statistic, "p": test.p_value,
                "cut": buckets[i].lo,
            }
    return best


def detect_threshold(buckets: list[Bucket], *, column: str = "",
                     min_jump: float = 0.10, min_ratio: float = 1.5,
                     min_bucket_n: int = 30, min_rel_gain: float = 0.5,
                     alpha: float | None = None, max_cuts: int = 2
                     ) -> ThresholdFinding:
    """Find the cut point(s) at which the outcome rate steps, if any.

    `recommend_bin` is True when the step is BOTH material and better than a line:

      material   : jump >= `min_jump` (absolute)  OR  ratio >= `min_ratio`
                   — either form counts, because a 0.001 -> 0.10 step is tiny in
                   absolute terms and enormous in relative ones, and vice versa.
      significant: the two-proportion test clears `alpha`
      structural : the staircase removes at least `min_rel_gain` of the *residual*
                   variance the straight line leaves behind

    That last test is deliberately relative, not absolute. A monotone staircase is
    partly captured by a line — on the real churn data a line scores R^2 0.86 against
    a 0.10 -> 0.58 -> 0.77 step, leaving only 0.14 of absolute headroom — so an
    absolute-gain rule silently misses the most important cliff in the dataset.
    Measured against the residual, the same staircase removes 97% of the error.
    """
    alpha = alpha or TOLERANCES.alpha
    buckets = sorted(buckets, key=lambda b: b.index)

    if len(buckets) < 3:
        return ThresholdFinding(column=column, kind="insufficient", buckets=buckets,
                                detail=f"need >=3 buckets, got {len(buckets)}")
    thin = [b.index for b in buckets if b.n < min_bucket_n]
    if thin:
        return ThresholdFinding(
            column=column, kind="insufficient", buckets=buckets,
            detail=f"buckets {thin} have fewer than {min_bucket_n} rows",
            flags=("thin buckets",))

    rates = [b.rate for b in buckets]
    ups = sum(1 for a, c in zip(rates, rates[1:]) if c > a)
    monotonicity = ups / (len(rates) - 1)
    lin = _linear_r2(buckets)

    best = _best_split(buckets, alpha)
    if best is None:
        return ThresholdFinding(column=column, kind="flat", buckets=buckets,
                                linear_r2=lin, monotonicity=monotonicity,
                                detail="no usable split")

    # The staircase, not just its single largest step, is what we weigh against a line.
    splits, step_r2 = _greedy_splits(buckets, max_cuts)
    sig = best["p"] is not None and best["p"] < alpha
    material = best["jump"] >= min_jump or best["ratio"] >= min_ratio
    rel_gain = (step_r2 - lin) / (1.0 - lin) if lin < 1.0 - 1e-9 else 0.0
    recommend = material and sig and rel_gain >= min_rel_gain

    if recommend:
        kind = "cliff"
    elif monotonicity >= 0.8:
        kind = "monotone"
    elif monotonicity <= 0.5:
        kind = "non_monotone"
    else:
        kind = "flat"

    cuts = sorted({float(buckets[i].lo) for i in splits}) or [float(best["cut"])]
    detail = (f"strongest step {best['direction']} at {best['cut']:g}: rate "
              f"{best['rate_below']:.4f} -> {best['rate_above']:.4f} "
              f"(jump {best['jump']:.4f}, ratio {best['ratio']:.2f}); "
              f"{len(cuts)}-cut step R2 {step_r2:.3f} vs linear R2 {lin:.3f} "
              f"-> removes {rel_gain:.0%} of the line's residual error")
    return ThresholdFinding(
        column=column, kind=kind, cut_values=cuts if recommend else [],
        jump=best["jump"], ratio=best["ratio"], z=best["z"], p_value=best["p"],
        monotonicity=monotonicity, linear_r2=lin, step_r2=step_r2,
        recommend_bin=recommend, buckets=buckets, detail=detail)
