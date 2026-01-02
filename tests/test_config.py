"""Tests for config module."""

from pathlib import Path

import pytest

from refcheck.config import Config, load_config, parse_duration_to_days


class TestParseDurationToDays:
    """Tests for parse_duration_to_days function."""

    def test_days(self):
        assert parse_duration_to_days("1 day") == 1
        assert parse_duration_to_days("5 days") == 5
        assert parse_duration_to_days("30 days") == 30

    def test_weeks(self):
        assert parse_duration_to_days("1 week") == 7
        assert parse_duration_to_days("2 weeks") == 14
        assert parse_duration_to_days("4 weeks") == 28

    def test_months(self):
        assert parse_duration_to_days("1 month") == 30
        assert parse_duration_to_days("6 months") == 180
        assert parse_duration_to_days("12 months") == 360

    def test_whitespace_handling(self):
        assert parse_duration_to_days("  1 week  ") == 7
        assert parse_duration_to_days("2   weeks") == 14

    def test_case_insensitive(self):
        assert parse_duration_to_days("1 WEEK") == 7
        assert parse_duration_to_days("2 Months") == 60

    def test_invalid_returns_default(self):
        assert parse_duration_to_days("invalid") == 7
        assert parse_duration_to_days("") == 7
        assert parse_duration_to_days("abc days") == 7


class TestConfig:
    """Tests for Config dataclass."""

    def test_defaults(self):
        config = Config()
        assert config.time_window == "6 months"
        assert config.stale_threshold_days == 7
        assert config.show_no_rules_hint is True

    def test_custom_values(self):
        config = Config(
            time_window="1 year",
            stale_threshold_days=30,
            show_no_rules_hint=False,
        )
        assert config.time_window == "1 year"
        assert config.stale_threshold_days == 30
        assert config.show_no_rules_hint is False


class TestLoadConfig:
    """Tests for load_config function."""

    def test_no_config_file_returns_defaults(self, temp_dir, monkeypatch):
        monkeypatch.setenv("HOME", str(temp_dir))
        config = load_config()
        assert config.time_window == "6 months"
        assert config.stale_threshold_days == 7
        assert config.show_no_rules_hint is True

    def test_loads_time_window(self, config_dir):
        config_file = config_dir / "config.toml"
        config_file.write_text('[learn]\ntime_window = "3 months"\n')

        config = load_config()
        assert config.time_window == "3 months"

    def test_loads_stale_threshold(self, config_dir):
        config_file = config_dir / "config.toml"
        config_file.write_text('[warnings]\nstale_threshold = "30 days"\n')

        config = load_config()
        assert config.stale_threshold_days == 30

    def test_loads_show_no_rules_hint(self, config_dir):
        config_file = config_dir / "config.toml"
        config_file.write_text("[warnings]\nshow_no_rules_hint = false\n")

        config = load_config()
        assert config.show_no_rules_hint is False

    def test_loads_full_config(self, config_dir):
        config_file = config_dir / "config.toml"
        config_file.write_text(
            '[learn]\n'
            'time_window = "1 year"\n'
            "\n"
            "[warnings]\n"
            'stale_threshold = "2 weeks"\n'
            "show_no_rules_hint = false\n"
        )

        config = load_config()
        assert config.time_window == "1 year"
        assert config.stale_threshold_days == 14
        assert config.show_no_rules_hint is False

    def test_invalid_toml_returns_defaults(self, config_dir):
        config_file = config_dir / "config.toml"
        config_file.write_text("this is not valid toml {{{")

        config = load_config()
        assert config.time_window == "6 months"
