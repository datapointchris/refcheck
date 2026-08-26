"""Tests for the move sweep run across repos rather than in one.

The reporting rule is the whole question. A basename swept over ninety repos
hits unrelated files in unrelated projects, and three of refcheck's first five
findings being its own bugs is why it went unused. So every shape that must stay
silent gets its own test, beside the ones that must fire.
"""

import pytest

from refcheck import sweep
from refcheck.registry import Registry
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
    return Registry(repos=[Repo(name=path.name, path=path, status='active') for path in paths], unusable=[])


def listing(*repos, unusable=()):
    return Registry(repos=list(repos), unusable=list(unusable))


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


class TestWhoCanOwnAGonePath:
    """Which repos are walked and which can own a gone path are different questions."""

    def test_a_reference_into_a_retired_repo_is_still_reported(self, two_repos):
        """The finding is in a live repo and so is its fix, whatever the owner's status."""
        upstream, consumer = two_repos
        (consumer / 'config.yml').write_text(f'versions_file: {upstream}/versions.json\n')
        listed = listing(Repo(name='upstream', path=upstream, status='retired'), Repo(name='consumer', path=consumer, status='active'))

        result = sweep.across_repos(listed, {'versions.json': 'now pinned-versions.json'})

        assert names(result) == ['consumer:config.yml']
        assert result.issues[0].message == 'Gone from upstream: versions.json'
        assert [repo.name for repo in result.retired] == ['upstream']

    def test_a_reference_into_a_repo_this_machine_lacks_is_not_reported(self, two_repos):
        """Nothing in an absent repo exists, so every reference into one would hit."""
        upstream, consumer = two_repos
        (consumer / 'config.yml').write_text(f'versions_file: {upstream.parent}/never-cloned/versions.json\n')
        listed = listing(
            Repo(name='never-cloned', path=upstream.parent / 'never-cloned', status='active'),
            Repo(name='consumer', path=consumer, status='active'),
        )

        assert names(sweep.across_repos(listed, {'versions.json': 'now pinned-versions.json'})) == []

    def test_a_traversal_still_lands_inside_the_repo_it_names(self, two_repos):
        """`is_relative_to` is a string comparison, so it gets the walked-out path."""
        upstream, consumer = two_repos
        (consumer / 'config.yml').write_text(f'versions_file: {consumer}/../upstream/versions.json\n')

        result = sweep.across_repos(repos_for(upstream, consumer), {'versions.json': 'now pinned-versions.json'})

        assert names(result) == ['consumer:config.yml']
        assert result.issues[0].message == 'Gone from upstream: versions.json'

    def test_a_traversal_through_a_symlink_is_not_reported_when_the_file_is_there(self, temp_dir):
        """The path a program opens is the one as written, so that is what existence asks about.

        `repo/link/../versions.json` where `link` points away resolves to a real
        file. Flattening it first asks about `repo/versions.json`, which is a
        different file and is not there.
        """
        repo, elsewhere, consumer = temp_dir / 'repo', temp_dir / 'elsewhere', temp_dir / 'consumer'
        for directory in (repo, elsewhere, consumer):
            directory.mkdir()
        (temp_dir / 'versions.json').write_text('{}\n')
        (repo / 'link').symlink_to(elsewhere)
        (consumer / 'config.yml').write_text(f'versions_file: {repo}/link/../versions.json\n')

        listed = repos_for(repo, consumer)
        assert names(sweep.across_repos(listed, {'versions.json': 'now pinned-versions.json'})) == []

    def test_a_traversal_through_a_symlink_is_credited_to_the_repo_holding_the_file(self, temp_dir):
        """Containment follows the link, so the owner is where the file actually was."""
        repo, elsewhere, consumer = temp_dir / 'repo', temp_dir / 'elsewhere', temp_dir / 'consumer'
        for directory in (repo, elsewhere, consumer):
            directory.mkdir()
        (repo / 'link').symlink_to(elsewhere)
        (consumer / 'config.yml').write_text(f'versions_file: {repo}/link/../versions.json\n')

        listed = listing(
            Repo(name='outer', path=temp_dir, status='active'),
            Repo(name='repo', path=repo, status='active'),
            Repo(name='consumer', path=consumer, status='active'),
        )
        result = sweep.across_repos(listed, {'versions.json': 'now pinned-versions.json'})

        assert names(result) == ['consumer:config.yml']
        assert result.issues[0].message == 'Gone from outer: versions.json'

    def test_a_repo_reached_through_a_symlinked_parent_is_credited(self, temp_dir):
        """`~/link/versions.json` where link points into a listed repo names a file in it."""
        upstream, consumer = temp_dir / 'upstream', temp_dir / 'consumer'
        upstream.mkdir()
        consumer.mkdir()
        (temp_dir / 'link').symlink_to(upstream)
        (consumer / 'config.yml').write_text(f'versions_file: {temp_dir}/link/versions.json\n')

        result = sweep.across_repos(repos_for(upstream, consumer), {'versions.json': 'now pinned-versions.json'})

        assert names(result) == ['consumer:config.yml']
        assert result.issues[0].message == 'Gone from upstream: versions.json'

    def test_a_repo_whose_declared_path_is_a_symlink_still_owns_its_files(self, temp_dir):
        """A registry may name a repo at a link, so homes are keyed physically too."""
        real, consumer = temp_dir / 'real-upstream', temp_dir / 'consumer'
        real.mkdir()
        consumer.mkdir()
        (temp_dir / 'declared').symlink_to(real)
        (consumer / 'config.yml').write_text(f'versions_file: {temp_dir}/declared/versions.json\n')

        listed = listing(
            Repo(name='upstream', path=temp_dir / 'declared', status='active'),
            Repo(name='consumer', path=consumer, status='active'),
        )
        result = sweep.across_repos(listed, {'versions.json': 'now pinned-versions.json'})

        assert names(result) == ['consumer:config.yml']
        assert result.issues[0].message == 'Gone from upstream: versions.json'

    def test_a_repo_does_not_report_its_own_missing_path_through_a_symlink(self, temp_dir):
        """The self-exclusion compares physical roots, so a symlinked checkout still excludes itself."""
        real, consumer = temp_dir / 'real-upstream', temp_dir / 'consumer'
        real.mkdir()
        consumer.mkdir()
        (temp_dir / 'upstream').symlink_to(real)
        (real / 'notes.md').write_text(f'Pins were at {temp_dir}/upstream/versions.json\n')

        listed = listing(
            Repo(name='upstream', path=temp_dir / 'upstream', status='active'),
            Repo(name='consumer', path=consumer, status='active'),
        )

        assert names(sweep.across_repos(listed, {'versions.json': 'now pinned-versions.json'})) == []


class TestTheRepoThePathsMovedIn:
    """A repo the registry never listed can own nothing, and that prints as clean."""

    def test_says_so_when_the_source_repo_is_not_listed(self, two_repos):
        upstream, consumer = two_repos

        result = sweep.across_repos(
            listing(Repo(name='consumer', path=consumer, status='active')),
            {'versions.json': 'now pinned-versions.json'},
            source_root=upstream,
        )

        assert not result.source_is_listed
        assert result.source_root == upstream

    def test_stays_quiet_when_it_is_listed(self, two_repos):
        upstream, consumer = two_repos

        result = sweep.across_repos(
            repos_for(upstream, consumer),
            {'versions.json': 'now pinned-versions.json'},
            source_root=upstream,
        )

        assert result.source_is_listed

    def test_an_unusable_entry_is_carried_into_the_result(self, two_repos):
        upstream, consumer = two_repos
        listed = listing(*repos_for(upstream, consumer).repos, unusable=['nameless names no path'])

        result = sweep.across_repos(listed, {'versions.json': 'now pinned-versions.json'})

        assert result.unusable == ['nameless names no path']


class TestNarrowingReachesEveryRepo:
    """A filter that narrows the local run and silently not the sweep is the defect."""

    def test_skip_docs_reaches_the_sweep(self, two_repos):
        upstream, consumer = two_repos
        (consumer / 'notes.md').write_text(f'The pins are at {upstream}/versions.json\n')

        pattern = {'versions.json': 'now pinned-versions.json'}
        assert names(sweep.across_repos(repos_for(upstream, consumer), pattern)) == ['consumer:notes.md']
        assert names(sweep.across_repos(repos_for(upstream, consumer), pattern, skip_docs=True)) == []

    def test_file_type_reaches_the_sweep(self, two_repos):
        upstream, consumer = two_repos
        (consumer / 'config.yml').write_text(f'versions_file: {upstream}/versions.json\n')
        (consumer / 'load.py').write_text(f'PINS = "{upstream}/versions.json"\n')

        pattern = {'versions.json': 'now pinned-versions.json'}
        assert names(sweep.across_repos(repos_for(upstream, consumer), pattern, file_type='py')) == ['consumer:load.py']

    def test_an_exclude_glob_reaches_the_sweep(self, two_repos):
        upstream, consumer = two_repos
        (consumer / 'build').mkdir()
        (consumer / 'build' / 'report.txt').write_text(f'ran against {upstream}/versions.json\n')

        pattern = {'versions.json': 'now pinned-versions.json'}
        assert names(sweep.across_repos(repos_for(upstream, consumer), pattern)) == ['consumer:build/report.txt']
        assert names(sweep.across_repos(repos_for(upstream, consumer), pattern, flag_excludes=['build/**'])) == []

    def test_a_repos_own_exclusions_still_apply(self, two_repos):
        """Which directories hold generated output is a fact only each repo knows."""
        upstream, consumer = two_repos
        (consumer / '.refcheck.toml').write_text('[scan]\nexclude = ["reports/**"]\n')
        (consumer / 'reports').mkdir()
        (consumer / 'reports' / 'run.txt').write_text(f'ran against {upstream}/versions.json\n')

        assert names(sweep.across_repos(repos_for(upstream, consumer), {'versions.json': 'now pinned-versions.json'})) == []


class TestWhatWasNotSwept:
    """A sweep covering fewer repos than the caller believes is a false clean."""

    def test_a_retired_repo_is_reported_as_skipped(self, two_repos):
        upstream, consumer = two_repos
        listed = listing(Repo(name='upstream', path=upstream, status='active'), Repo(name='old', path=consumer, status='retired'))

        result = sweep.across_repos(listed, {'versions.json': 'now pinned-versions.json'})

        assert [repo.name for repo in result.retired] == ['old']
        assert result.scanned == 1

    def test_a_path_that_is_not_there_is_reported_as_skipped(self, two_repos):
        upstream, _ = two_repos
        listed = listing(
            Repo(name='upstream', path=upstream, status='active'), Repo(name='gone', path=upstream / 'nowhere', status='active')
        )

        result = sweep.across_repos(listed, {'versions.json': 'now pinned-versions.json'})

        assert [repo.name for repo in result.absent] == ['gone']
        assert result.scanned == 1

    def test_no_patterns_reads_no_repo(self, two_repos):
        """Reporting a clean 90 after reading no files is the false clean, not a pass."""
        upstream, consumer = two_repos
        (consumer / 'config.yml').write_text(f'versions_file: {upstream}/versions.json\n')

        result = sweep.across_repos(repos_for(upstream, consumer), {})

        assert result.issues == []
        assert result.scanned == 0
