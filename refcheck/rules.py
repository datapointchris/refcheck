"""Rules loading and learning from git history."""

import datetime as dt
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import git
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


def get_repo_root(cwd: Path | None = None) -> Path | None:
    """Get git repo root, or None if not in a repo."""
    try:
        return Path(git.run(['rev-parse', '--show-toplevel'], cwd=cwd).strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def get_rules_path(repo_root: Path) -> Path:
    """Get the rules file path for a given repo root."""
    safe_name = str(repo_root).lstrip('/').replace('/', '--')
    return user_state_dir() / 'repos' / safe_name / 'rules.json'


def load_rules(root_dir: Path) -> tuple[dict, Path | None]:
    """
    Load rules from repos/{safe-repo-path}/rules.json under the user state directory.

    Returns (rules_dict, rules_path) tuple.
    """
    rules: dict = {'directory_mappings': {}, 'file_mappings': {}}
    rules_path = None

    repo_root = get_repo_root(root_dir)
    if repo_root is None:
        return rules, rules_path

    rules_path = get_rules_path(repo_root)

    if rules_path.exists():
        try:
            with rules_path.open() as f:
                loaded = json.load(f)
                if loaded:
                    rules = loaded
        except (OSError, json.JSONDecodeError):
            return rules, rules_path

    return rules, rules_path


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
    repo_root = get_repo_root()
    if repo_root is None:
        raise NotAGitRepository('not a git repository (or any of the parent directories): .git')

    try:
        log = git.run(
            [
                'log',
                f'--since={time_window} ago',
                '--diff-filter=R',
                '-M',
                '--name-status',
                '--format=%H %aI',
            ],
            cwd=repo_root,
        )
    except subprocess.CalledProcessError as error:
        raise LearnRulesError(f'git could not read the rename history: {error.stderr.strip() or error}') from error

    directory_mappings: dict[str, tuple[str, int]] = {}
    file_mappings: dict[str, str] = {}
    commits_analyzed: set[str] = set()

    for line in log.splitlines():
        line = line.strip()
        if not line:
            continue

        if ' ' in line and len(line.split()[0]) == 40:
            commits_analyzed.add(line.split()[0][:8])
            continue

        if line.startswith('R'):
            parts = line.split('\t')
            if len(parts) == 3:
                old_path = parts[1]
                new_path = parts[2]

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
