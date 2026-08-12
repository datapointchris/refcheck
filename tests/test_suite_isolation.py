"""The suite runs inside a git hook, so it must not touch the repository running it."""

import os
import subprocess
import sys
from pathlib import Path


def a_repository_tracking_one_file(root: Path) -> Path:
    root.mkdir(parents=True)
    subprocess.run(['git', 'init'], cwd=root, capture_output=True, check=True)
    (root / 'tracked.txt').write_text('keep me\n')
    subprocess.run(['git', 'add', 'tracked.txt'], cwd=root, capture_output=True, check=True)
    subprocess.run(
        ['git', '-c', 'user.email=t@t', '-c', 'user.name=T', 'commit', '-m', 'init'],
        cwd=root,
        capture_output=True,
        check=True,
    )
    return root


def test_git_fixtures_leave_the_calling_repository_alone(tmp_path, pytestconfig):
    """A hook's GIT_DIR reached the fixtures, and one `git add` emptied the real index.

    pre-commit runs this suite with GIT_DIR and GIT_INDEX_FILE exported. Both
    beat directory discovery, so a fixture's `git init` reinitialized the
    repository being committed and its `git add` replaced that repository's
    index with the fixture's .gitkeep. Measured on a clone: 29 tracked files
    down to one, and the commit died building the tree.

    test_moves.py is the target because every one of its cases builds a
    repository, which is exactly the shape that did the damage.
    """
    host = a_repository_tracking_one_file(tmp_path / 'host')
    hook_environment = {name: value for name, value in os.environ.items() if not name.startswith('GIT_')}
    hook_environment['GIT_DIR'] = str(host / '.git')
    hook_environment['GIT_INDEX_FILE'] = str(host / '.git' / 'index')

    subprocess.run(
        [sys.executable, '-m', 'pytest', 'tests/test_moves.py', '-q', '-p', 'no:cacheprovider'],
        cwd=pytestconfig.rootpath,
        capture_output=True,
        env=hook_environment,
    )

    tracked = subprocess.run(['git', 'ls-files'], cwd=host, capture_output=True, text=True, check=True)
    assert tracked.stdout.split() == ['tracked.txt']
