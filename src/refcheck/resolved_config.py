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
from .config import KEYS
from .config import REPO_CONFIG_NAME
from .config import load_config
from .config import user_config_path
from .rules import get_rules_path
from .scan_scope import BUILTIN_LAYERS
from .scan_scope import BuiltinLayer


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
        Resolved('rules_file', str(rules_file) if rules_file else None, from_environment('XDG_STATE_HOME', '~/.local/state'), rules_note),
        *(builtin_row(layer) for layer in BUILTIN_LAYERS),
        *(Resolved(key.dotted, getattr(config, key.name), config.set_by.get(key.dotted, 'the default')) for key in KEYS),
    ]


def builtin_row(layer: BuiltinLayer) -> Resolved:
    """A built-in layer's exclusions, with what reads past it."""
    value = [layer.rule] if layer.rule else sorted(layer.directories) or list(layer.patterns)
    label = f'built-in {layer.name}, which check --test-mode reads' if layer.read_under_test_mode else f'built-in {layer.name}'
    return Resolved('scan.exclude', value, label)
