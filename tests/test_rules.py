"""Tests for rules module."""

import json
from pathlib import Path

from refcheck.rules import get_rules_path
from refcheck.rules import load_rules


class TestGetRulesPath:
    """Tests for get_rules_path function."""

    def test_mirrors_the_checkouts_absolute_path(self):
        """A `--` in a directory name cannot then make two checkouts share a file."""
        repos = Path.home() / '.local/state/refcheck/repos'

        assert get_rules_path(Path('/srv/dev/my--project')) == repos / 'srv/dev/my--project/rules.json'
        assert get_rules_path(Path('/srv/dev/my/project')) == repos / 'srv/dev/my/project/rules.json'

    def test_rules_are_read_under_the_xdg_state_home(self, temp_git_repo, tmp_path, monkeypatch):
        """HOME points elsewhere, so a path built from HOME finds nothing here."""
        state_home = tmp_path / 'xdg-state'
        monkeypatch.setenv('XDG_STATE_HOME', str(state_home))
        monkeypatch.setenv('HOME', str(tmp_path / 'home'))
        rules_path = get_rules_path(temp_git_repo)
        rules_path.parent.mkdir(parents=True)
        rules_path.write_text(json.dumps({'directory_mappings': {'old/': 'new/'}, 'file_mappings': {}}))

        rules, path = load_rules(temp_git_repo)

        assert path == rules_path
        assert path.is_relative_to(state_home)
        assert rules['directory_mappings'] == {'old/': 'new/'}


class TestLoadRules:
    """Tests for load_rules function."""

    def test_returns_empty_rules_when_no_file(self, temp_dir):
        rules, path = load_rules(temp_dir)

        assert rules == {'directory_mappings': {}, 'file_mappings': {}}
        assert path is None
