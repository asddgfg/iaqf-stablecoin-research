"""Publish a completed study run while preserving unrelated or previous results."""

import hashlib
import os
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory, gettempdir


@contextmanager
def publication_lock(destination: Path) -> Iterator[None]:
    """Serialize local publishers targeting the same resolved results directory.

    The OS releases the lock when the handle closes, even after a process exit.
    Its identifying file stays in the system temp directory, outside the study.
    """
    identity = os.path.normcase(str(destination.resolve())).encode("utf-8")
    digest = hashlib.sha256(identity).hexdigest()
    lock_path = Path(gettempdir()) / f"iaqf-publish-{digest}.lock"
    with lock_path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield


def publish_results(staged: Path, destination: Path) -> None:
    """Replace only staged tables and figures, rolling back a failed replacement.

    Staging takes place on the destination filesystem so each Path.replace is
    atomic. Readers opening multiple files should do so after the CLI finishes.
    """
    files = sorted(
        path.relative_to(staged)
        for group in ("tables", "figures")
        for path in (staged / group).glob("*")
        if path.is_file()
    )
    destination.mkdir(parents=True, exist_ok=True)
    with publication_lock(destination), TemporaryDirectory(dir=staged) as temp:
        backup_dir = Path(temp)
        # Complete all backups first. A permission or disk-space error here
        # leaves the previously published run intact.
        for relative in files:
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                backup = backup_dir / relative
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)

        published = []
        try:
            for relative in files:
                (staged / relative).replace(destination / relative)
                published.append(relative)
        except BaseException:
            # Include interrupts: clean up new files and restore exactly the
            # files this run replaced, keeping any user's extra outputs intact.
            for relative in reversed(published):
                target, backup = destination / relative, backup_dir / relative
                if backup.exists():
                    backup.replace(target)
                else:
                    target.unlink()
            raise
