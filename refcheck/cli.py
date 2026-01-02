"""Command-line interface for refcheck."""

import argparse
import sys
from pathlib import Path

from .checker import ReferenceChecker
from .config import load_config
from .output import print_results
from .rules import learn_rules_from_git


def main():
    parser = argparse.ArgumentParser(
        prog="refcheck",
        description="Find broken file references and old path patterns",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate all references + warn about fragile paths
  %(prog)s
  %(prog)s --skip-docs              # Skip markdown files

  # Check specific directory
  %(prog)s management/
  %(prog)s apps/ --type sh          # Only shell scripts in apps/

  # Control warnings
  %(prog)s --no-warn                # Only check errors, skip fragile path warnings
  %(prog)s --strict                 # Treat warnings as errors (CI mode)

  # Find old patterns after refactoring
  %(prog)s --pattern "old/path/"
  %(prog)s --pattern "FooClass" --desc "Renamed to BarClass"

What it checks:
  Errors (always checked, exit 1):
    - Broken source commands (source statements pointing to non-existent files)
    - Broken bash commands (bash/sh invocations pointing to non-existent scripts)
    - Old path patterns (after moving/renaming directories)

  Warnings (checked by default, exit 0 unless --strict):
    - Fragile CWD paths: Relative paths that only work from specific directories
    - Fragile traversal paths: Directory variables using ../ traversal

Learn from git history:
  %(prog)s --learn-rules           # Generate rules from git renames

Exit codes:
  0 - No errors (warnings OK unless --strict)
  1 - Found errors, or warnings in --strict mode
        """,
    )
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        help="Directory to check (default: current directory)",
    )
    parser.add_argument(
        "--pattern",
        metavar="PATTERN",
        help="Check for specific old path pattern (e.g., 'old/path/')",
    )
    parser.add_argument(
        "--desc",
        metavar="DESC",
        help="Description for pattern check",
    )
    parser.add_argument(
        "--type",
        "-t",
        metavar="TYPE",
        help="Filter by file type (e.g., 'sh', 'py')",
    )
    parser.add_argument(
        "--skip-docs",
        action="store_true",
        help="Skip documentation (.md) files",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors (exit 1 if warnings found)",
    )
    parser.add_argument(
        "--no-warn",
        action="store_true",
        help="Disable fragile path warnings (only check for errors)",
    )
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Include test fixtures (normally excluded)",
    )
    parser.add_argument(
        "--learn-rules",
        action="store_true",
        help="Generate rules.json from git rename history",
    )
    args = parser.parse_args()

    config = load_config()

    if args.learn_rules:
        learn_rules_from_git(config.time_window)
        sys.exit(0)

    root_dir = Path.cwd()
    search_path = args.path.resolve() if args.path else root_dir

    try:
        search_path.relative_to(root_dir)
    except ValueError:
        root_dir = search_path

    checker = ReferenceChecker(
        root_dir=root_dir,
        search_path=search_path,
        skip_docs=args.skip_docs,
        file_type=args.type,
        warn_fragile=not args.no_warn,
        strict=args.strict,
        test_mode=args.test_mode,
        config=config,
    )

    if args.pattern:
        checker.check_pattern(args.pattern, args.desc)
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

    if checker.issues:
        sys.exit(1)
    elif checker.strict and checker.warnings:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
