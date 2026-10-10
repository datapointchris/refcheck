"""Command-line interface for refcheck."""

import shlex
import sys
from pathlib import Path
from typing import Annotated

import typer
from pyselfupdate import notify
from pyselfupdate.typercmd import add_update_command
from typer._click.core import Context
from typer._click.exceptions import NoSuchOption
from typer.core import TyperGroup

from . import moves as moves_module
from . import registry as registry_module
from . import sweep as sweep_module
from .checker import ReferenceChecker
from .config import REPO_CONFIG_NAME
from .config import load_config
from .names import FLAG_WORD
from .names import NAME_WORD
from .output import print_config
from .output import print_results
from .output import print_sweep
from .rules import get_repo_root
from .rules import learn_rules_from_git
from .selfupdate import CONFIG as UPDATE_CONFIG
from .selfupdate import print_version

HELP = (
    'Find file references that no longer resolve, and path patterns that will break the next time '
    'something moves. [b]check[/b] is the tool; [b]update[/b] and [b]learn-rules[/b] maintain it. '
    'A reference breaks in the file that was not edited, so [b]check[/b] always reads the whole tree '
    'rather than a changeset, and infers the repo from the directory you run it in. Run any command '
    'with --help to see what comes next.'
)

CHECK_HELP = (
    'Validate every file reference in the tree. Give it a directory to narrow the search, --pattern '
    'to ask the one question a move leaves behind — what still points at the old path? — or --name to '
    'ask what a rename or a removal leaves behind: where is a tool, a subcommand or a flag that is gone '
    'still named? "Which flag answers which change", below, maps each kind of change to its flag.'
)

EPILOG = '\n\n'.join(
    [
        '[b]Examples[/b]',
        '[b]refcheck check[/b] — every source and bash reference in the repo, plus fragile-path warnings',
        '[b]refcheck check apps/ --type sh[/b] — narrow to one directory and one file type',
        '[b]refcheck check --strict[/b] — CI mode, where a warning is a failure',
        '[b]refcheck check --pattern "old/path/" --desc "now new/path/"[/b] — after a move, what still points at the old name',
        '[b]refcheck check --moves[/b] — ask that of every rename and deletion you have staged, without naming them',
        '[b]refcheck check --moves-since origin/main[/b] — the same over a branch, for CI',
        (
            '[b]refcheck check --moves-since origin/main --registry <repos.json>[/b] — and of every other '
            'repo the registry lists, which is where a rename breaks something you cannot see'
        ),
        (
            '[b]refcheck check --name oldtool --desc "now newtool" --registry <repos.json> --registry <stores.json>[/b] '
            '— after renaming a tool, every place in every listed repo and store that still names it'
        ),
        (
            '[b]refcheck check --name "tool oldsub" --desc "now newtool sub" --registry <repos.json> --registry <stores.json>[/b] '
            '— after renaming, moving or removing a subcommand, every caller and every mention of it'
        ),
        '[b]refcheck check --show-config[/b] — every exclusion in force, and the layer that set it',
        "[b]refcheck learn-rules[/b] — derive pattern rules from git's own rename history",
        '[b]refcheck update[/b] — install the latest release',
    ]
)

CHECK_EPILOG = '\n\n'.join(
    [
        '[b]Which flag answers which change[/b]',
        (
            'Moved, renamed or deleted a file or directory: --moves before committing, --moves-since '
            '<base> over a branch, or --pattern "old/path/" by hand. With --registry, --moves also asks '
            'where a filename the change took out of use is still cited, once neither this tree nor any '
            'listed repo holds a file of that name.\n'
            'Renamed or removed a tool: --name oldtool.\n'
            'Renamed, moved or removed a subcommand: --name "tool oldsub", once per subcommand.\n'
            'Moved a flag under a subcommand, renamed or removed it: --name "tool --oldflag", or '
            '--name "tool sub --oldflag" for a subcommand\'s flag, once per flag.\n'
            'Add --registry once per registry to ask every repo and store, not just this one. A tool, '
            'a subcommand or a flag is not a file git moves, so a pre-commit hook never asks --name for you: '
            'run it when the change lands.'
        ),
        '[b]Excluding a repo of its own generated output[/b]',
        (
            'refcheck excludes what is true of any repository — logs, changelogs, tool caches. '
            'Which of [i]this[/i] repo’s directories hold generated output is a fact only the repo '
            f'knows, so it says so in [b]{REPO_CONFIG_NAME}[/b] at its root:'
        ),
        '[b][scan][/b]\n[b]exclude = ["build/reports/**", "*.snapshot.json"][/b]',
        (
            'A file written by a tool names what a path was when the tool ran, so a hit inside one is '
            'history rather than a stale reference. --exclude adds a pattern for one run without '
            'declaring it.'
        ),
        '[b]What counts as what[/b]',
        (
            'Errors, always checked, exit 1: a source statement or a bash/sh invocation naming a file '
            'that is not there, any --pattern hit, and any path this run was handed and could not read.'
        ),
        (
            'Warnings, checked by default, exit 0 unless --strict: relative paths that only resolve from '
            'one directory, and directory variables built by ../ traversal.'
        ),
        (
            'Set aside, never a failure: a --pattern hit whose path is on disk. Whether that means the '
            'reference was repaired or that the old name is simply still there is yours to say, so each '
            'one is listed with the path it resolved to. --moves knows what each path became and lists '
            'only the hits that record cannot account for.'
        ),
        '[b]What --name counts as a use of the name[/b]',
        (
            'On any line: a code span opening on it, a quoted literal, bold or a table cell holding only '
            'it, and a path segment such as ~/tools/oldtool or oldtool.db. On a line of code or config, '
            'also an import, a value that is only it, a list item, and a line opening on it in aligned '
            'columns. On a line a shell would run, the whole word outside a comment.'
        ),
        (
            'A tool and its subcommand, "tool oldsub", count as the words in order on a line of code, '
            'config or shell, comments included, with or without an installed path ahead of the tool '
            '(/usr/bin/tool oldsub). In prose they count in the shapes a single name takes: a code '
            'span, a quoted literal, bold, or a table cell. On every line they also count as '
            'consecutive quoted items of an argument list: ["tool", "oldsub"]. A flag between them, '
            'tool --json oldsub, is not matched.'
        ),
        (
            'A tool and a flag, "tool --oldflag", take the same shapes, and other flags may stand before '
            'it: tool --json --oldflag. A word between the tool and the flag that is not itself a flag '
            'is taken for a subcommand, so "tool sub --oldflag", the corrected call, is not matched; '
            'name a subcommand\'s own flag as "tool sub --oldflag". A flag after a value or a positional '
            'argument, as in tool --type md --oldflag or tool sub src/ --oldflag, is not matched, because '
            'nothing tells the value from a subcommand.'
        ),
        (
            'The bare word in a sentence is not one, because nothing tells the tool from the English word '
            'it may also be — so a name in running prose is left for you to find. A subcommand that kept '
            'the old name in the tool that absorbed it is reported too: read those hits, and exclude them '
            f'in that repo’s {REPO_CONFIG_NAME}.'
        ),
    ]
)


class RootGroup(TyperGroup):
    """The root command, which points a scan flag given ahead of any command at check.

    The scan's flags belong to check, so refcheck itself refuses them. Click's
    own refusal names the flag and stops there; this one also names the command
    the flag belongs to, and spells the call that runs it.
    """

    def parse_args(self, ctx: Context, args: list[str]) -> list[str]:
        # Click consumes the list it parses, so the call as given is kept aside.
        given = list(args)
        try:
            return super().parse_args(ctx, args)
        except NoSuchOption as error:
            check_command = self.get_command(ctx, 'check')
            if check_command is None:
                raise
            check_flags = {flag for param in check_command.params for flag in (*param.opts, *param.secondary_opts)}
            if error.option_name not in check_flags:
                raise
            # The whole call moves under check only when it names no command of
            # its own, since then every argument in it is one of check's.
            commands = set(self.list_commands(ctx))
            rest = given if not commands.intersection(given) else [error.option_name]
            raise NoSuchOption(
                error.option_name,
                message=f'{error.option_name} belongs to check: {ctx.command_path} check {shlex.join(rest)}',
                ctx=ctx,
            ) from error


app = typer.Typer(
    cls=RootGroup,
    add_completion=False,
    no_args_is_help=True,
    help=HELP,
    epilog=EPILOG,
    context_settings={'help_option_names': ['-h', '--help']},
)


def _version_callback(value: bool) -> None:
    if value:
        print_version()
        raise typer.Exit(0)


@app.callback()
def root(
    version: Annotated[
        bool,
        typer.Option(
            '--version',
            callback=_version_callback,
            is_eager=True,
            help='Show the installed version and exit.',
        ),
    ] = False,
):
    """Options that belong to refcheck itself rather than to any one of its commands."""


@app.command(help=CHECK_HELP, epilog=CHECK_EPILOG)
def check(
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
    exclude: Annotated[
        list[str] | None,
        typer.Option(
            '--exclude',
            help=f'Also skip paths matching this glob. Repeatable, and added to {REPO_CONFIG_NAME}.',
            rich_help_panel='Filters',
        ),
    ] = None,
    pattern: Annotated[
        str | None,
        typer.Option('--pattern', help="An old path or name to hunt for, e.g. 'old/path/'.", rich_help_panel='Pattern search'),
    ] = None,
    desc: Annotated[
        str | None,
        typer.Option('--desc', help='What the pattern became, shown alongside each hit.', rich_help_panel='Pattern search'),
    ] = None,
    check_moves: Annotated[
        bool,
        typer.Option(
            '--moves',
            help='Also hunt for what the staged renames and deletions left behind, or those in the range pre-commit names.',
            rich_help_panel='Pattern search',
        ),
    ] = False,
    moves_since: Annotated[
        str | None,
        typer.Option('--moves-since', help='The same, for every move between REF and HEAD.', rich_help_panel='Pattern search'),
    ] = None,
    name: Annotated[
        str | None,
        typer.Option(
            '--name',
            help=(
                "A tool's old name, or a tool and its old subcommand or flag, reported wherever it is "
                "still named, e.g. 'oldtool', 'tool oldsub' or 'tool --oldflag'. One per run."
            ),
            rich_help_panel='Pattern search',
        ),
    ] = None,
    registry: Annotated[
        list[Path] | None,
        typer.Option(
            '--registry',
            help='Ask the same of every repo or store this registry lists, not just this one. Repeatable.',
            rich_help_panel='Pattern search',
        ),
    ] = None,
    strict: Annotated[
        bool,
        typer.Option('--strict', help='Treat warnings as errors, so CI fails on them.', rich_help_panel='Severity'),
    ] = False,
    no_warn: Annotated[
        bool,
        typer.Option('--no-warn', help='Check only for errors, skipping fragile-path warnings.', rich_help_panel='Severity'),
    ] = False,
    show_config: Annotated[
        bool,
        typer.Option(
            '--show-config', help='Print the exclusions in force and where each came from, then exit.', rich_help_panel='Maintenance'
        ),
    ] = False,
):
    root_dir = Path.cwd()
    search_path = path.resolve() if path else root_dir

    # A directory that is not there holds no references, so walking it finds
    # nothing, every check passes over nothing, and the run reports valid. That
    # is the tool certifying a tree it never opened, which is worse than any
    # finding it could have reported.
    if path is not None and not search_path.exists():
        print(f'refcheck: {search_path} is not there, so a scan of it would call every reference in it valid.', file=sys.stderr)
        raise typer.Exit(2)

    try:
        search_path.relative_to(root_dir)
    except ValueError:
        root_dir = search_path

    # Discovery starts at the repo root rather than the cwd, so narrowing the
    # scan to a subdirectory reads the same declarations as a whole-repo run.
    config = load_config(root_dir)
    repo_patterns = list(config.exclude)
    flag_patterns = list(exclude or [])
    config.exclude = [*repo_patterns, *flag_patterns]

    if show_config:
        print_config(
            config.config_path,
            [
                ('Excluded directory names', sorted(ReferenceChecker.DEFAULT_EXCLUDES)),
                ('Built-in patterns', ReferenceChecker.DEFAULT_EXCLUDE_PATTERNS),
                ('Test fixtures, scanned under --test-mode', [] if test_mode else ReferenceChecker.TEST_FIXTURE_PATTERNS),
                (f'{REPO_CONFIG_NAME} [scan] exclude', repo_patterns),
                ('--exclude', flag_patterns),
            ],
        )
        raise typer.Exit(0)

    # The sweep needs old paths to look for, and the source/bash checks are not
    # one: validating another repo's references is that repo's own run. Saying
    # so beats parsing into a walk of 90 repos that asks them nothing.
    if registry and not (pattern or check_moves or moves_since or name):
        print(
            '--registry sweeps other repos for what a move or a rename left behind, '
            'so it needs --moves, --moves-since, --pattern or --name to say what.',
            file=sys.stderr,
        )
        raise typer.Exit(2)

    # Each of these is its own question, and a run answers one. Taking two would
    # answer the first and print a tick the caller reads as covering both.
    asked = [flag for flag, given in (('--pattern', pattern), ('--name', name), ('--moves', check_moves or moves_since)) if given]
    if len(asked) > 1:
        print(f'refcheck: {" and ".join(asked)} each ask a different question, so pass one per run.', file=sys.stderr)
        raise typer.Exit(2)

    # A name is one word or several, each of word characters, dots and hyphens,
    # and any word after the first may be a flag. A slash makes it a path, which
    # --pattern resolves and --name would only match as text.
    if name is not None:
        first, *rest = name.split() or ['']
        if not NAME_WORD.fullmatch(first) or not all(NAME_WORD.fullmatch(word) or FLAG_WORD.fullmatch(word) for word in rest):
            path_hint = ' For a path, use --pattern.' if '/' in name else ''
            print(
                "refcheck: --name takes a tool's name, then optionally its subcommand or one of its flags: "
                "'oldtool', 'tool oldsub' or 'tool --oldflag'. A name is letters, digits, '.', '_' or '-', "
                "and a flag is '-' or '--' and then letters, digits, '_' or '-'. "
                f'{name!r} is not one of those.{path_hint}',
                file=sys.stderr,
            )
            raise typer.Exit(2)
        name = ' '.join(name.split())

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

    listed = _load_registries(registry) if registry else None
    sweep_patterns: dict[str, str] = {}
    found: list[moves_module.Move] = []
    gone_filenames: dict[str, str] = {}
    filenames_still_held: list[str] = []
    unmatchable: list[str] = []

    if pattern:
        checker.check_pattern(pattern, desc)
        sweep_patterns = {pattern: desc or f'Old pattern: {pattern}'}
    elif name:
        sweep_patterns = {name: desc or ''}
        checker.check_names(sweep_patterns)
    else:
        checker.run_all_checks()

        if check_moves or moves_since:
            repo_root = get_repo_root(root_dir)
            if repo_root is None:
                print('fatal: not a git repository (or any of the parent directories): .git', file=sys.stderr)
                raise typer.Exit(128)

            # A bare name is asked for only when there are other repos to ask,
            # where an absolute path settles it. In this repo it stays out.
            try:
                found = (
                    moves_module.since(moves_since, repo_root, include_bare_names=True)
                    if moves_since
                    else moves_module.in_pre_commit_change(repo_root, include_bare_names=True)
                )
            except moves_module.UnreadableChange as error:
                print(f'refcheck: git could not read the change, so no move in it was checked.\n{error}', file=sys.stderr)
                raise typer.Exit(2) from error
            # git recorded what each path became, so a hit that resolves can be
            # tested against it rather than taken for a repair on the strength
            # of some file of that name being on disk.
            checker.check_patterns(
                {move.old: move.description for move in found if not move.is_bare},
                {move.old: move.new for move in found if move.new},
            )
            sweep_patterns = {move.old: move.description for move in found}

    swept = None
    if listed:
        # A filename the change took out of use is cited alone as often as by
        # path. It is asked only once neither this tree nor any listed repo
        # holds a file of that name, because until then the citation names
        # something real.
        candidates, unmatchable = moves_module.old_filenames(found)
        if candidates:
            roots = [get_repo_root(root_dir) or root_dir, *(repo.path for repo in listed.repos if repo.is_on_disk)]
            held = sweep_module.held_filenames(roots)
            gone_filenames = {old: became for old, became in candidates.items() if old not in held}
            filenames_still_held = sorted(set(candidates) - set(gone_filenames))
            checker.check_filenames(gone_filenames)
        swept = _sweep_other_repos(
            listed, sweep_patterns, bool(name), skip_docs, file_type, test_mode, flag_patterns, root_dir, search_path, gone_filenames
        )

    print_results(
        checker.issues,
        checker.warnings,
        checker.get_rules_path(),
        checker.root_dir,
        checker.search_path,
        checker.unreadable,
        checker.set_aside,
    )

    if swept is not None:
        print_sweep(swept, sweep_patterns, by_name=bool(name), filenames=gone_filenames)
        if filenames_still_held:
            print(f'Not asked as old filenames, because this tree or a listed repo still holds one: {", ".join(filenames_still_held)}')
        if unmatchable:
            print(f'Not asked as old filenames, because no shape can match them: {", ".join(unmatchable)}')
        if filenames_still_held or unmatchable:
            print()

    notify(UPDATE_CONFIG)

    # A path the run was handed and could not read fails it, the same as a
    # finding. Both mean the tick would be a lie, and the tick is the product.
    unreached = bool(checker.unreadable) or bool(swept and swept.unreached)

    if checker.issues or (swept and swept.issues) or unreached or (checker.strict and checker.warnings):
        raise typer.Exit(1)
    raise typer.Exit(0)


@app.command(name='learn-rules')
def learn_rules():
    """Write rules.json from git's rename history, so a miss can suggest what replaced it."""
    learn_rules_from_git(load_config(Path.cwd()).time_window)


# Registered last so `check` heads the command list, and by the library rather
# than by hand: the step order inside run_update is load-bearing, so calling it
# is what keeps the update path the same as every other consumer's.
add_update_command(app, UPDATE_CONFIG)


def _load_registries(registries: list[Path]) -> registry_module.Registry:
    try:
        return registry_module.load_all(registries)
    except registry_module.RegistryError as error:
        print(f'refcheck: {error}', file=sys.stderr)
        raise typer.Exit(2) from error


def _sweep_other_repos(
    listed: registry_module.Registry,
    patterns: dict[str, str],
    by_name: bool,
    skip_docs: bool,
    file_type: str | None,
    test_mode: bool,
    flag_excludes: list[str],
    source_root: Path,
    scanned_here: Path,
    filenames: dict[str, str],
) -> sweep_module.SweepResult:
    """Ask every repo the registries list what a move or a rename left behind, printing nothing."""
    if by_name:
        swept = sweep_module.names_across_repos(
            listed,
            patterns,
            skip_docs=skip_docs,
            file_type=file_type,
            test_mode=test_mode,
            flag_excludes=flag_excludes,
            already_scanned=scanned_here,
        )
    else:
        swept = sweep_module.across_repos(
            listed,
            patterns,
            skip_docs=skip_docs,
            file_type=file_type,
            test_mode=test_mode,
            flag_excludes=flag_excludes,
            source_root=source_root,
            filenames=filenames,
            already_scanned=scanned_here,
        )
    return swept


if __name__ == '__main__':
    app()
