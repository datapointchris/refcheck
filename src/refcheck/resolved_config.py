"""Every value refcheck resolves before a run, and the layer that set it, as `refcheck config show` prints them.

A key appears once per layer that contributes to it, so `scan.exclude` has a
row for each built-in list and one for the repo's own. A row with an empty
value is printed rather than dropped: an absent row reads the same as a layer
that does not exist.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from . import repository
from .checker import ReferenceChecker
from .config import REPO_CONFIG_NAME
from .config import USER_CONFIG_TABLES
from .config import load_config
from .config import read_toml
from .config import user_config_path
from .rules import get_rules_path
from .scan_scope import CARGO_BUILD_DIR


@dataclass(frozen=True)
class Resolved:
    """One value, the layer that set it, and what a reader should know about it, such as a file not being there."""

    key: str
    value: str | list[str] | None
    layer: str
    note: str | None = None


def from_environment(variable: str, fallback: str) -> str:
    return f'${variable}' if os.environ.get(variable) else f'{fallback}, as ${variable} is unset'


def resolved_config(start: Path) -> list[Resolved]:
    """The rows for a run started in start. Raises ConfigError where a config file cannot be taken as written."""
    config = load_config(start)
    user_config = user_config_path()
    learn = read_toml(user_config, USER_CONFIG_TABLES).get('learn', {})
    repo_root = repository.root(start)
    rules_file = get_rules_path(repo_root) if repo_root is not None else None

    if rules_file is None:
        rules_note: str | None = 'no git repository holds this directory, so it has none'
    else:
        rules_note = None if rules_file.exists() else "not learned yet: 'refcheck rules learn' writes it"

    return [
        Resolved(
            'user_config',
            str(user_config),
            from_environment('XDG_CONFIG_HOME', '~/.config'),
            None if user_config.exists() else 'not there, so every key it holds is at its default',
        ),
        Resolved(
            'repo_config',
            str(config.config_path) if config.config_path else None,
            f'the nearest {REPO_CONFIG_NAME} at or above {start}, stopping at the git root',
            None if config.config_path else "none found: 'refcheck config example repo' starts one",
        ),
        Resolved('learn.time_window', config.time_window, 'user_config' if 'time_window' in learn else 'the default'),
        Resolved('rules_file', str(rules_file) if rules_file else None, from_environment('XDG_STATE_HOME', '~/.local/state'), rules_note),
        Resolved('scan.exclude', sorted(ReferenceChecker.DEFAULT_EXCLUDES), 'built-in directory names'),
        Resolved('scan.exclude', [CARGO_BUILD_DIR], 'built-in build output'),
        Resolved('scan.exclude', list(ReferenceChecker.DEFAULT_EXCLUDE_PATTERNS), 'built-in patterns'),
        Resolved('scan.exclude', list(ReferenceChecker.TEST_FIXTURE_PATTERNS), 'built-in recorded fixtures, which check --test-mode reads'),
        Resolved('scan.exclude', config.exclude, 'repo_config'),
    ]
