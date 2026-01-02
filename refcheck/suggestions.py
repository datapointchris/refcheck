"""File similarity and suggestion finding."""

from difflib import get_close_matches
from pathlib import Path
from typing import Dict, List, Optional, Set


class FileSuggestions:
    """Find similar files for missing references."""

    def __init__(self, root_dir: Path, exclude_dirs: Set[str], exclude_patterns: List[str]):
        self.root_dir = root_dir
        self.exclude_dirs = exclude_dirs
        self.exclude_patterns = exclude_patterns
        self._file_index: Optional[List[Path]] = None

    def should_skip_file(self, file_path: Path) -> bool:
        """Determine if file should be skipped."""
        for part in file_path.parts:
            if part in self.exclude_dirs:
                return True

        for pattern in self.exclude_patterns:
            if file_path.match(pattern):
                return True

        if file_path.suffix in {".pyc", ".so", ".o", ".a", ".dylib"}:
            return True

        return False

    def build_file_index(self) -> List[Path]:
        """Build index of all files in repo for suggestion matching."""
        if self._file_index is not None:
            return self._file_index

        self._file_index = []
        for file_path in self.root_dir.rglob("*"):
            if not file_path.is_file():
                continue
            try:
                rel_path = file_path.relative_to(self.root_dir)
            except ValueError:
                continue
            if self.should_skip_file(rel_path):
                continue
            self._file_index.append(rel_path)
        return self._file_index

    def find_similar_files(self, missing_path: str, rules: Dict) -> List[str]:
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
        seen_paths: Set[str] = set()

        def add_suggestion(path: str, reason: str):
            if path not in seen_paths:
                seen_paths.add(path)
                suggestions.append(f"{path} ({reason})")

        # Check directory mappings from rules
        for old_prefix, new_prefix in rules.get("directory_mappings", {}).items():
            if missing_path.startswith(old_prefix):
                mapped_path = missing_path.replace(old_prefix, new_prefix, 1)
                if (self.root_dir / mapped_path).exists():
                    add_suggestion(mapped_path, "known mapping")

        # Check file mappings from rules
        if basename in rules.get("file_mappings", {}):
            new_name = rules["file_mappings"][basename]
            for f in file_index:
                if f.name == new_name:
                    add_suggestion(str(f), "known mapping")

        # 1. Exact basename match
        for f in file_index:
            if f.name == basename:
                add_suggestion(str(f), "basename match")

        # 2. Transform variants (hyphen <-> underscore)
        variants = {
            basename.replace("-", "_"),
            basename.replace("_", "-"),
            basename.lower(),
            basename.replace("-", "_").lower(),
            basename.replace("_", "-").lower(),
        }
        variants.discard(basename)

        for f in file_index:
            if f.name in variants:
                add_suggestion(str(f), "name variant")

        # 3. Fuzzy match using difflib (only if few suggestions so far)
        if len(suggestions) < 3:
            all_names = [f.name for f in file_index]
            matches = get_close_matches(basename, all_names, n=3, cutoff=0.8)
            for m in matches:
                if m != basename and m not in variants:
                    for f in file_index:
                        if f.name == m:
                            add_suggestion(str(f), "similar name")
                            break

        return suggestions[:5]
