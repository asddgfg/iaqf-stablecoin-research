"""Regression test for a failed commit of staged research products."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from iaqf.workflow.publication import publish_results


def write_products(directory: Path, contents: dict[str, bytes]) -> None:
    """Materialize nested table and chart fixtures under one output directory."""
    for relative, payload in contents.items():
        path = directory / relative
        path.parent.mkdir(exist_ok=True, parents=True)
        path.write_bytes(payload)


class PublicationTests(unittest.TestCase):
    """Ensure users see their last successful run when publication fails."""

    def test_partial_replacement_restores_prior_products(self) -> None:
        """Roll back updated and newly created files while preserving unrelated work."""
        previous = {
            "figures/chart.jpg": b"old chart",
            "tables/detail.csv": b"old detail",
            "notes.txt": b"user's unrelated notes",
        }
        incoming = {
            "figures/chart.jpg": b"updated chart",
            "figures/new.jpg": b"new plot",
            "tables/detail.csv": b"updated detail",
            "tables/summary.csv": b"new summary",
        }
        with TemporaryDirectory() as temporary:
            staged = Path(temporary) / "staged"
            destination = Path(temporary) / "results"
            write_products(destination, previous)
            write_products(staged, incoming)
            replace = Path.replace
            attempts = []

            def fail_last_product(source: Path, target: Path) -> Path:
                """Interrupt the fourth stage-to-final move and allow recovery moves."""
                if source.is_relative_to(staged):
                    key = source.relative_to(staged).as_posix()
                    if key in incoming and Path(target) == destination / key:
                        attempts.append(key)
                        # Among the first three, at least one replaces an earlier
                        # result and one creates a new file in either traversal order.
                        if len(attempts) == len(incoming):
                            raise OSError("simulated publication failure")
                return replace(source, target)

            with (
                patch.object(Path, "replace", fail_last_product),
                self.assertRaisesRegex(OSError, "simulated publication failure"),
            ):
                publish_results(staged, destination)
            self.assertEqual(len(attempts), len(incoming))
            after = {
                path.relative_to(destination).as_posix(): path.read_bytes()
                for path in destination.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, previous)
