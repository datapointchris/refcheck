"""Output formatting and result printing."""

import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from .config import Config
from .rules import get_rules_age_days


class CheckType(Enum):
    PATTERN = "old_path_pattern"
    SOURCE = "broken_source_command"
    SCRIPT = "broken_bash_command"
    FRAGILE_CWD = "fragile_cwd_path"
    FRAGILE_REFACTOR = "fragile_traversal_path"


@dataclass
class Issue:
    file: Path
    line_num: int
    check_type: CheckType
    message: str
    suggestion: Optional[str] = None
    similar_files: List[str] = field(default_factory=list)


@dataclass
class Warning:
    file: Path
    line_num: int
    check_type: CheckType
    message: str
    suggestion: Optional[str] = None


def print_results(
    issues: List[Issue],
    warnings: List[Warning],
    rules: Dict,
    rules_path: Optional[Path],
    root_dir: Path,
    search_path: Path,
    config: Config,
) -> None:
    """Print validation results."""
    try:
        search_info = (
            f" in {search_path.relative_to(root_dir)}" if search_path != root_dir else ""
        )

        # Show hint if no rules file exists for this repo
        if rules_path and not rules_path.exists():
            if config.show_no_rules_hint:
                print(
                    "\n💡 No learned rules found. "
                    "Run 'refcheck --learn-rules' to learn from git rename history.\n"
                )
        else:
            # Check for stale rules (older than threshold)
            age_days = get_rules_age_days(rules)
            if age_days is not None and age_days > config.stale_threshold_days:
                print(
                    f"\n⚠️  Rules last updated {age_days} days ago. "
                    "Run 'refcheck --learn-rules' to refresh.\n"
                )

        # If no issues or warnings, success!
        if not issues and not warnings:
            print(f"\n✅ All file references valid{search_info}\n")
            return

        # Print summary header
        error_count = len(issues)
        warning_count = len(warnings)

        if error_count > 0 and warning_count > 0:
            print(f"\n❌ Found {error_count} error(s) and {warning_count} warning(s){search_info}\n")
        elif error_count > 0:
            print(f"\n❌ Found {error_count} error(s){search_info}\n")
        else:
            print(f"\n⚠️  Found {warning_count} warning(s){search_info}\n")

        # Print errors
        if issues:
            print("Errors:")
            print("─" * 60)

            by_type: Dict[CheckType, List[Issue]] = {}
            for issue in issues:
                by_type.setdefault(issue.check_type, []).append(issue)

            for check_type, type_issues in sorted(by_type.items(), key=lambda x: x[0].value):
                print(f"\n{check_type.value.replace('_', ' ').title()} ({len(type_issues)}):")
                print("─" * 60)
                for issue in type_issues:
                    print(f"  {issue.file}:{issue.line_num}")
                    print(f"    {issue.message}")
                    if issue.similar_files:
                        print("    → Possible matches:")
                        for similar in issue.similar_files:
                            print(f"        {similar}")
                    if issue.suggestion:
                        print(f"    → {issue.suggestion}")

        # Print warnings
        if warnings:
            if issues:
                print()  # Extra space between errors and warnings

            print("Warnings:")
            print("─" * 60)

            by_type: Dict[CheckType, List[Warning]] = {}
            for warning in warnings:
                by_type.setdefault(warning.check_type, []).append(warning)

            for check_type, type_warnings in sorted(by_type.items(), key=lambda x: x[0].value):
                print(f"\n{check_type.value.replace('_', ' ').title()} ({len(type_warnings)}):")
                print("─" * 60)
                for warning in type_warnings:
                    print(f"  {warning.file}:{warning.line_num}")
                    print(f"    {warning.message}")
                    if warning.suggestion:
                        print(f"    → {warning.suggestion}")

        print()
    except BrokenPipeError:
        sys.stderr.close()
