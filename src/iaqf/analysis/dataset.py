"""Build one aligned panel for both the market overview and the published study."""

from pathlib import Path

import numpy as np
import pandas as pd

from iaqf.config import DATA_DIR, MARKETS
from iaqf.data.candles import valid_ohlc
from iaqf.utils.observations import observation_flags

from .comparisons import DATASET_COMPARISONS


def utc_minute_keys(values: pd.Series, source: str) -> pd.Series:
    """Parse UTC timestamps and reject missing, duplicated or subminute keys."""
    times = pd.to_datetime(values, utc=True, errors="raise", format="mixed")
    if times.isna().any() or times.duplicated().any():
        raise ValueError(f"{source}: missing or duplicate UTC timestamp")
    if not times.eq(times.dt.floor("min")).all():
        raise ValueError(f"{source}: timestamp outside the one-minute grid")
    return times


def traded_minutes(close: pd.Series, volume: pd.Series) -> pd.Series:
    """Select positive finite closes backed by positive finite minute volume."""
    return np.isfinite(volume) & volume.gt(0) & np.isfinite(close) & close.gt(0)


def _observed_minutes(flags: pd.Series, volume: pd.Series, path: Path) -> pd.Series:
    """Validate provenance labels before selecting candles supplied by a venue."""
    normalized = observation_flags(flags)
    if not normalized.isin(["true", "false"]).all():
        raise ValueError(f"{path}: invalid is_observed flag")
    if (normalized.eq("false") & volume.ne(0)).any():
        raise ValueError(f"{path}: synthetic candle without zero volume")
    return normalized.eq("true")


def _trade_range(candles: pd.DataFrame, traded: pd.Series) -> pd.Series:
    """Measure (high − low) / open for valid OHLC bars with a recorded trade."""
    ohlc = candles[["open", "high", "low", "close"]].apply(pd.to_numeric)
    # This is within-candle price dispersion. An order-book spread would
    # require simultaneous bid and ask observations.
    return (ohlc["high"] - ohlc["low"]) / ohlc["open"].where(traded & valid_ohlc(ohlc))


def load_pair(
    filename: str | Path,
    col_name: str,
    data_dir: str | Path = DATA_DIR,
    *,
    include_range: bool = False,
) -> pd.DataFrame:
    """Read a market snapshot and retain volume and eligible closes by minute.

    A zero-volume row may repeat a prior close. It keeps its timestamp but
    cannot contribute a new price. Historic snapshots lack is_observed, so
    the volume criterion applies independently of that optional column.
    """
    path = Path(data_dir) / filename
    required = {"datetime", "close", "volume"}
    if include_range:
        required.update(("open", "high", "low"))
    wanted = required | {"is_observed"}
    candles = pd.read_csv(path, usecols=wanted.__contains__)
    if candles.empty or not required.issubset(candles):
        raise ValueError(
            f"{path}: expected nonempty candle data with {sorted(required)}"
        )
    times = utc_minute_keys(candles["datetime"], str(path))
    close = pd.to_numeric(candles["close"], errors="raise")
    volume = pd.to_numeric(candles["volume"], errors="raise")
    traded = traded_minutes(close, volume)
    if "is_observed" in candles:
        traded &= _observed_minutes(candles["is_observed"], volume, path)
    frame = pd.DataFrame(
        {"datetime": times, col_name: close.where(traded), f"{col_name}_volume": volume}
    )
    if include_range:
        frame[f"{col_name}_range"] = _trade_range(candles, traded)
    return frame.sort_values("datetime", ignore_index=True)


def align_minutes(markets: list[pd.DataFrame]) -> pd.DataFrame:
    """Align independent markets on the complete UTC grid spanned by the inputs."""
    if not markets:
        raise ValueError("At least one market is required for alignment")
    series = [market.set_index("datetime") for market in markets]
    if any(not market.index.is_unique for market in series):
        raise ValueError("A market has duplicate UTC minutes")
    # An empty minute on Bitstamp must not discard a Binance.US/Coinbase pair.
    aligned = pd.concat(series, axis="columns", join="outer", sort=True)
    minutes = pd.date_range(aligned.index.min(), aligned.index.max(), freq="min")
    return aligned.reindex(minutes).rename_axis("datetime").reset_index()


def prepare_q1_dataset(data_dir: str | Path = DATA_DIR) -> pd.DataFrame:
    """Read each source once and return the aligned prices, volumes and pairwise bases."""
    markets = [
        load_pair(
            filename, name, data_dir, include_range=name in {"bs_usdc", "cb_usdc"}
        )
        for name, filename in MARKETS.items()
    ]
    frame = align_minutes(markets)
    for pair in DATASET_COMPARISONS:
        frame[pair.difference_column] = pair.price_difference(frame)
    return frame


def overview_from_dataset(dataset: pd.DataFrame) -> pd.DataFrame:
    """Build the overview from prepared closes without rereading source candles.

    Its two cross-venue columns use Coinbase BTC/USD and Coinbase BTC/USDC
    as the reference legs. The within-Binance.US comparison is in the Q1 table.
    """
    columns = {market: Path(filename).stem for market, filename in MARKETS.items()}
    overview = dataset[["datetime", *columns]].rename(columns=columns)
    overview["basis_USDT_USD"] = dataset["bu_usdt"] - dataset["cb_usd"]
    overview["basis_USDT_USDC"] = dataset["bu_usdt"] - dataset["cb_usdc"]
    return overview


def read_prepared_dataset(
    path: str | Path, raw_dir: str | Path | None = None
) -> pd.DataFrame:
    """Read a saved panel, rebuilding old volume-free panels from their raw candles.

    A caller can supply an explicit raw directory for restarts. When reading
    an archived flat project, its six source files live in the adjacent data folder.
    """
    path = Path(path)
    panel = pd.read_csv(path)
    required = {f"{name}_volume" for name in MARKETS} | {
        "cb_usdc_range",
        "bs_usdc_range",
    }
    if required.issubset(panel):
        return panel
    source = Path(raw_dir) if raw_dir is not None else path.parent / "data"
    if not all((source / name).is_file() for name in MARKETS.values()):
        raise ValueError(
            "The saved panel lacks volume/range columns; supply the six source candle files."
        )
    return prepare_q1_dataset(source)
