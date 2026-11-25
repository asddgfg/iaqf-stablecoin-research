"""Draw UTC scatter plots, distribution box plots and return comparisons."""

from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib import dates as mdates
from matplotlib.figure import Figure
from matplotlib.ticker import PercentFormatter, ScalarFormatter

from iaqf.analysis.regimes import REGIMES, RETURN_MARKETS, mean_absolute_returns

REGIME_LABELS = ("Mar 1–9", "Mar 10–12", "Mar 13–21")


def plot_time_series(
    frame: pd.DataFrame,
    destination: Path,
    title: str,
    columns: list[tuple[str, str, str]],
    ylabel: str,
    *,
    percentage: bool = True,
    fee: float | None = None,
) -> None:
    """Plot eligible minutes as points with an optional two-leg fee band."""
    figure = Figure(figsize=(11, 4.3), layout="constrained")
    axes = figure.subplots()
    for column, label, color in columns:
        # Separate dots leave visible gaps when a book goes minutes without a
        # trade. Connecting those prices could imply continuous observations.
        axes.scatter(
            frame["datetime"],
            frame[column],
            s=5,
            linewidths=0,
            color=color,
            alpha=0.75,
            label=label,
        )
    if fee is not None:
        axes.axhline(
            fee,
            color="#555555",
            linestyle="--",
            linewidth=1,
            label=f"Assumed two-leg fee band (±{fee:.2%})",
        )
        axes.axhline(-fee, color="#555555", linestyle="--", linewidth=1)
    formatter = (
        PercentFormatter(xmax=1) if percentage else ScalarFormatter(useOffset=False)
    )
    axes.yaxis.set_major_formatter(formatter)
    locator = mdates.AutoDateLocator(minticks=4, maxticks=9, tz="UTC")
    axes.xaxis.set_major_locator(locator)
    axes.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator, tz="UTC"))
    axes.set(title=title, xlabel="Time (UTC)", ylabel=ylabel)
    axes.grid(axis="y", alpha=0.2)
    axes.legend(loc="best")
    figure.savefig(destination, dpi=150)


def plot_basis_distribution(frame: pd.DataFrame, destination: Path) -> None:
    """Compare the Binance.US BTC/USDT versus BTC/USDC basis across periods."""
    figure = Figure(figsize=(9, 4.3), layout="constrained")
    axes = figure.subplots()
    groups = [
        frame.loc[frame["regime"].eq(regime), "pct_basis_usdt_usdc"].dropna()
        for regime in REGIMES
    ]
    axes.boxplot(
        groups,
        widths=0.45,
        patch_artist=True,
        boxprops={"facecolor": "#a8c7e3"},
        flierprops={"marker": ".", "markersize": 3, "alpha": 0.35},
        medianprops={"color": "#7c2d12", "linewidth": 2},
    )
    axes.set_xticks([1, 2, 3], REGIME_LABELS)
    axes.set(
        title="Binance.US BTC/USDT relative to BTC/USDC",
        xlabel="March 2023 UTC regime",
        ylabel="BTC quote basis",
    )
    axes.yaxis.set_major_formatter(PercentFormatter(xmax=1))
    axes.grid(axis="y", alpha=0.2)
    figure.savefig(destination, dpi=150)


def plot_absolute_returns(frame: pd.DataFrame, destination: Path) -> None:
    """Draw the mean of eligible one-minute absolute log returns for each regime."""
    figure = Figure(figsize=(9, 4.3), layout="constrained")
    axes = figure.subplots()
    means = mean_absolute_returns(frame)
    positions = np.arange(len(REGIMES))
    width = 0.23
    for number, (market, label) in enumerate(RETURN_MARKETS.items()):
        axes.bar(positions + (number - 1) * width, means[market], width, label=label)
    axes.set_xticks(positions, REGIME_LABELS)
    axes.set(
        title="BTC price changes within each regime",
        xlabel="March 2023 UTC regime",
        ylabel="Mean absolute one-minute log return",
    )
    axes.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=3))
    axes.grid(axis="y", alpha=0.2)
    axes.legend(loc="best")
    figure.savefig(destination, dpi=150)
