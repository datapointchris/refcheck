"""Rules loading and learning from git history."""

import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional


def get_repo_root(cwd: Path = None) -> Optional[Path]:
    """Get git repo root, or None if not in a repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd,
        )
        return Path(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def get_rules_path(repo_root: Path) -> Path:
    """Get the rules file path for a given repo root."""
    safe_name = str(repo_root).lstrip("/").replace("/", "--")
    return Path.home() / ".config" / "refcheck" / "repos" / safe_name / "rules.json"


def load_rules(root_dir: Path) -> tuple[Dict, Optional[Path]]:
    """
    Load rules from ~/.config/refcheck/repos/{safe-repo-path}/rules.json.

    Returns (rules_dict, rules_path) tuple.
    """
    rules = {"directory_mappings": {}, "file_mappings": {}}
    rules_path = None

    repo_root = get_repo_root(root_dir)
    if repo_root is None:
        return rules, rules_path

    rules_path = get_rules_path(repo_root)

    if rules_path.exists():
        try:
            with open(rules_path) as f:
                loaded = json.load(f)
                if loaded:
                    rules = loaded
        except Exception:
            pass

    return rules, rules_path


def get_rules_age_days(rules: Dict) -> Optional[int]:
    """
    Get the age of the rules in days from metadata.

    Returns None if rules have no timestamp.
    """
    metadata = rules.get("_metadata", {})
    generated = metadata.get("generated")

    if not generated:
        return None

    try:
        generated_dt = datetime.fromisoformat(generated)
        now = datetime.now()
        delta = now - generated_dt
        return delta.days
    except (ValueError, TypeError):
        return None


def learn_rules_from_git(time_window: str = "6 months") -> None:
    """
    Scan git history for renames and generate rules.json.

    Always operates from the git repo root, regardless of cwd.
    Analyzes git rename operations from the specified time window to extract:
    - Directory prefix mappings (e.g., management/tests/ -> tests/install/)
    - File name mappings (e.g., parse-packages.py -> parse_packages.py)
    """
    repo_root = get_repo_root()
    if repo_root is None:
        print(
            "fatal: not a git repository (or any of the parent directories): .git",
            file=sys.stderr,
        )
        sys.exit(128)

    try:
        result = subprocess.run(
            [
                "git",
                "log",
                f"--since={time_window} ago",
                "--diff-filter=R",
                "-M",
                "--name-status",
                "--format=%H %aI",
            ],
            capture_output=True,
            text=True,
            check=True,
            cwd=repo_root,
        )
    except subprocess.CalledProcessError as e:
        print(f"Error running git: {e}", file=sys.stderr)
        sys.exit(1)

    directory_mappings = defaultdict(int)
    file_mappings = {}
    commits_analyzed = set()

    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue

        if " " in line and len(line.split()[0]) == 40:
            commits_analyzed.add(line.split()[0][:8])
            continue

        if line.startswith("R"):
            parts = line.split("\t")
            if len(parts) == 3:
                old_path = parts[1]
                new_path = parts[2]

                old_name = Path(old_path).name
                new_name = Path(new_path).name
                old_dir = str(Path(old_path).parent)
                new_dir = str(Path(new_path).parent)

                if old_name != new_name:
                    file_mappings[old_name] = new_name

                if old_dir != new_dir and old_dir != ".":
                    old_parts = old_dir.split("/")
                    new_parts = new_dir.split("/")

                    if old_parts[0] != new_parts[0] or len(old_parts) != len(new_parts):
                        old_key = f"{old_dir}/"
                        new_val = f"{new_dir}/"
                        if old_key in directory_mappings:
                            existing_new, count = directory_mappings[old_key]
                            directory_mappings[old_key] = (existing_new, count + 1)
                        else:
                            directory_mappings[old_key] = (new_val, 1)

    rules_path = get_rules_path(repo_root)
    rules_path.parent.mkdir(parents=True, exist_ok=True)

    sorted_dirs = sorted(directory_mappings.items(), key=lambda x: -x[1][1])
    rules = {
        "_metadata": {
            "generated": datetime.now().isoformat()[:19],
            "time_window": time_window,
            "commits_analyzed": len(commits_analyzed),
        },
        "directory_mappings": {k: v[0] for k, v in sorted_dirs[:20]},
        "file_mappings": file_mappings,
    }

    with open(rules_path, "w") as f:
        json.dump(rules, f, indent=2)

    print(f"✅ Generated {rules_path}")
    print(f"   Time window: {time_window}")
    print(f"   Commits analyzed: {len(commits_analyzed)}")
    print(f"   Directory mappings: {len(rules['directory_mappings'])}")
    print(f"   File mappings: {len(file_mappings)}")
