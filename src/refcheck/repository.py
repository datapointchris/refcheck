"""Which repository holds a path.

A directory is in a repository when it or a parent holds a `.git` entry: a
directory in a main checkout, a file in a linked worktree or a submodule. That
entry is the marker git's own discovery looks for, so reading it gives git's
answer without a process. It also answers about the directory asked, where
`git rev-parse` would answer about whatever repository `GIT_DIR` names inside
a hook.
"""

import os
from pathlib import Path


def root(start: Path) -> Path | None:
    """The top of the repository holding start, in start's own form made absolute, or None outside one.

    Symlinks stay as written, so the answer compares against paths built from
    the same start. A caller wanting the physical directory resolves start first.
    """
    current = Path(os.path.abspath(start))
    for directory in (current, *current.parents):
        if (directory / '.git').exists():
            return directory
    return None
