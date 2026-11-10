"""Rules loading and learning from git history."""

import datetime as dt
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import git
from . import repository
from .config import user_state_dir


class LearnRulesError(Exception):
    """git could not read the rename history, so no rules were written."""


class NotAGitRepository(LearnRulesError):
    """The working directory is in no git repository, so it has no history to learn from."""


@dataclass(frozen=True)
class LearnedRules:
    """What one learn run wrote, for the command to report."""

    path: Path
    time_window: str
    commits_analyzed: int
    directory_mappings: int
    file_mappings: int


def rules_root() -> Path:
    """The directory every checkout's rules sit under."""
    return user_state_dir() / 'repos'


def get_rules_path(repo_root: Path) -> Path:
    """Where a checkout's rules live: its absolute path, mirrored under `rules_root`.

    Every checkout gets a directory of its own, so no two share a file, and
    the path can be found by hand from the checkout's.
    """
    return rules_root() / repo_root.relative_to(repo_root.anchor) / 'rules.json'


def no_rules() -> dict:
    return {'directory_mappings': {}, 'file_mappings': {}}


def read_rules(rules_path: Path) -> dict:
    """The rules in one file, or empty mappings where there is none or it will not parse."""
    try:
        with rules_path.open() as f:
            loaded = json.load(f)
    except (OSError, json.JSONDecodeError):
        return no_rules()
    return loaded or no_rules()


def load_rules(root_dir: Path) -> tuple[dict, Path | None]:
    """The rules for the repository holding root_dir, and the path they are read from.

    Outside a repository the path is None. With no rules file the rules are empty.
    """
    repo_root = repository.root(root_dir)
    if repo_root is None:
        return no_rules(), None
    rules_path = get_rules_path(repo_root)
    return read_rules(rules_path), rules_path


def learned_checkouts() -> list[tuple[Path, Path]]:
    """Every checkout with rules on this machine, beside its rules file, in path order."""
    root = rules_root()
    return sorted((Path(root.anchor) / path.parent.relative_to(root), path) for path in root.rglob('rules.json'))


def clear_rules(checkout: Path) -> Path | None:
    """Delete a checkout's rules and the directories that leaves empty, returning the file deleted.

    None where the checkout had no rules.
    """
    path = get_rules_path(checkout)
    try:
        path.unlink()
    except FileNotFoundError:
        return None
    root = rules_root()
    for parent in path.parents:
        if parent == root or not parent.is_relative_to(root):
            break
        try:
            parent.rmdir()
        except OSError:
            break
    return path


def learn_rules_from_git(time_window: str = '6 months') -> LearnedRules:
    """
    Scan git history for renames and generate rules.json.

    Always operates from the git repo root, regardless of cwd.
    Analyzes git rename operations from the specified time window to extract:
    - Directory prefix mappings (e.g., management/tests/ -> tests/install/)
    - File name mappings (e.g., parse-packages.py -> parse_packages.py)

    Raises NotAGitRepository outside a repository and LearnRulesError where
    git cannot read the log. The command decides what each means for the run.
    """
    repo_root = repository.root(Path.cwd())
    if repo_root is None:
        raise NotAGitRepository(f'{Path.cwd()} is in no git repository')

    try:
        log = git.run(
            [
                'log',
                f'--since={time_window} ago',
                '--diff-filter=R',
                '-M',
                '--name-status',
                '-z',
                '--format=%H',
            ],
            cwd=repo_root,
        )
    except subprocess.CalledProcessError as error:
        raise LearnRulesError(f'git could not read the rename history: {error.stderr.strip() or error}') from error
    except FileNotFoundError as error:
        raise LearnRulesError('git is not installed, so there is no rename history to read') from error

    directory_mappings: dict[str, tuple[str, int]] = {}
    file_mappings: dict[str, str] = {}
    commits_analyzed: set[str] = set()

    for status, old_path, new_path in git.name_status(log):
        if not status:
            commits_analyzed.add(old_path[:8])
            continue
        if not status.startswith('R') or new_path is None:
            continue

        old_name = Path(old_path).name
        new_name = Path(new_path).name
        old_dir = str(Path(old_path).parent)
        new_dir = str(Path(new_path).parent)

        if old_name != new_name:
            file_mappings[old_name] = new_name

        if old_dir != new_dir and old_dir != '.':
            old_parts = old_dir.split('/')
            new_parts = new_dir.split('/')

            if old_parts[0] != new_parts[0] or len(old_parts) != len(new_parts):
                old_key = f'{old_dir}/'
                new_val = f'{new_dir}/'
                if old_key in directory_mappings:
                    existing_new, count = directory_mappings[old_key]
                    directory_mappings[old_key] = (existing_new, count + 1)
                else:
                    directory_mappings[old_key] = (new_val, 1)

    rules_path = get_rules_path(repo_root)
    rules_path.parent.mkdir(parents=True, exist_ok=True)

    sorted_dirs = sorted(directory_mappings.items(), key=lambda x: -x[1][1])
    top_directory_mappings = {k: v[0] for k, v in sorted_dirs[:20]}
    rules = {
        '_metadata': {
            'generated': dt.datetime.now().isoformat()[:19],
            'time_window': time_window,
            'commits_analyzed': len(commits_analyzed),
        },
        'directory_mappings': top_directory_mappings,
        'file_mappings': file_mappings,
    }

    with rules_path.open('w') as f:
        json.dump(rules, f, indent=2)

    return LearnedRules(
        path=rules_path,
        time_window=time_window,
        commits_analyzed=len(commits_analyzed),
        directory_mappings=len(top_directory_mappings),
        file_mappings=len(file_mappings),
    )
