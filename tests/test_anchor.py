"""Where a referenced path is looked for, which is three places and was two.

A `~/` reference is the *deployed* spelling — the one a script that runs outside
the repo has to use. It was joined onto the repo root like a relative path, which
produces `<repo>/~/…` and cannot exist for any input, so every tilde reference
was reported missing on every run.

Measured on dotfiles: three deployed shell libraries sourced by
`tests/apps/all-apps.sh`, all three resolving fine, all three reported. That is a
checker spending its whole value on noise — it is worth exactly its
false-positive rate, and standing errors are what teach a reader to skim past the
findings that are real.
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
