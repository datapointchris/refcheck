"""The move sweep, run across every repo on the machine rather than one.

A rename is answerable in the repo that made it and unanswerable everywhere
else, which is the whole gap. `--moves` asks what still points at the old name
and can only ask it of the tree it is standing in, so a consumer in another repo
keeps a path that no longer resolves and no check ever looks at it. The renaming
repo cannot see its consumers, and nothing pointed refcheck at them.

Driving the sweep from git's own rename history is what makes it free at the
moment it is worth running. The patterns are not typed in; they are what the
commit already recorded.
"""

import os
from collections.abc import Sequence
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

from .checker import ReferenceChecker
from .config import load_config
from .output import Issue
from .registry import Registry
from .registry import Repo


@dataclass
class RepoResult:
    """What one repo in the sweep had to say."""

    repo: Repo
    issues: list[Issue] = field(default_factory=list)


@dataclass
class SweepResult:
    """The sweep's findings, and what it did not look at.

    Four things stop a repo owning a gone path and they arrive from three
    places: never listed, listed but unreadable, listed and retired, listed and
    not on disk. All four end in the same tick unless each is counted, and a
    reader cannot then tell "no stale references" from "the repo the file left
    was not in the map".
    """

    results: list[RepoResult] = field(default_factory=list)
    retired: list[Repo] = field(default_factory=list)
    absent: list[Repo] = field(default_factory=list)
    unusable: list[str] = field(default_factory=list)
    source_root: Path | None = None
    source_is_listed: bool = True

    @property
    def scanned(self) -> int:
        return len(self.results)

    @property
    def issues(self) -> list[Issue]:
        return [issue for result in self.results for issue in result.issues]

    @property
    def with_issues(self) -> list[RepoResult]:
        return [result for result in self.results if result.issues]


def across_repos(
    registry: Registry,
    patterns: dict[str, str],
    skip_docs: bool = False,
    file_type: str | None = None,
    test_mode: bool = False,
    flag_excludes: Sequence[str] = (),
    source_root: Path | None = None,
) -> SweepResult:
    """Ask every listed repo what it still points at, in one walk each.

    A repo whose directory is not there is reported rather than skipped in
    silence: a registry naming a path this machine does not hold is drift of its
    own, and a sweep that quietly covered fewer repos than the caller believes
    is the false clean this tool exists to avoid.

    Every filter narrowing the local run narrows this one too. A flag reaching
    part of the work and silently not the rest is the failure mode a narrowing
    flag has, because it is designed against the case it was invented for. Each
    repo still reads its own declared exclusions, with the flag's added on top —
    which of a repo's directories hold generated output is a fact only that repo
    knows, and it stays that way across ninety of them.
    """
    sweep = SweepResult(unusable=list(registry.unusable), source_root=source_root)

    # Nothing moved, so no repo is asked anything. Walking them to report a
    # clean 90 would be a sweep that read no files claiming it read them all.
    if not patterns:
        return sweep

    live = []
    for repo in registry.repos:
        if not repo.is_swept:
            sweep.retired.append(repo)
        elif not repo.is_on_disk:
            sweep.absent.append(repo)
        else:
            live.append(repo)

    # Which repos are walked and which can own a gone path are different
    # questions, and only the first one is about where a fix would land. A live
    # repo holding a path into a retired one still holds a path that does not
    # resolve, and the edit that fixes it is in the live repo. So the map is
    # every listed repo on disk; only the walk list drops the retired.
    #
    # Absent repos stay out of both. Without that, every reference into a repo
    # this machine does not hold becomes a hit, because nothing there exists.
    # Keyed by the physical path, since that is the form a token is compared
    # against. A repo reached through a symlink is then credited to the repo
    # that holds the file rather than to nothing.
    homes = {Path(os.path.realpath(repo.path)): repo.name for repo in registry.repos if repo.is_on_disk}
    sweep.source_is_listed = source_root is None or Path(os.path.realpath(source_root)) in homes

    for repo in live:
        config = load_config(repo.path)
        config.exclude = [*config.exclude, *flag_excludes]
        checker = ReferenceChecker(
            root_dir=repo.path,
            search_path=repo.path,
            skip_docs=skip_docs,
            file_type=file_type,
            test_mode=test_mode,
            warn_fragile=False,
            config=config,
        )
        checker.check_patterns_across_repos(patterns, homes)
        sweep.results.append(RepoResult(repo=repo, issues=checker.issues))

    return sweep
