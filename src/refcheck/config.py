"""Configuration management for refcheck."""

import os
import tomllib
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

from . import repository

REPO_CONFIG_NAME = '.refcheck.toml'


@dataclass
class Config:
    """Settings from the user config and from the repository being checked."""

    time_window: str = '6 months'
    exclude: list[str] = field(default_factory=list)
    config_path: Path | None = None


def user_config_dir() -> Path:
    """refcheck's directory under `$XDG_CONFIG_HOME`, or under ~/.config when that is unset."""
    base = os.environ.get('XDG_CONFIG_HOME')
    root = Path(base) if base else Path.home() / '.config'
    return root / 'refcheck'


def user_state_dir() -> Path:
    """refcheck's directory under `$XDG_STATE_HOME`, or under ~/.local/state when that is unset.

    The learned rules live here: refcheck writes them, nobody edits them, and
    deleting them changes what a run suggests rather than costing a recompute.
    """
    base = os.environ.get('XDG_STATE_HOME')
    root = Path(base) if base else Path.home() / '.local' / 'state'
    return root / 'refcheck'


def user_config_path() -> Path:
    """Where the per-user config lives."""
    return user_config_dir() / 'config.toml'


def find_repo_config(start: Path) -> Path | None:
    """The nearest .refcheck.toml at or above start, no further than the git root.

    Exclusions belong to a repository rather than to a person, because a
    directory that records history in one tree is ordinary content in another:
    a generated snapshot directory is history where a tool writes it and a
    hand-written one somewhere else. Putting them in the user config would
    silence a path across every repo on the machine.

    The walk stops at the repository's root so a checkout never inherits the
    config of whatever encloses it. A file sitting in the root itself is still
    read, because the directory is tested before it is judged to be the root.
    """
    current = start.resolve()
    top = repository.root(current)
    for directory in (current, *current.parents):
        candidate = directory / REPO_CONFIG_NAME
        if candidate.is_file():
            return candidate
        if directory == top:
            return None
    return None


class ConfigError(Exception):
    """A config file refcheck could not take as written, and the file it was."""

    def __init__(self, path: Path, message: str):
        super().__init__(message)
        self.path = path


USER_CONFIG_TABLES = {'learn': {'time_window': 'a string'}}
REPO_CONFIG_TABLES = {'scan': {'exclude': 'an array of strings'}}

READS_AS = {
    'a string': lambda value: isinstance(value, str),
    'an array of strings': lambda value: isinstance(value, list) and all(isinstance(item, str) for item in value),
}


def toml_kind(value: object) -> str:
    """What TOML calls a parsed value's type."""
    match value:
        case bool():
            return 'a boolean'
        case str():
            return 'a string'
        case int():
            return 'an integer'
        case float():
            return 'a float'
        case list():
            return 'an array'
        case dict():
            return 'a table'
        case _:
            return 'a date or time'


def read_toml(path: Path, tables: dict[str, dict[str, str]]) -> dict[str, dict]:
    """A config file's tables, checked against what refcheck reads from it. An absent file is empty.

    Anything else it cannot take as written raises ConfigError. Running on the
    defaults instead would scan what a repo declared excluded, or read history
    from a window nobody asked for, and the run would look like every other.
    """
    try:
        with path.open('rb') as handle:
            data = tomllib.load(handle)
    except FileNotFoundError:
        return {}
    except OSError as error:
        raise ConfigError(path, f'{path} could not be read: {error.strerror}') from error
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(path, f'{path} is not TOML: {error}') from error

    for table, body in data.items():
        if table not in tables:
            raise ConfigError(path, f'unknown table "{table}" in {path}; known tables: {", ".join(tables)}')
        if not isinstance(body, dict):
            raise ConfigError(path, f'"{table}" in {path} is {toml_kind(body)}; refcheck reads a table there')
        for key, value in body.items():
            expected = tables[table].get(key)
            if expected is None:
                known = ', '.join(tables[table])
                raise ConfigError(path, f'unknown key "{table}.{key}" in {path}; known keys: {known}')
            if not READS_AS[expected](value):
                raise ConfigError(path, f'"{table}.{key}" in {path} is {toml_kind(value)}; refcheck reads {expected} there')
    return data


def user_config_example() -> str:
    """An annotated user config holding every key refcheck reads from it, each at its default."""
    return '\n'.join(
        [
            "# refcheck's user config. `refcheck config show` names where it is read from.",
            '',
            '[learn]',
            "# How far back `refcheck rules learn` reads git's rename history, in git log --since's terms.",
            f'time_window = "{Config().time_window}"',
            '',
        ]
    )


def repo_config_example() -> str:
    """An annotated repo config holding every key refcheck reads from it, each at its default."""
    return '\n'.join(
        [
            f"# A repository's refcheck config, read from {REPO_CONFIG_NAME} at the repository's root.",
            '',
            '[scan]',
            '# Globs matched against the repo-relative path, added to the built-in exclusions',
            '# `refcheck config show` lists. `**` crosses directory separators. Name the',
            '# directories this repo fills with generated output, such as test reports.',
            f'exclude = {Config().exclude}',
            '',
        ]
    )


def load_config(start: Path | None = None) -> Config:
    """Merge the per-user config with the repo config found from start.

    A file that is not there leaves its defaults. One that is there and cannot
    be taken as written raises ConfigError.
    """
    config = Config()

    learn = read_toml(user_config_path(), USER_CONFIG_TABLES).get('learn', {})
    config.time_window = learn.get('time_window', config.time_window)

    repo_config = find_repo_config(start or Path.cwd())
    if repo_config is None:
        return config

    config.config_path = repo_config
    config.exclude = list(read_toml(repo_config, REPO_CONFIG_TABLES).get('scan', {}).get('exclude', []))

    return config
