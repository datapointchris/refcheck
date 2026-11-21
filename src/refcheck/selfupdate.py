"""Version reporting against GitHub releases.

Updating is `pyselfupdate.typercmd.run_update`, which the CLI calls directly.
The step order in that function is load-bearing -- everything that reaches the
network happens before the install -- so it is imported, never reimplemented.
"""

import importlib.metadata
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pyselfupdate


def update_config() -> 'pyselfupdate.Config':
    """What `update` installs and what the release notice compares against.

    One source, so the notice cannot name a release the update command would
    not install. Importing pyselfupdate loads the HTTP and TLS stack, so it is
    imported here, when an update path runs, rather than by every command."""
    # 444ms → 340ms on `refcheck --help`, 2026-11-21
    import pyselfupdate

    return pyselfupdate.Config(tool='refcheck', owner='datapointchris')


def installed_version() -> str:
    try:
        return importlib.metadata.version('refcheck')
    except importlib.metadata.PackageNotFoundError:
        return 'unknown'


def installed_commit() -> str | None:
    """The git commit refcheck was built from, when uv installed it from a VCS ref."""
    try:
        direct_url = importlib.metadata.distribution('refcheck').read_text('direct_url.json')
        recorded = json.loads(direct_url) if direct_url else {}
    except (importlib.metadata.PackageNotFoundError, OSError, ValueError):
        return None
    return recorded.get('vcs_info', {}).get('commit_id')


def print_version() -> None:
    commit = installed_commit()
    suffix = f' @ {commit[:8]}' if commit else ''
    print(f'refcheck {installed_version()}{suffix}')
