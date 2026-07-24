"""Per-run budget tracking. The one place full-auto still pauses is a projected
warehouse scan over budget — enforced here and in the connector's run()."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from atlas.config import BUDGETS


class BudgetBreach(Exception):
    pass


@dataclass
class RunBudget:
    max_queries: int = field(default_factory=lambda: BUDGETS.max_queries)
    max_bytes_scanned: int = field(default_factory=lambda: BUDGETS.max_bytes_scanned)
    max_wallclock_s: int = field(default_factory=lambda: BUDGETS.max_wallclock_s)

    queries_used: int = 0
    bytes_used: int = 0
    _start: float = field(default_factory=time.monotonic)

    def charge_query(self, bytes_scanned: int | None = None) -> None:
        self.queries_used += 1
        if bytes_scanned:
            self.bytes_used += bytes_scanned
        self._check()

    def elapsed_s(self) -> float:
        return time.monotonic() - self._start

    def remaining_bytes(self) -> int:
        return max(0, self.max_bytes_scanned - self.bytes_used)

    def _check(self) -> None:
        if self.queries_used > self.max_queries:
            raise BudgetBreach(f"query cap exceeded ({self.queries_used}/{self.max_queries})")
        if self.bytes_used > self.max_bytes_scanned:
            raise BudgetBreach(
                f"scan-byte cap exceeded ({self.bytes_used:,}/{self.max_bytes_scanned:,})"
            )
        if self.elapsed_s() > self.max_wallclock_s:
            raise BudgetBreach(
                f"wall-clock cap exceeded ({self.elapsed_s():.0f}s/{self.max_wallclock_s}s)"
            )

    def snapshot(self) -> dict:
        return {
            "queries_used": self.queries_used,
            "max_queries": self.max_queries,
            "bytes_used": self.bytes_used,
            "max_bytes_scanned": self.max_bytes_scanned,
            "elapsed_s": round(self.elapsed_s(), 1),
            "max_wallclock_s": self.max_wallclock_s,
        }
