"""Command-line interface for refcheck."""

from pathlib import Path
from typing import Annotated

import typer
from pyselfupdate import notify

from .checker import ReferenceChecker
from .config import load_config
from .output import print_results
from .rules import learn_rules_from_git
from .selfupdate import CONFIG as UPDATE_CONFIG
from .selfupdate import print_version
from .selfupdate import run_update

HELP = (
    'Find file references that no longer resolve, and path patterns that will break the next time '
    'something moves. A reference breaks in the file that was not edited, so refcheck always reads the '
    'whole tree rather than a changeset. Give it a directory to narrow the search, or --pattern to ask '
    'the one question a move leaves behind: what still points at the old name?'
)

EPILOG = '\n\n'.join(
    [
        '[b]Examples[/b]',
        '[b]refcheck[/b] — every source and bash reference in the repo, plus fragile-path warnings',
        '[b]refcheck apps/ --type sh[/b] — narrow to one directory and one file type',
        '[b]refcheck --strict[/b] — CI mode, where a warning is a failure',
        '[b]refcheck --pattern "old/path/" --desc "now new/path/"[/b] — after a move, what still points at the old name',
        "[b]refcheck --learn-rules[/b] — derive pattern rules from git's own rename history",
        '[b]What counts as what[/b]',
        (
            'Errors, always checked, exit 1: a source statement or a bash/sh invocation naming a file '
            'that is not there, and any --pattern hit.'
        ),
        (
            'Warnings, checked by default, exit 0 unless --strict: relative paths that only resolve from '
            'one directory, and directory variables built by ../ traversal.'
        ),
    ]
)

app = typer.Typer(
    add_completion=False,
    context_settings={'help_option_names': ['-h', '--help']},
)


@app.command(help=HELP, epilog=EPILOG)
def main(
    path: Annotated[
        Path | None,
        typer.Argument(help='Directory to check. Defaults to the current one.', rich_help_panel='Scope'),
    ] = None,
    file_type: Annotated[
        str | None,
        typer.Option('--type', '-t', help="Only files of this extension, e.g. 'sh' or 'py'.", rich_help_panel='Filters'),
    ] = None,
    skip_docs: Annotated[
        bool,
        typer.Option('--skip-docs', help='Leave markdown out of the scan.', rich_help_panel='Filters'),
    ] = False,
    test_mode: Annotated[
        bool,
        typer.Option('--test-mode', help='Include test fixtures, which are excluded by default.', rich_help_panel='Filters'),
    ] = False,
    pattern: Annotated[
        str | None,
        typer.Option('--pattern', help="An old path or name to hunt for, e.g. 'old/path/'.", rich_help_panel='Pattern search'),
    ] = None,
    desc: Annotated[
        str | None,
        typer.Option('--desc', help='What the pattern became, shown alongside each hit.', rich_help_panel='Pattern search'),
    ] = None,
    strict: Annotated[
        bool,
        typer.Option('--strict', help='Treat warnings as errors, so CI fails on them.', rich_help_panel='Severity'),
    ] = False,
    no_warn: Annotated[
        bool,
        typer.Option('--no-warn', help='Check only for errors, skipping fragile-path warnings.', rich_help_panel='Severity'),
    ] = False,
    learn_rules: Annotated[
        bool,
        typer.Option('--learn-rules', help="Write rules.json from git's rename history.", rich_help_panel='Maintenance'),
    ] = False,
    update: Annotated[
        bool,
        typer.Option('--update', help='Install the latest refcheck release.', rich_help_panel='Maintenance'),
    ] = False,
    check: Annotated[
        bool,
        typer.Option('--check', help='With --update, report an available release without installing it.', rich_help_panel='Maintenance'),
    ] = False,
    version: Annotated[
        bool,
        typer.Option('--version', help='Show the installed version and exit.', rich_help_panel='Maintenance'),
    ] = False,
):
    if version:
        print_version()
        raise typer.Exit(0)

    if update:
        raise typer.Exit(run_update(check_only=check))

    config = load_config()

    if learn_rules:
        learn_rules_from_git(config.time_window)
        raise typer.Exit(0)

    root_dir = Path.cwd()
    search_path = path.resolve() if path else root_dir

    try:
        search_path.relative_to(root_dir)
    except ValueError:
        root_dir = search_path

    checker = ReferenceChecker(
        root_dir=root_dir,
        search_path=search_path,
        skip_docs=skip_docs,
        file_type=file_type,
        warn_fragile=not no_warn,
        strict=strict,
        test_mode=test_mode,
        config=config,
    )

    if pattern:
        checker.check_pattern(pattern, desc)
    else:
        checker.run_all_checks()

    print_results(
        checker.issues,
        checker.warnings,
        checker.get_rules(),
        checker.get_rules_path(),
        checker.root_dir,
        checker.search_path,
        checker.config,
    )

    notify(UPDATE_CONFIG)

    if checker.issues or checker.strict and checker.warnings:
        raise typer.Exit(1)
    raise typer.Exit(0)


if __name__ == '__main__':
    app()
