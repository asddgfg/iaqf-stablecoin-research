"""Identify UTC event periods and measure adjacent-minute BTC price variation."""

import numpy as np
import pandas as pd

STRESS_START = pd.Timestamp("2023-03-10", tz="UTC")
RECOVERY_START = pd.Timestamp("2023-03-13", tz="UTC")
REGIMES = ("pre_event", "stress", "recovery")
RETURN_MARKETS = {
    "cb_usd": "Coinbase BTC/USD",
    "cb_usdc": "Coinbase BTC/USDC",
    "bu_usdt": "Binance.US BTC/USDT",
}


def label_regimes(times: pd.Series) -> pd.Series:
    """Label UTC minutes before, during and after the March 10–12 stress window."""
    labels = np.select(
        [times.lt(STRESS_START), times.lt(RECOVERY_START)],
        REGIMES[:2],
        default=REGIMES[2],
    )
    return pd.Series(labels, index=times.index)


def add_regime_measures(frame: pd.DataFrame) -> None:
    """Attach period labels and absolute one-minute log returns to a sorted panel."""
    times = frame["datetime"]
    frame["regime"] = label_regimes(times)
    # Filter after differencing on the clock grid. Dropping untraded minutes
    # first would turn the return across a long gap into a one-minute change.
    same_regime = frame["regime"].eq(frame["regime"].shift())
    adjacent = times.diff().eq(pd.Timedelta(minutes=1)) & same_regime
    for market in RETURN_MARKETS:
        frame[f"abs_log_return_{market}"] = (
            np.log(frame[market]).diff().abs().where(adjacent)
        )


def mean_absolute_returns(frame: pd.DataFrame) -> pd.DataFrame:
    """Return figure 7's mean absolute log returns for each period and market."""
    columns = {f"abs_log_return_{market}": market for market in RETURN_MARKETS}
    grouped = frame.groupby("regime")[list(columns)].mean()
    return grouped.reindex(REGIMES).rename(columns=columns)
