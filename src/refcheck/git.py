"""The one place refcheck runs git, and reads the path lists it prints.

Every git call in the package goes through `run`, so a timeout, a changed
environment or a test stub has one place to attach. Each caller decides what a
failure means for its own question, so `run` raises rather than interpreting.
"""

import re
import subprocess
from collections.abc import Iterator
from pathlib import Path

# A status letter, then the similarity score a rename or a copy carries.
STATUS = re.compile(r'[ABCDMRTUX]\d*')


def name_status(output: str) -> Iterator[tuple[str, str, str | None]]:
    """Each (status, path, new path) in the output of `--name-status -z`.

    Read NUL-delimited, because without -z git C-quotes any path holding a
    non-ASCII byte, a quote or a backslash, and the quoted form names no file.
    A rename or a copy carries the path it left and the one it took; every
    other status carries one path and None. Any other field, such as the
    commit header `git log` writes ahead of a commit's files, comes back as the
    path with an empty status.
    """
    fields = [field.lstrip('\n') for field in output.split('\0')]
    index = 0
    while index < len(fields):
        status = fields[index]
        if STATUS.fullmatch(status) and status[0] in 'RC' and index + 2 < len(fields):
            yield status, fields[index + 1], fields[index + 2]
            index += 3
        elif STATUS.fullmatch(status) and index + 1 < len(fields):
            yield status, fields[index + 1], None
            index += 2
        else:
            if status:
                yield '', status, None
            index += 1


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
