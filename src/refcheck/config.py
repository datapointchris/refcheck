"""Configuration management for refcheck."""

import json
import os
import tomllib
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

from . import repository

REPO_CONFIG_NAME = '.refcheck.toml'

USER_CONFIG = 'user_config'
REPO_CONFIG = 'repo_config'


@dataclass(frozen=True)
class Key:
    """One setting refcheck reads, declared once.

    Reading and checking a file, its annotated example and `config show` are
    each built from these, so a new key is one record.
    """

    file: str
    table: str
    name: str
    reads_as: str
    default: str | tuple[str, ...]
    explanation: tuple[str, ...]

    @property
    def dotted(self) -> str:
        return f'{self.table}.{self.name}'


TIME_WINDOW = Key(
    USER_CONFIG,
    'learn',
    'time_window',
    'a string',
    '6 months',
    ("How far back `refcheck rules learn` reads git's rename history, in git log --since's terms.",),
)
EXCLUDE = Key(
    REPO_CONFIG,
    'scan',
    'exclude',
    'an array of strings',
    (),
    (
        'Globs matched against the repo-relative path, added to the built-in exclusions',
        '`refcheck config show` lists. `**` crosses directory separators. Name the',
        'directories this repo fills with generated output, such as test reports.',
    ),
)
KEYS = (TIME_WINDOW, EXCLUDE)


def tables_in(file: str) -> dict[str, dict[str, str]]:
    """Each table a config file may hold, with each key in it and what that key reads as."""
    tables: dict[str, dict[str, str]] = {}
    for key in KEYS:
        if key.file == file:
            tables.setdefault(key.table, {})[key.name] = key.reads_as
    return tables


@dataclass
class Config:
    """Settings from the user config and from the repository being checked.

    `set_by` names the file that set each key, by its dotted name. A key absent
    from it is at its default.
    """

    time_window: str = str(TIME_WINDOW.default)
    exclude: list[str] = field(default_factory=lambda: list(EXCLUDE.default))
    config_path: Path | None = None
    set_by: dict[str, str] = field(default_factory=dict)


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


EXAMPLE_HEADERS = {
    USER_CONFIG: "# refcheck's user config. `refcheck config show` names where it is read from.",
    REPO_CONFIG: f"# A repository's refcheck config, read from {REPO_CONFIG_NAME} at the repository's root.",
}


def config_example(file: str) -> str:
    """An annotated config file holding every key refcheck reads from it, each at its default."""
    lines = [EXAMPLE_HEADERS[file], '']
    for table in tables_in(file):
        lines.append(f'[{table}]')
        for key in KEYS:
            if key.file == file and key.table == table:
                lines.extend(f'# {line}' for line in key.explanation)
                lines.append(f'{key.name} = {json.dumps(key.default if isinstance(key.default, str) else list(key.default))}')
        lines.append('')
    return '\n'.join(lines)


def load_config(start: Path | None = None) -> Config:
    """Merge the per-user config with the repo config found from start.

    A file that is not there leaves its defaults. One that is there and cannot
    be taken as written raises ConfigError.
    """
    config = Config(config_path=find_repo_config(start or Path.cwd()))
    for file, path in ((USER_CONFIG, user_config_path()), (REPO_CONFIG, config.config_path)):
        if path is None:
            continue
        data = read_toml(path, tables_in(file))
        for key in KEYS:
            if key.file == file and key.name in data.get(key.table, {}):
                value = data[key.table][key.name]
                setattr(config, key.name, list(value) if isinstance(value, list) else value)
                config.set_by[key.dotted] = file
    return config
