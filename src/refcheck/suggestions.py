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
        self._by_name: dict[str, list[Path]] | None = None

    def build_file_index(self) -> list[Path]:
        """Build index of all files in repo for suggestion matching."""
        if self._file_index is None:
            self._file_index = self._list_files()
        return self._file_index

    def files_named(self) -> dict[str, list[Path]]:
        """Each basename in the index with the files carrying it, in index order.

        Every broken reference asks for a name, so the index is grouped once
        rather than scanned once per question.
        """
        if self._by_name is None:
            self._by_name = {}
            for file_path in self.build_file_index():
                self._by_name.setdefault(file_path.name, []).append(file_path)
        return self._by_name

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
        by_name = self.files_named()
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
            for f in by_name.get(new_name, []):
                add_suggestion(str(f), 'known mapping')

        # 1. Exact basename match
        for f in by_name.get(basename, []):
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

        # The index is sorted, so sorting the variants' files keeps index order.
        for f in sorted(f for variant in variants for f in by_name.get(variant, [])):
            add_suggestion(str(f), 'name variant')

        # 3. Fuzzy match using difflib (only if few suggestions so far).
        # Over distinct names, so three files sharing one name take one slot.
        if len(suggestions) < 3:
            matches = get_close_matches(basename, list(by_name), cutoff=0.8)
            for m in matches:
                if m != basename and m not in variants:
                    add_suggestion(str(by_name[m][0]), 'similar name')

        return suggestions[:5]
