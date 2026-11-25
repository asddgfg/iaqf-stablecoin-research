"""Step 1. Identify missing snapshots and obtain them when online."""

import logging
from pathlib import Path

from iaqf.config import PAIRS, market_filename
from iaqf.data.downloader import DataDownloader


def missing_markets(data_dir: Path) -> dict[str, list[str]]:
    """Group absent pairs by exchange so each venue needs at most one client."""
    missing = {}
    for exchange, symbols in PAIRS.items():
        absent = [
            s
            for s in symbols
            if not (data_dir / market_filename(exchange, s)).is_file()
        ]
        if absent:
            missing[exchange] = absent
    return missing


def acquire_inputs(data_dir: Path, *, offline: bool) -> None:
    """Require a complete offline snapshot or download only the missing pairs."""
    missing = missing_markets(data_dir)
    if missing and offline:
        filenames = [
            market_filename(venue, pair)
            for venue, pairs in missing.items()
            for pair in pairs
        ]
        raise FileNotFoundError(
            f"Missing market files in {data_dir}: {', '.join(filenames)}"
        )
    for exchange, symbols in missing.items():
        downloader = DataDownloader(exchange, data_dir=data_dir)
        for symbol in symbols:
            logging.getLogger(__name__).info("Fetching %s %s", exchange, symbol)
            downloader.fetch_pair(symbol)
