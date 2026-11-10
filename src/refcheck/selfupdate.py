"""Version reporting against GitHub releases.

Updating is `pyselfupdate.typercmd.run_update`, which the CLI calls directly.
The step order in that function is load-bearing -- everything that reaches the
network happens before the install -- so it is imported, never reimplemented.
"""

import importlib.metadata
import json

from pyselfupdate import Config

CONFIG = Config(tool='refcheck', owner='datapointchris')


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
