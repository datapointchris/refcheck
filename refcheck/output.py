"""Output formatting and result printing."""

import sys
from dataclasses import dataclass
from dataclasses import field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .sweep import SweepResult


class CheckType(Enum):
    PATTERN = 'old_path_pattern'
    SOURCE = 'broken_source_command'
    SCRIPT = 'broken_bash_command'
    FRAGILE_CWD = 'fragile_cwd_path'
    FRAGILE_REFACTOR = 'fragile_traversal_path'


@dataclass
class Issue:
    file: Path
    line_num: int
    check_type: CheckType
    message: str
    suggestion: str | None = None
    similar_files: list[str] = field(default_factory=list)


@dataclass
class Warning:
    file: Path
    line_num: int
    check_type: CheckType
    message: str
    suggestion: str | None = None


@dataclass(frozen=True)
class Unreadable:
    """A path the walk was told to read and could not, with what the kernel said.

    A file that will not open and a directory that will not list are both
    unscanned, and a scan that covered less than it was handed cannot print a
    tick. So a refusal is carried out to the report rather than swallowed where
    it happens, which is the same false clean a missing repo produces one level
    up.
    """

    path: Path
    reason: str


def print_results(
    issues: list[Issue],
    warnings: list[Warning],
    rules_path: Path | None,
    root_dir: Path,
    search_path: Path,
    unreadable: list[Unreadable] | None = None,
) -> None:
    """Print validation results."""
    unreadable = unreadable or []
    try:
        search_info = f' in {search_path.relative_to(root_dir)}' if search_path != root_dir else ''

        # If no issues or warnings, success!
        if not issues and not warnings:
            if unreadable:
                _print_unreadable(unreadable)
                return
            print(f'\n✅ All file references valid{search_info}\n')
            return

        # Print summary header
        error_count = len(issues)
        warning_count = len(warnings)

        if error_count > 0 and warning_count > 0:
            print(f'\n❌ Found {error_count} error(s) and {warning_count} warning(s){search_info}\n')
        elif error_count > 0:
            print(f'\n❌ Found {error_count} error(s){search_info}\n')
        else:
            print(f'\n⚠️  Found {warning_count} warning(s){search_info}\n')

        # Print errors
        if issues:
            print('Errors:')
            print('─' * 60)

            issues_by_type: dict[CheckType, list[Issue]] = {}
            for issue in issues:
                issues_by_type.setdefault(issue.check_type, []).append(issue)

            for check_type, type_issues in sorted(issues_by_type.items(), key=lambda x: x[0].value):
                print(f'\n{check_type.value.replace("_", " ").title()} ({len(type_issues)}):')
                print('─' * 60)
                for issue in type_issues:
                    print(f'  {issue.file}:{issue.line_num}')
                    print(f'    {issue.message}')
                    if issue.similar_files:
                        print('    → Possible matches:')
                        for similar in issue.similar_files:
                            print(f'        {similar}')
                    if issue.suggestion:
                        print(f'    → {issue.suggestion}')

        # Print warnings
        if warnings:
            if issues:
                print()  # Extra space between errors and warnings

            print('Warnings:')
            print('─' * 60)

            warnings_by_type: dict[CheckType, list[Warning]] = {}
            for warning in warnings:
                warnings_by_type.setdefault(warning.check_type, []).append(warning)

            for check_type, type_warnings in sorted(warnings_by_type.items(), key=lambda x: x[0].value):
                print(f'\n{check_type.value.replace("_", " ").title()} ({len(type_warnings)}):')
                print('─' * 60)
                for warning in type_warnings:
                    print(f'  {warning.file}:{warning.line_num}')
                    print(f'    {warning.message}')
                    if warning.suggestion:
                        print(f'    → {warning.suggestion}')

        if unreadable:
            print()
            _print_unreadable(unreadable)

        print_rules_hint(issues, rules_path)
        print()
    except BrokenPipeError:
        sys.stderr.close()


def _print_unreadable(unreadable: list[Unreadable]) -> None:
    """Say which files and directories the walk could not read.

    The one thing this tool sells is a clean result that means something, and a
    tree it could only partly open cannot support one. Naming what it could not
    reach is what keeps the tick honest for the files it did read.
    """
    print(f'\n❌ {len(unreadable)} path(s) could not be read, so this scan covered less than the tree\n')
    print('Unreadable:')
    print('─' * 60)
    for entry in unreadable:
        print(f'  {entry.path}')
        print(f'    {entry.reason}')


def print_sweep(sweep: 'SweepResult', patterns: dict[str, str]) -> None:
    """Print a cross-repo sweep, grouped by the repo each finding sits in.

    Paths are printed absolute rather than repo-relative. Every other refcheck
    run prints relative to the tree you are standing in, and this one is the
    exception because it is standing in none of them: 90 repo-relative paths
    with no repo in front of them are not something a reader can open.

    What was not swept is printed too. A registry naming a path this machine
    does not hold is drift of its own, and a sweep reporting a clean 60 repos
    when the caller expected 90 is the false clean this tool exists to avoid.
    """
    try:
        print()
        if not patterns:
            print('✅ Nothing moved, so no repo was swept\n')
            return

        skipped = f' (skipped {len(sweep.retired)} retired)' if sweep.retired else ''

        repos = _count(sweep.scanned, 'repo')

        # The tick is a claim about every repo the caller named, so a run that
        # could not read one of them has no tick to print. Saying "no repo names
        # a path that moved" above a repo the sweep never opened is the false
        # clean in one line.
        if sweep.issues:
            print(f'❌ Found {len(sweep.issues)} stale reference(s) in {len(sweep.with_issues)} of {repos}{skipped}')
        elif not sweep.unreached:
            print(f'✅ No repo names a path that moved — {repos}, {len(patterns)} moved path(s){skipped}')
        else:
            print(f'❌ {repos} swept, {len(patterns)} moved path(s){skipped} — but the sweep could not read everything it was given')

        _print_unlisted_source(sweep)
        print()

        for result in sweep.with_issues:
            print(f'{result.repo.name}  ({result.repo.path})')
            print('─' * 60)
            for issue in result.issues:
                print(f'  {result.repo.path / issue.file}:{issue.line_num}')
                print(f'    {issue.message}')
                if issue.suggestion:
                    print(f'    → {issue.suggestion}')
            print()

        _print_unreached(sweep)
    except BrokenPipeError:
        sys.stderr.close()


def _count(number: int, noun: str) -> str:
    return f'{number} {noun}' if number == 1 else f'{number} {noun}s'


def _print_unreached(sweep: 'SweepResult') -> None:
    """Say what the sweep was asked to read and could not, as an error.

    Retired is the one deliberate skip, so it stays in the count line above.
    Everything here is the sweep covering less than it was handed, which the
    tick above cannot distinguish from a machine with nothing stale. A clean
    result is the entire product, so anything that narrows it without saying so
    is worse than a finding nobody wanted.
    """
    if not sweep.unreached:
        return

    unreadable = [entry for result in sweep.with_unreadable for entry in result.unreadable]
    total = len(sweep.absent) + len(sweep.unusable) + len(unreadable)

    print(f'❌ {_count(total, "path")} the sweep was asked to read and could not, so this run covered less than it claims')
    print('─' * 60)
    for description in sweep.unusable:
        print(f'  {description}')
    for repo in sweep.absent:
        print(f'  {repo.name}  ({repo.path})')
        print('    No directory here, though the registry says this machine holds it')
    for entry in unreadable:
        print(f'  {entry.path}')
        print(f'    {entry.reason}')
    print()


def _print_unlisted_source(sweep: 'SweepResult') -> None:
    """Say when the repo the paths moved in is not one the sweep can credit.

    A hit is credited to the repo holding the path that went away, so a repo the
    registry never listed can own nothing and its renames are unanswerable. Left
    unsaid that prints the same tick as a machine with no stale references, and
    a registry omitting one repo silently answers a different question.
    """
    if sweep.source_is_listed or sweep.source_root is None:
        return

    print(f'⚠️  {sweep.source_root} is not in the registry, so a path that moved here can be credited to no repo.')


def print_config(repo_config: Path | None, layers: list[tuple[str, list[str]]]) -> None:
    """Print every exclusion in force, grouped by the layer that set it.

    The layer is the half of the answer that says whether a skipped file was
    asked for. A built-in pattern, a repo declaration and a --exclude flag all
    produce the same silence, and only the source tells them apart.
    """
    print()
    print(f'Repo config: {repo_config if repo_config else "none found"}')

    for label, patterns in layers:
        if not patterns:
            continue
        print(f'\n{label} ({len(patterns)}):')
        print('─' * 60)
        for pattern in patterns:
            print(f'  {pattern}')
    print()


def print_rules_hint(issues: list[Issue], rules_path: Path | None) -> None:
    """Mention learned rules only where they would have changed this output.

    Rules feed exactly one thing: the "Possible matches" line under a broken
    reference. They detect nothing on their own, so a run that found nothing has
    nothing to gain from them. Printed unconditionally the hint lands on nearly
    every passing run, and a prompt to do maintenance with no finding behind it
    is what teaches a reader to skim past the output.
    """
    if rules_path is None or rules_path.exists():
        return

    unsuggested = [issue for issue in issues if issue.check_type in (CheckType.SOURCE, CheckType.SCRIPT) and not issue.similar_files]
    if not unsuggested:
        return

    print(f'\n💡 {len(unsuggested)} broken reference(s) came up with no suggestions.')
    print("   'refcheck learn-rules' reads git's rename history to improve them.")
