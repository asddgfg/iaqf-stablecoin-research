"""Step 5. Generate the regime summary and figures used by the Word/PDF report."""

from pathlib import Path

import pandas as pd

from iaqf.analysis import summarize_bases
from iaqf.reporting import make_plots_q1
from iaqf.utils.csv_io import atomic_write_csv


def create_report_outputs(
    minutes: pd.DataFrame, table_dir: Path, figure_dir: Path
) -> None:
    """Build the summary and the eight numbered figures from one analyzed panel."""
    atomic_write_csv(summarize_bases(minutes), table_dir / "q1_summary.csv")
    make_plots_q1(minutes, figure_dir)
