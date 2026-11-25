"""Exercise the public workflow and CLI on isolated, deterministic candles."""

import csv
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from iaqf.cli import main
from iaqf.data.downloader import DataDownloader
from iaqf.workflow.pipeline import run_pipeline

MARKETS = (
    "binanceus_BTC_USDC.csv",
    "binanceus_BTC_USDT.csv",
    "bitstamp_BTC_USD.csv",
    "bitstamp_BTC_USDC.csv",
    "coinbase_BTC_USD.csv",
    "coinbase_BTC_USDC.csv",
)


def write_snapshots(directory: Path) -> None:
    """Write three UTC minutes in the timestamp formats used by historical exports."""
    directory.mkdir(parents=True)
    timestamps = (
        "2023-03-01T00:00:00Z",
        "2023-02-28 19:01:00-05:00",
        "2023-03-01T00:02:00.000+00:00",
    )
    for filename in MARKETS:
        is_usdc = filename == "bitstamp_BTC_USDC.csv"
        price = 101 if is_usdc else 100
        with (directory / filename).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(
                ("datetime", "timestamp", "open", "high", "low", "close", "volume")
            )
            for minute, stamp in enumerate(timestamps):
                # Only the Bitstamp USDC book has an inactive last minute. The
                # BTC close still exists, but it cannot establish a matched trade.
                volume = int(not (is_usdc and minute == 2))
                epoch_ms = 1_677_628_800_000 + minute * 60_000
                writer.writerow((stamp, epoch_ms, price, price, price, price, volume))


class WorkflowTests(unittest.TestCase):
    """Verify selective acquisition, validation, data flow, and publication."""

    def setUp(self) -> None:
        """Give each workflow its own raw snapshots and output directory."""
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.data = Path(temp.name) / "data" / "raw"
        self.results = Path(temp.name) / "results"
        self.tables = self.results / "tables"
        self.figures = self.results / "figures"
        write_snapshots(self.data)

    def test_offline_fails_before_opening_an_exchange(self) -> None:
        """Report all missing markets while the exchange adapter remains unused."""
        absent = [MARKETS[0], MARKETS[-1]]
        for name in absent:
            (self.data / name).unlink()
        with patch.object(
            DataDownloader, "__init__", side_effect=AssertionError
        ) as client:
            with self.assertRaises(FileNotFoundError) as caught:
                run_pipeline(self.data, self.results, offline=True)
        for name in absent:
            self.assertIn(name, str(caught.exception))
        client.assert_not_called()

    def test_partial_cache_requests_only_the_missing_pair(self) -> None:
        """Resume the absent pair and leave previously downloaded inputs unchanged."""
        missing = self.data / "bitstamp_BTC_USD.csv"
        missing.unlink()
        cached = {path: path.read_bytes() for path in self.data.iterdir()}
        # Stop at the network boundary. The test observes the selected pair
        # without contacting a venue or requiring an installed exchange client.
        with (
            patch.object(DataDownloader, "__init__", return_value=None) as client,
            patch.object(
                DataDownloader, "fetch_pair", side_effect=ConnectionError("offline")
            ) as fetch,
            self.assertRaises(ConnectionError),
        ):
            run_pipeline(self.data, self.results, offline=False)
        client.assert_called_once()
        self.assertEqual(client.call_args.args[0], "bitstamp")
        fetch.assert_called_once_with("BTC/USD")
        self.assertEqual(
            {path: path.read_bytes() for path in self.data.iterdir()}, cached
        )

    def test_cli_rebuilds_tables_and_figures_from_raw_data(self) -> None:
        """Replace a stale table, preserve input bytes, and generate all published products."""
        self.tables.mkdir(parents=True)
        detail = self.tables / "q1_analysis_output.csv"
        detail.write_text("obsolete result", encoding="utf-8")
        original = {path: path.read_bytes() for path in self.data.iterdir()}
        args = [
            "--offline",
            "--data-dir",
            str(self.data),
            "--output-dir",
            str(self.results),
        ]
        with patch.object(
            DataDownloader, "__init__", side_effect=AssertionError
        ) as client:
            self.assertEqual(main(args), 0)
        client.assert_not_called()
        self.assertEqual(
            {path: path.read_bytes() for path in self.data.iterdir()}, original
        )
        self.assertEqual(
            {p.name for p in self.results.iterdir()}, {"tables", "figures"}
        )
        self.assertEqual(
            {path.name for path in self.tables.iterdir()},
            {
                "basis_output.csv",
                "missing_report.csv",
                "q1_analysis_output.csv",
                "q1_basis_dataset.csv",
                "q1_summary.csv",
            },
        )
        charts = sorted(self.figures.glob("q1_plot*.jpg"))
        self.assertEqual(len(charts), 8)
        for chart in charts:
            with chart.open("rb") as stream:
                self.assertEqual(stream.read(2), b"\xff\xd8", chart.name)
        with detail.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        bitstamp = [row["pct_basis_usdc_usd_bitstamp"] for row in rows]
        observed = [float(value) for value in bitstamp if value]
        self.assertEqual(len(observed), 2)
        for basis in observed:
            self.assertAlmostEqual(basis, 0.01)
        self.assertEqual(bitstamp[-1], "")

    def test_validation_reports_ambiguous_minutes_before_analysis(self) -> None:
        """A duplicate input minute must leave a diagnostic report and no new analysis."""
        path = self.data / MARKETS[0]
        repeated = path.read_text(encoding="utf-8").splitlines()[-1]
        with path.open("a", encoding="utf-8") as stream:
            stream.write(repeated + "\n")
        with self.assertRaisesRegex(ValueError, path.stem):
            run_pipeline(self.data, self.results, offline=True)
        report = self.tables / "missing_report.csv"
        with report.open(encoding="utf-8", newline="") as stream:
            market = next(
                row for row in csv.DictReader(stream) if row["file"] == path.name
            )
        self.assertEqual(int(market["duplicate_datetimes"]), 1)
        self.assertFalse((self.tables / "q1_analysis_output.csv").exists())

    def test_plot_failure_preserves_previously_published_results(self) -> None:
        """Keep the prior table and chart intact if rendering fails before publication."""
        self.tables.mkdir(parents=True)
        self.figures.mkdir()
        marker = self.tables / "q1_analysis_output.csv"
        chart = self.figures / "q1_plot1_usdt_vs_usd_cost_band.jpg"
        marker.write_bytes(b"previous detailed results")
        chart.write_bytes(b"previous plot")
        with (
            patch(
                "matplotlib.figure.Figure.savefig",
                side_effect=RuntimeError("plot failure"),
            ),
            self.assertRaisesRegex(RuntimeError, "plot failure"),
        ):
            run_pipeline(self.data, self.results, offline=True)
        self.assertEqual(marker.read_bytes(), b"previous detailed results")
        self.assertEqual(chart.read_bytes(), b"previous plot")
        self.assertFalse((self.tables / "q1_basis_dataset.csv").exists())
