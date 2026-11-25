"""Step 3. Align raw candles once and write the two preparation products."""

from pathlib import Path

from iaqf.analysis import overview_from_dataset, prepare_q1_dataset
from iaqf.utils.csv_io import atomic_write_csv


def prepare_tables(data_dir: Path, table_dir: Path) -> Path:
    """Write the overview and full aligned dataset, returning the analysis input."""
    aligned = prepare_q1_dataset(data_dir)
    # Both exports must use identical positive-volume and UTC alignment rules.
    # Deriving the overview from this panel also avoids reading six files twice.
    atomic_write_csv(overview_from_dataset(aligned), table_dir / "basis_output.csv")
    return atomic_write_csv(aligned, table_dir / "q1_basis_dataset.csv")
