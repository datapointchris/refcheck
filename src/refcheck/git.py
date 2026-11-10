"""The one place refcheck runs git.

Every git call in the package goes through `run`, so a timeout, a changed
environment or a test stub has one place to attach. Each caller decides what a
failure means for its own question, so `run` raises rather than interpreting.
"""

import subprocess
from pathlib import Path


def run(args: list[str], cwd: Path | None = None) -> str:
    """Run `git` with these arguments and return its stdout.

    Raises subprocess.CalledProcessError on a non-zero exit, with git's stderr
    attached, and FileNotFoundError where git is not installed.
    """
    result = subprocess.run(
        ['git', *args],
        capture_output=True,
        text=True,
        check=True,
        cwd=cwd,
    )
    return result.stdout
