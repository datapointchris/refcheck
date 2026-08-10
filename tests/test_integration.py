"""Integration tests ported from bash test suite."""

import json
import subprocess
from datetime import datetime
from datetime import timedelta
from pathlib import Path

import pytest

from refcheck.checker import ReferenceChecker


def run_refcheck(*args, cwd=None):
    """Run refcheck command and return result."""
    result = subprocess.run(
        ['refcheck', *args],
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
        result = run_refcheck('src/', cwd=test_fixtures)
        assert result.returncode == 1

    def test_passes_for_clean_directory(self, test_fixtures):
        result = run_refcheck('docs/', cwd=test_fixtures)
        assert result.returncode == 0

    def test_checks_single_file(self, test_fixtures):
        """Single file argument should be checked directly."""
        result = run_refcheck('src/broken-source.sh', cwd=test_fixtures)
        assert result.returncode == 1
        assert 'nonexistent' in result.stdout

    def test_single_file_clean(self, test_fixtures):
        """Single clean file should pass."""
        result = run_refcheck('valid/clean.sh', cwd=test_fixtures)
        assert result.returncode == 0


class TestPatternChecking:
    """Test 3: Pattern checking."""

    def test_finds_old_pattern(self, test_fixtures):
        result = run_refcheck('--pattern', 'management/tests/', cwd=test_fixtures)
        assert result.returncode == 1

    def test_finds_pattern_in_specific_dir(self, test_fixtures):
        result = run_refcheck('--pattern', 'management/tests/', 'src/', cwd=test_fixtures)
        assert result.returncode == 1

    def test_pattern_with_skip_docs(self, test_fixtures):
        result = run_refcheck('--pattern', 'management/tests/', 'docs/', '--skip-docs', cwd=test_fixtures)
        assert result.returncode == 0


class TestPatternWithDescription:
    """Test 4: Pattern with description."""

    def test_accepts_pattern_description(self, test_fixtures):
        result = run_refcheck(
            '--pattern',
            'management/tests/',
            '--desc',
            'Update to tests/install/',
            cwd=test_fixtures,
        )
        assert result.returncode == 1


class TestTypeFiltering:
    """Test 5: Type filtering."""

    def test_filters_by_shell_scripts(self, test_fixtures):
        result = run_refcheck('--type', 'sh', 'src/', cwd=test_fixtures)
        assert result.returncode == 1

    def test_filters_by_python_files(self, test_fixtures):
        (test_fixtures / 'src' / 'test.py').write_text('# Python file\nimport nonexistent_module\n')
        result = run_refcheck('--type', 'py', 'src/', cwd=test_fixtures)
        assert result.returncode == 0


class TestSkipDocs:
    """Test 6: Skip docs flag."""

    def test_skip_docs_reduces_pattern_matches(self, test_fixtures):
        with_docs = run_refcheck('--pattern', 'management/tests/', cwd=test_fixtures)
        without_docs = run_refcheck('--pattern', 'management/tests/', '--skip-docs', cwd=test_fixtures)

        with_count = with_docs.stdout.count('management/tests/')
        without_count = without_docs.stdout.count('management/tests/')

        assert without_count < with_count or without_count == 0


class TestCombinedFilters:
    """Test 7: Combined filters."""

    def test_type_and_skip_docs(self, test_fixtures):
        result = run_refcheck('--type', 'sh', '--skip-docs', 'src/', cwd=test_fixtures)
        assert result.returncode == 1

    def test_pattern_and_directory(self, test_fixtures):
        result = run_refcheck('--pattern', 'management/tests/', 'src/', cwd=test_fixtures)
        assert result.returncode == 1

    def test_all_filters(self, test_fixtures):
        result = run_refcheck(
            '--pattern',
            'management/tests/',
            '--type',
            'sh',
            '--skip-docs',
            'src/',
            cwd=test_fixtures,
        )
        assert result.returncode == 1


class TestValidReferences:
    """Test 8: Valid references should pass."""

    def test_passes_for_valid_refs(self, test_fixtures):
        result = run_refcheck('valid/', cwd=test_fixtures)
        assert result.returncode == 0

    def test_filename_list_is_not_a_script_invocation(self, test_fixtures):
        """`for f in functions.sh aliases.sh` is a word list, not `sh aliases.sh`."""
        result = run_refcheck('valid/filename-list.sh', cwd=test_fixtures)
        assert result.returncode == 0
        assert 'aliases.sh' not in result.stdout

    def test_remote_execution_paths_are_not_local_references(self, test_fixtures):
        """A script run through pct exec or ssh lives on a filesystem we cannot see."""
        result = run_refcheck('valid/remote-exec.sh', cwd=test_fixtures)
        assert result.returncode == 0
        assert 'install.sh' not in result.stdout
        assert 'remote-only.sh' not in result.stdout

    def test_commented_source_is_not_flagged_as_fragile(self, test_fixtures):
        """A source in a usage comment has no working directory to be fragile about."""
        result = run_refcheck('valid/documented-usage.sh', cwd=test_fixtures)
        assert result.returncode == 0
        assert 'Fragile' not in result.stdout


class TestMarkdownReferences:
    """Docs carry the same references as code and must be resolved the same way."""

    def test_finds_stale_source_in_markdown(self, test_fixtures):
        """The regression: these checks globbed **/*.sh, so docs were never read."""
        result = run_refcheck('stale-docs/stale-source.md', cwd=test_fixtures)
        assert result.returncode == 1
        assert 'gone.sh' in result.stdout

    def test_finds_stale_script_invocation_in_markdown(self, test_fixtures):
        result = run_refcheck('stale-docs/stale-source.md', cwd=test_fixtures)
        assert 'also-gone.sh' in result.stdout

    def test_resolves_dotfiles_dir_in_markdown(self, test_fixtures):
        """Prose has no assignments to parse, so $DOTFILES_DIR must be seeded."""
        result = run_refcheck('docs/live-source.md', cwd=test_fixtures)
        assert result.returncode == 0
        assert 'helpers.sh' not in result.stdout

    def test_placeholders_are_not_reported(self, test_fixtures):
        """A how-to naming toolname.sh describes a file it never intended to ship."""
        result = run_refcheck('docs/placeholders.md', cwd=test_fixtures)
        assert result.returncode == 0
        for stand_in in ('toolname.sh', 'tool}-plugins.sh', 'my-library.sh', 'script.sh'):
            assert stand_in not in result.stdout

    def test_placeholder_stems_still_resolve_in_shell(self, test_fixtures):
        """`bash script.sh` is prose in a README and a real invocation in code."""
        result = run_refcheck('src/broken-script.sh', cwd=test_fixtures)
        assert result.returncode == 1
        assert 'script.sh' in result.stdout

    def test_skip_docs_excludes_markdown_references(self, test_fixtures):
        result = run_refcheck('stale-docs/stale-source.md', '--skip-docs', cwd=test_fixtures)
        assert result.returncode == 0

    def test_other_projects_trees_are_not_reported(self, test_fixtures):
        """Docs quote other people's layouts; none of it is a claim about this repo."""
        result = run_refcheck('docs/other-trees.md', cwd=test_fixtures)
        assert result.returncode == 0
        for foreign in ('child.sh', 'mylib_test.sh', 'deploy.sh'):
            assert foreign not in result.stdout

    def test_resource_is_not_a_source_statement(self, test_fixtures):
        """`resource "aws_lambda_function"` ends in `source "..."` without a boundary."""
        result = run_refcheck('docs/other-trees.md', cwd=test_fixtures)
        assert 'aws_lambda_function' not in result.stdout
        assert 'freshrss' not in result.stdout

    def test_rename_under_an_existing_directory_is_still_reported(self, test_fixtures):
        """The signal the tree rule must preserve: our directory, moved file."""
        result = run_refcheck('stale-docs/renamed-dir.md', cwd=test_fixtures)
        assert result.returncode == 1
        assert 'runner.sh' in result.stdout


class TestDocumentedInvocations:
    """A shell script explains itself in comments and usage strings."""

    def test_illustrated_invocations_are_not_reported(self, test_fixtures):
        result = run_refcheck('valid/documented-invocations.sh', cwd=test_fixtures)
        assert result.returncode == 0
        for illustrative in ('install.sh', 'run-and-summarize.sh', 'lib.sh'):
            assert illustrative not in result.stdout

    def test_documented_reference_under_an_existing_directory_is_still_reported(self, test_fixtures):
        """The signal the widened guard must preserve, in both contexts."""
        result = run_refcheck('stale-docs/documented-stale.sh', cwd=test_fixtures)
        assert result.returncode == 1
        assert result.stdout.count('valid/gone/runner.sh') == 2

    def test_a_real_invocation_is_still_a_real_invocation(self, test_fixtures):
        """Only the leading command decides; a script run after an echo still resolves."""
        script = test_fixtures / 'valid' / 'runs-after-echo.sh'
        script.write_text('#!/usr/bin/env bash\nbash valid/gone/runner.sh && echo done\n')
        result = run_refcheck('valid/runs-after-echo.sh', cwd=test_fixtures)
        assert result.returncode == 1
        assert 'runner.sh' in result.stdout


class TestMovesEndToEnd:
    """The question a move leaves behind, asked without naming the old path."""

    @staticmethod
    def _repo_with_a_staged_move(repo):
        (repo / 'lib').mkdir()
        (repo / 'lib' / 'helpers.sh').write_text('echo hi\n')
        (repo / 'deploy.yml').write_text('script: lib/helpers.sh\n')
        subprocess.run(['git', 'add', '-A'], cwd=repo, capture_output=True, check=True)
        subprocess.run(['git', 'commit', '-m', 'add helpers'], cwd=repo, capture_output=True, check=True)

        (repo / 'shared').mkdir()
        subprocess.run(['git', 'mv', 'lib/helpers.sh', 'shared/helpers.sh'], cwd=repo, capture_output=True, check=True)

    def test_finds_what_a_staged_rename_left_behind(self, temp_git_repo):
        self._repo_with_a_staged_move(temp_git_repo)

        result = run_refcheck('--moves', cwd=temp_git_repo)
        assert result.returncode == 1
        assert 'deploy.yml' in result.stdout
        assert 'now shared/helpers.sh' in result.stdout

    def test_says_nothing_when_the_references_were_updated(self, temp_git_repo):
        self._repo_with_a_staged_move(temp_git_repo)
        (temp_git_repo / 'deploy.yml').write_text('script: shared/helpers.sh\n')
        subprocess.run(['git', 'add', '-A'], cwd=temp_git_repo, capture_output=True, check=True)

        result = run_refcheck('--moves', cwd=temp_git_repo)
        assert result.returncode == 0

    def test_moves_is_off_unless_asked_for(self, temp_git_repo):
        self._repo_with_a_staged_move(temp_git_repo)

        result = run_refcheck(cwd=temp_git_repo)
        assert result.returncode == 0

    def test_changelog_entries_are_not_stale_references(self, temp_git_repo):
        """A changelog names where a file was when it shipped. That is the point of it."""
        self._repo_with_a_staged_move(temp_git_repo)
        (temp_git_repo / 'deploy.yml').write_text('script: shared/helpers.sh\n')
        (temp_git_repo / 'CHANGELOG.md').write_text('# Changelog\n\n- Added `lib/helpers.sh`\n')
        subprocess.run(['git', 'add', '-A'], cwd=temp_git_repo, capture_output=True, check=True)

        result = run_refcheck('--moves', cwd=temp_git_repo)
        assert result.returncode == 0


class TestSelfReferences:
    """Test 9: Self-references in comments should be ignored."""

    def test_ignores_self_references(self, test_fixtures):
        result = run_refcheck('src/self-ref.sh', cwd=test_fixtures)
        assert result.returncode == 0
        assert 'self-ref.sh' not in result.stdout or 'Missing' not in result.stdout


class TestExitCodes:
    """Test 10: Exit codes."""

    def test_exit_0_for_valid(self, test_fixtures):
        result = run_refcheck('valid/', cwd=test_fixtures)
        assert result.returncode == 0

    def test_exit_1_for_broken(self, test_fixtures):
        result = run_refcheck('src/', cwd=test_fixtures)
        assert result.returncode == 1


class TestHelpFlag:
    """Test 11: Help flag."""

    def test_shows_help(self):
        result = run_refcheck('--help')
        assert result.returncode == 0
        assert 'refcheck' in result.stdout


class TestRealWorldDotfiles:
    """Test 12: Real-world usage on dotfiles."""

    def test_validates_management_directory(self, dotfiles_dir):
        if dotfiles_dir is None:
            pytest.skip('Dotfiles directory not found')

        result = run_refcheck('management/', cwd=dotfiles_dir)
        assert result.returncode == 0

    def test_validates_apps_directory(self, dotfiles_dir):
        if dotfiles_dir is None:
            pytest.skip('Dotfiles directory not found')

        result = run_refcheck('apps/', '--type', 'sh', cwd=dotfiles_dir)
        assert result.returncode == 0


class TestVariablePathResolution:
    """Test 13: Variable path resolution."""

    def test_detects_broken_variable_references(self, dotfiles_dir):
        if dotfiles_dir is None:
            pytest.skip('Dotfiles directory not found')

        fixtures_dir = dotfiles_dir / 'tests' / 'apps' / 'fixtures' / 'refcheck-variables'
        if not fixtures_dir.exists():
            pytest.skip('Test fixtures not found')

        result = run_refcheck('--test-mode', str(fixtures_dir), cwd=dotfiles_dir)
        assert result.returncode == 1

    def test_shows_variable_resolution(self, dotfiles_dir):
        if dotfiles_dir is None:
            pytest.skip('Dotfiles directory not found')

        fixtures_dir = dotfiles_dir / 'tests' / 'apps' / 'fixtures' / 'refcheck-variables'
        if not fixtures_dir.exists():
            pytest.skip('Test fixtures not found')

        result = run_refcheck('--test-mode', str(fixtures_dir), cwd=dotfiles_dir)
        assert '→' in result.stdout


class TestSuggestionFeature:
    """Test 14: Suggestion feature."""

    def test_shows_possible_matches(self, suggestion_fixtures):
        result = run_refcheck(str(suggestion_fixtures / 'suggestions'), cwd=suggestion_fixtures)
        assert 'Possible matches:' in result.stdout

    def test_shows_basename_match(self, suggestion_fixtures):
        result = run_refcheck(str(suggestion_fixtures / 'suggestions'), cwd=suggestion_fixtures)
        assert 'basename match' in result.stdout

    def test_shows_name_variant(self, suggestion_fixtures):
        result = run_refcheck(str(suggestion_fixtures / 'suggestions'), cwd=suggestion_fixtures)
        assert 'name variant' in result.stdout


class TestLearnRules:
    """Test 15: --learn-rules command."""

    def test_runs_learn_rules(self, dotfiles_dir):
        if dotfiles_dir is None:
            pytest.skip('Dotfiles directory not found')

        result = run_refcheck('--learn-rules', cwd=dotfiles_dir)
        assert result.returncode == 0

    def test_creates_rules_file(self, dotfiles_dir):
        if dotfiles_dir is None:
            pytest.skip('Dotfiles directory not found')

        run_refcheck('--learn-rules', cwd=dotfiles_dir)

        safe_name = str(dotfiles_dir).lstrip('/').replace('/', '--')
        rules_path = Path.home() / '.config' / 'refcheck' / 'repos' / safe_name / 'rules.json'

        assert rules_path.exists()

    def test_rules_file_valid_json(self, dotfiles_dir):
        if dotfiles_dir is None:
            pytest.skip('Dotfiles directory not found')

        run_refcheck('--learn-rules', cwd=dotfiles_dir)

        safe_name = str(dotfiles_dir).lstrip('/').replace('/', '--')
        rules_path = Path.home() / '.config' / 'refcheck' / 'repos' / safe_name / 'rules.json'

        rules = json.loads(rules_path.read_text())
        assert 'directory_mappings' in rules
        assert 'file_mappings' in rules


class TestConfigToml:
    """Test 16: config.toml support."""

    def test_custom_stale_threshold(self, dotfiles_dir, monkeypatch, tmp_path):
        if dotfiles_dir is None:
            pytest.skip('Dotfiles directory not found')

        config_dir = tmp_path / '.config' / 'refcheck'
        config_dir.mkdir(parents=True)
        monkeypatch.setenv('HOME', str(tmp_path))

        (config_dir / 'config.toml').write_text('[warnings]\nstale_threshold = "30 days"\n')

        safe_name = str(dotfiles_dir).lstrip('/').replace('/', '--')
        repos_dir = config_dir / 'repos' / safe_name
        repos_dir.mkdir(parents=True)

        old_date = (datetime.now() - timedelta(days=15)).isoformat()[:19]
        rules = {
            '_metadata': {'generated': old_date},
            'directory_mappings': {},
            'file_mappings': {},
        }
        (repos_dir / 'rules.json').write_text(json.dumps(rules))

        result = run_refcheck('--no-warn', cwd=dotfiles_dir)
        assert 'Rules last updated' not in result.stdout

    def test_show_no_rules_hint_disabled(self, dotfiles_dir, monkeypatch, tmp_path):
        if dotfiles_dir is None:
            pytest.skip('Dotfiles directory not found')

        config_dir = tmp_path / '.config' / 'refcheck'
        config_dir.mkdir(parents=True)
        monkeypatch.setenv('HOME', str(tmp_path))

        (config_dir / 'config.toml').write_text('[warnings]\nshow_no_rules_hint = false\n')

        result = run_refcheck('--no-warn', cwd=dotfiles_dir)
        assert 'No learned rules found' not in result.stdout


class TestStaleRulesWarning:
    """Test stale rules warning."""

    def test_shows_stale_warning(self, dotfiles_dir, monkeypatch, tmp_path):
        if dotfiles_dir is None:
            pytest.skip('Dotfiles directory not found')

        config_dir = tmp_path / '.config' / 'refcheck'
        config_dir.mkdir(parents=True)
        monkeypatch.setenv('HOME', str(tmp_path))

        safe_name = str(dotfiles_dir).lstrip('/').replace('/', '--')
        repos_dir = config_dir / 'repos' / safe_name
        repos_dir.mkdir(parents=True)

        old_date = '2020-01-01T00:00:00'
        rules = {
            '_metadata': {'generated': old_date},
            'directory_mappings': {},
            'file_mappings': {},
        }
        (repos_dir / 'rules.json').write_text(json.dumps(rules))

        result = run_refcheck('--no-warn', cwd=dotfiles_dir)
        assert 'Rules last updated' in result.stdout
        assert 'days ago' in result.stdout

    def test_no_warning_for_fresh_rules(self, dotfiles_dir, monkeypatch, tmp_path):
        if dotfiles_dir is None:
            pytest.skip('Dotfiles directory not found')

        config_dir = tmp_path / '.config' / 'refcheck'
        config_dir.mkdir(parents=True)
        monkeypatch.setenv('HOME', str(tmp_path))

        safe_name = str(dotfiles_dir).lstrip('/').replace('/', '--')
        repos_dir = config_dir / 'repos' / safe_name
        repos_dir.mkdir(parents=True)

        now = datetime.now().isoformat()[:19]
        rules = {
            '_metadata': {'generated': now},
            'directory_mappings': {},
            'file_mappings': {},
        }
        (repos_dir / 'rules.json').write_text(json.dumps(rules))

        result = run_refcheck('--no-warn', cwd=dotfiles_dir)
        assert 'Rules last updated' not in result.stdout


def test_pattern_ignores_hit_inside_a_path_that_exists(tmp_path):
    """A moved directory reached by a longer, correct path is not stale.

    `--pattern boards/arm` reported `config/boards/arm/...` right after the
    move that made it correct — the substring is there, but the path resolves.
    """
    (tmp_path / 'config' / 'boards' / 'arm' / 'piantor').mkdir(parents=True)
    (tmp_path / 'README.md').write_text('Board def in `config/boards/arm/piantor/`, moved from `boards/arm/piantor/`.\n')

    checker = ReferenceChecker(tmp_path)
    checker.check_pattern('boards/arm', 'moved under config/')

    # The stale half of that sentence is still a hit; the corrected half is not.
    assert len(checker.issues) == 1


def test_pattern_still_reports_a_path_that_does_not_resolve(tmp_path):
    """Prefixing a stale path does not launder it."""
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs' / 'guide.md').write_text('See vendor/boards/arm/thing for the pinout.\n')

    checker = ReferenceChecker(tmp_path)
    checker.check_pattern('boards/arm', 'moved under config/')

    assert len(checker.issues) == 1


def test_pattern_ignores_a_hit_inside_a_url(tmp_path):
    """A URL is never a file reference, however much of the pattern it contains."""
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs' / 'hooks.md').write_text('- [Hooks Guide](https://docs.anthropic.com/en/docs/claude-code/hooks) - Official docs\n')

    checker = ReferenceChecker(tmp_path)
    checker.check_pattern('docs/claude-code', 'moved to the docs hub')

    assert checker.issues == []


def test_pattern_reports_a_stale_path_on_a_line_that_also_holds_a_url(tmp_path):
    """The URL exemption is per-hit, not per-line."""
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs' / 'hooks.md').write_text('See docs/claude-code/index.md and https://docs.anthropic.com/en/docs/claude-code/hooks\n')

    checker = ReferenceChecker(tmp_path)
    checker.check_pattern('docs/claude-code', 'moved to the docs hub')

    assert len(checker.issues) == 1


def test_pattern_ignores_hits_inside_run_logs(tmp_path):
    """A run transcript names what existed when it ran, like the .jsonl logs.

    Renaming backmeup to packup reported one miss against a gitignored
    test-wsl-docker.log, after every live reference had already been updated.
    """
    (tmp_path / 'test-wsl-docker.log').write_text('✓ backmeup help\n')
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs' / 'guide.md').write_text('Run backmeup to archive a directory.\n')

    checker = ReferenceChecker(tmp_path)
    checker.check_pattern('backmeup', 'renamed to packup')

    assert len(checker.issues) == 1
    assert 'docs/guide.md' in str(checker.issues[0])


def test_pattern_ignores_hits_inside_tool_caches(tmp_path):
    """A tool cache records what a path *was* on the last run, like the .jsonl logs.

    Renaming a test package reported twenty misses against
    .pytest_cache/v/cache/nodeids — a file the next pytest run rewrites — which
    buried the one real hit in the docs.
    """
    for cache in ('.pytest_cache/v/cache', '.ruff_cache', '.mypy_cache'):
        (tmp_path / cache).mkdir(parents=True)
        (tmp_path / cache / 'nodeids').write_text('tests/appcore/test_formatting.py::test_clip\n')

    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs' / 'guide.md').write_text('The palette lives in tests/appcore/test_formatting.py.\n')

    checker = ReferenceChecker(tmp_path)
    checker.check_pattern('tests/appcore', 'moved to the pytermstyle repo')

    assert len(checker.issues) == 1
    assert 'docs/guide.md' in str(checker.issues[0])
