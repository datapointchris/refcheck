"""Configuration management for refcheck."""

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    """User configuration loaded from ~/.config/refcheck/config.toml."""

    time_window: str = "6 months"
    stale_threshold_days: int = 7
    show_no_rules_hint: bool = True


def parse_duration_to_days(duration: str) -> int:
    """
    Parse a human-readable duration string to days.

    Examples: "1 week" -> 7, "2 weeks" -> 14, "1 month" -> 30, "6 months" -> 180
    """
    duration = duration.strip().lower()

    match = re.match(r"(\d+)\s*(day|days|week|weeks|month|months)", duration)
    if not match:
        return 7

    value = int(match.group(1))
    unit = match.group(2)

    if unit.startswith("day"):
        return value
    elif unit.startswith("week"):
        return value * 7
    elif unit.startswith("month"):
        return value * 30

    return 7


def load_config() -> Config:
    """
    Load user configuration from ~/.config/refcheck/config.toml.

    Returns default config if file doesn't exist or can't be parsed.
    """
    config_path = Path.home() / ".config" / "refcheck" / "config.toml"
    config = Config()

    if not config_path.exists():
        return config

    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            return config

    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)

        learn = data.get("learn", {})
        if "time_window" in learn:
            config.time_window = learn["time_window"]

        warnings = data.get("warnings", {})
        if "stale_threshold" in warnings:
            config.stale_threshold_days = parse_duration_to_days(warnings["stale_threshold"])
        if "show_no_rules_hint" in warnings:
            config.show_no_rules_hint = warnings["show_no_rules_hint"]

    except Exception:
        pass

    return config
