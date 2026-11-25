"""Produce full-study and event-period summary statistics in report order."""

import pandas as pd

from .comparisons import REPORT_COMPARISONS, BasisComparison
from .regimes import REGIMES


def _summarize_comparison(
    period: str, sample: pd.DataFrame, pair: BasisComparison
) -> dict:
    """Summarize valid paired prices, fee breaches and the earliest tied extrema."""
    rates = sample[f"pct_basis_{pair.name}"].dropna()
    count = len(rates)
    breaches = None
    if pair.fee is not None:
        breaches = int(sample[f"exceeds_cost_{pair.name}"].sum())
    # Coverage and breach rate have different denominators. An empty period
    # reports zero observations and leaves its percentages and extrema blank.
    return {
        "period": period,
        "comparison": pair.name,
        "grid_minutes": len(sample),
        "eligible_minutes": count,
        "fee_band_pct": 100 * pair.fee if pair.fee is not None else None,
        "breach_minutes": breaches,
        "breach_pct_of_eligible": (
            100 * breaches / count if breaches is not None and count else None
        ),
        "median_basis_pct": 100 * rates.median() if count else None,
        "min_basis_pct": 100 * rates.min() if count else None,
        "min_utc": sample.at[rates.idxmin(), "datetime"] if count else None,
        "max_basis_pct": 100 * rates.max() if count else None,
        "max_utc": sample.at[rates.idxmax(), "datetime"] if count else None,
    }


def summarize_bases(frame: pd.DataFrame) -> pd.DataFrame:
    """Summarize each comparison for the entire study and its three UTC periods."""
    periods = {"full": frame}
    periods.update(
        (period, frame.loc[frame["regime"].eq(period)]) for period in REGIMES
    )
    return pd.DataFrame(
        [
            _summarize_comparison(period, sample, pair)
            for period, sample in periods.items()
            for pair in REPORT_COMPARISONS
        ]
    )
