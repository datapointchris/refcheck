"""Which files and directories a scan reads."""

from fnmatch import fnmatch
from pathlib import Path

CARGO_BUILD_DIR = 'target beside a Cargo.toml'


def is_cargo_build_dir(directory: Path) -> bool:
    """Whether a directory is Cargo's build output, which sits beside the Cargo.toml that owns it.

    Its dependency files and fingerprints name every source file as of the last
    build. Deleting one module from a Rust workspace failed --moves on two `.d`
    files under crates/target and on nothing else. A `target` with no Cargo.toml
    beside it is matched by nothing here, so a source directory of that name is
    still read.
    """
    return directory.name == 'target' and (directory.parent / 'Cargo.toml').is_file()


class ScanScope:
    """The exclusions one tree is scanned under, asked of repo-relative paths."""

    BINARY_SUFFIXES = {'.pyc', '.so', '.o', '.a', '.dylib'}

    def __init__(self, root_dir: Path, exclude_dirs: set[str], exclude_patterns: list[str]):
        self.root_dir = root_dir
        self.exclude_dirs = exclude_dirs
        self.exclude_patterns = exclude_patterns

    def should_skip_directory(self, rel_path: Path) -> bool:
        """Whether a whole subtree is outside what the scan reads.

        Asked during the descent rather than after it, so an excluded
        directory is never entered. That is what keeps it out of the coverage
        claim as well as out of the results: a directory the scan was
        configured to skip is outside what the run promised to read, so a
        refusal inside it is not a shortfall and must not fail the run.

        A subtree pattern is matched against the path with a trailing slash.
        `build/**` describes what is under `build`, and without the slash the
        directory itself matches nothing while everything inside it matches.
        """
        if any(part in self.exclude_dirs for part in rel_path.parts):
            return True
        if is_cargo_build_dir(self.root_dir / rel_path):
            return True
        return any(fnmatch(f'{rel_path.as_posix()}/', pattern) for pattern in self.exclude_patterns)

    def should_skip_file(self, rel_path: Path) -> bool:
        """Whether a file is outside what the scan reads, by its place, its name or its content."""
        if any(part in self.exclude_dirs for part in rel_path.parts):
            return True

        if any(is_cargo_build_dir(self.root_dir / parent) for parent in rel_path.parents if parent.name == 'target'):
            return True

        if self._matches_exclusion(rel_path):
            return True

        if rel_path.suffix in self.BINARY_SUFFIXES:
            return True

        # Callers pass a repo-relative path, so the read is anchored at the root
        # rather than at the working directory. Scanning a repo that is not the
        # one you are standing in opened the wrong path, got OSError, and read
        # "not binary" — which let a 30 MB Go executable through as text.
        return self._holds_binary_content(self.root_dir / rel_path)

    def _matches_exclusion(self, rel_path: Path) -> bool:
        """Match an exclusion pattern against a repo-relative path.

        Two matchers, because the patterns are two kinds. `*.log` and
        `CHANGELOG.md` name a file wherever it sits, which is Path.match's
        right-anchored semantics. `dir/**` names a subtree — and Path.match
        reads `**` as one component, so alone it would exclude
        `build/reports/top.json` while scanning `build/reports/a/b.json`
        right beside it. fnmatch over the posix string is anchored at the root and
        lets `*` cross separators, which is what a subtree pattern means.
        """
        posix = rel_path.as_posix()
        return any(rel_path.match(pattern) or fnmatch(posix, pattern) for pattern in self.exclude_patterns)

    @staticmethod
    def _holds_binary_content(file_path: Path) -> bool:
        """True if the first block holds a NUL byte — the heuristic git uses.

        A suffix list never keeps up. A multi-gigabyte SQLite database with no
        matching extension was read as text and pattern-matched, producing 29 of
        the 31 hits for one `--pattern` query. Every false positive spends the
        credibility this tool needs to get used at all.
        """
        try:
            with file_path.open('rb') as handle:
                return b'\0' in handle.read(8192)
        except OSError:
            return False
