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

from dataclasses import dataclass
from dataclasses import field

from .checker import ReferenceChecker
from .config import load_config
from .output import Issue
from .registry import Repo


@dataclass
class RepoResult:
    """What one repo in the sweep had to say."""

    repo: Repo
    issues: list[Issue] = field(default_factory=list)


@dataclass
class SweepResult:
    """The sweep's findings, and what it did not look at."""

    results: list[RepoResult] = field(default_factory=list)
    retired: list[Repo] = field(default_factory=list)
    absent: list[Repo] = field(default_factory=list)

    @property
    def scanned(self) -> int:
        return len(self.results)

    @property
    def issues(self) -> list[Issue]:
        return [issue for result in self.results for issue in result.issues]

    @property
    def with_issues(self) -> list[RepoResult]:
        return [result for result in self.results if result.issues]


def across_repos(repos: list[Repo], patterns: dict[str, str], skip_docs: bool = False) -> SweepResult:
    """Ask every listed repo what it still points at, in one walk each.

    A repo whose directory is not there is reported rather than skipped in
    silence: a registry naming a path this machine does not hold is drift of its
    own, and a sweep that quietly covered fewer repos than the caller believes
    is the false clean this tool exists to avoid.
    """
    sweep = SweepResult()

    # Nothing moved, so no repo is asked anything. Walking them to report a
    # clean 90 would be a sweep that read no files claiming it read them all.
    if not patterns:
        return sweep

    live = []
    for repo in repos:
        if not repo.is_swept:
            sweep.retired.append(repo)
        elif not repo.is_on_disk:
            sweep.absent.append(repo)
        else:
            live.append(repo)

    # Every repo's home, so a hit can be credited to the repo whose file went
    # away. A path reaching none of them names something outside the registry
    # and is nobody's stale reference.
    homes = {repo.path: repo.name for repo in live}

    for repo in live:
        checker = ReferenceChecker(
            root_dir=repo.path,
            search_path=repo.path,
            skip_docs=skip_docs,
            warn_fragile=False,
            config=load_config(repo.path),
        )
        checker.check_patterns_across_repos(patterns, homes)
        sweep.results.append(RepoResult(repo=repo, issues=checker.issues))

    return sweep
