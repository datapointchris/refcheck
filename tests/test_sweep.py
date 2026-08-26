"""Tests for the move sweep run across repos rather than in one.

The reporting rule is the whole question. A basename swept over ninety repos
hits unrelated files in unrelated projects, and three of refcheck's first five
findings being its own bugs is why it went unused. So every shape that must stay
silent gets its own test, beside the ones that must fire.
"""

import pytest

from refcheck import sweep
from refcheck.registry import Repo


@pytest.fixture
def two_repos(temp_dir):
    """A repo that moved a file, and a repo that names it."""
    upstream = temp_dir / 'upstream'
    consumer = temp_dir / 'consumer'
    upstream.mkdir()
    consumer.mkdir()
    (upstream / 'pinned-versions.json').write_text('{}\n')
    return upstream, consumer


def repos_for(*paths):
    return [Repo(name=path.name, path=path, status='active') for path in paths]


def names(sweep_result):
    return [f'{result.repo.name}:{issue.file}' for result in sweep_result.with_issues for issue in result.issues]


class TestTheReferenceThatBroke:
    """The case the sweep exists for: a consumer left holding the old path."""

    def test_reports_an_absolute_path_that_is_gone(self, two_repos):
        upstream, consumer = two_repos
        (consumer / 'config.yml').write_text(f'versions_file: {upstream}/versions.json\n')

        result = sweep.across_repos(repos_for(upstream, consumer), {'versions.json': 'now pinned-versions.json'})

        assert names(result) == ['consumer:config.yml']
        assert result.issues[0].message == 'Gone from upstream: versions.json'
        assert result.issues[0].suggestion == 'now pinned-versions.json'

    def test_reports_a_home_relative_path_that_is_gone(self, two_repos, monkeypatch):
        """The reference that actually broke was `~`-rooted, not absolute."""
        upstream, consumer = two_repos
        monkeypatch.setenv('HOME', str(upstream.parent))
        (consumer / 'config.yml').write_text('versions_file: ~/upstream/versions.json\n')

        result = sweep.across_repos(repos_for(upstream, consumer), {'versions.json': 'now pinned-versions.json'})

        assert names(result) == ['consumer:config.yml']

    def test_reports_a_path_behind_a_variable_that_is_set(self, two_repos, monkeypatch):
        upstream, consumer = two_repos
        monkeypatch.setenv('UPSTREAM_DIR', str(upstream))
        (consumer / 'config.yml').write_text('versions_file: $UPSTREAM_DIR/versions.json\n')

        result = sweep.across_repos(repos_for(upstream, consumer), {'versions.json': 'now pinned-versions.json'})

        assert names(result) == ['consumer:config.yml']

    def test_reports_a_deletion_the_same_way(self, two_repos):
        upstream, consumer = two_repos
        (consumer / 'config.yml').write_text(f'versions_file: {upstream}/versions.json\n')

        result = sweep.across_repos(repos_for(upstream, consumer), {'versions.json': 'deleted in this change'})

        assert names(result) == ['consumer:config.yml']


class TestWhatStaysSilent:
    """Every shape a basename hits that is not a reference into another repo."""

    def test_the_corrected_reference(self, two_repos):
        """The name that replaced it contains the name it replaced."""
        upstream, consumer = two_repos
        (consumer / 'config.yml').write_text(f'versions_file: {upstream}/pinned-versions.json\n')

        assert names(sweep.across_repos(repos_for(upstream, consumer), {'versions.json': 'now pinned-versions.json'})) == []

    def test_a_bare_filename_in_prose(self, two_repos):
        upstream, consumer = two_repos
        (consumer / 'README.md').write_text('The pins live in versions.json at the root.\n')

        assert names(sweep.across_repos(repos_for(upstream, consumer), {'versions.json': 'now pinned-versions.json'})) == []

    def test_a_filename_literal_in_code(self, two_repos):
        upstream, consumer = two_repos
        (consumer / 'load.py').write_text('PINS = "versions.json"\n')

        assert names(sweep.across_repos(repos_for(upstream, consumer), {'versions.json': 'now pinned-versions.json'})) == []

    def test_the_repos_own_file_of_the_same_name(self, two_repos):
        """A consumer with its own versions.json is naming its own file."""
        upstream, consumer = two_repos
        (consumer / 'versions.json').write_text('{}\n')
        (consumer / 'load.py').write_text('PINS = "config/versions.json"\nOWN = "versions.json"\n')

        assert names(sweep.across_repos(repos_for(upstream, consumer), {'versions.json': 'now pinned-versions.json'})) == []

    def test_a_missing_path_in_no_listed_repo(self, two_repos):
        """`/srv/versions.json` names nowhere the registry knows, so it is nobody's stale reference."""
        upstream, consumer = two_repos
        (consumer / 'config.yml').write_text('versions_file: /srv/versions.json\n')

        assert names(sweep.across_repos(repos_for(upstream, consumer), {'versions.json': 'now pinned-versions.json'})) == []

    def test_a_variable_this_process_does_not_carry(self, two_repos):
        upstream, consumer = two_repos
        (consumer / 'config.yml').write_text('versions_file: $NOT_SET_ANYWHERE/versions.json\n')

        assert names(sweep.across_repos(repos_for(upstream, consumer), {'versions.json': 'now pinned-versions.json'})) == []

    def test_a_url_carrying_the_name(self, two_repos):
        upstream, consumer = two_repos
        (consumer / 'README.md').write_text(f'See https://example.com{upstream}/versions.json for the pins.\n')

        assert names(sweep.across_repos(repos_for(upstream, consumer), {'versions.json': 'now pinned-versions.json'})) == []

    def test_a_repo_naming_its_own_missing_path(self, two_repos):
        """The repo that moved the file answers for itself through --moves, not the sweep."""
        upstream, consumer = two_repos
        (upstream / 'notes.md').write_text(f'Pins were at {upstream}/versions.json\n')

        assert names(sweep.across_repos(repos_for(upstream, consumer), {'versions.json': 'now pinned-versions.json'})) == []


class TestWhatWasNotSwept:
    """A sweep covering fewer repos than the caller believes is a false clean."""

    def test_a_retired_repo_is_reported_as_skipped(self, two_repos):
        upstream, consumer = two_repos
        repos = [Repo(name='upstream', path=upstream, status='active'), Repo(name='old', path=consumer, status='retired')]

        result = sweep.across_repos(repos, {'versions.json': 'now pinned-versions.json'})

        assert [repo.name for repo in result.retired] == ['old']
        assert result.scanned == 1

    def test_a_path_that_is_not_there_is_reported_as_skipped(self, two_repos):
        upstream, _ = two_repos
        repos = [Repo(name='upstream', path=upstream, status='active'), Repo(name='gone', path=upstream / 'nowhere', status='active')]

        result = sweep.across_repos(repos, {'versions.json': 'now pinned-versions.json'})

        assert [repo.name for repo in result.absent] == ['gone']
        assert result.scanned == 1

    def test_no_patterns_reads_no_repo(self, two_repos):
        """Reporting a clean 90 after reading no files is the false clean, not a pass."""
        upstream, consumer = two_repos
        (consumer / 'config.yml').write_text(f'versions_file: {upstream}/versions.json\n')

        result = sweep.across_repos(repos_for(upstream, consumer), {})

        assert result.issues == []
        assert result.scanned == 0
