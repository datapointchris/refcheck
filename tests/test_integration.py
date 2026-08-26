"""Integration tests ported from bash test suite."""

import json
import subprocess
from pathlib import Path

import pytest

from refcheck.checker import ReferenceChecker
from refcheck.config import Config


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


class TestLearnedRulesHint:
    """Rules feed the suggestion line, so the hint belongs where that line is empty."""

    def test_silent_on_a_clean_run(self, temp_git_repo, monkeypatch, tmp_path):
        monkeypatch.setenv('HOME', str(tmp_path))

        result = run_refcheck(cwd=temp_git_repo)
        assert result.returncode == 0
        assert 'learn-rules' not in result.stdout

    def test_offered_when_a_broken_reference_has_no_suggestion(self, temp_git_repo, monkeypatch, tmp_path):
        monkeypatch.setenv('HOME', str(tmp_path))
        (temp_git_repo / 'run.sh').write_text('#!/usr/bin/env bash\nbash lib/vanished.sh\n')

        result = run_refcheck(cwd=temp_git_repo)
        assert result.returncode == 1
        assert 'learn-rules' in result.stdout

    def test_silent_when_a_suggestion_already_landed(self, temp_git_repo, monkeypatch, tmp_path):
        monkeypatch.setenv('HOME', str(tmp_path))
        (temp_git_repo / 'lib').mkdir()
        (temp_git_repo / 'lib' / 'helpers.sh').write_text('echo hi\n')
        (temp_git_repo / 'run.sh').write_text('#!/usr/bin/env bash\nbash shared/helpers.sh\n')

        result = run_refcheck(cwd=temp_git_repo)
        assert result.returncode == 1
        assert 'Possible matches' in result.stdout
        assert 'learn-rules' not in result.stdout


def test_every_way_of_sourcing_a_file_is_validated(tmp_path):
    """`bash x.sh` was checked and `source x.sh` was not, so docs went stale unwatched.

    Only two spellings resolved before: a quoted argument, and one led by a
    variable. Shell writes `source lib/gone.sh` and `. lib/gone.sh` far more
    often, and a markdown file citing a moved script that way passed clean.
    """
    (tmp_path / 'lib').mkdir()
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs' / 'guide.md').write_text(
        '# Guide\n\n```bash\nbash lib/gone.sh\nsource lib/gone.sh\n. lib/gone.sh\nsource "lib/gone.sh"\n```\n'
    )

    checker = ReferenceChecker(tmp_path)
    checker.run_all_checks()

    assert len(checker.issues) == 4


def test_dot_sources_a_file_in_shell_too(tmp_path):
    """The gap was in the shared check, so scripts were as unwatched as prose."""
    (tmp_path / 'lib').mkdir()
    (tmp_path / 'run.sh').write_text('#!/usr/bin/env bash\n. lib/gone.sh\n[ -f x ] && . lib/also-gone.sh\n')

    checker = ReferenceChecker(tmp_path)
    checker.check_source_statements()

    assert len(checker.issues) == 2


def test_prose_full_stops_are_not_source_statements(tmp_path):
    """A period followed by a space is a sentence, and this repo is mostly sentences.

    The dot form only matches in command position — line start, or after a
    shell separator — because an English full stop always follows a word.
    """
    (tmp_path / 'lib').mkdir()
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs' / 'prose.md').write_text(
        '# Notes\n\n'
        'The installer writes the file. Then it reboots.\n'
        'Read the source of truth before changing anything.\n'
        'Everything lands under lib/. Nothing else moves.\n'
        'Run it once. lib/gone.sh is regenerated each time.\n'
        'Copy the file, back it up. ./lib/gone.sh stays put.\n'
        'We do . nothing special here, and neither does it.\n'
        'Ellipsis... lib/gone.sh trails off mid-thought.\n'
        '1. Install lib/gone.sh first.\n'
        '- See lib/gone.sh. Also see docs/.\n'
        'Nothing here is a reference. bash is not invoked either.\n\n'
        '```bash\n'
        'find . lib/gone.sh\n'
        'tar -C . -xf lib/gone.sh\n'
        'rsync -a . lib/gone.sh\n'
        'git add . && git commit -m "lib/gone.sh"\n'
        '```\n'
    )

    checker = ReferenceChecker(tmp_path)
    checker.run_all_checks()

    assert checker.issues == []


def test_a_dot_after_a_shell_keyword_still_sources(tmp_path):
    """`then`, `else` and `do` open a command, so a period following one is not prose."""
    (tmp_path / 'lib').mkdir()
    (tmp_path / 'run.sh').write_text('#!/usr/bin/env bash\nif true; then . lib/gone.sh; fi\nwhile read -r f; do . lib/also-gone.sh; done\n')

    checker = ReferenceChecker(tmp_path)
    checker.check_source_statements()

    assert len(checker.issues) == 2


def test_a_dot_argument_is_judged_by_the_same_tree_rule_as_bash(tmp_path):
    """`. ./gone.sh` in prose anchors to nothing, exactly as `bash ./gone.sh` does."""
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs' / 'guide.md').write_text('# Guide\n\n```bash\nbash ./gone.sh\n. ./gone.sh\nsource ./gone.sh\n```\n')

    checker = ReferenceChecker(tmp_path)
    checker.run_all_checks()

    assert checker.issues == []


def test_an_unquoted_variable_source_resolves_instead_of_going_absolute(tmp_path):
    """The old pattern captured from the slash on, so `$DIR/lib/x.sh` became `/lib/x.sh`.

    That reported a path nobody wrote, and would have passed silently on a
    machine that happened to have one at the root.
    """
    (tmp_path / 'lib').mkdir()
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs' / 'guide.md').write_text('# Guide\n\n```bash\nsource $DOTFILES_DIR/lib/gone.sh\n```\n')

    checker = ReferenceChecker(tmp_path)
    checker.check_source_statements()

    assert len(checker.issues) == 1
    assert '$DOTFILES_DIR/lib/gone.sh' in checker.issues[0].message
    assert str(tmp_path / 'lib' / 'gone.sh') in checker.issues[0].message


def test_a_system_file_under_etc_is_not_a_repo_reference(tmp_path):
    """Whether /etc/os-release exists says which OS is linting, not what went stale.

    theme and font both source it behind a `-f /etc/os-release` guard, and both
    already carry a comment that it is absent on macOS. The dot form is the
    usual spelling, so matching it put those two files one platform away from
    being reported.
    """
    (tmp_path / 'run.sh').write_text('#!/usr/bin/env bash\n. /etc/absent-on-every-machine.conf\n')

    checker = ReferenceChecker(tmp_path)
    checker.check_source_statements()

    assert checker.issues == []


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


def test_pattern_ignores_a_bare_name_inside_the_name_that_replaced_it(tmp_path):
    """A rename whose new name ends in the old one repairs every site into a hit.

    `tools.json` became `fleet-built-tools.json`, so the pattern sits inside
    every reference that was just corrected. Reporting those is a clean tree
    coming back red, which is how a checker stops being run.
    """
    (tmp_path / 'fleet-built-tools.json').write_text('{}\n')
    (tmp_path / 'README.md').write_text('The list is `fleet-built-tools.json` now.\n')

    checker = ReferenceChecker(tmp_path)
    checker.check_pattern('tools.json', 'fleet-built-tools.json')

    assert checker.issues == []


def test_pattern_still_reports_a_bare_name_standing_on_its_own(tmp_path):
    """The old name alone is the reference the rename left behind."""
    (tmp_path / 'fleet-built-tools.json').write_text('{}\n')
    (tmp_path / 'README.md').write_text('The list is `tools.json` at the root.\n')

    checker = ReferenceChecker(tmp_path)
    checker.check_pattern('tools.json', 'fleet-built-tools.json')

    assert len(checker.issues) == 1


def test_pattern_resolves_a_relative_link_against_the_file_holding_it(tmp_path):
    """A markdown link spells its target relative to itself, not to the root.

    `[pinned-versions.json](../pinned-versions.json)` in standards/ resolves
    from standards/ and from nowhere else, so resolving only against the root
    reports a working link.
    """
    (tmp_path / 'pinned-versions.json').write_text('{}\n')
    (tmp_path / 'standards').mkdir()
    (tmp_path / 'standards' / 'go.md').write_text('The numbers are [pinned-versions.json](../pinned-versions.json).\n')

    checker = ReferenceChecker(tmp_path)
    checker.check_pattern('versions.json', 'pinned-versions.json')

    assert checker.issues == []


def test_pattern_still_reports_a_relative_link_to_something_gone(tmp_path):
    """Resolving against the file's own directory does not launder a dead link."""
    (tmp_path / 'pinned-versions.json').write_text('{}\n')
    (tmp_path / 'standards').mkdir()
    (tmp_path / 'standards' / 'go.md').write_text('The numbers are [versions.json](../versions.json).\n')

    checker = ReferenceChecker(tmp_path)
    checker.check_pattern('versions.json', 'pinned-versions.json')

    assert len(checker.issues) == 1


def test_pattern_resolves_a_token_rooted_at_a_shell_variable(tmp_path):
    """`$REPO_ROOT/homelab-hosts.json` is the corrected reference, not a stale one.

    The variable has no literal path to test, so the token resolves to
    nothing and every repaired assignment in a test file comes back as a hit.
    """
    (tmp_path / 'homelab-hosts.json').write_text('{}\n')
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests' / 'registry.bats').write_text('  HOMELAB_HOSTS="$REPO_ROOT/homelab-hosts.json"\n')

    checker = ReferenceChecker(tmp_path)
    checker.check_pattern('hosts.json', 'homelab-hosts.json')

    assert checker.issues == []


def test_pattern_still_reports_a_stale_name_under_a_shell_variable(tmp_path):
    """Dropping the variable resolves the name; it does not excuse a dead one."""
    (tmp_path / 'homelab-hosts.json').write_text('{}\n')
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests' / 'registry.bats').write_text('  HOSTS="$REPO_ROOT/hosts.json"\n')

    checker = ReferenceChecker(tmp_path)
    checker.check_pattern('hosts.json', 'homelab-hosts.json')

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


def test_pattern_ignores_hits_inside_a_declared_exclusion(tmp_path):
    """The built-in patterns cover what is true of any repo; a repo adds its own.

    Which directories hold generated output is a fact only that repository
    knows, so hardcoding one repo's layout here would put private structure in
    a public tool and still miss the next repo.
    """
    reports = tmp_path / 'build' / 'reports'
    (reports / 'nested').mkdir(parents=True)
    (reports / 'run.json').write_text('{"name": "tests/appcore/test_formatting.py::test_clip"}\n')
    (reports / 'nested' / 'timing.json').write_text('{"name": "tests/appcore/test_formatting.py::test_clip"}\n')

    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs' / 'guide.md').write_text('The palette lives in tests/appcore/test_formatting.py.\n')

    checker = ReferenceChecker(tmp_path, config=Config(exclude=['build/reports/**']))
    checker.check_pattern('tests/appcore', 'moved to the pytermstyle repo')

    assert len(checker.issues) == 1
    assert 'docs/guide.md' in str(checker.issues[0])


def test_repo_config_excludes_a_subtree(temp_git_repo):
    """The declaration reaches a real run through .refcheck.toml at the repo root."""
    reports = temp_git_repo / 'build' / 'reports'
    reports.mkdir(parents=True)
    (reports / 'run.json').write_text('{"ran": "lib/helpers.sh"}\n')

    assert run_refcheck('--pattern', 'lib/helpers.sh', cwd=temp_git_repo).returncode == 1

    (temp_git_repo / '.refcheck.toml').write_text('[scan]\nexclude = ["build/reports/**"]\n')

    assert run_refcheck('--pattern', 'lib/helpers.sh', cwd=temp_git_repo).returncode == 0


def test_exclude_flag_skips_a_subtree_without_declaring_it(temp_git_repo):
    reports = temp_git_repo / 'build' / 'reports'
    reports.mkdir(parents=True)
    (reports / 'run.json').write_text('{"ran": "lib/helpers.sh"}\n')

    assert run_refcheck('--pattern', 'lib/helpers.sh', cwd=temp_git_repo).returncode == 1

    narrowed = run_refcheck('--pattern', 'lib/helpers.sh', '--exclude', 'build/reports/**', cwd=temp_git_repo)

    assert narrowed.returncode == 0


def test_show_config_names_the_layer_each_exclusion_came_from(temp_git_repo):
    (temp_git_repo / '.refcheck.toml').write_text('[scan]\nexclude = ["build/reports/**"]\n')

    result = run_refcheck('--show-config', '--exclude', 'tmp/**', cwd=temp_git_repo)

    assert result.returncode == 0
    assert '.refcheck.toml' in result.stdout
    assert 'build/reports/**' in result.stdout
    assert 'tmp/**' in result.stdout
    assert 'CHANGELOG.md' in result.stdout


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


def test_pattern_expands_a_home_rooted_token_before_resolving_it(tmp_path, monkeypatch):
    """A corrected reference to another repo hangs off no root in this one.

    `~/.local/share/<repo>/pinned-versions.json` is literal text until `~` is
    expanded, so joining it to the repo root built a path that cannot exist and
    reported the file that had just been repaired.
    """
    monkeypatch.setenv('HOME', str(tmp_path))
    (tmp_path / 'elsewhere').mkdir()
    (tmp_path / 'elsewhere' / 'pinned-versions.json').write_text('{}\n')
    repo = tmp_path / 'repo'
    repo.mkdir()
    (repo / 'config.yml').write_text('versions_file: ~/elsewhere/pinned-versions.json\n')

    checker = ReferenceChecker(repo)
    checker.check_pattern('versions.json', 'now pinned-versions.json')

    assert checker.issues == []


def test_pattern_still_reports_a_home_rooted_token_that_is_not_there(tmp_path, monkeypatch):
    """Expanding `~` does not launder a path that is genuinely gone."""
    monkeypatch.setenv('HOME', str(tmp_path))
    (tmp_path / 'elsewhere').mkdir()
    repo = tmp_path / 'repo'
    repo.mkdir()
    (repo / 'config.yml').write_text('versions_file: ~/elsewhere/versions.json\n')

    checker = ReferenceChecker(repo)
    checker.check_pattern('versions.json', 'now pinned-versions.json')

    assert len(checker.issues) == 1


def test_pattern_falls_back_when_a_variable_points_somewhere_else(tmp_path, monkeypatch):
    """Expansion is tried first and is never the only answer.

    `$REPO_ROOT` set to another checkout expands to a path with no
    homelab-hosts.json in it, and the corrected reference is still corrected.
    """
    monkeypatch.setenv('REPO_ROOT', str(tmp_path / 'somewhere-else'))
    (tmp_path / 'somewhere-else').mkdir()
    repo = tmp_path / 'repo'
    repo.mkdir()
    (repo / 'homelab-hosts.json').write_text('{}\n')
    (repo / 'registry.bats').write_text('  HOMELAB_HOSTS="$REPO_ROOT/homelab-hosts.json"\n')

    checker = ReferenceChecker(repo)
    checker.check_pattern('hosts.json', 'now homelab-hosts.json')

    assert checker.issues == []


def test_pattern_skips_a_binary_in_a_repo_that_is_not_the_working_directory(tmp_path, monkeypatch):
    """The binary sniff opens a repo-relative path, so it needs the root in front of it.

    Scanning a repo you are not standing in opened the wrong path, read
    "not binary" off the OSError, and pattern-matched a 30 MB Go executable as
    text.
    """
    repo = tmp_path / 'repo'
    repo.mkdir()
    (repo / 'compiled').write_bytes(b'\x7fELF\x00\x00 versions.json \x00 padding')
    monkeypatch.chdir(tmp_path)

    checker = ReferenceChecker(repo)
    checker.check_pattern('versions.json', 'now pinned-versions.json')

    assert checker.issues == []


class TestSweepAcrossRepos:
    """--registry asks the same question of every repo the caller lists."""

    def registry_at(self, path, *repos):
        path.write_text(json.dumps({'repos': [{'name': repo.name, 'path': str(repo), 'status': 'active'} for repo in repos]}))
        return path

    def test_reports_a_consumer_left_holding_the_old_path(self, tmp_path, temp_git_repo):
        consumer = tmp_path / 'consumer'
        consumer.mkdir()
        (temp_git_repo / 'pinned-versions.json').write_text('{}\n')
        subprocess.run(['git', 'add', '-A'], cwd=temp_git_repo, capture_output=True, check=True)
        subprocess.run(['git', 'commit', '-m', 'add pins'], cwd=temp_git_repo, capture_output=True, check=True)
        subprocess.run(['git', 'mv', 'pinned-versions.json', 'versions.json'], cwd=temp_git_repo, capture_output=True, check=True)
        subprocess.run(['git', 'commit', '-m', 'rename back'], cwd=temp_git_repo, capture_output=True, check=True)
        subprocess.run(['git', 'mv', 'versions.json', 'pinned-versions.json'], cwd=temp_git_repo, capture_output=True, check=True)
        subprocess.run(['git', 'commit', '-m', 'rename'], cwd=temp_git_repo, capture_output=True, check=True)
        (consumer / 'config.yml').write_text(f'versions_file: {temp_git_repo}/versions.json\n')
        registry = self.registry_at(tmp_path / 'reg.json', temp_git_repo, consumer)

        result = run_refcheck('--moves-since', 'HEAD~1', '--registry', str(registry), cwd=temp_git_repo)

        assert result.returncode == 1
        assert 'Gone from' in result.stdout
        assert 'config.yml:1' in result.stdout

    def test_says_nothing_when_the_consumer_names_the_new_path(self, tmp_path, temp_git_repo):
        consumer = tmp_path / 'consumer'
        consumer.mkdir()
        (temp_git_repo / 'versions.json').write_text('{}\n')
        subprocess.run(['git', 'add', '-A'], cwd=temp_git_repo, capture_output=True, check=True)
        subprocess.run(['git', 'commit', '-m', 'add pins'], cwd=temp_git_repo, capture_output=True, check=True)
        subprocess.run(['git', 'mv', 'versions.json', 'pinned-versions.json'], cwd=temp_git_repo, capture_output=True, check=True)
        subprocess.run(['git', 'commit', '-m', 'rename'], cwd=temp_git_repo, capture_output=True, check=True)
        (consumer / 'config.yml').write_text(f'versions_file: {temp_git_repo}/pinned-versions.json\n')
        registry = self.registry_at(tmp_path / 'reg.json', temp_git_repo, consumer)

        result = run_refcheck('--moves-since', 'HEAD~1', '--registry', str(registry), cwd=temp_git_repo)

        assert result.returncode == 0
        assert 'No repo names a path that moved' in result.stdout

    def test_sweeps_a_pattern_named_by_hand(self, tmp_path, temp_git_repo):
        consumer = tmp_path / 'consumer'
        consumer.mkdir()
        (consumer / 'config.yml').write_text(f'versions_file: {temp_git_repo}/versions.json\n')
        registry = self.registry_at(tmp_path / 'reg.json', temp_git_repo, consumer)

        result = run_refcheck('--pattern', 'versions.json', '--registry', str(registry), cwd=temp_git_repo)

        assert result.returncode == 1
        assert 'Gone from' in result.stdout

    def test_refuses_a_registry_with_nothing_to_sweep_for(self, tmp_path, temp_git_repo):
        """A sweep with no moved path asks ninety repos nothing and exits clean."""
        registry = self.registry_at(tmp_path / 'reg.json', temp_git_repo)

        result = run_refcheck('--registry', str(registry), cwd=temp_git_repo)

        assert result.returncode == 2
        assert '--moves' in result.stderr

    def test_refuses_a_registry_that_is_not_one(self, tmp_path, temp_git_repo):
        (tmp_path / 'reg.json').write_text('{not json')

        result = run_refcheck('--pattern', 'x', '--registry', str(tmp_path / 'reg.json'), cwd=temp_git_repo)

        assert result.returncode == 2
        assert 'not valid JSON' in result.stderr
