"""Renames and deletions read from git, for the check a move leaves behind.

The question refcheck exists to answer is "what still points at the old name",
and until now it had to be asked by hand, with the old name typed in. git
already knows: a rename is staged as R, a deletion as D, and the old path is
right there in the changeset. Reading it at commit time is what makes the check
automatic, and it needs no stored state — unlike learned rules, which describe
moves already reconciled and go stale between runs.
"""

import subprocess
from pathlib import Path


class Move:
    """A path that moved or went away, and where it went."""

    def __init__(self, old: str, new: str | None):
        self.old = old
        self.new = new

    @property
    def description(self) -> str:
        return f'now {self.new}' if self.new else 'deleted in this change'

    @property
    def is_bare(self) -> bool:
        """No directory in front of the name, so the name is all there is."""
        return '/' not in self.old


def staged(repo_root: Path, include_bare_names: bool = False) -> list[Move]:
    """Renames and deletions in the git index — what a pre-commit hook sees."""
    return _read(['git', 'diff', '--cached', '--diff-filter=RD', '-M', '--name-status'], repo_root, include_bare_names)


def since(ref: str, repo_root: Path, include_bare_names: bool = False) -> list[Move]:
    """Renames and deletions between a ref and HEAD, for CI and manual runs."""
    return _read(['git', 'diff', '--diff-filter=RD', '-M', '--name-status', ref, 'HEAD'], repo_root, include_bare_names)


def _read(command: list[str], repo_root: Path, include_bare_names: bool = False) -> list[Move]:
    try:
        result = subprocess.run(  # nosec B603
            command,
            capture_output=True,
            text=True,
            check=True,
            cwd=repo_root,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

    moves = []
    for line in result.stdout.splitlines():
        fields = line.split('\t')
        status = fields[0]

        if status.startswith('R') and len(fields) == 3:
            old, new = fields[1], fields[2]
        elif status.startswith('D') and len(fields) == 2:
            old, new = fields[1], None
        else:
            continue

        # A bare filename is too generic to match on within this repo: `main.go`
        # appears in every Go repo's prose, and a substring check cannot tell
        # which one is meant. The directory is what makes a pattern specific
        # enough to be evidence.
        #
        # A sweep across other repos asks for them anyway, because there the
        # evidence is not the pattern. A consumer in another repo reaches this
        # file through an absolute path, and that path either exists or does
        # not — which settles it without the pattern carrying any weight. A
        # registry file renamed at a repo root has no directory in front of it,
        # so filtering bare names leaves such a sweep nothing to look for.
        if '/' not in old and not include_bare_names:
            continue

        # Moved away and back within one changeset, or replaced by a directory
        # of the same name. Nothing points at a name that is still there.
        if (repo_root / old).exists():
            continue

        moves.append(Move(old, new))

    return moves
