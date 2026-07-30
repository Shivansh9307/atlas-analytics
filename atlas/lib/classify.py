"""Classification metrics, hand-rolled — no scikit-learn.

Why not sklearn: statsmodels (already a dependency) is the estimator, because it
returns standard errors, p-values and confidence intervals that sklearn's
`LogisticRegression` does not — and sklearn regularises by default (`C=1.0`), which
silently shrinks the coefficients this system then reports as odds ratios. Given
that, the only sklearn pieces left to want are these metrics, and they are all
counting or a rank identity. About 150 lines, each directly checkable against a
hand-computed fixture, versus a ~30MB dependency used at a few percent.

`accuracy` is deliberately never reported alone: on a target with a 47% base rate,
"always predict the majority" scores 53% and looks respectable while being useless.
`majority_baseline()` exists so that comparison is always available.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = [
    "ConfusionMatrix", "confusion_at", "roc_auc", "roc_curve", "threshold_table",
    "calibration_bins", "brier_score", "majority_baseline", "ks_statistic",
]


@dataclass
class ConfusionMatrix:
    tp: int
    fp: int
    tn: int
    fn: int

    @property
    def n(self) -> int:
        return self.tp + self.fp + self.tn + self.fn

    @property
    def accuracy(self) -> float:
        return (self.tp + self.tn) / self.n if self.n else 0.0

    @property
    def precision(self) -> float:
        d = self.tp + self.fp
        return self.tp / d if d else 0.0

    @property
    def recall(self) -> float:
        d = self.tp + self.fn
        return self.tp / d if d else 0.0

    @property
    def specificity(self) -> float:
        d = self.tn + self.fp
        return self.tn / d if d else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    def as_dict(self) -> dict:
        return {"tp": self.tp, "fp": self.fp, "tn": self.tn, "fn": self.fn,
                "n": self.n, "accuracy": self.accuracy, "precision": self.precision,
                "recall": self.recall, "specificity": self.specificity, "f1": self.f1}


def confusion_at(y_true, y_score, threshold: float) -> ConfusionMatrix:
    """Confusion matrix at a decision threshold. `score >= threshold` predicts 1."""
    tp = fp = tn = fn = 0
    for y, s in zip(y_true, y_score):
        pred = 1 if s >= threshold else 0
        if y == 1 and pred == 1:
            tp += 1
        elif y == 0 and pred == 1:
            fp += 1
        elif y == 0 and pred == 0:
            tn += 1
        else:
            fn += 1
    return ConfusionMatrix(tp=tp, fp=fp, tn=tn, fn=fn)


def roc_auc(y_true, y_score) -> float | None:
    """ROC-AUC via the Mann-Whitney rank identity, with correct mid-rank ties.

        AUC = (sum of ranks of positives - n_pos(n_pos+1)/2) / (n_pos * n_neg)

    Tied scores must share an averaged rank; without that, a model that predicts one
    constant for everyone scores 1.0 or 0.0 depending on sort order instead of the
    correct 0.5.
    """
    pairs = sorted(zip(y_score, y_true), key=lambda t: t[0])
    n = len(pairs)
    n_pos = sum(1 for _, y in pairs if y == 1)
    n_neg = n - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    rank_sum_pos = 0.0
    i = 0
    while i < n:
        j = i
        while j < n and pairs[j][0] == pairs[i][0]:
            j += 1
        mid_rank = (i + 1 + j) / 2.0          # 1-indexed average rank of the tie block
        rank_sum_pos += sum(mid_rank for k in range(i, j) if pairs[k][1] == 1)
        i = j
    return (rank_sum_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def roc_curve(y_true, y_score, *, points: int = 100) -> list[tuple[float, float]]:
    """(fpr, tpr) pairs across evenly spaced thresholds, for plotting."""
    out = []
    for i in range(points + 1):
        t = i / points
        cm = confusion_at(y_true, y_score, t)
        out.append((1 - cm.specificity, cm.recall))
    return out


def threshold_table(y_true, y_score, thresholds) -> list[dict]:
    """Precision/recall/F1 across candidate cutoffs.

    This table is the honest way to present a classifier: 0.5 is a *modelling*
    default, not a business decision, and the cost of missing a churner is rarely
    equal to the cost of flagging a loyal customer. Showing the trade-off lets the
    operating point be chosen deliberately.
    """
    rows = []
    for t in thresholds:
        cm = confusion_at(y_true, y_score, t)
        rows.append({"threshold": round(float(t), 4), "flagged": cm.tp + cm.fp,
                     "precision": cm.precision, "recall": cm.recall, "f1": cm.f1,
                     "tp": cm.tp, "fp": cm.fp, "fn": cm.fn, "tn": cm.tn})
    return rows


def calibration_bins(y_true, y_score, k: int = 10) -> list[dict]:
    """Predicted vs observed rate per score decile — does 0.7 mean 70%?

    A model can rank perfectly (high AUC) and still be badly calibrated, which
    matters here because the predicted probability is what a risk tier is cut on.
    """
    pairs = sorted(zip(y_score, y_true), key=lambda t: t[0])
    n = len(pairs)
    if n == 0:
        return []
    out = []
    size = max(1, n // k)
    for b in range(k):
        lo = b * size
        hi = n if b == k - 1 else min(n, (b + 1) * size)
        chunk = pairs[lo:hi]
        if not chunk:
            continue
        pred = sum(s for s, _ in chunk) / len(chunk)
        obs = sum(y for _, y in chunk) / len(chunk)
        out.append({"bin": b + 1, "n": len(chunk), "predicted": pred,
                    "observed": obs, "gap": obs - pred})
    return out


def brier_score(y_true, y_score) -> float:
    """Mean squared error of the probabilities. Lower is better; 0.25 == coin flip."""
    n = len(y_true)
    return sum((s - y) ** 2 for y, s in zip(y_true, y_score)) / n if n else 0.0


def majority_baseline(y_true) -> ConfusionMatrix:
    """What "always predict the majority class" scores — the floor any model must clear."""
    n = len(y_true)
    n_pos = sum(y_true)
    if n_pos * 2 >= n:                       # majority is 1
        return ConfusionMatrix(tp=n_pos, fp=n - n_pos, tn=0, fn=0)
    return ConfusionMatrix(tp=0, fp=0, tn=n - n_pos, fn=n_pos)


def ks_statistic(y_true, y_score) -> float:
    """Max separation between the positive and negative score distributions."""
    pos = sorted(s for y, s in zip(y_true, y_score) if y == 1)
    neg = sorted(s for y, s in zip(y_true, y_score) if y == 0)
    if not pos or not neg:
        return 0.0
    best = 0.0
    for t in sorted(set(y_score)):
        fp = sum(1 for s in pos if s <= t) / len(pos)
        fn = sum(1 for s in neg if s <= t) / len(neg)
        best = max(best, abs(fn - fp))
    return best


def _safe_log(x: float, eps: float = 1e-12) -> float:
    return math.log(max(eps, min(1 - eps, x)))
