"""Calculate signed BTC quote bases, fee comparisons and period returns."""

import pandas as pd

from iaqf.config import MARKETS

from .comparisons import REPORT_COMPARISONS
from .dataset import traded_minutes, utc_minute_keys
from .regimes import add_regime_measures


def analyze_bases(dataset: pd.DataFrame) -> pd.DataFrame:
    """Return per-minute results from the prepared panel without changing its inputs.

    Rates in pct_basis_* columns are fractional. Missing or untraded legs
    leave the corresponding basis and fee flag unavailable for that minute.
    """
    frame = dataset.copy()
    frame["datetime"] = utc_minute_keys(frame["datetime"], "Q1 dataset")
    frame = frame.sort_values("datetime", ignore_index=True)
    # Reapply the eligibility rule to reopened panels as well as fresh inputs.
    for market in MARKETS:
        close = pd.to_numeric(frame[market], errors="raise")
        volume = pd.to_numeric(frame[f"{market}_volume"], errors="raise")
        frame[market] = close.where(traded_minutes(close, volume))
    for comparison in REPORT_COMPARISONS:
        comparison.add_measures(frame)
    add_regime_measures(frame)
    return frame
