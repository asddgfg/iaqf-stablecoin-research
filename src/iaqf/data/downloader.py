"""Retrieve historical one-minute candles through a reusable CCXT venue client."""

from pathlib import Path

from iaqf.config import (
    DATA_DIR,
    END_DATE,
    LIMIT,
    MINUTE_MS,
    START_DATE,
    TIMEFRAME,
    market_filename,
)
from iaqf.data.candles import regularize_candles
from iaqf.utils.csv_io import atomic_write_csv
from iaqf.utils.time import minute_bounds


class DataDownloader:
    """Fetch and atomically publish complete historical snapshots for one venue."""

    def __init__(
        self, exchange_name: str, data_dir: str | Path = DATA_DIR, *, exchange=None
    ):
        """Reuse a rate-limited client, optionally substituting an offline test client."""
        if exchange is None:
            # Import on demand so local runs can use the cache without CCXT.
            import ccxt

            if exchange_name not in ccxt.exchanges:
                raise ValueError(f"Unknown CCXT exchange: {exchange_name}")
            exchange = getattr(ccxt, exchange_name)({"enableRateLimit": True})
        self.exchange = exchange
        self.exchange_name = exchange_name
        self.data_dir = Path(data_dir)

    def _fetch_window(self, symbol: str, start: int, end: int) -> list:
        """Request consecutive bounded pages, retaining rows in each requested window."""
        rows = []
        # Advance by the requested time span even when a venue returns no ticks.
        # A thin order book may resume trading after one or more empty pages.
        for since in range(start, end + MINUTE_MS, LIMIT * MINUTE_MS):
            last = min(since + (LIMIT - 1) * MINUTE_MS, end)
            limit = (last - since) // MINUTE_MS + 1
            page = self.exchange.fetch_ohlcv(
                symbol,
                timeframe=TIMEFRAME,
                since=since,
                limit=limit,
                params={"until": last + MINUTE_MS - 1},
            )
            window_rows = [row for row in page if since <= row[0] <= last]
            if page and not window_rows:
                raise ValueError(
                    f"{self.exchange_name} {symbol} returned candles outside "
                    f"the requested window beginning at {since} ms"
                )
            rows.extend(window_rows)
        return rows

    def fetch_pair(
        self, symbol: str, start_date: str = START_DATE, end_date: str = END_DATE
    ) -> Path:
        """Download an inclusive window and return the published market CSV path.

        Exchange, pagination and validation errors propagate before the
        destination is replaced, so a previous snapshot remains readable.
        """
        start, end = minute_bounds(start_date, end_date)
        destination = self.data_dir / market_filename(self.exchange_name, symbol)
        rows = self._fetch_window(symbol, start, end)
        frame = regularize_candles(rows, start, end)
        return atomic_write_csv(frame, destination)
