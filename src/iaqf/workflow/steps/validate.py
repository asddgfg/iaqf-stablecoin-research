"""Step 2. Reject structurally invalid snapshots and retain the diagnostic table."""

from pathlib import Path

from iaqf.data.validation import STRUCTURAL_ERRORS, DataValidator
from iaqf.utils.csv_io import atomic_write_csv


def validate_inputs(data_dir: Path, staged_audit: Path, diagnostic_path: Path) -> None:
    """Stage a valid audit or expose its file-specific error counts on failure."""
    audit = DataValidator(data_dir=data_dir).run(output_path=staged_audit)
    # Sparse trading is meaningful in this study. Only the structural error
    # columns invalidate an input; zero-volume and coverage counts stay visible.
    damaged = audit.loc[audit[list(STRUCTURAL_ERRORS)].ne(0).any(axis=1), "file"]
    if not damaged.empty:
        atomic_write_csv(audit, diagnostic_path)
        raise ValueError(
            f"Invalid market data in {', '.join(map(str, damaged))}. See {diagnostic_path}"
        )
