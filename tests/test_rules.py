"""Tests for rules module."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from refcheck.rules import get_repo_root, get_rules_age_days, get_rules_path, load_rules


class TestGetRepoRoot:
    """Tests for get_repo_root function."""

    def test_returns_path_in_git_repo(self, temp_git_repo):
        subdir = temp_git_repo / "subdir"
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
        repo_root = Path("/Users/chris/dotfiles")
        rules_path = get_rules_path(repo_root)

        assert rules_path == Path.home() / ".config/refcheck/repos/Users--chris--dotfiles/rules.json"

    def test_handles_nested_paths(self):
        repo_root = Path("/home/user/projects/my-project")
        rules_path = get_rules_path(repo_root)

        assert "home--user--projects--my-project" in str(rules_path)


class TestLoadRules:
    """Tests for load_rules function."""

    def test_returns_empty_rules_when_no_file(self, temp_dir):
        rules, path = load_rules(temp_dir)

        assert rules == {"directory_mappings": {}, "file_mappings": {}}
        assert path is None

    def test_loads_existing_rules(self, temp_git_repo, monkeypatch):
        config_dir = temp_git_repo / ".config" / "refcheck"
        monkeypatch.setenv("HOME", str(temp_git_repo))

        # Use resolved path (git returns /private/var on macOS, not /var)
        resolved_repo = temp_git_repo.resolve()
        safe_name = str(resolved_repo).lstrip("/").replace("/", "--")
        repos_dir = config_dir / "repos" / safe_name
        repos_dir.mkdir(parents=True)
        rules_path = repos_dir / "rules.json"

        expected_rules = {
            "_metadata": {"generated": "2024-01-01T00:00:00"},
            "directory_mappings": {"old/": "new/"},
            "file_mappings": {"foo.sh": "bar.sh"},
        }
        rules_path.write_text(json.dumps(expected_rules))

        rules, path = load_rules(temp_git_repo)

        assert rules["directory_mappings"] == {"old/": "new/"}
        assert rules["file_mappings"] == {"foo.sh": "bar.sh"}
        assert path == rules_path


class TestGetRulesAgeDays:
    """Tests for get_rules_age_days function."""

    def test_returns_none_for_no_metadata(self):
        rules = {"directory_mappings": {}, "file_mappings": {}}
        assert get_rules_age_days(rules) is None

    def test_returns_none_for_no_generated(self):
        rules = {"_metadata": {}}
        assert get_rules_age_days(rules) is None

    def test_returns_age_in_days(self):
        yesterday = (datetime.now() - timedelta(days=1)).isoformat()[:19]
        rules = {"_metadata": {"generated": yesterday}}

        age = get_rules_age_days(rules)
        assert age == 1

    def test_returns_zero_for_today(self):
        now = datetime.now().isoformat()[:19]
        rules = {"_metadata": {"generated": now}}

        age = get_rules_age_days(rules)
        assert age == 0

    def test_handles_old_dates(self):
        old_date = (datetime.now() - timedelta(days=100)).isoformat()[:19]
        rules = {"_metadata": {"generated": old_date}}

        age = get_rules_age_days(rules)
        assert age == 100

    def test_handles_invalid_date(self):
        rules = {"_metadata": {"generated": "not-a-date"}}
        assert get_rules_age_days(rules) is None
