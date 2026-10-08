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
from .output import Unreadable
from .registry import Registry
from .registry import Repo


@dataclass
class RepoResult:
    """What one repo in the sweep had to say."""

    repo: Repo
    issues: list[Issue] = field(default_factory=list)
    unreadable: list[Unreadable] = field(default_factory=list)
    filenames: set[str] = field(default_factory=set)


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
    def filenames(self) -> set[str]:
        """Every filename a swept repo still holds.

        A filename still on disk names that file, so a citation of it is not
        stale evidence of anything. `main.go` leaving one repo is not news to
        the others.
        """
        return {name for result in self.results for name in result.filenames}

    @property
    def scanned(self) -> int:
        return len(self.results)

    @property
    def issues(self) -> list[Issue]:
        return [issue for result in self.results for issue in result.issues]

    @property
    def with_issues(self) -> list[RepoResult]:
        return [result for result in self.results if result.issues]

    @property
    def with_unreadable(self) -> list[RepoResult]:
        return [result for result in self.results if result.unreadable]

    @property
    def unreached(self) -> bool:
        """True when the sweep was asked for a repo or a file it could not read.

        Retired is the one deliberate skip and is not counted here. Everything
        else in this list is the sweep failing to look: an entry naming no path,
        a repo the machine does not hold, a directory that would not list, a
        file that would not open. Each one shrinks what the run covered without
        changing what it claims, and a clean result that means nothing is the
        only outcome this tool cannot afford.
        """
        return bool(self.absent or self.unusable or self.with_unreadable)


def homes_by_path(registry: Registry) -> dict[Path, str]:
    """Which repo holds a resolved path, for every listed repo on disk.

    Keyed physically, since that is the form a token is compared against once
    its symlinks and `..` are walked out. A repo reached through a symlink is
    then credited to the repo that holds the file rather than to nothing.

    A repo this machine does not hold is left out. Nothing inside one exists,
    so every reference into it would resolve to a missing file and be reported.
    """
    return {Path(os.path.realpath(repo.path)): repo.name for repo in registry.repos if repo.is_on_disk}


def homes_by_name(registry: Registry) -> dict[str, Path]:
    """Where a named repo sits, for every listed repo on disk.

    The same set keyed the other way, for a citation that names its target
    rather than spelling a path to it. Not `homes_by_path` inverted: two
    declared paths can walk out to one physical directory, and inverting would
    drop whichever name lost the collision.

    An absent repo is excluded here for its own reason, not as a copy of the
    one above. A citation naming a repo this machine has never cloned would
    otherwise resolve to a path that cannot exist, and every such citation
    would be reported as a stale reference into a repo nobody can check.
    """
    return {repo.name: Path(os.path.realpath(repo.path)) for repo in registry.repos if repo.is_on_disk}


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

    live = _partition(registry, sweep)

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
    homes = homes_by_path(registry)
    sweep.source_is_listed = source_root is None or Path(os.path.realpath(source_root)) in homes
    paths = homes_by_name(registry)

    for repo in live:
        checker = _checker_for(repo, skip_docs, file_type, test_mode, flag_excludes)
        checker.check_patterns_across_repos(patterns, homes, paths)
        sweep.results.append(RepoResult(repo=repo, issues=checker.issues, unreadable=checker.unreadable, filenames=checker.filenames()))

    return sweep


def names_across_repos(
    registry: Registry,
    names: dict[str, str],
    skip_docs: bool = False,
    file_type: str | None = None,
    test_mode: bool = False,
    flag_excludes: Sequence[str] = (),
    already_scanned: Path | None = None,
) -> SweepResult:
    """Ask every listed repo where it still names a tool that was renamed.

    The other half of a rename. A moved path is something git recorded and a
    resolver can test, while a renamed tool is a word left in prose, commands and
    paths across every repo and store that ever mentioned it. Neither the renaming
    repo nor a path check can see those, so the sweep reads them where they are.

    Nothing is credited to an owner, because a name is stale wherever it stands.

    `already_scanned` is the tree the local run read, and the sweep reads none of
    it again, which would print every finding twice. It reads everything else,
    including the rest of a repo the local run was narrowed inside: a narrowed
    run that skipped its whole starting repo here would tick over files nobody
    read.
    """
    sweep = SweepResult(unusable=list(registry.unusable))

    if not names:
        return sweep

    scanned = Path(os.path.realpath(already_scanned)) if already_scanned is not None else None
    for repo in _partition(registry, sweep):
        home = Path(os.path.realpath(repo.path))
        skip: list[str] = []
        if scanned is not None and scanned.is_relative_to(home):
            if scanned == home:
                continue
            inside = scanned.relative_to(home).as_posix()
            skip = [inside, f'{inside}/**']
        checker = _checker_for(repo, skip_docs, file_type, test_mode, [*flag_excludes, *skip])
        checker.check_names(names)
        sweep.results.append(RepoResult(repo=repo, issues=checker.issues, unreadable=checker.unreadable))

    return sweep


def _partition(registry: Registry, sweep: SweepResult) -> list[Repo]:
    """The repos to walk, with the retired and the absent recorded on the sweep."""
    live = []
    for repo in registry.repos:
        if not repo.is_swept:
            sweep.retired.append(repo)
        elif not repo.is_on_disk:
            sweep.absent.append(repo)
        else:
            live.append(repo)
    return live


def _checker_for(
    repo: Repo,
    skip_docs: bool,
    file_type: str | None,
    test_mode: bool,
    flag_excludes: Sequence[str],
) -> ReferenceChecker:
    """A checker rooted at one listed repo, reading that repo's own exclusions."""
    config = load_config(repo.path)
    config.exclude = [*config.exclude, *flag_excludes]
    return ReferenceChecker(
        root_dir=repo.path,
        search_path=repo.path,
        skip_docs=skip_docs,
        file_type=file_type,
        test_mode=test_mode,
        warn_fragile=False,
        config=config,
    )
