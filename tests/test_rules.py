"""Tests for rules module."""

import json
from pathlib import Path

from refcheck.rules import get_repo_root
from refcheck.rules import get_rules_path
from refcheck.rules import load_rules


class TestGetRepoRoot:
    """Tests for get_repo_root function."""

    def test_returns_path_in_git_repo(self, temp_git_repo):
        subdir = temp_git_repo / 'subdir'
        subdir.mkdir()

        root = get_repo_root(subdir)
        # Resolve both paths to handle macOS /var -> /private/var symlink
        assert root.resolve() == temp_git_repo.resolve()

    def test_returns_none_outside_git_repo(self, temp_dir):
        result = get_repo_root(temp_dir)
        assert result is None


class TestGetRulesPath:
    """Tests for get_rules_path function."""

    def test_generates_safe_path(self):
        repo_root = Path('/Users/dev/dotfiles')
        rules_path = get_rules_path(repo_root)

        assert rules_path == Path.home() / '.config/refcheck/repos/Users--dev--dotfiles/rules.json'

    def test_handles_nested_paths(self):
        repo_root = Path('/home/user/projects/my-project')
        rules_path = get_rules_path(repo_root)

        assert 'home--user--projects--my-project' in str(rules_path)

    def test_rules_are_read_under_the_xdg_config_home(self, temp_git_repo, tmp_path, monkeypatch):
        """HOME points elsewhere, so a path built from HOME finds nothing here."""
        config_home = tmp_path / 'xdg-config'
        monkeypatch.setenv('XDG_CONFIG_HOME', str(config_home))
        monkeypatch.setenv('HOME', str(tmp_path / 'home'))
        safe_name = str(temp_git_repo.resolve()).lstrip('/').replace('/', '--')
        rules_path = config_home / 'refcheck' / 'repos' / safe_name / 'rules.json'
        rules_path.parent.mkdir(parents=True)
        rules_path.write_text(json.dumps({'directory_mappings': {'old/': 'new/'}, 'file_mappings': {}}))

        rules, path = load_rules(temp_git_repo)

        assert path == rules_path
        assert rules['directory_mappings'] == {'old/': 'new/'}


class TestLoadRules:
    """Tests for load_rules function."""

    def test_returns_empty_rules_when_no_file(self, temp_dir):
        rules, path = load_rules(temp_dir)

        assert rules == {'directory_mappings': {}, 'file_mappings': {}}
        assert path is None

    def test_loads_existing_rules(self, temp_git_repo, monkeypatch):
        config_dir = temp_git_repo / '.config' / 'refcheck'
        monkeypatch.setenv('HOME', str(temp_git_repo))

        # Use resolved path (git returns /private/var on macOS, not /var)
        resolved_repo = temp_git_repo.resolve()
        safe_name = str(resolved_repo).lstrip('/').replace('/', '--')
        repos_dir = config_dir / 'repos' / safe_name
        repos_dir.mkdir(parents=True)
        rules_path = repos_dir / 'rules.json'

        expected_rules = {
            '_metadata': {'generated': '2024-01-01T00:00:00'},
            'directory_mappings': {'old/': 'new/'},
            'file_mappings': {'foo.sh': 'bar.sh'},
        }
        rules_path.write_text(json.dumps(expected_rules))

        rules, path = load_rules(temp_git_repo)

        assert rules['directory_mappings'] == {'old/': 'new/'}
        assert rules['file_mappings'] == {'foo.sh': 'bar.sh'}
        assert path == rules_path
