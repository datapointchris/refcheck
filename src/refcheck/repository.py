"""Which repository holds a path, and which checkout of it other repos name.

A directory is in a repository when it or a parent holds a `.git` entry: a
directory in a main checkout, a file in a linked worktree or a submodule. That
entry is the marker git's own discovery looks for, so reading it gives git's
answer without a process. It also answers about the directory asked, where
`git rev-parse` would answer about whatever repository `GIT_DIR` names inside
a hook.
"""

import os
import subprocess
from pathlib import Path

from . import git


class UnknownMainCheckout(Exception):
    """git could not say which repository a checkout belongs to."""


def main_checkout(checkout: Path) -> Path:
    """The main checkout of the repository a checkout belongs to, with symlinks walked out.

    A linked worktree's main checkout is the directory every other repo's
    paths name, and it still holds what the worktree's change moved until the
    change lands. git's common directory is the main checkout's `.git`, so its
    parent is the answer. A main checkout is its own.

    Raises UnknownMainCheckout where git cannot say, because guessing the
    checkout itself would hide every reference to the main one.
    """
    try:
        common = Path(git.run(['rev-parse', '--path-format=absolute', '--git-common-dir'], cwd=checkout).strip())
    except subprocess.CalledProcessError as error:
        raise UnknownMainCheckout(error.stderr.strip() or str(error)) from error
    except FileNotFoundError as error:
        raise UnknownMainCheckout('git is not installed') from error
    if common.name == '.git':
        return Path(os.path.realpath(common.parent))
    return Path(os.path.realpath(checkout))


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
