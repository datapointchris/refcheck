"""Integration tests ported from bash test suite."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from refcheck import moves
from refcheck.checker import ReferenceChecker
from refcheck.config import Config


def run_refcheck(*args, cwd=None):
    """Run refcheck with the arguments exactly as given."""
    result = subprocess.run(
        ['refcheck', *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return result


def run_check(*args, cwd=None):
    """Run the check, which is what nearly every test below is asking for."""
    return run_refcheck('check', *args, cwd=cwd)


class TestBasicValidation:
    """Test 1: Basic validation (no flags)."""

    def test_finds_broken_references(self, test_fixtures):
        result = run_check(cwd=test_fixtures)
        assert result.returncode == 1


class TestDirectoryFiltering:
    """Test 2: Directory filtering (positional argument)."""

    def test_checks_specific_directory(self, test_fixtures):
        result = run_check('src/', cwd=test_fixtures)
        assert result.returncode == 1

    def test_passes_for_clean_directory(self, test_fixtures):
        result = run_check('docs/', cwd=test_fixtures)
        assert result.returncode == 0

    def test_checks_single_file(self, test_fixtures):
        """Single file argument should be checked directly."""
        result = run_check('src/broken-source.sh', cwd=test_fixtures)
        assert result.returncode == 1
        assert 'nonexistent' in result.stdout

    def test_single_file_clean(self, test_fixtures):
        """Single clean file should pass."""
        result = run_check('valid/clean.sh', cwd=test_fixtures)
        assert result.returncode == 0


class TestPatternChecking:
    """Test 3: Pattern checking."""

    def test_finds_old_pattern(self, test_fixtures):
        result = run_check('--pattern', 'management/tests/', cwd=test_fixtures)
        assert result.returncode == 1

    def test_finds_pattern_in_specific_dir(self, test_fixtures):
        result = run_check('--pattern', 'management/tests/', 'src/', cwd=test_fixtures)
        assert result.returncode == 1

    def test_pattern_with_skip_docs(self, test_fixtures):
        result = run_check('--pattern', 'management/tests/', 'docs/', '--skip-docs', cwd=test_fixtures)
        assert result.returncode == 0


class TestPatternWithDescription:
    """Test 4: Pattern with description."""

    def test_accepts_pattern_description(self, test_fixtures):
        result = run_check(
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
        result = run_check('--type', 'sh', 'src/', cwd=test_fixtures)
        assert result.returncode == 1

    def test_filters_by_python_files(self, test_fixtures):
        (test_fixtures / 'src' / 'test.py').write_text('# Python file\nimport nonexistent_module\n')
        result = run_check('--type', 'py', 'src/', cwd=test_fixtures)
        assert result.returncode == 0


class TestSkipDocs:
    """Test 6: Skip docs flag."""

    def test_skip_docs_reduces_pattern_matches(self, test_fixtures):
        with_docs = run_check('--pattern', 'management/tests/', cwd=test_fixtures)
        without_docs = run_check('--pattern', 'management/tests/', '--skip-docs', cwd=test_fixtures)

        with_count = with_docs.stdout.count('management/tests/')
        without_count = without_docs.stdout.count('management/tests/')

        assert without_count < with_count or without_count == 0


class TestCombinedFilters:
    """Test 7: Combined filters."""

    def test_type_and_skip_docs(self, test_fixtures):
        result = run_check('--type', 'sh', '--skip-docs', 'src/', cwd=test_fixtures)
        assert result.returncode == 1

    def test_pattern_and_directory(self, test_fixtures):
        result = run_check('--pattern', 'management/tests/', 'src/', cwd=test_fixtures)
        assert result.returncode == 1

    def test_all_filters(self, test_fixtures):
        result = run_check(
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
        result = run_check('valid/', cwd=test_fixtures)
        assert result.returncode == 0

    def test_filename_list_is_not_a_script_invocation(self, test_fixtures):
        """`for f in functions.sh aliases.sh` is a word list, not `sh aliases.sh`."""
        result = run_check('valid/filename-list.sh', cwd=test_fixtures)
        assert result.returncode == 0
        assert 'aliases.sh' not in result.stdout

    def test_remote_execution_paths_are_not_local_references(self, test_fixtures):
        """A script handed to another host, container or user is on a filesystem we cannot see.

        Asserted per executor. One assertion over a file holding all six lines
        passes on whichever pattern matches first, so the other five can be
        deleted with this test still green.
        """
        result = run_check('valid/remote-exec.sh', cwd=test_fixtures)

        assert result.returncode == 0
        for handed_off in (
            'container-only.sh',
            'lxc-only.sh',
            'docker-only.sh',
            'kube-only.sh',
            'remote-only.sh',
            'other-user-only.sh',
        ):
            assert handed_off not in result.stdout

    def test_commented_source_is_not_flagged_as_fragile(self, test_fixtures):
        """A source in a usage comment has no working directory to be fragile about."""
        result = run_check('valid/documented-usage.sh', cwd=test_fixtures)
        assert result.returncode == 0
        assert 'Fragile' not in result.stdout


class TestMarkdownReferences:
    """Docs carry the same references as code and must be resolved the same way."""

    def test_finds_stale_source_in_markdown(self, test_fixtures):
        """The regression: these checks globbed **/*.sh, so docs were never read."""
        result = run_check('stale-docs/stale-source.md', cwd=test_fixtures)
        assert result.returncode == 1
        assert 'gone.sh' in result.stdout

    def test_finds_stale_script_invocation_in_markdown(self, test_fixtures):
        result = run_check('stale-docs/stale-source.md', cwd=test_fixtures)
        assert 'also-gone.sh' in result.stdout

    def test_resolves_dotfiles_dir_in_markdown(self, test_fixtures):
        """Prose has no assignments to parse, so $DOTFILES_DIR must be seeded."""
        result = run_check('docs/live-source.md', cwd=test_fixtures)
        assert result.returncode == 0
        assert 'helpers.sh' not in result.stdout

    def test_placeholders_are_not_reported(self, test_fixtures):
        """A how-to naming toolname.sh describes a file it never intended to ship."""
        result = run_check('docs/placeholders.md', cwd=test_fixtures)
        assert result.returncode == 0
        for stand_in in ('toolname.sh', 'tool}-plugins.sh', 'my-library.sh', 'script.sh'):
            assert stand_in not in result.stdout

    def test_placeholder_stems_still_resolve_in_shell(self, test_fixtures):
        """`bash script.sh` is prose in a README and a real invocation in code."""
        result = run_check('src/broken-script.sh', cwd=test_fixtures)
        assert result.returncode == 1
        assert 'script.sh' in result.stdout

    def test_skip_docs_excludes_markdown_references(self, test_fixtures):
        result = run_check('stale-docs/stale-source.md', '--skip-docs', cwd=test_fixtures)
        assert result.returncode == 0

    def test_other_projects_trees_are_not_reported(self, test_fixtures):
        """Docs quote other people's layouts; none of it is a claim about this repo."""
        result = run_check('docs/other-trees.md', cwd=test_fixtures)
        assert result.returncode == 0
        for foreign in ('child.sh', 'mylib_test.sh', 'deploy.sh'):
            assert foreign not in result.stdout

    def test_resource_is_not_a_source_statement(self, test_fixtures):
        """`resource "aws_lambda_function"` ends in `source "..."` without a boundary."""
        result = run_check('docs/other-trees.md', cwd=test_fixtures)
        assert 'aws_lambda_function' not in result.stdout
        assert 'freshrss' not in result.stdout

    def test_rename_under_an_existing_directory_is_still_reported(self, test_fixtures):
        """The signal the tree rule must preserve: our directory, moved file."""
        result = run_check('stale-docs/renamed-dir.md', cwd=test_fixtures)
        assert result.returncode == 1
        assert 'runner.sh' in result.stdout


class TestDocumentedInvocations:
    """A shell script explains itself in comments and usage strings."""

    def test_illustrated_invocations_are_not_reported(self, test_fixtures):
        result = run_check('valid/documented-invocations.sh', cwd=test_fixtures)
        assert result.returncode == 0
        for illustrative in ('install.sh', 'run-and-summarize.sh', 'lib.sh'):
            assert illustrative not in result.stdout

    def test_documented_reference_under_an_existing_directory_is_still_reported(self, test_fixtures):
        """The signal the widened guard must preserve, in both contexts."""
        result = run_check('stale-docs/documented-stale.sh', cwd=test_fixtures)
        assert result.returncode == 1
        assert result.stdout.count('valid/gone/runner.sh') == 2

    def test_a_real_invocation_is_still_a_real_invocation(self, test_fixtures):
        """Only the leading command decides; a script run after an echo still resolves."""
        script = test_fixtures / 'valid' / 'runs-after-echo.sh'
        script.write_text('#!/usr/bin/env bash\nbash valid/gone/runner.sh && echo done\n')
        result = run_check('valid/runs-after-echo.sh', cwd=test_fixtures)
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

        result = run_check('--moves', cwd=temp_git_repo)
        assert result.returncode == 1
        assert 'deploy.yml' in result.stdout
        assert 'now shared/helpers.sh' in result.stdout

    def test_says_nothing_when_the_references_were_updated(self, temp_git_repo):
        self._repo_with_a_staged_move(temp_git_repo)
        (temp_git_repo / 'deploy.yml').write_text('script: shared/helpers.sh\n')
        subprocess.run(['git', 'add', '-A'], cwd=temp_git_repo, capture_output=True, check=True)

        result = run_check('--moves', cwd=temp_git_repo)
        assert result.returncode == 0

    def test_moves_is_off_unless_asked_for(self, temp_git_repo):
        self._repo_with_a_staged_move(temp_git_repo)

        result = run_check(cwd=temp_git_repo)
        assert result.returncode == 0

    def test_changelog_entries_are_not_stale_references(self, temp_git_repo):
        """A changelog names where a file was when it shipped. That is the point of it."""
        self._repo_with_a_staged_move(temp_git_repo)
        (temp_git_repo / 'deploy.yml').write_text('script: shared/helpers.sh\n')
        (temp_git_repo / 'CHANGELOG.md').write_text('# Changelog\n\n- Added `lib/helpers.sh`\n')
        subprocess.run(['git', 'add', '-A'], cwd=temp_git_repo, capture_output=True, check=True)

        result = run_check('--moves', cwd=temp_git_repo)
        assert result.returncode == 0


class TestSelfReferences:
    """Test 9: Self-references in comments should be ignored."""

    def test_ignores_self_references(self, test_fixtures):
        result = run_check('src/self-ref.sh', cwd=test_fixtures)
        assert result.returncode == 0
        assert 'self-ref.sh' not in result.stdout or 'Missing' not in result.stdout


class TestExitCodes:
    """Test 10: Exit codes."""

    def test_exit_0_for_valid(self, test_fixtures):
        result = run_check('valid/', cwd=test_fixtures)
        assert result.returncode == 0

    def test_exit_1_for_broken(self, test_fixtures):
        result = run_check('src/', cwd=test_fixtures)
        assert result.returncode == 1


class TestHelpFlag:
    """Test 11: Help flag."""

    def test_shows_help(self):
        result = run_refcheck('--help')
        assert result.returncode == 0
        assert 'refcheck' in result.stdout


class TestARepositoryItIsPointedAt:
    """The shapes a real checkout has, built here rather than read off the machine."""

    def test_a_clean_directory_passes(self, deployed_repo):
        result = run_check('shell/', cwd=deployed_repo)

        assert result.returncode == 0

    def test_a_clean_directory_passes_under_a_type_filter(self, deployed_repo):
        result = run_check('shell/', '--type', 'sh', cwd=deployed_repo)

        assert result.returncode == 0


class TestVariablePathResolution:
    """Test 13: Variable path resolution."""

    def test_detects_broken_variable_references(self, deployed_repo):
        """The fixture sits under fixtures/, so reaching it is what --test-mode is for."""
        result = run_check('--test-mode', 'tests/fixtures/variables', cwd=deployed_repo)

        assert result.returncode == 1
        assert 'absent-helper.sh' in result.stdout

    def test_shows_variable_resolution(self, deployed_repo):
        """Both spellings, because the resolved one is what says which file was looked for."""
        result = run_check('--test-mode', 'tests/fixtures/variables', cwd=deployed_repo)

        assert '$SCRIPT_DIR/absent-helper.sh' in result.stdout
        assert '\u2192' in result.stdout

    def test_a_fixture_directory_is_out_of_scope_without_test_mode(self, deployed_repo):
        """The flag has to be the reason the last two tests see anything."""
        result = run_check(cwd=deployed_repo)

        assert result.returncode == 0
        assert 'absent-helper.sh' not in result.stdout


class TestSuggestionFeature:
    """Test 14: Suggestion feature."""

    def test_shows_possible_matches(self, suggestion_fixtures):
        result = run_check(str(suggestion_fixtures / 'suggestions'), cwd=suggestion_fixtures)
        assert 'Possible matches:' in result.stdout

    def test_shows_basename_match(self, suggestion_fixtures):
        result = run_check(str(suggestion_fixtures / 'suggestions'), cwd=suggestion_fixtures)
        assert 'basename match' in result.stdout

    def test_shows_name_variant(self, suggestion_fixtures):
        result = run_check(str(suggestion_fixtures / 'suggestions'), cwd=suggestion_fixtures)
        assert 'name variant' in result.stdout


class TestLearnRules:
    """Test 15: learn-rules command."""

    def rules_file_for(self, repo):
        safe_name = str(repo).lstrip('/').replace('/', '--')
        return Path.home() / '.config' / 'refcheck' / 'repos' / safe_name / 'rules.json'

    def test_runs_learn_rules(self, deployed_repo):
        result = run_refcheck('learn-rules', cwd=deployed_repo)

        assert result.returncode == 0

    def test_creates_rules_file(self, deployed_repo):
        run_refcheck('learn-rules', cwd=deployed_repo)

        assert self.rules_file_for(deployed_repo).exists()

    def test_rules_file_valid_json(self, deployed_repo):
        run_refcheck('learn-rules', cwd=deployed_repo)

        rules = json.loads(self.rules_file_for(deployed_repo).read_text())

        assert 'directory_mappings' in rules
        assert 'file_mappings' in rules

    def test_reads_the_rename_out_of_the_history(self, deployed_repo):
        """Asserting on the shape alone passes over an empty result."""
        run_refcheck('learn-rules', cwd=deployed_repo)

        rules = json.loads(self.rules_file_for(deployed_repo).read_text())

        assert rules['file_mappings'] == {'logging.sh': 'log.sh'}


class TestLearnedRulesHint:
    """Rules feed the suggestion line, so the hint belongs where that line is empty."""

    def test_silent_on_a_clean_run(self, temp_git_repo, monkeypatch, tmp_path):
        monkeypatch.setenv('HOME', str(tmp_path))

        result = run_check(cwd=temp_git_repo)
        assert result.returncode == 0
        assert 'learn-rules' not in result.stdout

    def test_offered_when_a_broken_reference_has_no_suggestion(self, temp_git_repo, monkeypatch, tmp_path):
        monkeypatch.setenv('HOME', str(tmp_path))
        (temp_git_repo / 'run.sh').write_text('#!/usr/bin/env bash\nbash lib/vanished.sh\n')

        result = run_check(cwd=temp_git_repo)
        assert result.returncode == 1
        assert 'learn-rules' in result.stdout

    def test_silent_when_a_suggestion_already_landed(self, temp_git_repo, monkeypatch, tmp_path):
        monkeypatch.setenv('HOME', str(tmp_path))
        (temp_git_repo / 'lib').mkdir()
        (temp_git_repo / 'lib' / 'helpers.sh').write_text('echo hi\n')
        (temp_git_repo / 'run.sh').write_text('#!/usr/bin/env bash\nbash shared/helpers.sh\n')

        result = run_check(cwd=temp_git_repo)
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

    Two scripts sourced it behind a `-f /etc/os-release` guard, each already
    carrying a comment that it is absent on macOS. The dot form is the usual
    spelling, so matching it put both files one platform away from being
    reported.
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

    `tools.json` became `built-tools.json`, so the pattern sits inside every
    reference that was just corrected. Reporting those is a clean tree coming
    back red, which is how a checker stops being run.
    """
    (tmp_path / 'built-tools.json').write_text('{}\n')
    (tmp_path / 'README.md').write_text('The list is `built-tools.json` now.\n')

    checker = ReferenceChecker(tmp_path)
    checker.check_pattern('tools.json', 'built-tools.json')

    assert checker.issues == []


def test_pattern_still_reports_a_bare_name_standing_on_its_own(tmp_path):
    """The old name alone is the reference the rename left behind."""
    (tmp_path / 'built-tools.json').write_text('{}\n')
    (tmp_path / 'README.md').write_text('The list is `tools.json` at the root.\n')

    checker = ReferenceChecker(tmp_path)
    checker.check_pattern('tools.json', 'built-tools.json')

    assert len(checker.issues) == 1


def test_pattern_resolves_a_relative_link_against_the_file_holding_it(tmp_path):
    """A markdown link spells its target relative to itself, not to the root.

    `[pinned-versions.json](../pinned-versions.json)` in a subdirectory
    resolves from that subdirectory and from nowhere else, so resolving only
    against the root reports a working link.
    """
    (tmp_path / 'pinned-versions.json').write_text('{}\n')
    (tmp_path / 'guides').mkdir()
    (tmp_path / 'guides' / 'go.md').write_text('The numbers are [pinned-versions.json](../pinned-versions.json).\n')

    checker = ReferenceChecker(tmp_path)
    checker.check_pattern('versions.json', 'pinned-versions.json')

    assert checker.issues == []


def test_pattern_still_reports_a_relative_link_to_something_gone(tmp_path):
    """Resolving against the file's own directory does not launder a dead link."""
    (tmp_path / 'pinned-versions.json').write_text('{}\n')
    (tmp_path / 'guides').mkdir()
    (tmp_path / 'guides' / 'go.md').write_text('The numbers are [versions.json](../versions.json).\n')

    checker = ReferenceChecker(tmp_path)
    checker.check_pattern('versions.json', 'pinned-versions.json')

    assert len(checker.issues) == 1


def test_pattern_resolves_a_token_rooted_at_a_shell_variable(tmp_path):
    """`$REPO_ROOT/cluster-hosts.json` is the corrected reference, not a stale one.

    The variable has no literal path to test, so the token resolves to
    nothing and every repaired assignment in a test file comes back as a hit.
    """
    (tmp_path / 'cluster-hosts.json').write_text('{}\n')
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests' / 'registry.bats').write_text('  CLUSTER_HOSTS="$REPO_ROOT/cluster-hosts.json"\n')

    checker = ReferenceChecker(tmp_path)
    checker.check_pattern('hosts.json', 'cluster-hosts.json')

    assert checker.issues == []


def test_pattern_still_reports_a_stale_name_under_a_shell_variable(tmp_path):
    """Dropping the variable resolves the name; it does not excuse a dead one."""
    (tmp_path / 'cluster-hosts.json').write_text('{}\n')
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests' / 'registry.bats').write_text('  HOSTS="$REPO_ROOT/hosts.json"\n')

    checker = ReferenceChecker(tmp_path)
    checker.check_pattern('hosts.json', 'cluster-hosts.json')

    assert len(checker.issues) == 1


def test_pattern_ignores_a_hit_inside_a_url(tmp_path):
    """A URL is never a file reference, however much of the pattern it contains.

    Not listed as set aside either, and the two silences are different. The
    resolver guesses what a file being on disk means, so its drops are handed
    to the reader to check. A URL names no file here whatever the tree looks
    like, so there is no judgement to hand over — and a docs repo swept for a
    moved path would list every link that quotes it.
    """
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs' / 'hooks.md').write_text('- [Hooks Guide](https://docs.anthropic.com/en/docs/claude-code/hooks) - Official docs\n')

    checker = ReferenceChecker(tmp_path)
    checker.check_pattern('docs/claude-code', 'moved to the docs hub')

    assert checker.issues == []
    assert checker.set_aside == []


def test_pattern_reports_a_stale_path_on_a_line_that_also_holds_a_url(tmp_path):
    """The URL exemption is per-hit, not per-line."""
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs' / 'hooks.md').write_text('See docs/claude-code/index.md and https://docs.anthropic.com/en/docs/claude-code/hooks\n')

    checker = ReferenceChecker(tmp_path)
    checker.check_pattern('docs/claude-code', 'moved to the docs hub')

    assert len(checker.issues) == 1


def test_pattern_ignores_hits_inside_run_logs(tmp_path):
    """A run transcript names what existed when it ran, like the .jsonl logs.

    Renaming a tool reported one miss against a gitignored run log, after every
    live reference had already been updated.
    """
    (tmp_path / 'run-transcript.log').write_text('✓ oldname help\n')
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs' / 'guide.md').write_text('Run oldname to archive a directory.\n')

    checker = ReferenceChecker(tmp_path)
    checker.check_pattern('oldname', 'renamed to newname')

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

    assert run_check('--pattern', 'lib/helpers.sh', cwd=temp_git_repo).returncode == 1

    (temp_git_repo / '.refcheck.toml').write_text('[scan]\nexclude = ["build/reports/**"]\n')

    assert run_check('--pattern', 'lib/helpers.sh', cwd=temp_git_repo).returncode == 0


def test_exclude_flag_skips_a_subtree_without_declaring_it(temp_git_repo):
    reports = temp_git_repo / 'build' / 'reports'
    reports.mkdir(parents=True)
    (reports / 'run.json').write_text('{"ran": "lib/helpers.sh"}\n')

    assert run_check('--pattern', 'lib/helpers.sh', cwd=temp_git_repo).returncode == 1

    narrowed = run_check('--pattern', 'lib/helpers.sh', '--exclude', 'build/reports/**', cwd=temp_git_repo)

    assert narrowed.returncode == 0


def test_show_config_names_the_layer_each_exclusion_came_from(temp_git_repo):
    (temp_git_repo / '.refcheck.toml').write_text('[scan]\nexclude = ["build/reports/**"]\n')

    result = run_check('--show-config', '--exclude', 'tmp/**', cwd=temp_git_repo)

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
    cluster-hosts.json in it, and the corrected reference is still corrected.
    """
    monkeypatch.setenv('REPO_ROOT', str(tmp_path / 'somewhere-else'))
    (tmp_path / 'somewhere-else').mkdir()
    repo = tmp_path / 'repo'
    repo.mkdir()
    (repo / 'cluster-hosts.json').write_text('{}\n')
    (repo / 'registry.bats').write_text('  CLUSTER_HOSTS="$REPO_ROOT/cluster-hosts.json"\n')

    checker = ReferenceChecker(repo)
    checker.check_pattern('hosts.json', 'now cluster-hosts.json')

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


class TestSetAsideHits:
    """A hit the resolver drops is named, because a silent drop reads as a clean sweep."""

    def markdownlint_repo(self, root):
        """A repo still holding the old name at its root, with the literal deeper in.

        The shape a generator repo takes: it deploys `.markdownlint.json` to
        every repo including itself, so the old name is on disk at the root
        while the templates naming it are two directories down.
        """
        (root / '.markdownlint.json').write_text('{}\n')
        (root / 'configs').mkdir()
        (root / 'configs' / 'prettierignore.txt').write_text('.pre-commit-config.yaml\n.markdownlint.json\n')
        return root

    def test_a_hit_dropped_because_the_old_name_is_still_on_disk_is_named(self, tmp_path):
        """Existence at the root suppressed every mention and said nothing about it.

        `--pattern markdownlint.json` reported one file and stayed silent on
        ten more, because `.markdownlint.json` was still at the root and every
        widened token resolved to it. The run printed what a repo with nothing
        stale prints.
        """
        repo = self.markdownlint_repo(tmp_path)

        checker = ReferenceChecker(repo)
        checker.check_pattern('markdownlint.json', 'now markdownlint.yml')

        assert checker.issues == []
        assert [(entry.file.as_posix(), entry.line_num) for entry in checker.set_aside] == [('configs/prettierignore.txt', 2)]
        assert checker.set_aside[0].token == '.markdownlint.json'
        assert checker.set_aside[0].target == Path('.markdownlint.json')

    def test_the_same_name_is_found_whichever_spelling_the_pattern_uses(self, tmp_path):
        """A broader pattern must never return fewer hits than a narrower one.

        `.markdownlint.json` covers the token's left edge and is reported on
        sight; `markdownlint.json` does not and goes to the resolver. The same
        line then came back as a finding under one spelling and as nothing at
        all under the other.
        """
        repo = self.markdownlint_repo(tmp_path)

        seen = []
        for pattern in ('markdownlint.json', '.markdownlint.json'):
            checker = ReferenceChecker(repo)
            checker.check_pattern(pattern, 'now markdownlint.yml')
            found = {(issue.file.as_posix(), issue.line_num) for issue in checker.issues}
            seen.append(found | {(entry.file.as_posix(), entry.line_num) for entry in checker.set_aside})

        assert seen[0] == seen[1]

    def test_a_hit_resolving_to_the_old_name_is_named_even_when_the_new_one_is_known(self, tmp_path):
        """The token resolves, but to the path that moved rather than the one it became.

        Knowing the new name is what separates a repair from a coincidence.
        This is the coincidence, so it stays in the list the run prints.
        """
        repo = self.markdownlint_repo(tmp_path)

        checker = ReferenceChecker(repo)
        checker.check_patterns({'markdownlint.json': 'now markdownlint.yml'}, {'markdownlint.json': 'configs/markdownlint.yml'})

        assert checker.issues == []
        assert [entry.file.as_posix() for entry in checker.set_aside] == ['configs/prettierignore.txt']

    def test_a_repair_the_rename_record_confirms_is_not_listed(self, tmp_path):
        """A hit spelling the new path is a repair the run can prove, so it says nothing.

        Every rename repairs sites the pattern still matches, and listing all
        of them puts a screen of noise above the findings.
        """
        (tmp_path / 'built-tools.json').write_text('{}\n')
        (tmp_path / 'README.md').write_text('The list is `built-tools.json` now.\n')

        checker = ReferenceChecker(tmp_path)
        checker.check_patterns({'tools.json': 'now built-tools.json'}, {'tools.json': 'built-tools.json'})

        assert checker.issues == []
        assert checker.set_aside == []

    def test_knowing_the_new_name_never_turns_a_dropped_hit_into_a_finding(self, tmp_path):
        """A vendored copy resolves and is not the renamed file, and is not broken either.

        Reporting on "resolves but does not name the new path" would call that
        stale. The reference opens the file it names, so the rename record
        decides what gets listed and never what gets reported.
        """
        (tmp_path / 'vendor' / 'configs').mkdir(parents=True)
        (tmp_path / 'vendor' / 'configs' / 'markdownlint.json').write_text('{}\n')
        (tmp_path / 'README.md').write_text('The pinned copy is vendor/configs/markdownlint.json.\n')

        moved = 'configs/markdownlint.json'
        checker = ReferenceChecker(tmp_path)
        checker.check_patterns({moved: 'now configs/markdownlint.yml'}, {moved: 'configs/markdownlint.yml'})

        assert checker.issues == []

    def test_one_line_naming_the_same_path_twice_is_one_row(self, tmp_path):
        """A row per occurrence says the same thing twice and buries the next hit."""
        (tmp_path / '.markdownlint.json').write_text('{}\n')
        (tmp_path / 'notes.md').write_text('Both .markdownlint.json and .markdownlint.json are ignored.\n')

        checker = ReferenceChecker(tmp_path)
        checker.check_pattern('markdownlint.json', 'now markdownlint.yml')

        assert len(checker.set_aside) == 1

    def test_a_hit_resolving_outside_the_repo_keeps_its_absolute_path(self, tmp_path):
        """A `~`-rooted token has no repo-relative form to print.

        Forcing one would name a file the repo does not hold, which is worse
        than the long path: the reader opens it and finds nothing there.
        """
        outside = tmp_path / 'elsewhere'
        outside.mkdir()
        (outside / 'pinned-versions.json').write_text('{}\n')
        repo = tmp_path / 'repo'
        repo.mkdir()
        (repo / 'notes.md').write_text(f'The pins live at {outside}/pinned-versions.json today.\n')

        checker = ReferenceChecker(repo)
        checker.check_pattern('versions.json', 'now pinned-versions.json')

        assert checker.issues == []
        assert [entry.target for entry in checker.set_aside] == [outside / 'pinned-versions.json']

    def test_a_run_with_hits_set_aside_does_not_claim_every_reference_is_valid(self, temp_git_repo):
        """The tick is the product, so it cannot be printed over a judgement call."""
        (temp_git_repo / '.markdownlint.json').write_text('{}\n')
        (temp_git_repo / 'configs').mkdir()
        (temp_git_repo / 'configs' / 'prettierignore.txt').write_text('.markdownlint.json\n')

        result = run_check('--pattern', 'markdownlint.json', cwd=temp_git_repo)

        assert result.returncode == 0
        assert 'All file references valid' not in result.stdout
        assert '1 hit matched the text and resolved to a path on disk' in result.stdout
        assert 'configs/prettierignore.txt:1' in result.stdout

    def moved_boards_repo(self, root):
        """`boards/` moved under `config/`, with a vendored copy that did not move.

        Two tokens, and the predicate has to separate them. Both resolve and
        both contain the old path, so a repo carrying only the repaired one
        cannot tell a working test from one that always passes.
        """
        boards = root / 'boards' / 'arm'
        boards.mkdir(parents=True)
        (boards / 'defconfig').write_text('CONFIG_ARM=y\n')
        subprocess.run(['git', 'add', '-A'], cwd=root, capture_output=True, check=True)
        subprocess.run(['git', 'commit', '-m', 'add boards'], cwd=root, capture_output=True, check=True)
        (root / 'config').mkdir()
        subprocess.run(['git', 'mv', 'boards', 'config/boards'], cwd=root, capture_output=True, check=True)
        vendored = root / 'vendor' / 'boards' / 'arm'
        vendored.mkdir(parents=True)
        (vendored / 'defconfig').write_text('CONFIG_ARM=y\n')
        return root

    def staged_moves(self, root):
        """The renames git has staged, as the patterns and replacements they become."""
        found = moves.staged(root)
        return {move.old: move.description for move in found}, {move.old: move.new for move in found if move.new}

    def test_moves_does_not_list_the_site_the_rename_repaired(self, temp_git_repo):
        """A token spelling the new path is a repair the record proves, so it is not named."""
        repo = self.moved_boards_repo(temp_git_repo)
        (repo / 'README.md').write_text('The board is config/boards/arm/defconfig now.\n')
        patterns, replacements = self.staged_moves(repo)

        checker = ReferenceChecker(repo)
        checker.check_patterns(patterns, replacements)

        assert checker.issues == []
        assert checker.set_aside == []

    def test_moves_lists_a_hit_the_rename_record_cannot_account_for(self, temp_git_repo):
        """A token that resolves and names neither the new path nor the new name is named.

        The move kept the filename, so `defconfig` sits inside the old path as
        well as the new one. Asking whether the token holds it asks what put
        the line here rather than what the token says, and every hit passes.
        """
        repo = self.moved_boards_repo(temp_git_repo)
        (repo / 'README.md').write_text('The pinned copy is vendor/boards/arm/defconfig.\n')
        patterns, replacements = self.staged_moves(repo)

        checker = ReferenceChecker(repo)
        checker.check_patterns(patterns, replacements)

        assert checker.issues == []
        assert [entry.token for entry in checker.set_aside] == ['vendor/boards/arm/defconfig']

    def test_moves_names_the_unaccounted_hit_through_the_cli_too(self, temp_git_repo):
        """The replacements reach the resolver from git, not only from a test."""
        repo = self.moved_boards_repo(temp_git_repo)
        (repo / 'README.md').write_text('The pinned copy is vendor/boards/arm/defconfig.\n')

        result = run_check('--moves', cwd=repo)

        assert result.returncode == 0
        assert 'README.md:1' in result.stdout
        assert 'vendor/boards/arm/defconfig' in result.stdout

    def test_an_unreadable_path_does_not_swallow_the_hits_that_were_set_aside(self, temp_git_repo):
        """Three outcomes are independent, so none of them may return in front of another.

        A clean run that also failed to read a directory printed the refusal
        and nothing else, which drops the whole list on exactly the runs that
        already covered less than the tree.
        """
        if os.geteuid() == 0:
            pytest.skip('root reads a 0o000 directory, so there is no refusal to observe')

        (temp_git_repo / '.markdownlint.json').write_text('{}\n')
        (temp_git_repo / 'configs').mkdir()
        (temp_git_repo / 'configs' / 'prettierignore.txt').write_text('.markdownlint.json\n')
        locked = temp_git_repo / 'locked'
        locked.mkdir()
        os.chmod(locked, 0o000)
        try:
            result = run_check('--pattern', 'markdownlint.json', cwd=temp_git_repo)
        finally:
            os.chmod(locked, 0o755)

        assert 'could not be read' in result.stdout
        assert 'configs/prettierignore.txt:1' in result.stdout

    def test_a_pattern_run_names_the_same_sites_moves_can_prove_are_repaired(self, temp_git_repo):
        """Typed in by hand there is no rename record, so the run says it is guessing."""
        boards = temp_git_repo / 'config' / 'boards' / 'arm'
        boards.mkdir(parents=True)
        (boards / 'defconfig').write_text('CONFIG_ARM=y\n')
        (temp_git_repo / 'README.md').write_text('The board is config/boards/arm/defconfig now.\n')

        result = run_check('--pattern', 'boards/arm/defconfig', cwd=temp_git_repo)

        assert result.returncode == 0
        assert '1 hit matched the text and resolved to a path on disk' in result.stdout
        assert 'README.md:1' in result.stdout


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

        result = run_check('--moves-since', 'HEAD~1', '--registry', str(registry), cwd=temp_git_repo)

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

        result = run_check('--moves-since', 'HEAD~1', '--registry', str(registry), cwd=temp_git_repo)

        assert result.returncode == 0
        assert 'No repo names a path that moved' in result.stdout

    def test_sweeps_a_pattern_named_by_hand(self, tmp_path, temp_git_repo):
        consumer = tmp_path / 'consumer'
        consumer.mkdir()
        (consumer / 'config.yml').write_text(f'versions_file: {temp_git_repo}/versions.json\n')
        registry = self.registry_at(tmp_path / 'reg.json', temp_git_repo, consumer)

        result = run_check('--pattern', 'versions.json', '--registry', str(registry), cwd=temp_git_repo)

        assert result.returncode == 1
        assert 'Gone from' in result.stdout

    def test_refuses_a_registry_with_nothing_to_sweep_for(self, tmp_path, temp_git_repo):
        """A sweep with no moved path asks ninety repos nothing and exits clean."""
        registry = self.registry_at(tmp_path / 'reg.json', temp_git_repo)

        result = run_check('--registry', str(registry), cwd=temp_git_repo)

        assert result.returncode == 2
        assert '--moves' in result.stderr

    def test_says_when_the_repo_the_paths_moved_in_is_not_listed(self, tmp_path, temp_git_repo):
        """A repo the registry never listed can own nothing, and that prints as clean."""
        consumer = tmp_path / 'consumer'
        consumer.mkdir()
        (consumer / 'config.yml').write_text(f'versions_file: {temp_git_repo}/versions.json\n')
        registry = self.registry_at(tmp_path / 'reg.json', consumer)

        result = run_check('--pattern', 'versions.json', '--registry', str(registry), cwd=temp_git_repo)

        assert 'is not in the registry' in result.stdout

    def test_counts_a_registry_entry_it_could_not_read(self, tmp_path, temp_git_repo):
        """An entry it could not read fails the run, rather than sitting inside the clean total."""
        (tmp_path / 'reg.json').write_text(json.dumps({'repos': [{'name': 'good', 'path': str(temp_git_repo)}, {'name': 'nameless'}]}))

        result = run_check('--pattern', 'versions.json', '--registry', str(tmp_path / 'reg.json'), cwd=temp_git_repo)

        assert result.returncode == 1
        assert 'nameless names no path' in result.stdout
        assert 'covered less than it claims' in result.stdout

    def test_refuses_a_registry_that_is_not_one(self, tmp_path, temp_git_repo):
        (tmp_path / 'reg.json').write_text('{not json')

        result = run_check('--pattern', 'x', '--registry', str(tmp_path / 'reg.json'), cwd=temp_git_repo)

        assert result.returncode == 2
        assert 'not valid JSON' in result.stderr

    def test_reports_a_citation_that_names_the_repo_it_reaches(self, tmp_path, temp_git_repo):
        """The reported false negative, through the registry file and the CLI.

        A document cited `<repo-name>/path/inside-it` and the rename deleted
        that path. The in-repo run found the citation. The --registry run, which
        is the only form that can see a consumer in another repo, reported clean
        across every repo it swept.
        """
        consumer = tmp_path / 'consumer'
        consumer.mkdir()
        (consumer / 'guide.md').write_text(f'The live reader is `{temp_git_repo.name}/versions.json`, which builds the pins.\n')
        registry = self.registry_at(tmp_path / 'reg.json', temp_git_repo, consumer)

        result = run_check('--pattern', 'versions.json', '--desc', 'now pinned', '--registry', str(registry), cwd=temp_git_repo)

        assert result.returncode == 1
        assert f'{consumer}/guide.md:1' in result.stdout
        assert f'Gone from {temp_git_repo.name}: versions.json' in result.stdout

    def test_the_registry_form_finds_what_the_in_repo_form_finds(self, tmp_path, temp_git_repo):
        """Two ways of extracting the same fact, required to agree.

        The bug was one form reporting a hit and the other a tick over the same
        line, and neither result carried anything saying the two disagreed. A
        single-form assertion cannot see that, so both run here and the lines are
        compared.
        """
        consumer = tmp_path / 'consumer'
        consumer.mkdir()
        (consumer / 'guide.md').write_text(
            f'The live reader is `{temp_git_repo.name}/versions.json`.\nAlso at {temp_git_repo}/versions.json today.\n'
        )
        registry = self.registry_at(tmp_path / 'reg.json', temp_git_repo, consumer)

        in_repo = run_check('--pattern', 'versions.json', cwd=consumer)
        through_registry = run_check('--pattern', 'versions.json', '--registry', str(registry), cwd=temp_git_repo)

        found_locally = {line for line in in_repo.stdout.splitlines() if 'guide.md:' in line}
        found_by_sweep = {line.split('/')[-1] for line in through_registry.stdout.splitlines() if 'guide.md:' in line}

        assert {line.strip() for line in found_locally} == {'guide.md:1', 'guide.md:2'}
        assert found_by_sweep == {'guide.md:1', 'guide.md:2'}

    def test_expands_a_home_relative_registry_path(self, tmp_path, temp_git_repo, monkeypatch):
        """The registry spells its paths with `~`, so an unexpanded one would sweep nothing."""
        monkeypatch.setenv('HOME', str(tmp_path))
        consumer = tmp_path / 'consumer'
        consumer.mkdir()
        (consumer / 'config.yml').write_text(f'versions_file: {temp_git_repo}/versions.json\n')
        registry = tmp_path / 'reg.json'
        registry.write_text(
            json.dumps(
                {
                    'repos': [
                        {'name': temp_git_repo.name, 'path': str(temp_git_repo), 'status': 'active'},
                        {'name': 'consumer', 'path': '~/consumer', 'status': 'active'},
                    ]
                }
            )
        )

        result = run_check('--pattern', 'versions.json', '--registry', str(registry), cwd=temp_git_repo)

        assert result.returncode == 1
        assert f'{consumer}/config.yml:1' in result.stdout

    def test_a_listed_repo_with_no_directory_fails_the_sweep(self, tmp_path, temp_git_repo):
        """A sweep that could not reach a repo has to say so, or its tick means nothing."""
        registry = tmp_path / 'reg.json'
        registry.write_text(
            json.dumps(
                {
                    'repos': [
                        {'name': temp_git_repo.name, 'path': str(temp_git_repo), 'status': 'active'},
                        {'name': 'never-cloned', 'path': str(tmp_path / 'never-cloned'), 'status': 'active'},
                    ]
                }
            )
        )

        result = run_check('--pattern', 'versions.json', '--registry', str(registry), cwd=temp_git_repo)

        assert result.returncode == 1
        assert 'never-cloned' in result.stdout
        assert 'covered less than it claims' in result.stdout

    def test_a_retired_repo_still_leaves_the_sweep_clean(self, tmp_path, temp_git_repo):
        """Retired is the deliberate skip the tool already had a vocabulary for."""
        registry = tmp_path / 'reg.json'
        retired = tmp_path / 'retired'
        retired.mkdir()
        registry.write_text(
            json.dumps(
                {
                    'repos': [
                        {'name': temp_git_repo.name, 'path': str(temp_git_repo), 'status': 'active'},
                        {'name': 'old', 'path': str(retired), 'status': 'retired'},
                    ]
                }
            )
        )

        result = run_check('--pattern', 'versions.json', '--registry', str(registry), cwd=temp_git_repo)

        assert result.returncode == 0
        assert 'skipped 1 retired' in result.stdout


class TestAPathTheScanCouldNotRead:
    """A tree it could only partly open still printed the tick."""

    def test_a_directory_that_will_not_list_fails_the_run(self, temp_git_repo):
        if os.geteuid() == 0:
            pytest.skip('root reads a 0o000 directory, so there is no refusal to observe')

        locked = temp_git_repo / 'locked'
        locked.mkdir()
        os.chmod(locked, 0o000)
        try:
            result = run_check(cwd=temp_git_repo)
        finally:
            os.chmod(locked, 0o755)

        assert result.returncode == 1
        assert 'could not be read' in result.stdout
        assert 'locked' in result.stdout

    def test_the_sweep_prints_no_tick_over_a_repo_it_could_not_read(self, tmp_path, temp_git_repo):
        """The tick claims every repo the caller named, so one unread repo removes it."""
        registry = tmp_path / 'reg.json'
        registry.write_text(
            json.dumps(
                {
                    'repos': [
                        {'name': temp_git_repo.name, 'path': str(temp_git_repo), 'status': 'active'},
                        {'name': 'never-cloned', 'path': str(tmp_path / 'never-cloned'), 'status': 'active'},
                    ]
                }
            )
        )

        result = run_check('--pattern', 'versions.json', '--registry', str(registry), cwd=temp_git_repo)

        assert result.returncode == 1
        assert 'No repo names a path that moved' not in result.stdout
        assert 'could not read everything it was given' in result.stdout

    def test_an_unreadable_excluded_directory_does_not_fail_the_run(self, temp_git_repo):
        """`node_modules` is excluded by declaration, so a refusal inside it is not a gap."""
        if os.geteuid() == 0:
            pytest.skip('root reads a 0o000 directory, so there is no refusal to observe')

        blocked = temp_git_repo / 'node_modules' / 'blocked'
        blocked.mkdir(parents=True)
        os.chmod(blocked, 0o000)
        try:
            result = run_check(cwd=temp_git_repo)
        finally:
            os.chmod(blocked, 0o755)

        assert result.returncode == 0
        assert 'could not be read' not in result.stdout

    def test_a_path_is_tested_as_written_rather_than_with_its_undecodable_bytes_dropped(self, temp_git_repo):
        """Dropping bytes it cannot decode hands on a path nobody wrote."""
        accented = 'See ~/x/r\xe9sum\xe9s/versions.json for the pins.\n'
        (temp_git_repo / 'notes.md').write_bytes(accented.encode('latin-1'))

        result = run_check('--pattern', 'versions.json', cwd=temp_git_repo)

        assert 'notes.md' not in result.stdout

    def test_a_directory_that_is_not_there_is_refused(self, temp_git_repo):
        """Walking a path that does not exist finds nothing and passes every check."""
        result = run_check('management/', cwd=temp_git_repo)

        assert result.returncode == 2
        assert 'is not there' in result.stderr
