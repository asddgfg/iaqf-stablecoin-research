"""Define the market pairs, quote directions, and fee bands used in the study."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from iaqf.config import (
    ROUND_TRIP_USDC_USD,
    ROUND_TRIP_USDC_USD_BITSTAMP,
    ROUND_TRIP_USDT_USD,
    ROUND_TRIP_USDT_USDC,
)


@dataclass(frozen=True)
class BasisComparison:
    """One signed BTC quote comparison, with its right-hand reference and fee."""

    name: str
    left: str
    right: str
    fee: float | None

    @property
    def difference_column(self) -> str:
        """Identify the absolute price difference in quote units per BTC."""
        return f"basis_{self.left}_minus_{self.right}"

    def price_difference(self, prices: pd.DataFrame) -> pd.Series:
        """Subtract the reference close from the left quote at each UTC minute."""
        return prices[self.left] - prices[self.right]

    def add_measures(self, frame: pd.DataFrame) -> None:
        """Write absolute and fractional bases and any applicable fee flags in place."""
        difference = self.price_difference(frame)
        fraction = difference / frame[self.right]
        frame[self.difference_column] = difference
        frame[f"pct_basis_{self.name}"] = fraction
        if self.fee is None:
            return

        # Price decimals may miss the fee by a few ulps. Count only a genuine
        # breach, and leave a missing minute out of the eligible denominator.
        magnitude = fraction.abs()
        over = magnitude.gt(self.fee) & ~np.isclose(
            magnitude, self.fee, rtol=1e-12, atol=0.0
        )
        frame[f"exceeds_cost_{self.name}"] = over.astype("boolean").where(
            fraction.notna()
        )


USDT_USD = BasisComparison("usdt_usd", "bu_usdt", "cb_usd", ROUND_TRIP_USDT_USD)
USDC_USD = BasisComparison("usdc_usd", "bs_usdc", "cb_usd", ROUND_TRIP_USDC_USD)
USDT_USDC = BasisComparison("usdt_usdc", "bu_usdt", "bu_usdc", ROUND_TRIP_USDT_USDC)
BITSTAMP_USDC_USD = BasisComparison(
    "usdc_usd_bitstamp", "bs_usdc", "bs_usd", ROUND_TRIP_USDC_USD_BITSTAMP
)
COINBASE_USDC_USD = BasisComparison("usdc_usd_coinbase", "cb_usdc", "cb_usd", None)

# Absolute differences appear in their established dataset column order; the
# report leads with cross-venue bases and ends with the Coinbase book check.
DATASET_COMPARISONS = (
    COINBASE_USDC_USD,
    BITSTAMP_USDC_USD,
    USDT_USDC,
    USDT_USD,
    USDC_USD,
)
REPORT_COMPARISONS = (
    USDT_USD,
    USDC_USD,
    USDT_USDC,
    BITSTAMP_USDC_USD,
    COINBASE_USDC_USD,
)
