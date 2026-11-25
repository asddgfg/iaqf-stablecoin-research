"""Rebuild the March 2023 BTC quote-currency study from six market snapshots."""

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from iaqf.config import DATA_DIR, RESULTS_DIR
from iaqf.workflow.pipeline import run_pipeline


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Read input/output directory overrides and the offline switch."""
    parser = argparse.ArgumentParser(prog="iaqf-study", description=__doc__)
    parser.add_argument(
        "--data-dir", default=DATA_DIR, type=Path, help="raw market CSVs"
    )
    parser.add_argument(
        "--output-dir",
        default=RESULTS_DIR,
        type=Path,
        help="results directory containing tables/ and figures/",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="use six local snapshots and never contact an exchange",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the requested workflow and return a shell-compatible exit status."""
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        run_pipeline(args.data_dir, args.output_dir, offline=args.offline)
    except (OSError, ValueError, RuntimeError) as error:
        logging.getLogger(__name__).error("%s", error)
        return 1
    return 0
