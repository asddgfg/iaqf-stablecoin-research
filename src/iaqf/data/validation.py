"""Audit minute-grid coverage, OHLCV values and the provenance of market candles."""

from pathlib import Path

import numpy as np
import pandas as pd

from iaqf.config import (
    CANDLE_COLUMNS,
    DATA_DIR,
    END_DATE,
    MINUTE_MS,
    PAIRS,
    PRICE_COLUMNS,
    START_DATE,
    TABLES_DIR,
    market_filename,
)
from iaqf.data.candles import valid_ohlc
from iaqf.utils.csv_io import atomic_write_csv
from iaqf.utils.observations import observation_flags
from iaqf.utils.time import minute_bounds

# These defects invalidate price comparisons. Coverage counts, including genuine
# zero-volume minutes, stay descriptive so inactive books remain visible.
STRUCTURAL_ERRORS = (
    "duplicate_datetimes",
    "invalid_datetimes",
    "outside_window",
    "off_grid",
    "timestamp_mismatches",
    "invalid_volume_rows",
    "invalid_flags",
    "invalid_candle_rows",
)


def _audit_time_grid(
    dates: pd.Series, timestamps: pd.Series, expected: pd.DatetimeIndex
) -> dict[str, int]:
    """Count duplicate, missing, off-grid and inconsistent timestamp keys."""
    millis = pd.to_numeric(timestamps, errors="coerce")
    encoded_dates = pd.to_datetime(millis, unit="ms", utc=True, errors="coerce")
    valid_dates = dates.dropna()
    in_window = valid_dates.between(expected[0], expected[-1])
    return {
        "expected": len(expected),
        "actual": len(dates),
        # Compare timestamp sets: a duplicate and a gap can coexist at equal counts.
        "missing": len(expected.difference(valid_dates)),
        "duplicate_datetimes": int(valid_dates.duplicated().sum()),
        "invalid_datetimes": int(dates.isna().sum()),
        "outside_window": int((~in_window).sum()),
        "off_grid": int(valid_dates.ne(valid_dates.dt.floor("min")).sum()),
        "timestamp_mismatches": int((dates.isna() | dates.ne(encoded_dates)).sum()),
    }


def _provenance_masks(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Classify exchange, synthetic and unmarked rows without inferring from volume."""
    flags = pd.Series(pd.NA, index=frame.index, dtype="string")
    if "is_observed" in frame:
        flags = observation_flags(frame["is_observed"])
    observed = flags.eq("true").fillna(False)
    synthetic = flags.eq("false").fillna(False)
    return observed, synthetic, ~(observed | synthetic)


def _audit_candles(frame: pd.DataFrame, dates: pd.Series) -> dict[str, int]:
    """Count invalid OHLCV values and separate legacy coverage from observed rows."""
    prices = frame[PRICE_COLUMNS].apply(pd.to_numeric, errors="coerce")
    volume = pd.to_numeric(frame["volume"], errors="coerce")
    valid_prices = valid_ohlc(prices)
    observed, synthetic, unknown = _provenance_masks(frame)

    # Before the first quote there is no earlier close to carry forward. Four
    # blank prices with zero volume are a valid leading unobserved candle.
    first_price = dates[valid_prices].min()
    leading_gap = (
        (dates.lt(first_price) | pd.isna(first_price))
        & frame[PRICE_COLUMNS].isna().all(axis=1)
        & volume.eq(0)
        & ~observed
    )
    invalid_volume = ~np.isfinite(volume) | volume.lt(0) | (synthetic & volume.ne(0))
    return {
        "invalid_price_rows": int((~valid_prices).sum()),
        "invalid_candle_rows": int((~(valid_prices | leading_gap)).sum()),
        "invalid_volume_rows": int(invalid_volume.sum()),
        "zero_volume_rows": int(volume.eq(0).sum()),
        "observed_rows": int(observed.sum()),
        "synthetic_rows": int(synthetic.sum()),
        "unknown_provenance_rows": int(unknown.sum()),
        # Legacy files with no flag column have unknown provenance throughout.
        "invalid_flags": int(unknown.sum()) if "is_observed" in frame else 0,
    }


class DataValidator:
    """Validate all markets against the same inclusive study window."""

    def __init__(
        self,
        start_date: str = START_DATE,
        end_date: str = END_DATE,
        *,
        data_dir: str | Path = DATA_DIR,
    ):
        """Build the expected UTC minute grid and remember the raw data directory."""
        start, end = minute_bounds(start_date, end_date)
        self.full_index = pd.to_datetime(
            range(start, end + MINUTE_MS, MINUTE_MS), unit="ms", utc=True
        )
        self.data_dir = Path(data_dir)

    def check_file(self, filepath: str | Path) -> dict[str, str | int]:
        """Return a single-file audit, counting every raw row and every absent minute."""
        path = Path(filepath)
        frame = pd.read_csv(path)
        missing_columns = sorted(
            {"datetime", *CANDLE_COLUMNS}.difference(frame.columns)
        )
        if missing_columns:
            raise ValueError(f"{path.name} lacks required columns: {missing_columns}")

        dates = pd.to_datetime(
            frame["datetime"], utc=True, errors="coerce", format="mixed"
        )
        return {
            "file": path.name,
            **_audit_time_grid(dates, frame["timestamp"], self.full_index),
            **_audit_candles(frame, dates),
        }

    def run(
        self, output_path: str | Path = TABLES_DIR / "missing_report.csv"
    ) -> pd.DataFrame:
        """Audit every configured market, publish the sorted table and return it."""
        reports = [
            self.check_file(self.data_dir / market_filename(exchange, symbol))
            for exchange, symbols in PAIRS.items()
            for symbol in symbols
        ]
        report = pd.DataFrame(reports).sort_values("file", ignore_index=True)
        atomic_write_csv(report, output_path)
        return report
