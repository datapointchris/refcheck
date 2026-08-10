"""Tests for config module."""

from refcheck.config import Config
from refcheck.config import load_config


class TestConfig:
    """Tests for Config dataclass."""

    def test_defaults(self):
        config = Config()
        assert config.time_window == '6 months'

    def test_custom_values(self):
        config = Config(time_window='1 year')
        assert config.time_window == '1 year'


class TestLoadConfig:
    """Tests for load_config function."""

    def test_no_config_file_returns_defaults(self, temp_dir, monkeypatch):
        monkeypatch.setenv('HOME', str(temp_dir))
        config = load_config()
        assert config.time_window == '6 months'

    def test_loads_time_window(self, config_dir):
        config_file = config_dir / 'config.toml'
        config_file.write_text('[learn]\ntime_window = "3 months"\n')

        config = load_config()
        assert config.time_window == '3 months'

    def test_loads_full_config(self, config_dir):
        config_file = config_dir / 'config.toml'
        config_file.write_text('[learn]\ntime_window = "1 year"\n')

        config = load_config()
        assert config.time_window == '1 year'

    def test_invalid_toml_returns_defaults(self, config_dir):
        config_file = config_dir / 'config.toml'
        config_file.write_text('this is not valid toml {{{')

        config = load_config()
        assert config.time_window == '6 months'
