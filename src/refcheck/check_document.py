"""The document `check --json` prints, whose shape `schemas/check.schema.json` publishes.

A field added or renamed here changes the schema in the same commit, and
`SCHEMA_VERSION` moves when a reader of the old shape would misread the new one.
"""

from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

from .output import Issue
from .output import SetAside
from .output import Unreadable
from .output import Warning

if TYPE_CHECKING:
    from .moves import Move
    from .sweep import SweepResult

SCHEMA_VERSION = 1


def document(
    *,
    question: str,
    pattern: str | None,
    name: str | None,
    description: str | None,
    moves_since: str | None,
    moves: 'list[Move] | None',
    tree: dict[str, Any] | None,
    sweep: dict[str, Any] | None,
    exit_code: int,
) -> dict[str, Any]:
    return {
        'schema_version': SCHEMA_VERSION,
        'question': question,
        'pattern': pattern,
        'name': name,
        'description': description,
        'moves_since': moves_since,
        'moves': None if moves is None else [{'old': move.old, 'new': move.new, 'asked_in_tree': not move.is_bare} for move in moves],
        'tree': tree,
        'sweep': sweep,
        'exit_code': exit_code,
    }


def tree_record(
    root: Path,
    searched: Path,
    files_scanned: int,
    issues: list[Issue],
    warnings: list[Warning],
    set_aside: list[SetAside],
    unreadable: list[Unreadable],
) -> dict[str, Any]:
    return {
        'root': str(root),
        'searched': str(searched),
        'files_scanned': files_scanned,
        'issues': [finding(issue) for issue in issues],
        'warnings': [
            {
                'file': str(warning.file),
                'line': warning.line_num,
                'kind': warning.check_type.value,
                'message': warning.message,
                'suggestion': warning.suggestion,
            }
            for warning in warnings
        ],
        'set_aside': [
            {'file': str(entry.file), 'line': entry.line_num, 'pattern': entry.pattern, 'token': entry.token, 'target': str(entry.target)}
            for entry in set_aside
        ],
        'unreadable': [{'path': str(entry.path), 'reason': entry.reason} for entry in unreadable],
    }


def sweep_record(
    sweep: 'SweepResult',
    filenames_asked: dict[str, str],
    filenames_still_held: list[str],
    filenames_unmatchable: list[str],
) -> dict[str, Any]:
    return {
        'repos_scanned': sweep.scanned,
        'files_scanned': sweep.files_scanned,
        'source_root': None if sweep.source_root is None else str(sweep.source_root),
        'source_is_listed': sweep.source_is_listed,
        'retired': [{'name': repo.name, 'path': str(repo.path)} for repo in sweep.retired],
        'absent': [{'name': repo.name, 'path': str(repo.path)} for repo in sweep.absent],
        'unusable': list(sweep.unusable),
        'issues': [
            {'repo': result.repo.name, 'repo_path': str(result.repo.path), **finding(issue)}
            for result in sweep.with_issues
            for issue in result.issues
        ],
        'unreadable': [
            {'repo': result.repo.name, 'path': str(entry.path), 'reason': entry.reason}
            for result in sweep.with_unreadable
            for entry in result.unreadable
        ],
        'old_filenames': {
            'asked': [{'filename': filename, 'description': became} for filename, became in filenames_asked.items()],
            'still_held': filenames_still_held,
            'unmatchable': filenames_unmatchable,
        },
    }


def finding(issue: Issue) -> dict[str, Any]:
    return {
        'file': str(issue.file),
        'line': issue.line_num,
        'kind': issue.check_type.value,
        'message': issue.message,
        'suggestion': issue.suggestion,
        'similar_files': list(issue.similar_files),
        'target': issue.target,
    }
