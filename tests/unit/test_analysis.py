"""Regression tests for UTC alignment, quote orientation, fee bands and output."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from iaqf.analysis import (
    analyze_bases,
    overview_from_dataset,
    prepare_q1_dataset,
    read_prepared_dataset,
    summarize_bases,
)
from iaqf.analysis.dataset import align_minutes, load_pair
from iaqf.analysis.regimes import mean_absolute_returns
from iaqf.config import MARKETS


def sample_minutes(prices: dict[str, list[float]]) -> pd.DataFrame:
    """Build a UTC minute panel with traded defaults and selected price overrides."""
    count = len(next(iter(prices.values())))
    dates = pd.date_range("2023-03-11 08:10", periods=count, freq="min", tz="UTC")
    frame = pd.DataFrame({"datetime": dates})
    for market in MARKETS:
        frame[market] = prices.get(market, [100.0] * count)
        frame[f"{market}_volume"] = 1.0
    return frame


def write_markets(directory: Path, panel: pd.DataFrame) -> None:
    """Write six small candle CSVs exactly as the Q1 entry points receive them."""
    directory.mkdir(parents=True, exist_ok=True)
    for market, filename in MARKETS.items():
        candles = pd.DataFrame(
            {
                "datetime": panel["datetime"],
                "open": panel[market],
                "high": panel[market],
                "low": panel[market],
                "close": panel[market],
                "volume": panel[f"{market}_volume"],
            }
        )
        candles.to_csv(directory / filename, index=False)


class MarketAlignmentTests(unittest.TestCase):
    """Exercise source validation and pairwise time alignment."""

    def test_nontrades_and_synthetic_rows_are_missing_prices(self):
        """Filter zero volume, explicit synthetic bars, and invalid closes independently."""
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            frame = pd.DataFrame(
                {
                    "datetime": pd.date_range("2023-03-11", periods=5, freq="min"),
                    "close": [100, 105, 99, 0, float("inf")],
                    "volume": [1, 0, 0, 1, 1],
                    "is_observed": [True, True, False, True, True],
                }
            )
            frame.to_csv(directory / "candles.csv", index=False)
            loaded = load_pair("candles.csv", "market", directory)
            self.assertEqual(loaded["market"].dropna().tolist(), [100.0])
            self.assertEqual(loaded["market_volume"].tolist(), [1, 0, 0, 1, 1])

    def test_synthetic_candles_cannot_claim_positive_volume(self):
        """Reject contradictory provenance instead of counting invented trades."""
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            pd.DataFrame(
                {
                    "datetime": ["2023-03-10 19:00:00-05:00"],
                    "close": [100],
                    "volume": [1],
                    "is_observed": [" FALSE "],
                }
            ).to_csv(directory / "pair.csv", index=False)
            with self.assertRaisesRegex(ValueError, "synthetic"):
                load_pair("pair.csv", "x", directory)

    def test_duplicate_utc_keys_and_subminute_times_fail(self):
        """Reject UTC aliases for the same minute and keys that would split a candle."""
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for other, error in [
                ("2023-03-10 19:00:00-05:00", "duplicate"),
                ("2023-03-11 00:00:30+00:00", "grid"),
            ]:
                with self.subTest(other=other):
                    pd.DataFrame(
                        {
                            "datetime": ["2023-03-11 00:00:00+00:00", other],
                            "close": [100, 101],
                            "volume": [1, 2],
                        }
                    ).to_csv(directory / "pair.csv", index=False)
                    with self.assertRaisesRegex(ValueError, error):
                        load_pair("pair.csv", "x", directory)

    def test_utc_union_includes_a_minute_missing_on_every_market(self):
        """Keep missing minutes and preserve a trade on an unrelated market."""
        panel = sample_minutes({"cb_usd": [100.0, 101.0, 102.0]})
        first = panel.loc[[0, 2], ["datetime", "cb_usd"]]
        second = panel.loc[[2], ["datetime", "bs_usdc"]]
        joined = align_minutes([first, second])
        self.assertEqual(len(joined), 3)
        self.assertTrue(pd.isna(joined.loc[1, "cb_usd"]))
        self.assertTrue(pd.isna(joined.loc[0, "bs_usdc"]))
        self.assertEqual(joined.loc[0, "cb_usd"], 100.0)


class BasisCalculationTests(unittest.TestCase):
    """Verify the report measures against hand-calculated minute observations."""

    def test_bases_use_right_hand_currency_and_venue(self):
        """Use each comparison's own denominator and preserve the quote direction."""
        panel = sample_minutes(
            {
                "bu_usdt": [102.0],
                "bu_usdc": [120.0],
                "bs_usdc": [125.0],
                "bs_usd": [110.0],
            }
        )
        computed = analyze_bases(panel).iloc[0]
        for column, expected in [
            ("pct_basis_usdt_usd", 0.02),
            ("pct_basis_usdc_usd", 0.25),
            ("pct_basis_usdt_usdc", -0.15),
            ("pct_basis_usdc_usd_bitstamp", 15.0 / 110.0),
            ("pct_basis_usdc_usd_coinbase", 0.0),
        ]:
            with self.subTest(column=column):
                self.assertAlmostEqual(computed[column], expected)

    def test_equal_fee_and_missing_prices_have_distinct_outcomes(self):
        """Treat fee equality as within the band and exclude missing samples from rates."""
        panel = sample_minutes(
            {"bu_usdt": [100.7, 99.29, 120.0], "cb_usd": [100, 100, 0]}
        )
        computed = analyze_bases(panel)
        flags = computed["exceeds_cost_usdt_usd"]
        self.assertFalse(flags.iat[0])
        self.assertTrue(flags.iat[1])
        self.assertTrue(pd.isna(flags.iat[2]))
        rows = summarize_bases(computed).set_index(["period", "comparison"])
        result = rows.loc[("full", "usdt_usd")]
        self.assertEqual(result["grid_minutes"], 3)
        self.assertEqual(result["eligible_minutes"], 2)
        self.assertEqual(result["breach_pct_of_eligible"], 50)
        self.assertTrue(pd.isna(rows.loc[("pre_event", "usdt_usd"), "min_utc"]))

    def test_both_same_exchange_fee_legs_match_the_actual_venues(self):
        """Charge 0.20% for two Binance.US legs and 0.80% for two Bitstamp legs."""
        panel = sample_minutes(
            {"bu_usdt": [100.20, 100.21], "bs_usdc": [100.80, 100.81]}
        )
        result = analyze_bases(panel)
        self.assertEqual(result["exceeds_cost_usdt_usdc"].tolist(), [False, True])
        self.assertEqual(
            result["exceeds_cost_usdc_usd_bitstamp"].tolist(), [False, True]
        )

    def test_flagged_leg_only_removes_the_affected_comparisons(self):
        """Carry missing and nonfinite fields through normalized and fee statistics."""
        panel = sample_minutes({"bs_usdc": [123.0, np.inf], "bu_usdt": [101.0, 101.0]})
        panel.loc[0, "bs_usdc_volume"] = 0
        result = analyze_bases(panel)
        self.assertTrue(result["pct_basis_usdc_usd_bitstamp"].isna().all())
        self.assertTrue(result["exceeds_cost_usdc_usd"].isna().all())
        self.assertTrue(result["exceeds_cost_usdt_usd"].all())

    def test_legacy_overview_and_q1_output_name_the_correct_legs(self):
        """Exercise real files including missing candles and the binanceus name."""
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            panel = sample_minutes(
                {"bu_usdt": [101, 102], "cb_usdc": [99, 98], "bu_usdc": [97, 96]}
            )
            write_markets(directory / "data", panel)
            prepared = prepare_q1_dataset(directory / "data")
            # Once the source panel exists, producing either view must require
            # no more reads from the six candle files.
            with patch("pandas.read_csv", side_effect=AssertionError("unexpected I/O")):
                result = overview_from_dataset(prepared)
            self.assertEqual(prepared["basis_bu_usdt_minus_bu_usdc"].tolist(), [4, 6])
            self.assertEqual(result["basis_USDT_USD"].tolist(), [1, 2])
            self.assertEqual(result["basis_USDT_USDC"].tolist(), [2, 4])

    def test_legacy_q1_input_recovers_trade_eligibility_from_candles(self):
        """Rebuild volume-free inputs and leave the legacy CSV untouched."""
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            panel = sample_minutes({"bu_usdt": [102.0, 103.0]})
            panel.loc[1, "bu_usdt_volume"] = 0
            write_markets(directory / "data", panel)
            source = directory / "legacy.csv"
            panel[["datetime", *MARKETS]].to_csv(source, index=False)
            result = analyze_bases(read_prepared_dataset(source))
            self.assertEqual(len(result["pct_basis_usdt_usd"].dropna()), 1)
            self.assertNotIn("bu_usdt_volume", pd.read_csv(source).columns)

    def test_reopen_complete_panel_works_without_source_dir(self):
        """Reopen a complete persisted table without requiring a second raw-data read."""
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            candles = directory / "data"
            write_markets(candles, sample_minutes({"bu_usdt": [101.0, 100.5]}))
            source = directory / "panel.csv"
            prepare_q1_dataset(candles).to_csv(source, index=False)
            panel = read_prepared_dataset(source, directory / "unused")
            result = analyze_bases(panel)
            self.assertEqual(result["pct_basis_usdt_usd"].tolist(), [0.01, 0.005])


class RegimeMeasureTests(unittest.TestCase):
    """Check the measurement choices behind report figures 5–8."""

    def test_range_normalization_respects_ohlc_bounds_and_volume(self):
        """Divide traded high–low by the open and mask incoherent or stale bars."""
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            candles = pd.DataFrame(
                {
                    "datetime": pd.date_range("2023-03-11", periods=3, freq="min"),
                    "open": [100, 100, 100],
                    "high": [110, 105, 110],
                    "low": [95, 95, 95],
                    "close": [108, 108, 108],
                    "volume": [1, 1, 0],
                }
            )
            candles.to_csv(directory / "pair.csv", index=False)
            prices = load_pair("pair.csv", "x", directory, include_range=True)
            self.assertAlmostEqual(prices.loc[0, "x_range"], 0.15)
            self.assertTrue(prices.loc[1:, "x_range"].isna().all())

    def test_returns_do_not_span_missing_minutes_or_regime_boundaries(self):
        """Keep absolute minute returns only for adjacent trades in the same regime."""
        panel = sample_minutes({"cb_usd": [100, 105, 115, 125, 110]})
        panel["datetime"] = pd.to_datetime(
            [
                "2023-03-09 23:59",
                "2023-03-10 00:00",
                "2023-03-10 00:01",
                "2023-03-10 00:03",
                "2023-03-10 00:04",
            ],
            utc=True,
        )
        panel.loc[4, "cb_usd_volume"] = 0
        frame = analyze_bases(panel)
        self.assertEqual(frame["regime"].tolist(), ["pre_event"] + ["stress"] * 4)
        returns = frame["abs_log_return_cb_usd"].dropna()
        self.assertEqual(returns.index.tolist(), [2])
        self.assertAlmostEqual(returns.iat[0], np.log(115 / 105))

    def test_regime_return_means_are_fractional_and_preserve_empty_periods(self):
        """Compute the figure's mean from eligible returns and keep empty periods missing."""
        panel = sample_minutes({"cb_usd": [100.0, 110.0, 121.0]})
        means = mean_absolute_returns(analyze_bases(panel))
        self.assertEqual(list(means.index), ["pre_event", "stress", "recovery"])
        self.assertTrue(pd.isna(means.at["pre_event", "cb_usd"]))
        self.assertAlmostEqual(means.at["stress", "cb_usd"], np.log(1.1))
