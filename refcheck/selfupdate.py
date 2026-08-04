"""Version reporting and self-update against GitHub releases.

The reporting format is copied from `pyselfupdate.typercmd.run_update` rather
than imported: that module pulls in typer, and refcheck's CLI is argparse. A
fleet that reports the same thing three different ways is a fleet you have to
read carefully, so the strings stay identical.
"""

import importlib.metadata
import json
import sys

from pyselfupdate import Config
from pyselfupdate import SelfUpdateError
from pyselfupdate import changelog
from pyselfupdate import check
from pyselfupdate import update

CONFIG = Config(tool='refcheck', owner='datapointchris')


def installed_version() -> str:
    try:
        return importlib.metadata.version('refcheck')
    except importlib.metadata.PackageNotFoundError:
        return 'unknown'


def installed_commit() -> str | None:
    """The git commit refcheck was built from, when uv installed it from a VCS ref."""
    try:
        distribution = importlib.metadata.distribution('refcheck')
        direct_url = distribution.read_text('direct_url.json')
        if direct_url:
            return json.loads(direct_url).get('vcs_info', {}).get('commit_id')
    except Exception:
        return None
    return None


def print_version() -> None:
    commit = installed_commit()
    suffix = f' @ {commit[:8]}' if commit else ''
    print(f'refcheck {installed_version()}{suffix}')


def run_update(check_only: bool = False) -> int:
    try:
        result = check(CONFIG) if check_only else update(CONFIG)
    except SelfUpdateError as error:
        print(f'✗ refcheck update failed: {error}', file=sys.stderr)
        return 1

    if not result.update_available:
        print(f'✓ refcheck already at latest: {result.latest}')
        return 0

    if result.applied:
        print(f'✓ refcheck updated: {result.current} → {result.latest}')
    else:
        print(f'✓ refcheck update available: {result.current} → {result.latest}')

    subjects = changelog(CONFIG, result.current, result.latest)
    if subjects:
        print()
        print('Changes:')
        for subject in subjects:
            print(f'  • {subject}')

    # The environment this interpreter runs in has just been replaced, so
    # nothing further may be imported.
    sys.stdout.flush()
    return 0
