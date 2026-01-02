"""Core reference checking logic."""

import re
from pathlib import Path
from typing import Dict, List, Optional, Set

from .config import Config
from .output import CheckType, Issue, Warning
from .rules import load_rules
from .suggestions import FileSuggestions


class ReferenceChecker:
    """Validates file references across a codebase."""

    DEFAULT_EXCLUDES = {
        ".git",
        "node_modules",
        ".venv",
        "site",
        "__pycache__",
        ".cache",
    }

    DEFAULT_EXCLUDE_PATTERNS = [
        "*.pyc",
        ".claude/metrics/**",
        ".planning/**",
        "site/**",
    ]

    TEST_FIXTURE_PATTERNS = [
        "tests/apps/test-refcheck.sh",
        "tests/apps/fixtures/refcheck-*/**",
        "docs/archive/**",
    ]

    DYNAMIC_PATH_PATTERNS = [
        r"^\$",
        r"^/tmp/",
        r"^/root/",
        r"^/home/",
        r"^/Users/",
        r"/nvm\.sh$",
        r"^/lib/lib\.sh",
    ]

    def __init__(
        self,
        root_dir: Path = None,
        search_path: Path = None,
        skip_docs: bool = False,
        file_type: str = None,
        warn_fragile: bool = True,
        strict: bool = False,
        test_mode: bool = False,
        config: Config = None,
    ):
        self.root_dir = root_dir or Path.cwd()
        self.search_path = search_path or self.root_dir
        self.skip_docs = skip_docs
        self.file_type = file_type
        self.warn_fragile = warn_fragile
        self.strict = strict
        self.test_mode = test_mode
        self.config = config or Config()
        self.issues: List[Issue] = []
        self.warnings: List[Warning] = []
        self.exclude_dirs = self.DEFAULT_EXCLUDES.copy()
        self.exclude_patterns = self.DEFAULT_EXCLUDE_PATTERNS.copy()
        self._rules: Optional[Dict] = None
        self._rules_path: Optional[Path] = None

        if not test_mode:
            self.exclude_patterns.extend(self.TEST_FIXTURE_PATTERNS)

        self._suggestions = FileSuggestions(
            self.root_dir, self.exclude_dirs, self.exclude_patterns
        )

    def should_skip_file(self, file_path: Path) -> bool:
        """Determine if file should be skipped."""
        return self._suggestions.should_skip_file(file_path)

    def is_dynamic_path(self, path: str) -> bool:
        """Check if path is dynamic/runtime-generated."""
        for pattern in self.DYNAMIC_PATH_PATTERNS:
            if re.search(pattern, path):
                return True
        return False

    def load_rules(self) -> Dict:
        """Load rules from config directory."""
        if self._rules is not None:
            return self._rules
        self._rules, self._rules_path = load_rules(self.root_dir)
        return self._rules

    def find_similar_files(self, missing_path: str) -> List[str]:
        """Find files that might be renamed versions of missing_path."""
        rules = self.load_rules()
        return self._suggestions.find_similar_files(missing_path, rules)

    def find_files(self, pattern: str = "**/*") -> List[Path]:
        """Find all files matching pattern, respecting exclusions."""
        files = []
        search_root = self.search_path

        # Handle single file argument
        if search_root.is_file():
            if self.file_type and search_root.suffix != f".{self.file_type}":
                return files
            try:
                rel_path = search_root.relative_to(self.root_dir)
            except ValueError:
                return files
            if not self.should_skip_file(rel_path):
                files.append(search_root)
            return files

        for file_path in search_root.glob(pattern):
            if not file_path.is_file():
                continue

            try:
                rel_path = file_path.relative_to(self.root_dir)
            except ValueError:
                continue

            if self.should_skip_file(rel_path):
                continue

            if self.file_type and file_path.suffix != f".{self.file_type}":
                continue

            files.append(file_path)

        return files

    def check_pattern(self, pattern: str, description: str = None):
        """Check for old path pattern references."""
        description = description or f"Old pattern: {pattern}"

        for file_path in self.find_files():
            if self.skip_docs and file_path.suffix == ".md":
                continue

            if file_path.name in ("refcheck", "verify-references.py", "verify-file-references.sh"):
                continue

            try:
                rel_path = file_path.relative_to(self.root_dir)
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line_num, line in enumerate(f, 1):
                        if pattern in line:
                            self.issues.append(
                                Issue(
                                    file=rel_path,
                                    line_num=line_num,
                                    check_type=CheckType.PATTERN,
                                    message=f"Found: {pattern}",
                                    suggestion=description,
                                )
                            )
            except (OSError, UnicodeDecodeError):
                continue

    def go_up_n_levels(self, file_path: Path, n: int) -> Path:
        """Go up N directory levels from file_path."""
        path = file_path.parent
        for _ in range(n - 1):
            path = path.parent
        return path

    def find_repo_root(self, file_path: Path) -> Path:
        """Find git repo root from file path."""
        current = file_path.parent
        while current != current.parent:
            if (current / ".git").exists():
                return current
            current = current.parent
        return self.root_dir

    def parse_variable_assignments(self, file_path: Path) -> Dict[str, str]:
        """Parse common shell variable assignment patterns."""
        symbol_table = {}

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError):
            return symbol_table

        if re.search(r'SCRIPT_DIR="\$\(cd.*BASH_SOURCE', content):
            symbol_table["SCRIPT_DIR"] = str(file_path.parent)

        match = re.search(r'DOTFILES_DIR="\$\(cd "\$SCRIPT_DIR/((?:\.\./?)+)" && pwd\)"', content)
        if match:
            relative_path = match.group(1)
            levels_up = relative_path.count("..")
            symbol_table["DOTFILES_DIR"] = str(self.go_up_n_levels(file_path, levels_up + 1))

        if re.search(r'DOTFILES_DIR="\$\{DOTFILES_DIR:-\$HOME/dotfiles\}"', content):
            symbol_table["DOTFILES_DIR"] = str(self.find_repo_root(file_path))

        return symbol_table

    def resolve_path(self, path_str: str, symbol_table: Dict[str, str], file_path: Path) -> str:
        """Resolve a path containing shell variables."""
        resolved = path_str

        for var_name, var_value in symbol_table.items():
            resolved = resolved.replace(f"${var_name}", var_value)
            resolved = resolved.replace(f"${{{var_name}}}", var_value)

        if "$" in resolved:
            raise ValueError(f"Cannot resolve variables in: {path_str}")

        return resolved

    def check_source_statements(self):
        """Check that source statements point to existing files."""
        source_pattern = re.compile(r'source\s+["\']([^"\']+)["\']|source\s+\$[^/]*(/[^\s]+)')

        for file_path in self.find_files("**/*.sh"):
            try:
                rel_path = file_path.relative_to(self.root_dir)
                symbol_table = self.parse_variable_assignments(file_path)

                with open(file_path, "r", encoding="utf-8") as f:
                    for line_num, line in enumerate(f, 1):
                        if "source" not in line:
                            continue

                        match = source_pattern.search(line)
                        if not match:
                            continue

                        source_path = match.group(1) or match.group(2)
                        if not source_path:
                            continue

                        if "$" not in source_path and self.is_dynamic_path(source_path):
                            continue

                        original_path = source_path
                        if "$" in source_path:
                            try:
                                source_path = self.resolve_path(source_path, symbol_table, file_path)
                            except ValueError:
                                continue

                        if source_path.startswith("/"):
                            resolved = Path(source_path)
                        else:
                            resolved = self.root_dir / source_path

                        if not resolved.exists():
                            similar = self.find_similar_files(source_path)
                            self.issues.append(
                                Issue(
                                    file=rel_path,
                                    line_num=line_num,
                                    check_type=CheckType.SOURCE,
                                    message=f"Missing: {original_path}"
                                    + (f" → {source_path}" if original_path != source_path else ""),
                                    suggestion="Verify path exists or update reference",
                                    similar_files=similar,
                                )
                            )
            except (OSError, UnicodeDecodeError):
                continue

    def check_script_references(self):
        """Check that bash script references point to existing files."""
        script_pattern = re.compile(r'(?:bash|sh)\s+["\']?([^\s"\']+\.sh)["\']?')

        for file_path in self.find_files("**/*.sh"):
            if self.skip_docs and file_path.suffix == ".md":
                continue

            try:
                rel_path = file_path.relative_to(self.root_dir)
                with open(file_path, "r", encoding="utf-8") as f:
                    for line_num, line in enumerate(f, 1):
                        if "bash" not in line and "sh" not in line:
                            continue

                        for match in script_pattern.finditer(line):
                            script_path = match.group(1).rstrip("\"'")

                            if not script_path or self.is_dynamic_path(script_path):
                                continue

                            if line.strip().startswith("#") and script_path == file_path.name:
                                continue

                            if script_path.startswith("/"):
                                resolved = Path(script_path)
                            else:
                                resolved = self.root_dir / script_path

                            if not resolved.exists():
                                similar = self.find_similar_files(script_path)
                                self.issues.append(
                                    Issue(
                                        file=rel_path,
                                        line_num=line_num,
                                        check_type=CheckType.SCRIPT,
                                        message=f"Missing: {script_path}",
                                        suggestion="Verify script exists or update reference",
                                        similar_files=similar,
                                    )
                                )
            except (OSError, UnicodeDecodeError):
                continue

    def check_relative_path_fragility(self):
        """Check if relative paths are fragile to working directory changes."""
        source_pattern = re.compile(r'source\s+(?:["\']([^"\']+)["\']|([^\s]+))')

        for file_path in self.find_files("**/*.sh"):
            try:
                rel_path = file_path.relative_to(self.root_dir)

                with open(file_path, "r", encoding="utf-8") as f:
                    for line_num, line in enumerate(f, 1):
                        if "source" not in line:
                            continue

                        match = source_pattern.search(line)
                        if not match:
                            continue

                        source_path = match.group(1) or match.group(2)
                        if not source_path:
                            continue

                        if (
                            "$" in source_path
                            or source_path.startswith("/")
                            or self.is_dynamic_path(source_path)
                        ):
                            continue

                        test_dirs = [
                            self.root_dir,
                            file_path.parent,
                            file_path.parent.parent,
                        ]

                        valid_from = []
                        for test_dir in test_dirs:
                            resolved = test_dir / source_path
                            if resolved.exists():
                                valid_from.append(test_dir)

                        if 0 < len(valid_from) < len(test_dirs):
                            try:
                                valid_desc = ", ".join(
                                    str(d.relative_to(self.root_dir)) if d != self.root_dir else "repo root"
                                    for d in valid_from
                                )
                            except ValueError:
                                valid_desc = ", ".join(str(d) for d in valid_from)

                            self.warnings.append(
                                Warning(
                                    file=rel_path,
                                    line_num=line_num,
                                    check_type=CheckType.FRAGILE_CWD,
                                    message=f"Relative path only valid from: {valid_desc}",
                                    suggestion="Use absolute path or root directory variable",
                                )
                            )
            except (OSError, UnicodeDecodeError):
                continue

    def check_relative_traversal(self):
        """Detect relative directory traversal patterns fragile to file moves."""
        traversal_pattern = re.compile(r'([A-Z_]+_DIR)=.*\$\(cd.*\.\./.*pwd\)')

        for file_path in self.find_files("**/*.sh"):
            try:
                rel_path = file_path.relative_to(self.root_dir)

                with open(file_path, "r", encoding="utf-8") as f:
                    for line_num, line in enumerate(f, 1):
                        match = traversal_pattern.search(line)
                        if not match:
                            continue

                        var_name = match.group(1)

                        self.warnings.append(
                            Warning(
                                file=rel_path,
                                line_num=line_num,
                                check_type=CheckType.FRAGILE_REFACTOR,
                                message=f"{var_name} uses relative directory traversal (../) - fragile to file moves",
                                suggestion="Consider dynamic root detection: git rev-parse --show-toplevel",
                            )
                        )
            except (OSError, UnicodeDecodeError):
                continue

    def run_all_checks(self):
        """Run all validation checks."""
        self.load_rules()
        self.check_source_statements()
        self.check_script_references()

        if self.warn_fragile:
            self.check_relative_path_fragility()
            self.check_relative_traversal()

    def get_rules(self) -> Dict:
        """Get loaded rules."""
        return self._rules or {}

    def get_rules_path(self) -> Optional[Path]:
        """Get rules file path."""
        return self._rules_path
