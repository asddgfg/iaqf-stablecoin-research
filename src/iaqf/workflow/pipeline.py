"""Run the five stages of the study and publish a completed set of products."""

import logging
from pathlib import Path
from tempfile import TemporaryDirectory

from iaqf.config import DATA_DIR, RESULTS_DIR
from iaqf.workflow.publication import publish_results
from iaqf.workflow.steps.acquire import acquire_inputs
from iaqf.workflow.steps.analyze import analyze_minutes
from iaqf.workflow.steps.prepare import prepare_tables
from iaqf.workflow.steps.report import create_report_outputs
from iaqf.workflow.steps.validate import validate_inputs

LOGGER = logging.getLogger(__name__)


def run_pipeline(
    data_dir: Path = DATA_DIR, output_dir: Path = RESULTS_DIR, *, offline: bool = False
) -> None:
    """Run acquisition, validation, alignment, analysis and reporting in order.

    The raw snapshots live outside the generated output tree. A failed data audit
    publishes a diagnostic CSV. Calculations and plots are staged before they can
    replace any earlier successful run.
    """
    data_dir, output_dir = Path(data_dir), Path(output_dir)
    LOGGER.info("1/5 Check market snapshots")
    acquire_inputs(data_dir, offline=offline)
    output_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output_dir, prefix=".iaqf-run-") as temp:
        staged = Path(temp)
        tables = staged / "tables"
        LOGGER.info("2/5 Validate UTC candles and data quality")
        audit = Path("tables") / "missing_report.csv"
        validate_inputs(data_dir, staged / audit, output_dir / audit)
        LOGGER.info("3/5 Align six markets and calculate price differences")
        prepared = prepare_tables(data_dir, tables)
        LOGGER.info("4/5 Calculate comparable-minute bases and fee thresholds")
        minutes = analyze_minutes(prepared, tables)
        LOGGER.info("5/5 Summarize periods and draw the eight report figures")
        create_report_outputs(minutes, tables, staged / "figures")
        publish_results(staged, output_dir)
    LOGGER.info("Study results written to %s", output_dir.resolve())
