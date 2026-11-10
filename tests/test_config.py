"""Tests for config module."""

import pytest

from refcheck.config import REPO_CONFIG_NAME
from refcheck.config import REPO_CONFIG_TABLES
from refcheck.config import USER_CONFIG_TABLES
from refcheck.config import ConfigError
from refcheck.config import load_config
from refcheck.config import read_toml
from refcheck.config import repo_config_example
from refcheck.config import user_config_example


@pytest.mark.parametrize(('example', 'tables'), [(user_config_example, USER_CONFIG_TABLES), (repo_config_example, REPO_CONFIG_TABLES)])
def test_an_example_config_reads_back_with_every_key_its_file_holds(tmp_path, example, tables):
    path = tmp_path / 'example.toml'
    path.write_text(example())

    data = read_toml(path, tables)

    assert {table: set(body) for table, body in data.items()} == {table: set(body) for table, body in tables.items()}


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

    def test_a_user_config_that_is_not_toml_is_refused(self, config_dir):
        """Running on the defaults would look like every other run."""
        (config_dir / 'config.toml').write_text('this is not valid toml {{{')

        with pytest.raises(ConfigError, match='is not TOML'):
            load_config()


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

    def test_a_table_the_repo_config_does_not_hold_is_refused(self, tmp_path):
        """The history window is a person's setting, so a repo config naming it is a mistake."""
        (tmp_path / '.git').mkdir()
        (tmp_path / REPO_CONFIG_NAME).write_text('[learn]\ntime_window = "1 year"\n')

        with pytest.raises(ConfigError, match='unknown table "learn" .*; known tables: scan'):
            load_config(tmp_path)

    def test_an_exclusion_written_as_one_string_is_refused(self, tmp_path):
        (tmp_path / '.git').mkdir()
        (tmp_path / REPO_CONFIG_NAME).write_text('[scan]\nexclude = "build/**"\n')

        with pytest.raises(ConfigError, match='"scan.exclude" .* is a string; refcheck reads an array of strings there'):
            load_config(tmp_path)
