# refcheck

Fast reference validator for codebases. Finds broken file references,
fragile path patterns, and validates variable-based paths.

## What it does

`refcheck` validates file references across your codebase, checking for:

### Errors (always exit 1)

1. **Broken source statements** - Missing files in `source` commands
   (including variable paths like `$SCRIPT_DIR/file.sh`)
2. **Broken script references** - Missing files in `bash` or `sh` commands
3. **Old path patterns** - Stale references after refactoring

### Warnings (exit 0 unless --strict)

1. **Fragile to working directory** - Relative paths that only work from
   specific directories
2. **Fragile to refactoring** - Variable assignments using `../` traversal
   (breaks when files move)

## Why use it

**Proactive error detection:**

- Catch broken references before running expensive test suites
- Find issues in seconds vs minutes for full e2e tests
- Validate changes before committing

**Refactoring safety:**

- After moving files, verify all references updated
- Find stale patterns across entire codebase
- Custom pattern checking for any refactoring

**Better than grep:**

- Validates file existence, not just pattern matching
- Automatically filters false positives (docs, planning, dynamic paths)
- Structured output with suggestions
- Exit codes for CI/CD integration

**Variable path validation:**

- Resolves shell variables like `$SCRIPT_DIR` and `$DOTFILES_DIR` before
  validation
- Detects broken paths hidden behind variables
- Shows both original and resolved paths in error messages
- Gracefully skips unresolvable variables to avoid false positives

**Warning system:**

- Detects fragile patterns that may break in different contexts
- Configurable severity: warnings (default) or errors (--strict)
- Can be disabled for legacy codebases (--no-warn)
- Actionable suggestions for each warning

## Installation

```bash
uv tool install https://github.com/datapointchris/refcheck.git
```

Update in place with `refcheck --update`, which installs the latest GitHub
release. Once a day, a run that is behind the latest release prints a one-line
notice to stderr; set `NO_AUTO_UPDATE` to silence it.

## Usage

```bash
# Validate all references in current directory
refcheck

# Check specific directory
refcheck install/

# Find old pattern after refactoring
refcheck --pattern "old/path/" --desc "Update to new/path/"

# Filter by file type (like fd -e)
refcheck --type sh apps/

# Skip documentation files
refcheck --skip-docs

# Combine filters
refcheck --pattern "FooClass" --type py --skip-docs src/

# Disable warnings (only check for errors)
refcheck --no-warn

# Treat warnings as errors (strict mode for CI)
refcheck --strict
```

## Common workflows

### After moving files

```bash
# Moved tests/install/ to tests/install/
refcheck --pattern "tests/install/"
# Finds all stale references across repo
```

### Before running tests

```bash
# Quick validation (2 seconds vs 10+ minutes for e2e tests)
refcheck --skip-docs
# Catches broken references early
```

### Check specific component

```bash
# Validate install/ directory only
refcheck install/

# Check only shell scripts in apps/
refcheck apps/ --type sh
```

### Use in CI/CD

```bash
# Strict mode - fail build on warnings
refcheck --strict

# Regular mode - warnings don't fail build
refcheck

# Disable warnings for legacy code
refcheck --no-warn
```

### Detect fragile patterns

```bash
# Find paths that only work from specific directories
refcheck  # Shows warnings for fragile relative paths

# Find variable assignments using ../ traversal
refcheck  # Shows warnings for SCRIPT_DIR="$(cd "$DIR/../../.." && pwd)"
```

### Learn from git history

```bash
# Generate rules from git rename history (last 6 months by default)
refcheck --learn-rules

# Rules are stored per-repo at ~/.config/refcheck/repos/{repo-name}/rules.json
# These help suggest correct paths when references are broken
```

## Configuration

Create `~/.config/refcheck/config.toml` to customize behavior:

```toml
[learn]
time_window = "6 months"  # How far back to analyze git history

[warnings]
stale_threshold = "7 days"  # Warn when rules are older than this
show_no_rules_hint = true   # Show hint to run --learn-rules
```

## Output

**When errors found:**

```yaml
❌ Found 2 error(s)

Errors:

Broken Source (2):
────────────────────────────────────────────────────────────
  tests/broken.sh:4
    Missing: $SCRIPT_DIR/nonexistent.sh → /path/to/nonexistent.sh
    → Verify path exists or update reference

  src/install.sh:15
    Missing: /path/to/missing.sh
    → Verify path exists or update reference
```

**When warnings found:**

```yaml
⚠️  Found 2 warning(s)

Warnings:

Fragile to Working Directory (1):
────────────────────────────────────────────────────────────
  scripts/deploy.sh:3
    Relative path only valid from: repo root
    source tests/helpers.sh
    → Use root directory variable (e.g., $PROJECT_ROOT, $REPO_ROOT)

Fragile to Refactoring (1):
────────────────────────────────────────────────────────────
  scripts/setup.sh:8
    SCRIPT_DIR uses relative directory traversal (../) - fragile to file moves
    → Consider dynamic root detection: git rev-parse --show-toplevel
```

**When all valid:**

```text
✅ All file references valid
```

## Exit codes

- `0` - All references valid, or only warnings found (default mode)
- `1` - Found errors, or warnings in strict mode (`--strict`)

**Use in scripts:**

```bash
# Normal mode - warnings don't fail
if refcheck; then
  echo "All references valid (warnings OK)"
fi

# Strict mode - warnings fail
if refcheck --strict; then
  echo "All references valid (no errors or warnings)"
else
  echo "Issues found, fix before deploying"
  exit 1
fi
```

## Flags

| Flag | Description | Example |
|------|-------------|---------|
| `path` | Directory to check (positional) | `refcheck install/` |
| `--pattern PATTERN` | Find old pattern | `--pattern "old/"` |
| `--desc DESC` | Description for pattern | `--desc "Now new/"` |
| `--type, -t TYPE` | Filter by file type | `--type sh` |
| `--skip-docs` | Skip markdown files | `--skip-docs` |
| `--strict` | Treat warnings as errors (exit 1) | `--strict` |
| `--no-warn` | Disable fragile path warnings | `--no-warn` |
| `--learn-rules` | Generate rules from git history | `--learn-rules` |
| `--test-mode` | Include test fixtures (normally excluded) | `--test-mode` |
| `--update` | Install the latest release | `--update --check` |
| `--version` | Show the installed version | `--version` |
| `--help, -h` | Show help | `--help` |

## Smart filtering

Automatically excludes:

- **Build artifacts**: `.git`, `node_modules`, `.venv`, `__pycache__`, `site/`
- **Historical files**: `.planning/`, `.claude/metrics/`
- **Dynamic paths**: Container paths (`/root/`, `/home/`), temp files (`/tmp/`)
- **Self-references**: Usage examples in scripts referencing themselves

## Development

```bash
uv run pytest
```

Tests cover config parsing, rules management, file suggestions, and end-to-end
CLI behavior. The suite also runs as a pre-commit hook.

Python 3.11+. The only runtime dependency is
[pyselfupdate](https://github.com/datapointchris/pyselfupdate); everything else
is stdlib.

Modular structure:

- `cli.py` - argparse CLI entry point
- `config.py` - Config dataclass, TOML loading
- `checker.py` - ReferenceChecker class (core logic)
- `rules.py` - Rules loading/learning from git
- `suggestions.py` - File similarity matching
- `output.py` - Result formatting
- `selfupdate.py` - Version reporting and release updates

## Comparison to alternatives

**vs grep:**

- `grep` finds patterns but doesn't validate file existence
- `refcheck` validates references point to real files
- `refcheck` auto-filters false positives

**vs shellcheck:**

- `shellcheck` checks literal paths in single files
- `refcheck` checks across entire codebase
- `refcheck` handles dynamic paths and patterns

**vs manual testing:**

- Manual testing requires running full test suite (minutes)
- `refcheck` validates in seconds
- Catches issues before expensive CI/CD runs
