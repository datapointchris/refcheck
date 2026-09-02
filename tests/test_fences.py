"""Which fenced blocks in a markdown file hold shell, and which hold something else.

A doc that prints refcheck's own output inside a fence gets that output read
back as source code: the sample names `tests/helpers.sh`, `tests/` is a real
directory, and every guard downstream passes it through. A checker is worth
exactly its false-positive rate, so a block tagged as another language is not
read as shell.

The other half is the one that keeps the fix honest. A bare fence and a shell
fence are still read, because that is where the stale references docs carry
actually live.
"""

from pathlib import Path

from refcheck.checker import ReferenceChecker


def check(root: Path, body: str) -> list[str]:
    """Every issue refcheck raises against a one-file repo holding `body`."""
    (root / 'tests').mkdir(exist_ok=True)
    (root / 'README.md').write_text(body)

    checker = ReferenceChecker(root_dir=root)
    checker.run_all_checks()
    return [issue.message for issue in checker.issues]


def test_a_yaml_block_is_not_read_as_shell(tmp_path: Path) -> None:
    """The reported case: refcheck's own output, quoted in refcheck's own README."""
    issues = check(
        tmp_path,
        '# Sample\n\n```yaml\nWarnings:\n  scripts/deploy.sh:3\n    bash tests/helpers.sh\n```\n',
    )

    assert issues == []


def test_a_source_statement_in_a_non_shell_block_is_not_read_as_shell(tmp_path: Path) -> None:
    """`source` and `bash` are two checks, and the block puts both out of scope."""
    issues = check(
        tmp_path,
        '# Sample\n\n```text\nErrors:\n  scripts/deploy.sh:4\n    source tests/helpers.sh\n```\n',
    )

    assert issues == []


def test_a_bash_block_is_still_read(tmp_path: Path) -> None:
    """The half that matters after a false-positive fix.

    Suppressing a block stops the noise the same way resolving a path does. The
    difference only shows on a block that is genuinely shell.
    """
    issues = check(tmp_path, '# Guide\n\n```bash\nbash tests/helpers.sh\nsource tests/helpers.sh\n```\n')

    assert len(issues) == 2
    assert all('tests/helpers.sh' in issue for issue in issues)


def test_an_untagged_block_is_still_read(tmp_path: Path) -> None:
    """An untagged block is very commonly shell, so nothing suppresses it."""
    issues = check(tmp_path, '# Guide\n\n```\nbash tests/helpers.sh\n```\n')

    assert len(issues) == 1


def test_a_console_block_is_still_read(tmp_path: Path) -> None:
    """The spelling a transcript uses, and a transcript is a documented invocation."""
    issues = check(tmp_path, '# Guide\n\n```console\n$ bash tests/helpers.sh\n```\n')

    assert len(issues) == 1


def test_prose_after_a_non_shell_block_is_still_read(tmp_path: Path) -> None:
    """The fence has to close, or the rest of the file goes unchecked."""
    issues = check(
        tmp_path,
        '# Guide\n\n```yaml\nbash tests/ignored.sh\n```\n\nThen run `bash tests/helpers.sh` to finish.\n',
    )

    assert len(issues) == 1
    assert 'tests/helpers.sh' in issues[0]


def test_a_tilde_fence_suppresses_its_block(tmp_path: Path) -> None:
    """Markdown opens a fence on tildes as readily as on backticks."""
    issues = check(tmp_path, '# Sample\n\n~~~yaml\nbash tests/helpers.sh\n~~~\n')

    assert issues == []


def test_a_shorter_run_inside_a_longer_fence_does_not_close_it(tmp_path: Path) -> None:
    """A doc showing a fence has to nest one, and the inner run is not the closer."""
    issues = check(
        tmp_path,
        '# Sample\n\n````yaml\n```\nbash tests/helpers.sh\n```\n````\n',
    )

    assert issues == []


def test_a_fence_attribute_line_is_not_an_invocation(tmp_path: Path) -> None:
    """```bash file=x.sh opens a block; its attributes are not a command."""
    issues = check(tmp_path, '# Guide\n\n```bash file=tests/nowhere.sh\necho hi\n```\n')

    assert issues == []


def test_a_shell_script_has_no_fences(tmp_path: Path) -> None:
    """Backticks in a heredoc are content, so nothing in a .sh file is suppressed."""
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'run.sh').write_text('#!/usr/bin/env bash\nbash tests/helpers.sh\n')

    checker = ReferenceChecker(root_dir=tmp_path)
    checker.run_all_checks()

    assert len(checker.issues) == 1
