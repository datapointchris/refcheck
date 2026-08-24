"""Configuration management for refcheck."""

import os
import tomllib
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

REPO_CONFIG_NAME = '.refcheck.toml'


@dataclass
class Config:
    """Settings from the user config and from the repository being checked."""

    time_window: str = '6 months'
    exclude: list[str] = field(default_factory=list)
    config_path: Path | None = None


def user_config_path() -> Path:
    """Where the per-user config lives."""
    base = os.environ.get('XDG_CONFIG_HOME')
    root = Path(base) if base else Path.home() / '.config'
    return root / 'refcheck' / 'config.toml'


def find_repo_config(start: Path) -> Path | None:
    """The nearest .refcheck.toml at or above start, no further than the git root.

    Exclusions belong to a repository rather than to a person, because a
    directory that records history in one tree is ordinary content in another:
    a generated snapshot directory is history where a tool writes it and a
    hand-written one somewhere else. Putting them in the user config would
    silence a path across every repo on the machine.

    The walk stops at the git root so a checkout never inherits the config of
    whatever encloses it. A file sitting in the root itself is still read,
    because the directory is tested before it is judged to be the root.
    """
    current = start.resolve()
    for directory in (current, *current.parents):
        candidate = directory / REPO_CONFIG_NAME
        if candidate.is_file():
            return candidate
        if (directory / '.git').exists():
            return None
    return None


def _read_toml(path: Path) -> dict:
    """Parse a TOML file, treating anything unreadable as absent."""
    try:
        with path.open('rb') as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def load_config(start: Path | None = None) -> Config:
    """Merge the per-user config with the repo config found from start.

    Returns default config where a file is missing or cannot be parsed.
    """
    config = Config()

    learn = _read_toml(user_config_path()).get('learn')
    if isinstance(learn, dict) and isinstance(learn.get('time_window'), str):
        config.time_window = learn['time_window']

    repo_config = find_repo_config(start or Path.cwd())
    if repo_config is None:
        return config

    config.config_path = repo_config
    scan = _read_toml(repo_config).get('scan')
    if isinstance(scan, dict) and isinstance(scan.get('exclude'), list):
        config.exclude = [str(pattern) for pattern in scan['exclude']]

    return config
