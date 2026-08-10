"""Configuration management for refcheck."""

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    """User configuration loaded from ~/.config/refcheck/config.toml."""

    time_window: str = '6 months'


def load_config() -> Config:
    """
    Load user configuration from ~/.config/refcheck/config.toml.

    Returns default config if file doesn't exist or can't be parsed.
    """
    config_path = Path.home() / '.config' / 'refcheck' / 'config.toml'
    config = Config()

    if not config_path.exists():
        return config

    try:
        with config_path.open('rb') as f:
            data = tomllib.load(f)

        learn = data.get('learn', {})
        if 'time_window' in learn:
            config.time_window = learn['time_window']

    except (OSError, tomllib.TOMLDecodeError, AttributeError, TypeError, ValueError):
        return config

    return config
