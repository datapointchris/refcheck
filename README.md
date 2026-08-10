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

Shell scripts and markdown are both checked. Documentation goes stale in
exactly the way code does — a usage example naming a library that has since
moved is the drift this tool exists to catch — so prose is scanned unless you
pass `--skip-docs`.

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
- In prose, `$DOTFILES_DIR` is the repo root; `$SCRIPT_DIR` stays unresolved,
  because a doc has no one script for it to be relative to

**Quiet on documentation that is not about your repo:**

Prose quotes other projects' trees constantly, so a reference is only checked
when its leading directory is one your repo actually has. A rename *under* a
directory you still have is reported — that is the case worth catching — while
`source child.sh` in a page explaining `set -e` is not. Documentation
placeholders (`toolname.sh`, `{tool}-plugins.sh`) are skipped in prose but not
in shell, where `bash script.sh` is a real invocation.

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

## As a pre-commit hook

```yaml
repos:
  - repo: https://github.com/datapointchris/refcheck
    rev: v0.4.1
    hooks:
      - id: refcheck
        args: [--moves]
```

`--moves` is what makes the hook worth having. Without it the hook validates
`source` and `bash` targets, which on a repo that is already clean finds nothing
most days. With it, every rename and deletion you have staged is also checked
for what still points at the old name — in any file type, not just shell. That
is the check a move actually needs, asked at the moment fixing it is free.

Add `args: [--moves, --strict]` to fail on warnings as well as errors.

The hook scans the whole repository rather than the staged files, and this is
deliberate: a reference breaks in the file that was *not* edited. Delete or move
`b.sh` and the stale `source b.sh` sits in `a.sh`, which is nowhere in the
changeset. Filtering to staged files would miss the entire class of bug the hook
exists to catch.

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
# Ask git what moved, instead of typing the old path in
refcheck --moves              # renames and deletions you have staged
refcheck --moves-since origin/main   # everything the branch moved

# Or name the old path yourself
refcheck --pattern "tests/install/"
```

`--moves` reads `git diff --diff-filter=RD -M` and runs a pattern check per old
path, so the answer covers markdown, YAML, Dockerfiles and code alike. Paths
that came back, and bare filenames with no directory, are skipped — the first is
not stale and the second is too generic to be evidence.

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
```

Rules improve the **Possible matches** line under a broken reference; they
detect nothing on their own, which is why refcheck only mentions them when a
finding came up with no suggestion. For catching what a move left behind, reach
for `--moves` instead — it reads the change you are actually making rather than
six months of history describing moves already reconciled.

## Configuration

Create `~/.config/refcheck/config.toml` to customize behavior:

```toml
[learn]
time_window = "6 months"  # How far back --learn-rules analyzes git history
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
| --- | --- | --- |
| `path` | Directory to check (positional) | `refcheck install/` |
| `--pattern PATTERN` | Find old pattern | `--pattern "old/"` |
| `--desc DESC` | Description for pattern | `--desc "Now new/"` |
| `--moves` | Check what staged renames and deletions left behind | `--moves` |
| `--moves-since REF` | The same, for every move between REF and HEAD | `--moves-since origin/main` |
| `--type, -t TYPE` | Filter by file type | `--type sh` |
| `--skip-docs` | Skip markdown files, for both reference and pattern checks | `--skip-docs` |
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
- **Historical files**: `.planning/`, `.claude/metrics/`, `*.log`, `*.jsonl`,
  `CHANGELOG.md` — each records what a path *was*, which is what makes a
  changelog entry naming the old location correct rather than stale
- **Recorded data**: `fixtures/`, `testdata/` — a captured tool output names
  every file that existed when it was taken, and is fixed by re-running the
  tool, never by editing. `--test-mode` scans them anyway
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
- `moves.py` - Renames and deletions read from git
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
