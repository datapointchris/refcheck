"""Integration tests ported from bash test suite."""

import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import pytest


def run_refcheck(*args, cwd=None):
    """Run refcheck command and return result."""
    result = subprocess.run(
        ["refcheck", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return result


class TestBasicValidation:
    """Test 1: Basic validation (no flags)."""

    def test_finds_broken_references(self, test_fixtures):
        result = run_refcheck(cwd=test_fixtures)
        assert result.returncode == 1


class TestDirectoryFiltering:
    """Test 2: Directory filtering (positional argument)."""

    def test_checks_specific_directory(self, test_fixtures):
        result = run_refcheck("src/", cwd=test_fixtures)
        assert result.returncode == 1

    def test_passes_for_clean_directory(self, test_fixtures):
        result = run_refcheck("docs/", cwd=test_fixtures)
        assert result.returncode == 0

    def test_checks_single_file(self, test_fixtures):
        """Single file argument should be checked directly."""
        result = run_refcheck("src/broken-source.sh", cwd=test_fixtures)
        assert result.returncode == 1
        assert "nonexistent" in result.stdout

    def test_single_file_clean(self, test_fixtures):
        """Single clean file should pass."""
        result = run_refcheck("valid/clean.sh", cwd=test_fixtures)
        assert result.returncode == 0


class TestPatternChecking:
    """Test 3: Pattern checking."""

    def test_finds_old_pattern(self, test_fixtures):
        result = run_refcheck("--pattern", "management/tests/", cwd=test_fixtures)
        assert result.returncode == 1

    def test_finds_pattern_in_specific_dir(self, test_fixtures):
        result = run_refcheck("--pattern", "management/tests/", "src/", cwd=test_fixtures)
        assert result.returncode == 1

    def test_pattern_with_skip_docs(self, test_fixtures):
        result = run_refcheck(
            "--pattern", "management/tests/", "docs/", "--skip-docs", cwd=test_fixtures
        )
        assert result.returncode == 0


class TestPatternWithDescription:
    """Test 4: Pattern with description."""

    def test_accepts_pattern_description(self, test_fixtures):
        result = run_refcheck(
            "--pattern",
            "management/tests/",
            "--desc",
            "Update to tests/install/",
            cwd=test_fixtures,
        )
        assert result.returncode == 1


class TestTypeFiltering:
    """Test 5: Type filtering."""

    def test_filters_by_shell_scripts(self, test_fixtures):
        result = run_refcheck("--type", "sh", "src/", cwd=test_fixtures)
        assert result.returncode == 1

    def test_filters_by_python_files(self, test_fixtures):
        (test_fixtures / "src" / "test.py").write_text(
            "# Python file\nimport nonexistent_module\n"
        )
        result = run_refcheck("--type", "py", "src/", cwd=test_fixtures)
        assert result.returncode == 0


class TestSkipDocs:
    """Test 6: Skip docs flag."""

    def test_skip_docs_reduces_pattern_matches(self, test_fixtures):
        with_docs = run_refcheck("--pattern", "management/tests/", cwd=test_fixtures)
        without_docs = run_refcheck(
            "--pattern", "management/tests/", "--skip-docs", cwd=test_fixtures
        )

        with_count = with_docs.stdout.count("management/tests/")
        without_count = without_docs.stdout.count("management/tests/")

        assert without_count < with_count or without_count == 0


class TestCombinedFilters:
    """Test 7: Combined filters."""

    def test_type_and_skip_docs(self, test_fixtures):
        result = run_refcheck("--type", "sh", "--skip-docs", "src/", cwd=test_fixtures)
        assert result.returncode == 1

    def test_pattern_and_directory(self, test_fixtures):
        result = run_refcheck("--pattern", "management/tests/", "src/", cwd=test_fixtures)
        assert result.returncode == 1

    def test_all_filters(self, test_fixtures):
        result = run_refcheck(
            "--pattern",
            "management/tests/",
            "--type",
            "sh",
            "--skip-docs",
            "src/",
            cwd=test_fixtures,
        )
        assert result.returncode == 1


class TestValidReferences:
    """Test 8: Valid references should pass."""

    def test_passes_for_valid_refs(self, test_fixtures):
        result = run_refcheck("valid/", cwd=test_fixtures)
        assert result.returncode == 0


class TestSelfReferences:
    """Test 9: Self-references in comments should be ignored."""

    def test_ignores_self_references(self, test_fixtures):
        result = run_refcheck("src/self-ref.sh", cwd=test_fixtures)
        assert result.returncode == 0
        assert "self-ref.sh" not in result.stdout or "Missing" not in result.stdout


class TestExitCodes:
    """Test 10: Exit codes."""

    def test_exit_0_for_valid(self, test_fixtures):
        result = run_refcheck("valid/", cwd=test_fixtures)
        assert result.returncode == 0

    def test_exit_1_for_broken(self, test_fixtures):
        result = run_refcheck("src/", cwd=test_fixtures)
        assert result.returncode == 1


class TestHelpFlag:
    """Test 11: Help flag."""

    def test_shows_help(self):
        result = run_refcheck("--help")
        assert result.returncode == 0
        assert "refcheck" in result.stdout


class TestRealWorldDotfiles:
    """Test 12: Real-world usage on dotfiles."""

    def test_validates_management_directory(self, dotfiles_dir):
        if dotfiles_dir is None:
            pytest.skip("Dotfiles directory not found")

        result = run_refcheck("management/", cwd=dotfiles_dir)
        assert result.returncode == 0

    def test_validates_apps_directory(self, dotfiles_dir):
        if dotfiles_dir is None:
            pytest.skip("Dotfiles directory not found")

        result = run_refcheck("apps/", "--type", "sh", cwd=dotfiles_dir)
        assert result.returncode == 0


class TestVariablePathResolution:
    """Test 13: Variable path resolution."""

    def test_detects_broken_variable_references(self, dotfiles_dir):
        if dotfiles_dir is None:
            pytest.skip("Dotfiles directory not found")

        fixtures_dir = dotfiles_dir / "tests" / "apps" / "fixtures" / "refcheck-variables"
        if not fixtures_dir.exists():
            pytest.skip("Test fixtures not found")

        result = run_refcheck("--test-mode", str(fixtures_dir), cwd=dotfiles_dir)
        assert result.returncode == 1

    def test_shows_variable_resolution(self, dotfiles_dir):
        if dotfiles_dir is None:
            pytest.skip("Dotfiles directory not found")

        fixtures_dir = dotfiles_dir / "tests" / "apps" / "fixtures" / "refcheck-variables"
        if not fixtures_dir.exists():
            pytest.skip("Test fixtures not found")

        result = run_refcheck("--test-mode", str(fixtures_dir), cwd=dotfiles_dir)
        assert "→" in result.stdout


class TestSuggestionFeature:
    """Test 14: Suggestion feature."""

    def test_shows_possible_matches(self, suggestion_fixtures):
        result = run_refcheck(str(suggestion_fixtures / "suggestions"), cwd=suggestion_fixtures)
        assert "Possible matches:" in result.stdout

    def test_shows_basename_match(self, suggestion_fixtures):
        result = run_refcheck(str(suggestion_fixtures / "suggestions"), cwd=suggestion_fixtures)
        assert "basename match" in result.stdout

    def test_shows_name_variant(self, suggestion_fixtures):
        result = run_refcheck(str(suggestion_fixtures / "suggestions"), cwd=suggestion_fixtures)
        assert "name variant" in result.stdout


class TestLearnRules:
    """Test 15: --learn-rules command."""

    def test_runs_learn_rules(self, dotfiles_dir):
        if dotfiles_dir is None:
            pytest.skip("Dotfiles directory not found")

        result = run_refcheck("--learn-rules", cwd=dotfiles_dir)
        assert result.returncode == 0

    def test_creates_rules_file(self, dotfiles_dir):
        if dotfiles_dir is None:
            pytest.skip("Dotfiles directory not found")

        run_refcheck("--learn-rules", cwd=dotfiles_dir)

        safe_name = str(dotfiles_dir).lstrip("/").replace("/", "--")
        rules_path = Path.home() / ".config" / "refcheck" / "repos" / safe_name / "rules.json"

        assert rules_path.exists()

    def test_rules_file_valid_json(self, dotfiles_dir):
        if dotfiles_dir is None:
            pytest.skip("Dotfiles directory not found")

        run_refcheck("--learn-rules", cwd=dotfiles_dir)

        safe_name = str(dotfiles_dir).lstrip("/").replace("/", "--")
        rules_path = Path.home() / ".config" / "refcheck" / "repos" / safe_name / "rules.json"

        rules = json.loads(rules_path.read_text())
        assert "directory_mappings" in rules
        assert "file_mappings" in rules


class TestConfigToml:
    """Test 16: config.toml support."""

    def test_custom_stale_threshold(self, dotfiles_dir, monkeypatch, tmp_path):
        if dotfiles_dir is None:
            pytest.skip("Dotfiles directory not found")

        config_dir = tmp_path / ".config" / "refcheck"
        config_dir.mkdir(parents=True)
        monkeypatch.setenv("HOME", str(tmp_path))

        (config_dir / "config.toml").write_text(
            '[warnings]\nstale_threshold = "30 days"\n'
        )

        safe_name = str(dotfiles_dir).lstrip("/").replace("/", "--")
        repos_dir = config_dir / "repos" / safe_name
        repos_dir.mkdir(parents=True)

        old_date = (datetime.now() - timedelta(days=15)).isoformat()[:19]
        rules = {
            "_metadata": {"generated": old_date},
            "directory_mappings": {},
            "file_mappings": {},
        }
        (repos_dir / "rules.json").write_text(json.dumps(rules))

        result = run_refcheck("--no-warn", cwd=dotfiles_dir)
        assert "Rules last updated" not in result.stdout

    def test_show_no_rules_hint_disabled(self, dotfiles_dir, monkeypatch, tmp_path):
        if dotfiles_dir is None:
            pytest.skip("Dotfiles directory not found")

        config_dir = tmp_path / ".config" / "refcheck"
        config_dir.mkdir(parents=True)
        monkeypatch.setenv("HOME", str(tmp_path))

        (config_dir / "config.toml").write_text("[warnings]\nshow_no_rules_hint = false\n")

        result = run_refcheck("--no-warn", cwd=dotfiles_dir)
        assert "No learned rules found" not in result.stdout


class TestStaleRulesWarning:
    """Test stale rules warning."""

    def test_shows_stale_warning(self, dotfiles_dir, monkeypatch, tmp_path):
        if dotfiles_dir is None:
            pytest.skip("Dotfiles directory not found")

        config_dir = tmp_path / ".config" / "refcheck"
        config_dir.mkdir(parents=True)
        monkeypatch.setenv("HOME", str(tmp_path))

        safe_name = str(dotfiles_dir).lstrip("/").replace("/", "--")
        repos_dir = config_dir / "repos" / safe_name
        repos_dir.mkdir(parents=True)

        old_date = "2020-01-01T00:00:00"
        rules = {
            "_metadata": {"generated": old_date},
            "directory_mappings": {},
            "file_mappings": {},
        }
        (repos_dir / "rules.json").write_text(json.dumps(rules))

        result = run_refcheck("--no-warn", cwd=dotfiles_dir)
        assert "Rules last updated" in result.stdout
        assert "days ago" in result.stdout

    def test_no_warning_for_fresh_rules(self, dotfiles_dir, monkeypatch, tmp_path):
        if dotfiles_dir is None:
            pytest.skip("Dotfiles directory not found")

        config_dir = tmp_path / ".config" / "refcheck"
        config_dir.mkdir(parents=True)
        monkeypatch.setenv("HOME", str(tmp_path))

        safe_name = str(dotfiles_dir).lstrip("/").replace("/", "--")
        repos_dir = config_dir / "repos" / safe_name
        repos_dir.mkdir(parents=True)

        now = datetime.now().isoformat()[:19]
        rules = {
            "_metadata": {"generated": now},
            "directory_mappings": {},
            "file_mappings": {},
        }
        (repos_dir / "rules.json").write_text(json.dumps(rules))

        result = run_refcheck("--no-warn", cwd=dotfiles_dir)
        assert "Rules last updated" not in result.stdout
