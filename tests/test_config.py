"""Tests for config module."""

from refcheck.config import REPO_CONFIG_NAME
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


class TestRepoConfig:
    """Exclusions belong to the repository, not to whoever runs the check."""

    def test_exclusions_come_from_the_repo_config(self, tmp_path):
        (tmp_path / '.git').mkdir()
        (tmp_path / REPO_CONFIG_NAME).write_text('[scan]\nexclude = ["build/reports/**"]\n')

        config = load_config(tmp_path)

        assert config.exclude == ['build/reports/**']
        assert config.config_path == (tmp_path / REPO_CONFIG_NAME).resolve()

    def test_the_repo_config_is_found_from_a_subdirectory(self, tmp_path):
        """Narrowing the scan to a subdirectory reads the same declarations."""
        (tmp_path / '.git').mkdir()
        (tmp_path / REPO_CONFIG_NAME).write_text('[scan]\nexclude = ["out/**"]\n')
        nested = tmp_path / 'src' / 'deep'
        nested.mkdir(parents=True)

        assert load_config(nested).exclude == ['out/**']

    def test_the_walk_stops_at_the_git_root(self, tmp_path):
        """A checkout never inherits the config of whatever encloses it."""
        (tmp_path / REPO_CONFIG_NAME).write_text('[scan]\nexclude = ["outer/**"]\n')
        repo = tmp_path / 'repo'
        (repo / '.git').mkdir(parents=True)

        assert load_config(repo).exclude == []

    def test_no_repo_config_leaves_exclusions_empty(self, tmp_path):
        (tmp_path / '.git').mkdir()

        config = load_config(tmp_path)

        assert config.exclude == []
        assert config.config_path is None

    def test_invalid_repo_toml_leaves_exclusions_empty(self, tmp_path):
        (tmp_path / '.git').mkdir()
        (tmp_path / REPO_CONFIG_NAME).write_text('this is not valid toml {{{')

        assert load_config(tmp_path).exclude == []

    def test_a_config_without_a_scan_table_leaves_exclusions_empty(self, tmp_path):
        (tmp_path / '.git').mkdir()
        (tmp_path / REPO_CONFIG_NAME).write_text('[learn]\ntime_window = "1 year"\n')

        assert load_config(tmp_path).exclude == []
