"""File similarity and suggestion finding."""

from collections.abc import Callable
from difflib import get_close_matches
from pathlib import Path

from .scan_scope import ScanScope


class FileSuggestions:
    """Find similar files for missing references."""

    def __init__(self, scope: ScanScope, list_files: Callable[[], list[Path]] | None = None):
        """`list_files` gives the repo-relative files a scan of the whole tree already found, so they are not walked and judged again."""
        self.root_dir = scope.root_dir
        self.scope = scope
        self._list_files = list_files or self._walk
        self._file_index: list[Path] | None = None

    def build_file_index(self) -> list[Path]:
        """Build index of all files in repo for suggestion matching."""
        if self._file_index is None:
            self._file_index = self._list_files()
        return self._file_index

    def _walk(self) -> list[Path]:
        """Every file under the root the scope reads, repo-relative. An excluded directory is never entered."""
        files = []
        for directory, directory_names, file_names in self.root_dir.walk():
            rel_dir = directory.relative_to(self.root_dir)
            directory_names[:] = [name for name in directory_names if not self.scope.should_skip_directory(rel_dir / name)]
            for name in file_names:
                rel_path = rel_dir / name
                if (directory / name).is_file() and not self.scope.should_skip_file(rel_path):
                    files.append(rel_path)
        return sorted(files)

    def find_similar_files(self, missing_path: str, rules: dict) -> list[str]:
        """
        Find files that might be renamed versions of missing_path.

        Searches for:
        1. Exact basename matches anywhere in repo
        2. Transform variants (hyphen <-> underscore, case changes)
        3. Fuzzy matches using difflib
        4. Known mappings from rules file
        """
        file_index = self.build_file_index()
        basename = Path(missing_path).name
        suggestions = []
        seen_paths: set[str] = set()

        def add_suggestion(path: str, reason: str):
            if path not in seen_paths:
                seen_paths.add(path)
                suggestions.append(f'{path} ({reason})')

        # Check directory mappings from rules
        for old_prefix, new_prefix in rules.get('directory_mappings', {}).items():
            if missing_path.startswith(old_prefix):
                mapped_path = missing_path.replace(old_prefix, new_prefix, 1)
                if (self.root_dir / mapped_path).exists():
                    add_suggestion(mapped_path, 'known mapping')

        # Check file mappings from rules
        if basename in rules.get('file_mappings', {}):
            new_name = rules['file_mappings'][basename]
            for f in file_index:
                if f.name == new_name:
                    add_suggestion(str(f), 'known mapping')

        # 1. Exact basename match
        for f in file_index:
            if f.name == basename:
                add_suggestion(str(f), 'basename match')

        # 2. Transform variants (hyphen <-> underscore)
        variants = {
            basename.replace('-', '_'),
            basename.replace('_', '-'),
            basename.lower(),
            basename.replace('-', '_').lower(),
            basename.replace('_', '-').lower(),
        }
        variants.discard(basename)

        for f in file_index:
            if f.name in variants:
                add_suggestion(str(f), 'name variant')

        # 3. Fuzzy match using difflib (only if few suggestions so far)
        if len(suggestions) < 3:
            all_names = [f.name for f in file_index]
            matches = get_close_matches(basename, all_names, cutoff=0.8)
            for m in matches:
                if m != basename and m not in variants:
                    for f in file_index:
                        if f.name == m:
                            add_suggestion(str(f), 'similar name')
                            break

        return suggestions[:5]
