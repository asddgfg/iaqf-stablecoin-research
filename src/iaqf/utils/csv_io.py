"""Publish a complete dataframe to a CSV on the local filesystem."""

from pathlib import Path
from tempfile import NamedTemporaryFile

import pandas as pd


def atomic_write_csv(frame: pd.DataFrame, path: str | Path) -> Path:
    """Publish a CSV without its index and return the destination path.

    The temporary file is on the same filesystem as its destination. A failed
    serialization therefore leaves an earlier successful run available.
    """
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        dir=destination.parent, prefix=f".{destination.name}.", delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        # Windows requires the temporary handle to be closed before replacement.
        frame.to_csv(temporary_path, index=False)
        temporary_path.replace(destination)
    finally:
        temporary_path.unlink(missing_ok=True)
    return destination
