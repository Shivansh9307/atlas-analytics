"""Quarter Repair: a precomputed Quarter column that disagrees with the date."""
from __future__ import annotations

from atlas.quality.modules.base import register
from atlas.quality.modules.month_repair import MonthRepair


@register
class QuarterRepair(MonthRepair):
    id = "quarter_repair"
    dimension = "consistency"
    _stored = ("quarter",)
    _label = "Quarter"
    # Lower: calendar quarter may not match an intentional fiscal-quarter scheme,
    # so this repair must be approved by a human, not auto-applied.
    _confidence = 0.70

    def _derived(self, dexpr: str) -> str:
        return f"('Q' || CAST(quarter({dexpr}) AS VARCHAR))"

    def _pandas_derived(self, date_col: str) -> str:
        return (f"'Q' + pd.to_datetime(df[{date_col!r}], errors='coerce')"
                f".dt.quarter.astype('Int64').astype(str)")
