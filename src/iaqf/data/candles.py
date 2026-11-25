"""Validate OHLC ranges and align exchange observations to a complete minute grid."""

import numpy as np
import pandas as pd

from iaqf.config import CANDLE_COLUMNS, MINUTE_MS, PRICE_COLUMNS


def valid_ohlc(prices: pd.DataFrame) -> pd.Series:
    """Mark numeric rows with finite positive prices and coherent OHLC bounds."""
    endpoints = prices[["open", "close"]]
    return (
        np.isfinite(prices[PRICE_COLUMNS]).all(axis=1)
        & prices["low"].gt(0)
        & prices["low"].le(endpoints.min(axis=1))
        & prices["high"].ge(endpoints.max(axis=1))
    )


def _validated_candles(rows: list) -> pd.DataFrame:
    """Return unique exchange candles indexed by minute, or reject invalid input."""
    if not rows:
        raise ValueError("The exchange returned no candles in the study window")
    candles = pd.DataFrame(rows, columns=CANDLE_COLUMNS).apply(
        pd.to_numeric, errors="raise"
    )
    if not np.isfinite(candles.to_numpy(dtype=float)).all():
        raise ValueError("Exchange candle contains a missing or infinite value")
    if (candles["timestamp"] % MINUTE_MS != 0).any():
        raise ValueError("Exchange candle timestamp is off the UTC minute grid")
    if not (valid_ohlc(candles) & candles["volume"].ge(0)).all():
        raise ValueError("Invalid OHLC price range or negative volume")

    # Identical repeats can occur where exchange pages overlap. Reject conflicting
    # prints because picking one would make the saved data depend on arrival order.
    candles = candles.drop_duplicates().set_index("timestamp")
    if not candles.index.is_unique:
        raise ValueError("Conflicting exchange candles share a timestamp")
    return candles


def regularize_candles(rows: list, start: int, end: int) -> pd.DataFrame:
    """Align validated exchange candles to the inclusive UTC minute grid.

    Missing minutes get a flat candle at the last known close and zero volume.
    Leading gaps retain missing prices. The observation flag identifies genuine
    exchange candles, including any the venue supplied with zero trade volume.
    """
    candles = _validated_candles(rows)
    minute_grid = pd.RangeIndex(start, end + MINUTE_MS, MINUTE_MS, name="timestamp")
    frame = candles.reindex(minute_grid)
    frame["is_observed"] = minute_grid.isin(candles.index)
    gaps = ~frame["is_observed"]
    previous_close = frame["close"].ffill()
    for column in PRICE_COLUMNS:
        frame.loc[gaps, column] = previous_close[gaps]
    frame.loc[gaps, "volume"] = 0
    frame = frame.reset_index()
    # Convert from milliseconds explicitly. Pandas datetime storage may use
    # different resolutions across versions, so integer casts are ambiguous.
    frame.insert(0, "datetime", pd.to_datetime(frame["timestamp"], unit="ms", utc=True))
    return frame
