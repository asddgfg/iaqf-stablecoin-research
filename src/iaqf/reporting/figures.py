"""Reproduce the eight published charts from the detailed analysis table."""

from pathlib import Path

import pandas as pd

from iaqf.config import ROUND_TRIP_USDC_USD_BITSTAMP, ROUND_TRIP_USDT_USD

from .charts import plot_absolute_returns, plot_basis_distribution, plot_time_series


def make_plots_q1(results: pd.DataFrame, figure_dir: str | Path) -> None:
    """Write all eight report JPEGs in figure_dir from analyzed minute data.

    Every chart receives the same result table used for summary calculations.
    Matplotlib draws on headless figures, so batch runs require no display.
    """
    directory = Path(figure_dir)
    directory.mkdir(parents=True, exist_ok=True)
    plot_time_series(
        results,
        directory / "q1_plot1_usdt_vs_usd_cost_band.jpg",
        "BTC/USDT on Binance.US vs BTC/USD on Coinbase",
        [("pct_basis_usdt_usd", "BTC/USDT vs BTC/USD", "#2459a0")],
        "BTC quote basis",
        fee=ROUND_TRIP_USDT_USD,
    )
    plot_time_series(
        results,
        directory / "q1_plot2_driver_comparison.jpg",
        "USDT- and USDC-quoted BTC vs Coinbase BTC/USD",
        [
            ("pct_basis_usdt_usd", "Binance.US BTC/USDT", "#2459a0"),
            ("pct_basis_usdc_usd", "Bitstamp BTC/USDC", "#b74913"),
        ],
        "BTC quote basis",
    )
    plot_time_series(
        results,
        directory / "q1_plot3_bitstamp_usdc_usd.jpg",
        "Bitstamp BTC/USDC vs BTC/USD",
        [("pct_basis_usdc_usd_bitstamp", "BTC/USDC vs BTC/USD", "#b74913")],
        "BTC quote basis",
        fee=ROUND_TRIP_USDC_USD_BITSTAMP,
    )
    plot_time_series(
        results,
        directory / "q1_plot4_coinbase_shared_book.jpg",
        "Coinbase BTC/USDC and BTC/USD reported closes",
        [("basis_cb_usdc_minus_cb_usd", "BTC/USDC minus BTC/USD", "#2459a0")],
        "Quote units per BTC",
        percentage=False,
    )
    plot_basis_distribution(results, directory / "q1_plot5_binanceus_regimes.jpg")
    plot_time_series(
        results,
        directory / "q1_plot6_usdc_venue_comparison.jpg",
        "BTC/USDC relative to BTC/USD on the same venue",
        [
            ("pct_basis_usdc_usd_coinbase", "Coinbase", "#2459a0"),
            ("pct_basis_usdc_usd_bitstamp", "Bitstamp", "#b74913"),
        ],
        "BTC quote basis",
    )
    plot_absolute_returns(results, directory / "q1_plot7_absolute_returns.jpg")
    plot_time_series(
        results,
        directory / "q1_plot8_usdc_intraminute_range.jpg",
        "BTC/USDC traded price range within each minute",
        [
            ("cb_usdc_range", "Coinbase", "#2459a0"),
            ("bs_usdc_range", "Bitstamp", "#b74913"),
        ],
        "(High − low) / open",
    )
