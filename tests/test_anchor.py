"""Where a referenced path is looked for, which is three places and was two.

A `~/` reference is the *deployed* spelling — the one a script that runs outside
the repo has to use. It was joined onto the repo root like a relative path, which
produces `<repo>/~/…` and cannot exist for any input, so every tilde reference
was reported missing on every run.

Measured on a repo whose only three errors were these: three deployed shell
libraries sourced by one test script, all three resolving fine, all three
reported. That is a checker spending its whole value on noise — it is worth
exactly its false-positive rate, and three standing errors out of three is what
teaches a reader to skim past the findings that are real.
"""

from pathlib import Path

from refcheck.checker import ReferenceChecker


def test_a_tilde_path_is_looked_for_under_home(tmp_path: Path) -> None:
    """Not under the repo, which is where every one of them was looked for."""
    checker = ReferenceChecker(root_dir=tmp_path)

    anchored = checker.anchor('~/.local/shell/logging.sh')

    assert anchored == Path.home() / '.local/shell/logging.sh'
    assert tmp_path not in anchored.parents


def test_an_absolute_path_is_itself(tmp_path: Path) -> None:
    checker = ReferenceChecker(root_dir=tmp_path)

    assert checker.anchor('/etc/os-release') == Path('/etc/os-release')


def test_a_bare_path_hangs_off_the_repo(tmp_path: Path) -> None:
    """The common case, and the one the other two are told apart from."""
    checker = ReferenceChecker(root_dir=tmp_path)

    assert checker.anchor('install/lib/logging.sh') == tmp_path / 'install/lib/logging.sh'


def test_a_tilde_path_that_is_not_there_is_still_reported(tmp_path: Path) -> None:
    """The half that matters after a false-positive fix.

    Expanding `~` stops the noise by making the reference resolvable, which is
    the same shape as stopping it by not looking. The difference is only visible
    on a path that genuinely is not there.
    """
    checker = ReferenceChecker(root_dir=tmp_path)

    assert not checker.anchor('~/.local/shell/nonexistent-xyz.sh').exists()


def _deploying_repo(tmp_path: Path, tracked: str) -> Path:
    """A repo tracking one file, with a home that holds nothing it deploys."""
    repo = tmp_path / 'repo'
    (repo / tracked).parent.mkdir(parents=True)
    (repo / tracked).write_text('')
    (tmp_path / 'home').mkdir()
    return repo


def test_a_tilde_path_the_repo_deploys_resolves_on_an_empty_home(tmp_path: Path, monkeypatch) -> None:
    """A CI runner's home, where nothing the repo installs has been installed."""
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    repo = _deploying_repo(tmp_path, 'configs/common/.local/shell/logging.sh')

    assert ReferenceChecker(root_dir=repo).resolves('~/.local/shell/logging.sh')


def test_a_repo_file_sharing_only_the_basename_does_not_satisfy_a_tilde_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    repo = _deploying_repo(tmp_path, 'lib/logging.sh')

    assert not ReferenceChecker(root_dir=repo).resolves('~/.local/shell/logging.sh')


def test_a_script_sourcing_what_its_repo_deploys_is_not_reported(tmp_path: Path, monkeypatch) -> None:
    """The source check asks resolves, not anchor alone."""
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    repo = _deploying_repo(tmp_path, 'configs/common/.local/shell/logging.sh')
    (repo / 'tests').mkdir()
    (repo / 'tests/loads.sh').write_text('#!/usr/bin/env bash\nsource ~/.local/shell/logging.sh\nsource ~/.local/shell/gone.sh\n')
    checker = ReferenceChecker(root_dir=repo)

    checker.check_source_statements()

    assert [issue.message for issue in checker.issues] == ['Missing: ~/.local/shell/gone.sh']
