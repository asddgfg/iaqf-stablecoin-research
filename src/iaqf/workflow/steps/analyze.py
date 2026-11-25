"""Step 4. Produce the reproducible per-minute analysis table."""

from pathlib import Path

import pandas as pd

from iaqf.analysis import analyze_bases, read_prepared_dataset
from iaqf.utils.csv_io import atomic_write_csv


def analyze_minutes(prepared_path: Path, table_dir: Path) -> pd.DataFrame:
    """Analyze the saved aligned table and return the same minutes used for plotting."""
    # Starting at this CSV also permits another researcher to reproduce the
    # detailed table from a saved intermediate with the same parsing semantics.
    minutes = analyze_bases(read_prepared_dataset(prepared_path))
    atomic_write_csv(minutes, table_dir / "q1_analysis_output.csv")
    return minutes
