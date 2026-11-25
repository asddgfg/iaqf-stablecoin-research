"""Convert offset-aware dates into inclusive UTC minute windows."""

from datetime import datetime, timedelta, timezone

from iaqf.config import MINUTE_MS


def iso_to_millis(date_str: str) -> int:
    """Convert an offset-aware ISO 8601 timestamp to Unix milliseconds."""
    instant = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    if instant.utcoffset() is None:
        raise ValueError(f"A UTC offset is required: {date_str!r}")
    if instant.microsecond % 1000:
        raise ValueError(f"Sub-millisecond timestamp: {date_str!r}")

    # Integer arithmetic avoids rounding a millisecond into the adjacent candle.
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (instant - epoch) // timedelta(milliseconds=1)


def minute_bounds(start_date: str, end_date: str) -> tuple[int, int]:
    """Return inclusive epoch-ms bounds for a whole-minute study window."""
    start, end = iso_to_millis(start_date), iso_to_millis(end_date)
    if start > end or start % MINUTE_MS or end % MINUTE_MS:
        raise ValueError("Use whole-minute bounds with start_date <= end_date")
    return start, end
