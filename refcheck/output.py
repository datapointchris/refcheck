"""Output formatting and result printing."""

import sys
from dataclasses import dataclass
from dataclasses import field
from enum import Enum
from pathlib import Path


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


def print_results(
    issues: list[Issue],
    warnings: list[Warning],
    rules_path: Path | None,
    root_dir: Path,
    search_path: Path,
) -> None:
    """Print validation results."""
    try:
        search_info = f' in {search_path.relative_to(root_dir)}' if search_path != root_dir else ''

        # If no issues or warnings, success!
        if not issues and not warnings:
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

        print_rules_hint(issues, rules_path)
        print()
    except BrokenPipeError:
        sys.stderr.close()


def print_rules_hint(issues: list[Issue], rules_path: Path | None) -> None:
    """Mention learned rules only where they would have changed this output.

    Rules feed exactly one thing: the "Possible matches" line under a broken
    reference. They detect nothing on their own, so a run that found nothing has
    nothing to gain from them — and the old unconditional hint printed on 48 of
    the 49 repos in the fleet, every one of them passing. A prompt to do
    maintenance with no finding behind it is what teaches a reader to skim past
    the output.
    """
    if rules_path is None or rules_path.exists():
        return

    unsuggested = [issue for issue in issues if issue.check_type in (CheckType.SOURCE, CheckType.SCRIPT) and not issue.similar_files]
    if not unsuggested:
        return

    print(f'\n💡 {len(unsuggested)} broken reference(s) came up with no suggestions.')
    print("   'refcheck --learn-rules' reads git's rename history to improve them.")
