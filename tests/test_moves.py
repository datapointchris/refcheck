"""Tests for reading renames and deletions out of git."""

import subprocess

import pytest

from refcheck import moves


def git(repo, *args):
    subprocess.run(['git', *args], cwd=repo, capture_output=True, check=True)


def commit(repo, message):
    git(repo, 'add', '-A')
    git(repo, 'commit', '-m', message)


class TestStagedMoves:
    """What a pre-commit hook sees in the index."""

    def test_reads_a_staged_rename(self, temp_git_repo):
        (temp_git_repo / 'lib').mkdir()
        (temp_git_repo / 'lib' / 'helpers.sh').write_text('echo hi\n')
        commit(temp_git_repo, 'add helpers')

        (temp_git_repo / 'shared').mkdir()
        git(temp_git_repo, 'mv', 'lib/helpers.sh', 'shared/helpers.sh')

        found = moves.staged(temp_git_repo)
        assert [(m.old, m.new) for m in found] == [('lib/helpers.sh', 'shared/helpers.sh')]
        assert found[0].description == 'now shared/helpers.sh'

    def test_reads_a_staged_deletion(self, temp_git_repo):
        (temp_git_repo / 'lib').mkdir()
        (temp_git_repo / 'lib' / 'gone.sh').write_text('echo hi\n')
        commit(temp_git_repo, 'add gone')

        git(temp_git_repo, 'rm', 'lib/gone.sh')

        found = moves.staged(temp_git_repo)
        assert [(m.old, m.new) for m in found] == [('lib/gone.sh', None)]
        assert found[0].description == 'deleted in this change'

    def test_skips_a_bare_filename(self, temp_git_repo):
        """`main.go` is in every Go repo's prose; a substring hit is not evidence."""
        (temp_git_repo / 'main.go').write_text('package main\n')
        commit(temp_git_repo, 'add main')

        git(temp_git_repo, 'rm', 'main.go')

        assert moves.staged(temp_git_repo) == []

    def test_keeps_a_bare_filename_when_the_caller_asks(self, temp_git_repo):
        """A sweep across other repos settles a bare name by absolute path instead.

        A registry file renamed at a repo root has no directory in front of
        it, so filtering bare names leaves such a sweep nothing to look for.
        """
        (temp_git_repo / 'versions.json').write_text('{}\n')
        commit(temp_git_repo, 'add versions')

        git(temp_git_repo, 'mv', 'versions.json', 'pinned-versions.json')

        found = moves.staged(temp_git_repo, include_bare_names=True)
        assert [(m.old, m.new) for m in found] == [('versions.json', 'pinned-versions.json')]
        assert found[0].is_bare

    def test_a_path_with_a_directory_is_not_bare(self, temp_git_repo):
        (temp_git_repo / 'lib').mkdir()
        (temp_git_repo / 'lib' / 'helpers.sh').write_text('echo hi\n')
        commit(temp_git_repo, 'add helpers')

        git(temp_git_repo, 'rm', 'lib/helpers.sh')

        assert not moves.staged(temp_git_repo)[0].is_bare

    def test_skips_a_path_that_is_back(self, temp_git_repo):
        """Moved away and replaced within one change: nothing points at a live name."""
        (temp_git_repo / 'lib').mkdir()
        (temp_git_repo / 'lib' / 'helpers.sh').write_text('echo old\n')
        commit(temp_git_repo, 'add helpers')

        git(temp_git_repo, 'mv', 'lib/helpers.sh', 'lib/renamed.sh')
        (temp_git_repo / 'lib' / 'helpers.sh').write_text('echo new\n')
        git(temp_git_repo, 'add', '-A')

        assert [m.old for m in moves.staged(temp_git_repo)] == []

    def test_nothing_staged_is_no_moves(self, temp_git_repo):
        assert moves.staged(temp_git_repo) == []


class TestMovesSince:
    """The same question over a range, for CI and manual runs."""

    def test_reads_a_committed_rename(self, temp_git_repo):
        (temp_git_repo / 'lib').mkdir()
        (temp_git_repo / 'lib' / 'helpers.sh').write_text('echo hi\n')
        commit(temp_git_repo, 'add helpers')
        base = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            cwd=temp_git_repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        (temp_git_repo / 'shared').mkdir()
        git(temp_git_repo, 'mv', 'lib/helpers.sh', 'shared/helpers.sh')
        commit(temp_git_repo, 'move helpers')

        found = moves.since(base, temp_git_repo)
        assert [(m.old, m.new) for m in found] == [('lib/helpers.sh', 'shared/helpers.sh')]

    def test_an_unknown_ref_raises_rather_than_reading_as_no_moves(self, temp_git_repo):
        with pytest.raises(moves.UnreadableChange):
            moves.since('no-such-ref', temp_git_repo)


def head(repo):
    return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()


class TestMovesInThePreCommitChange:
    """`--moves` reads whatever change pre-commit is checking."""

    def test_reads_the_range_pre_commit_exports(self, temp_git_repo, monkeypatch):
        (temp_git_repo / 'lib').mkdir()
        (temp_git_repo / 'lib' / 'helpers.sh').write_text('echo hi\n')
        commit(temp_git_repo, 'add helpers')
        base = head(temp_git_repo)
        (temp_git_repo / 'shared').mkdir()
        git(temp_git_repo, 'mv', 'lib/helpers.sh', 'shared/helpers.sh')
        commit(temp_git_repo, 'move helpers')

        monkeypatch.setenv('PRE_COMMIT_FROM_REF', base)
        monkeypatch.setenv('PRE_COMMIT_TO_REF', head(temp_git_repo))

        found = moves.in_pre_commit_change(temp_git_repo)
        assert [(m.old, m.new) for m in found] == [('lib/helpers.sh', 'shared/helpers.sh')]

    def test_reads_the_index_when_pre_commit_names_no_range(self, temp_git_repo):
        (temp_git_repo / 'lib').mkdir()
        (temp_git_repo / 'lib' / 'helpers.sh').write_text('echo hi\n')
        commit(temp_git_repo, 'add helpers')
        (temp_git_repo / 'shared').mkdir()
        git(temp_git_repo, 'mv', 'lib/helpers.sh', 'shared/helpers.sh')

        found = moves.in_pre_commit_change(temp_git_repo)
        assert [(m.old, m.new) for m in found] == [('lib/helpers.sh', 'shared/helpers.sh')]
