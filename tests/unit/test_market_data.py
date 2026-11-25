"""Offline regression tests for venue pagination, data quality, and safe writes."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

import pandas as pd

from iaqf.config import LIMIT, MINUTE_MS, PAIRS, default_project_dir, market_filename
from iaqf.data.downloader import DataDownloader
from iaqf.data.validation import STRUCTURAL_ERRORS, DataValidator
from iaqf.utils.csv_io import atomic_write_csv
from iaqf.utils.time import iso_to_millis, minute_bounds

START = "2023-03-01T00:00:00Z"
START_MS = iso_to_millis(START)


def candle(minute: int, close: float = 101.0, volume: float = 3.0) -> list:
    """Create a non-flat exchange candle at a given offset from the sample start."""
    return [START_MS + minute * MINUTE_MS, close, close + 2, close - 2, close, volume]


def minute_date(minute: int) -> str:
    """Express a minute offset as a timezone-aware study endpoint."""
    return (pd.Timestamp(START) + pd.Timedelta(minutes=minute)).isoformat()


class TimeWindowTests(TestCase):
    """Check time conversion independently from the machine's local timezone."""

    def test_timezone_offsets_and_fractional_milliseconds(self):
        """Preserve absolute time across offsets and represent a millisecond exactly."""
        self.assertEqual(iso_to_millis("2023-02-28T19:00:00-05:00"), START_MS)
        self.assertEqual(iso_to_millis("1970-01-01T00:00:00.001Z"), 1)

    def test_invalid_time_bounds(self):
        """Reject local times, reversed ranges and non-minute boundaries."""
        for start, end in (
            ("2023-03-01T00:00:00", START),
            (minute_date(1), START),
            (START, "2023-03-01T00:00:01Z"),
            (START, "2023-03-01T00:00:00.000001Z"),
        ):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                minute_bounds(start, end)


class StudyDirectoryTests(TestCase):
    """Verify where a checkout and a wheel find the user's raw data and results."""

    def test_source_tree_and_installed_wheel_directories(self):
        """Find the checkout from its project marker and use the launch directory for wheels."""
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            (root / "pyproject.toml").touch()
            source = root / "src" / "iaqf" / "config.py"
            installed = root / "site-packages" / "iaqf" / "config.py"
            for module_path, expected in ((source, root), (installed, Path.cwd())):
                with (
                    self.subTest(module_path=module_path),
                    patch("iaqf.config.__file__", str(module_path)),
                ):
                    self.assertEqual(default_project_dir(), expected)


class MarketDataTests(TestCase):
    """Exercise the pipeline's disk entry points with in-memory API replies."""

    def setUp(self):
        """Provide a separate cache and exchange client for every test."""
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.exchange = Mock()
        self.downloader = DataDownloader("coinbase", self.root, exchange=self.exchange)
        self.path = self.root / "coinbase_BTC_USD.csv"

    def test_pagination_crosses_empty_page_and_includes_last_minute(self):
        """Handle overlap, reversed row order, an empty window and an inclusive end."""
        last = LIMIT * 2
        self.exchange.fetch_ohlcv.side_effect = [
            [candle(3), candle(1, 102, 0), candle(1, 102, 0), candle(-1)],
            [],
            [candle(last, 111)],
        ]
        path = self.downloader.fetch_pair("BTC/USD", START, minute_date(last))
        frame = pd.read_csv(path)
        calls = [call.kwargs for call in self.exchange.fetch_ohlcv.call_args_list]
        self.assertEqual([c["limit"] for c in calls], [LIMIT, LIMIT, 1])
        for i, kwargs in enumerate(calls):
            self.assertEqual(kwargs["since"], START_MS + i * LIMIT * MINUTE_MS)
            self.assertEqual(
                kwargs["params"]["until"],
                kwargs["since"] + kwargs["limit"] * MINUTE_MS - 1,
            )

        self.assertEqual(len(frame), last + 1)
        self.assertEqual(frame.index[frame.is_observed].tolist(), [1, 3, last])
        self.assertTrue(pd.isna(frame.loc[0, "close"]))
        self.assertEqual(frame.loc[1, "volume"], 0)
        flat_prices = frame.loc[2, ["open", "high", "low", "close"]].tolist()
        self.assertEqual(flat_prices, [102] * 4)
        self.assertEqual(frame.loc[2, "volume"], 0)
        self.assertEqual(frame.loc[last, "timestamp"], START_MS + last * MINUTE_MS)

        report = DataValidator(START, minute_date(last)).check_file(path)
        self.assertEqual(report["observed_rows"], 3)
        self.assertEqual(report["synthetic_rows"], last - 2)
        self.assertEqual(report["invalid_price_rows"], 1)
        self.assertTrue(all(report[key] == 0 for key in STRUCTURAL_ERRORS))

    def test_single_minute_window_requests_one_candle(self):
        """Retrieve a one-minute window even when the end equals the start."""
        self.exchange.fetch_ohlcv.return_value = [candle(0)]
        self.downloader.fetch_pair("BTC/USD", START, START)
        self.assertEqual(self.exchange.fetch_ohlcv.call_args.kwargs["limit"], 1)
        self.assertEqual(pd.read_csv(self.path).at[0, "timestamp"], START_MS)

    def test_request_failure_preserves_preexisting_cache(self):
        """Propagate a second-page error without publishing a partially filled grid."""
        self.path.write_bytes(b"original")
        self.exchange.fetch_ohlcv.side_effect = [
            [candle(0)],
            ConnectionError("offline"),
        ]
        with self.assertRaisesRegex(ConnectionError, "offline"):
            self.downloader.fetch_pair("BTC/USD", START, minute_date(LIMIT))
        self.assertEqual(self.path.read_bytes(), b"original")

    def test_invalid_pages_cannot_replace_a_good_cache(self):
        """Reject unavailable history, stale windows, conflicts and corrupt OHLCV."""
        self.path.write_bytes(b"original")
        for page in (
            [],
            [candle(-1)],
            [candle(0), candle(0, close=105)],
            [candle(0, volume=-1)],
            [candle(0, close=float("inf"))],
            [[START_MS, 101, 99, 98, 100, 1]],
            [[START_MS + 1, 101, 102, 100, 101, 1]],
        ):
            with self.subTest(page=page), self.assertRaises(ValueError):
                self.exchange.fetch_ohlcv.return_value = page
                self.downloader.fetch_pair("BTC/USD", START, minute_date(1))
            self.assertEqual(self.path.read_bytes(), b"original")

    def test_atomic_write_failure_discards_the_temporary_file(self):
        """A failed CSV serialization must keep the previous complete output."""
        self.path.write_bytes(b"original")
        broken = Mock()
        broken.to_csv.side_effect = OSError("full disk")
        with self.assertRaisesRegex(OSError, "full disk"):
            atomic_write_csv(broken, self.path)
        self.assertEqual(list(self.root.iterdir()), [self.path])
        self.assertEqual(self.path.read_bytes(), b"original")

    def test_validator_distinguishes_duplicates_gaps_and_an_invalid_clock(self):
        """Report missing minutes even when duplicates leave the row count unchanged."""
        self.exchange.fetch_ohlcv.return_value = [candle(0), candle(1), candle(2)]
        path = self.downloader.fetch_pair("BTC/USD", START, minute_date(2))
        frame = pd.read_csv(path)
        frame.loc[1, "datetime"] = frame.loc[0, "datetime"]
        frame.loc[2, "datetime"] = "2023-03-01 00:03:30+00:00"
        frame.loc[2, "close"] = -1
        frame.loc[2, "volume"] = -1
        frame["is_observed"] = [" true ", " FALSE ", "bad"]
        frame.to_csv(path, index=False)
        report = DataValidator(START, minute_date(2)).check_file(path)
        for column, expected in {
            "actual": 3,
            "expected": 3,
            "missing": 2,
            "duplicate_datetimes": 1,
            "outside_window": 1,
            "off_grid": 1,
            "timestamp_mismatches": 2,
            "invalid_candle_rows": 1,
            "invalid_volume_rows": 2,
            "invalid_flags": 1,
            "unknown_provenance_rows": 1,
        }.items():
            with self.subTest(column=column):
                self.assertEqual(report[column], expected)

    def test_validator_distinguishes_legacy_grid_from_observations(self):
        """Validate all six original-format files without guessing from zero volume."""
        self.exchange.fetch_ohlcv.return_value = [candle(0, volume=0)]
        path = self.downloader.fetch_pair("BTC/USD", START, START)
        frame = pd.read_csv(path).drop(columns="is_observed")
        for exchange, symbols in PAIRS.items():
            for symbol in symbols:
                frame.to_csv(self.root / market_filename(exchange, symbol), index=False)
        validator = DataValidator(START, START, data_dir=self.root)
        path = self.root / "audit.csv"
        report = validator.run(path)
        self.assertEqual(len(report), 6)
        self.assertTrue((report["unknown_provenance_rows"] == 1).all())
        self.assertTrue((report["observed_rows"] == 0).all())
        self.assertTrue((report["synthetic_rows"] == 0).all())
        self.assertTrue((report["zero_volume_rows"] == 1).all())
        pd.testing.assert_frame_equal(pd.read_csv(path), report)
