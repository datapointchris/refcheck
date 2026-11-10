"""Rules loading and learning from git history."""

import contextlib
import datetime as dt
import functools
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import git
from . import repository
from .config import user_config_dir
from .config import user_state_dir


class LearnRulesError(Exception):
    """git could not read the rename history, or the rules file could not be written, so no rules changed."""


class NotAGitRepository(LearnRulesError):
    """The working directory is in no git repository, so it has no history to learn from."""


class RulesFileError(Exception):
    """A rules file that is there and cannot be read as rules, or cannot be deleted."""


@dataclass(frozen=True)
class LearnedRules:
    """What one learn run wrote, for the command to report."""

    path: Path
    time_window: str
    commits_analyzed: int
    directory_mappings: int
    file_mappings: int


def rules_root() -> Path:
    """The directory every checkout's rules sit under, with the earlier layout's files moved in."""
    root = user_state_dir() / 'checkouts'
    _adopt_the_earlier_layout(root)
    return root


def _rules_path_under(root: Path, checkout: Path) -> Path:
    return root / checkout.relative_to(checkout.anchor) / 'rules.json'


def get_rules_path(repo_root: Path) -> Path:
    """Where a checkout's rules live: its absolute path, mirrored under `rules_root`.

    Every checkout gets a directory of its own, so no two share a file, and
    the path can be found by hand from the checkout's.
    """
    return _rules_path_under(rules_root(), repo_root)


@functools.cache
def _adopt_the_earlier_layout(root: Path) -> None:
    """Move each rules file the earlier layout wrote to where `get_rules_path` looks, once per run.

    That layout named a checkout's directory by its path with `/` written as
    `--`, under `repos/` in the state directory or, before that, the config
    directory. A file already learned at the new place wins, and the earlier
    copy is deleted. A file that cannot be moved stays where it is.
    """
    for earlier in (root.parent / 'repos', user_config_dir() / 'repos'):
        for old in sorted(earlier.glob('*/rules.json')):
            new = _rules_path_under(root, Path('/' + old.parent.name.replace('--', '/')))
            try:
                if new.exists():
                    old.unlink()
                else:
                    new.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(old, new)
                old.parent.rmdir()
            except OSError:
                continue
        with contextlib.suppress(OSError):
            earlier.rmdir()


def no_rules() -> dict:
    return {'directory_mappings': {}, 'file_mappings': {}}


def read_rules(rules_path: Path) -> dict | None:
    """The rules in one file, or None where there is no file.

    A file that is there and cannot be read as rules raises RulesFileError.
    Empty mappings would read like a checkout whose history holds no rename.
    """
    try:
        with rules_path.open() as handle:
            loaded = json.load(handle)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise RulesFileError(f'{rules_path} could not be read: {error.strerror}') from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RulesFileError(f'{rules_path} is not JSON: {error}') from error
    if not isinstance(loaded, dict) or not all(isinstance(loaded.get(key), dict) for key in no_rules()):
        raise RulesFileError(f'{rules_path} holds no directory_mappings and file_mappings objects')
    return loaded


@dataclass(frozen=True)
class LoadedRules:
    """The rules a run reads, the file they come from, and why that file was not read where it could not be."""

    rules: dict
    path: Path | None
    unreadable: str | None = None


def load_rules(root_dir: Path) -> LoadedRules:
    """The rules for the repository holding root_dir.

    Outside a repository the path is None. With no rules file the rules are
    empty. A file that cannot be read leaves them empty too, with the reason,
    because rules only feed suggestions and the check runs without them.
    """
    repo_root = repository.root(root_dir)
    if repo_root is None:
        return LoadedRules(no_rules(), None)
    rules_path = get_rules_path(repo_root)
    try:
        return LoadedRules(read_rules(rules_path) or no_rules(), rules_path)
    except RulesFileError as error:
        return LoadedRules(no_rules(), rules_path, str(error))


def learned_checkouts() -> list[tuple[Path, Path]]:
    """Every checkout with rules on this machine, beside its rules file, in path order."""
    root = rules_root()
    return sorted((Path(root.anchor) / path.parent.relative_to(root), path) for path in root.rglob('rules.json'))


def clear_rules(checkout: Path) -> Path | None:
    """Delete a checkout's rules and the directories that leaves empty, returning the file deleted.

    None where the checkout had no rules. A file that is there and will not go
    raises RulesFileError.
    """
    path = get_rules_path(checkout)
    try:
        path.unlink()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise RulesFileError(f'{path} could not be deleted: {error.strerror}') from error
    root = rules_root()
    for parent in path.parents:
        if parent == root or not parent.is_relative_to(root):
            break
        try:
            parent.rmdir()
        except OSError:
            break
    return path


def write_rules(rules_path: Path, rules: dict) -> None:
    """Replace a checkout's rules file whole, so a write that fails leaves the previous file as it was.

    Raises LearnRulesError where the directory or the file cannot be written.
    """
    staged: Path | None = None
    try:
        rules_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile('w', dir=rules_path.parent, prefix='.rules.', suffix='.tmp', delete=False) as handle:
            staged = Path(handle.name)
            json.dump(rules, handle, indent=2)
        os.replace(staged, rules_path)
    except OSError as error:
        if staged is not None:
            staged.unlink(missing_ok=True)
        raise LearnRulesError(f'{rules_path} could not be written: {error.strerror}') from error


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

    sorted_dirs = sorted(directory_mappings.items(), key=lambda x: -x[1][1])
    top_directory_mappings = {k: v[0] for k, v in sorted_dirs[:20]}
    rules = {
        '_metadata': {
            'generated': dt.datetime.now(dt.UTC).isoformat(timespec='seconds'),
            'time_window': time_window,
            'commits_analyzed': len(commits_analyzed),
        },
        'directory_mappings': top_directory_mappings,
        'file_mappings': file_mappings,
    }

    write_rules(rules_path, rules)

    return LearnedRules(
        path=rules_path,
        time_window=time_window,
        commits_analyzed=len(commits_analyzed),
        directory_mappings=len(top_directory_mappings),
        file_mappings=len(file_mappings),
    )
