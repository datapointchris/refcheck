"""Tests for reading renames and deletions out of git."""

import subprocess

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

    def test_unknown_ref_is_not_a_crash(self, temp_git_repo):
        assert moves.since('no-such-ref', temp_git_repo) == []
