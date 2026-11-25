"""Interpret observation flags shared by the data audit and price-panel reader."""

import pandas as pd


def observation_flags(values: pd.Series) -> pd.Series:
    """Normalize candle-provenance labels, retaining missing and invalid values."""
    return values.astype("string").str.strip().str.lower()
