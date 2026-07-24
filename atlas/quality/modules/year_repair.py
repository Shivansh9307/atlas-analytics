"""Year Repair: a precomputed Year column that disagrees with the date."""
from __future__ import annotations

from atlas.quality.modules.base import register
from atlas.quality.modules.month_repair import MonthRepair


@register
class YearRepair(MonthRepair):
    id = "year_repair"
    dimension = "consistency"
    _stored = ("year",)
    _label = "Year"

    def _derived(self, dexpr: str) -> str:
        return f"CAST(year({dexpr}) AS VARCHAR)"

    def _pandas_derived(self, date_col: str) -> str:
        return (f"pd.to_datetime(df[{date_col!r}], errors='coerce')"
                f".dt.year.astype('Int64')")
