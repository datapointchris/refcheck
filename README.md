# refcheck

Fast reference validator for codebases. Finds broken file references,
fragile path patterns, and validates variable-based paths.

## What it does

`refcheck` validates file references across your codebase, checking for:

### Errors (always exit 1)

1. **Broken source statements** - Missing files in `source` and `.` commands,
   quoted or not (including variable paths like `$SCRIPT_DIR/file.sh`)
2. **Broken script references** - Missing files in `bash` or `sh` commands
3. **Old path patterns** - Stale references after refactoring
4. **A path it was handed and could not read** - a directory that will not list
   or a file that will not open, because a scan of a tree it could only partly
   open has no business printing a tick

A directory named on the command line and not there is refused outright, exit 2.
Walking it would find no files, pass every check over nothing, and certify a
tree that does not exist.

Shell scripts and markdown are both checked. Documentation goes stale in
exactly the way code does — a usage example naming a library that has since
moved is the drift this tool exists to catch — so prose is scanned unless you
pass `--skip-docs`.

Inside markdown, a fenced block is read as shell when it is tagged as shell
(` ```bash `, ` ```sh `, ` ```shell `, ` ```console `) or carries no tag at all.
A block tagged as another language holds another language: a ` ```yaml ` sample
showing a tool's own report is not an invocation, however much its
`bash some/path.sh` line looks like one.

### Warnings (exit 0 unless --strict)

1. **Fragile to working directory** - Relative paths that only work from
   specific directories
2. **Fragile to refactoring** - Variable assignments using `../` traversal
   (breaks when files move)

### Set aside (never a failure)

A `--pattern` hit is dropped when the path around it is on disk, because a
substring cannot tell a stale reference from a longer correct path that ends
the same way. `--pattern boards/arm` matching `config/boards/arm/` right after
the move that made it correct is the case that rule exists for.

Existence is weak evidence though. In a repo where the old name is still on
disk somewhere, every mention of it resolves and every mention is dropped — so
each dropped hit is listed with the path it resolved to, and you decide whether
it was repaired or merely has not been cleaned up yet.

`--moves` and `--moves-since` read what each path became out of git and list
only the hits that record cannot account for. A hit spelling the new path is a
repair the run can prove, so it says nothing about it.

What the listing covers is the resolver's guesses, not every occurrence of the
string. A hit inside a URL is not listed, because a URL names no file whatever
the tree holds, and a docs page swept for a moved path would otherwise list
every link quoting it. Nor is a file the scan never opened — `--show-config`
prints every exclusion in force and the layer that set it.

Two spellings of the same name are not ordered, so neither is a workaround for
the other. `--pattern .markdownlint.json` finds nothing on a line spelling the
name without the dot, and `--pattern markdownlint.json` finds both. Sweep for
the shortest form the rename left behind.

## Why use it

**Proactive error detection:**

- Catch broken references before running expensive test suites
- Find issues in seconds vs minutes for full e2e tests
- Validate changes before committing

**Refactoring safety:**

- After moving files, verify all references updated
- Find stale patterns across entire codebase
- Sweep the *other* repos on the machine, which the renaming repo cannot see
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

Update in place with `refcheck update`, which installs the latest GitHub
release. Once a day, a run that is behind the latest release prints a one-line
notice to stderr; set `NO_AUTO_UPDATE` to silence it.

## As a pre-commit hook

```yaml
repos:
  - repo: https://github.com/datapointchris/refcheck
    rev: v2.6.3
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

A renamed tool, subcommand or flag is not a file git moves, so the hook
never sees one. Run `--name` by hand when that change lands, per
[Which flag answers which change](#which-flag-answers-which-change).

`pre-commit run --from-ref A --to-ref B` stages nothing, and neither does the
pre-push stage. Both export the range as `PRE_COMMIT_FROM_REF` and
`PRE_COMMIT_TO_REF`, and `--moves` checks the moves in that range instead of the
index. That is how CI runs the same hook over a pushed branch.

The hook scans the whole repository rather than the staged files, and this is
deliberate: a reference breaks in the file that was *not* edited. Delete or move
`b.sh` and the stale `source b.sh` sits in `a.sh`, which is nowhere in the
changeset. Filtering to staged files would miss the entire class of bug the hook
exists to catch.

## Usage

```bash
# Validate all references in current directory
refcheck check

# Check specific directory
refcheck check install/

# Find old pattern after refactoring
refcheck check --pattern "old/path/" --desc "Update to new/path/"

# Filter by file type (like fd -e)
refcheck check --type sh apps/

# Skip documentation files
refcheck check --skip-docs

# Find a renamed tool's old name, wherever it is still used as one
refcheck check --name oldtool --desc "Now newtool"

# Find a renamed, moved or removed subcommand, wherever it is still named
refcheck check --name "tool oldsub" --desc "Now newtool sub"

# Find a flag that moved under a subcommand, wherever it is still called the old way
refcheck check --name "tool --oldflag" --desc "Now tool sub --oldflag"

# Combine filters
refcheck check --pattern "FooClass" --type py --skip-docs src/

# Disable warnings (only check for errors)
refcheck check --no-warn

# Treat warnings as errors (strict mode for CI)
refcheck check --strict
```

## Common workflows

### Which flag answers which change

| What changed | Run | Who runs it |
| --- | --- | --- |
| A file or directory moved, was renamed or was deleted | `--moves`, `--moves-since <base>`, or `--pattern "old/path/"` | The pre-commit hook, with `args: [--moves]`, for this repo. You, with `--moves-since <base> --registry`, for every other repo and for the old filename |
| A tool was renamed or removed | `--name oldtool` | You, when the change lands |
| A subcommand was renamed, moved to another tool, or removed | `--name "tool oldsub"`, once per subcommand | You, when the change lands |
| A flag moved under a subcommand, was renamed, or was removed | `--name "tool --oldflag"`, or `--name "tool sub --oldflag"` for a subcommand's flag, once per flag and once per subcommand that carried it | You, when the change lands |

Add `--registry` once per registry to ask every repo and store it lists, not
just this one.

### After moving files

```bash
# Ask git what moved, instead of typing the old path in
refcheck check --moves              # renames and deletions you have staged
refcheck check --moves-since origin/main   # everything the branch moved

# Or name the old path yourself
refcheck check --pattern "tests/install/"
```

`--moves` reads `git diff --diff-filter=RD -M` and runs a pattern check per old
path, so the answer covers markdown, YAML, Dockerfiles and code alike. Paths
that came back, and bare filenames with no directory, are skipped — the first is
not stale and the second is too generic to be evidence.

### After renaming a tool

A renamed tool leaves its old name in prose, commands and paths, and none of
those is a path git recorded moving. `--name` finds them:

```bash
refcheck check --name oldtool --desc "Now newtool" \
  --registry ~/.config/repos.json --registry ~/.config/stores.json
```

Matching the bare word buries the references in English whenever the old name
is also a word, because most lines holding it use the word. So a hit counts only
in a shape that kind of line does not take when it means the word:

| Line | Shape | Example |
| --- | --- | --- |
| Any | A code span opening on it | `` `oldtool` ``, `` `oldtool check` ``, `` `oldtool`'s `` |
| Any | A quoted literal holding only it | `"oldtool"`, `['oldtool', 'batch']` |
| Any | A path segment | `~/tools/oldtool`, `src/oldtool/main.py`, `oldtool.db`, `oldtool.storage` |
| Any | Bold, or a table cell, holding only it | `**oldtool**`, `\| oldtool \|` |
| Code or config | An import, or a value that is only it | `import oldtool`, `name: oldtool` |
| Code or config | A list item | `[indy, oldtool]`, `-F oldtool,nomad` |
| Code or config | A line opening on it in aligned columns | `oldtool     SQLite · CLI` |
| Shell | The whole word, outside a comment | `oldtool batch`, `uv tool install oldtool`, `if oldtool check; then` |

A shell line is one in a `.sh`, `.bash`, `.zsh` or `.ksh` file, an extensionless
file whose shebang names a shell, or a markdown fence tagged as shell or
untagged. Prose is markdown outside its fences and `.txt`, `.rst`, `.adoc`,
`.org`, `.html` and `.tex`. Every other file is code or config, which is what
keeps a docstring opening on the word from reading as a command.

What no shape reaches is the name in running prose — "across indy, oldtool and
syncer". Nothing on the line tells the tool from the word, so that one is left
for you to find.

Two kinds of hit are correct and reported anyway, because nothing on the line
says so. The renamed tool's own repo names its former name on purpose, in
migration code and its history. And where the old name lives on as a
subcommand or a key of the tool that absorbed it — `newtool oldtool` — every
mention of that live name is reported too. Read both rather than fixing them,
and add a `[scan] exclude` to that repo's `.refcheck.toml` to quiet them.

Each row prints the line it was found on, so a hit can be judged without
opening the file.

The tree the local run read is left out of the sweep, so nothing in it is
printed twice. A run narrowed to one directory still sweeps the rest of its
repo when the registry lists that repo. Both hold for a subcommand too.

### After renaming, moving or removing a subcommand

A subcommand that went away strands its callers in other repos. A caller in
code spells it as an argument list, which a text search for the phrase misses:

```bash
refcheck check --name "tool oldsub" --desc "Now newtool sub" \
  --registry ~/.config/repos.json --registry ~/.config/stores.json
```

A subcommand can also be an English phrase — `learning plan`, `fleet hosts` — so
which shapes count depends on the line, as they do for a single name:

| Line | Shape | Example |
| --- | --- | --- |
| Code, config or shell | The words in order, comments included, with or without an installed path ahead of the tool | `tool oldsub --json`, `f'tool oldsub failed: {e}'`, `ExecStart=/usr/bin/tool oldsub`, `"$HOME/go/bin/tool" oldsub` |
| Any | Consecutive quoted items of an argument list | `["tool", "oldsub"]`, `exec.Command("/usr/bin/tool", "oldsub")` |
| Any | A code span opening on it, a quoted literal, bold or a table cell holding only it | `` `tool oldsub` ``, `"tool oldsub"`, `**tool oldsub**` |

The phrase in a sentence of prose is not reported. A flag between the two,
`tool --json oldsub`, is not matched, and neither is a caller that passes the
tool and its arguments in separate fields. A line mentioning `tool` or `oldsub`
alone is never reported.

### After moving a flag under a subcommand, or removing it

A CLI that turns its root flags into subcommands, `tool --pattern x` becoming
`tool check --pattern x`, leaves every old call failing on an unknown option. A
flag takes the shapes a subcommand does, so name each flag that moved:

```bash
refcheck check --name "tool --pattern" --desc "Now tool check --pattern" \
  --registry ~/.config/repos.json --registry ~/.config/stores.json
```

Other flags may stand before it, so a removed flag is found behind the ones the
tool kept: `tool --json --legacy`. A word between the tool and the flag that is
not itself a flag is taken for a subcommand, so `tool check --pattern`, the
corrected call, is not matched. A flag after a value, as in
`tool --type md --oldflag`, is not matched either, because nothing tells the
value from a subcommand.

A subcommand's own flag, renamed or removed, is named with the subcommand:

```bash
refcheck check --name "tool check --strict" --desc "Now tool check --fail-on-warning"
```

The name fixes the command path, so any argument of that command may stand
before the flag: `tool check src/ --type md --strict` is matched. The command
ends at a `|`, `;`, `&`, a comment or the end of a code span, so
`tool check src/ | grep --strict` is not.

A flag several subcommands carry is named once per subcommand.
`--name "tool --strict"` finds none of them, because it reads each
`tool check --strict` as the corrected call.

A positional argument that moved, such as `tool src/` becoming
`tool check src/`, names nothing a shape can match, so it is left for you to
find.

### After moving files, in the repos that name them

A rename is answerable in the repo that made it and unanswerable everywhere
else. That is the gap `--registry` closes: it asks the same question of every
repo on the machine, driven by the same renames git already recorded.

```bash
refcheck check --moves-since origin/main --registry ~/.config/repos.json
```

The registry is named at the call site and refcheck never goes looking for one.
A check that resolved its own subject would sweep whatever the environment
answered at that moment, and one machine's registry lists a different set of
repos from another's. Any JSON naming repo paths works — a bare array of entries,
an object holding them under `stores`, or an object holding them under `repos`
beside an `exclude_paths` list, which is honored:

```json
{
  "exclude_paths": ["~/code/third-party"],
  "repos": [
    {"name": "toolbox", "path": "~/code/toolbox", "status": "active"},
    {"name": "old-thing", "path": "~/code/old-thing", "status": "retired"}
  ]
}
```

`--registry` repeats. A machine that declares its repos in one file and its
content directories in another passes both, and a directory both list is walked
once, under the name the first file gives it. An unset `$XDG_DATA_HOME`,
`$XDG_CONFIG_HOME`, `$XDG_STATE_HOME` or `$XDG_CACHE_HOME` in a path takes the
base-directory spec's default rather than staying literal text.

**A reference from one repo into another either spells a location or names the
repo.** Code spells it — an absolute path, a `~`, or a variable holding one.
Prose names it, because `<repo-name>/path/inside-it` is how a document points at
a file in another repo without knowing where that repo is checked out.
Both forms resolve to a directory here, which is what makes the sweep safe on a
pattern as loose as `versions.json`: the token becomes a location and the answer
is the filesystem's, not the string's. A hit is reported only when the path it
names sits inside a repo the registry lists and is not there.

The second form is resolved through the registry's own names, so a token is only
repo-qualified when its first segment is a name the registry carries. A repo
name and a directory name collide constantly — a registry of any size carries a
repo called `docs`, `assets` or `tools`, and so does half the trees it lists —
so the repo being scanned is asked first, and only a path it cannot answer for
is handed to the repo its first segment names.

Those two halves ask about different forms of the same path, because different
things answer them. **Is it there** is the kernel's answer, so it gets the path
as written — the one a program reading that line would open. **Whose is it** is
a string comparison, so it gets the path with its symlinks and `..` walked out,
and so do the repo paths it is compared against. Handing either the other's form
is a bug in whichever direction it is done: flatten before asking the kernel and
a file that is on disk is reported gone, compare an unwalked path and a real
file lands outside every repo that holds it.

Everything else stays quiet, and it has to — three of refcheck's first five
findings were its own bugs, which is why it went unused. Six registry files
renamed at a repo root hit roughly 150 lines across 90 repos on the bare
basename, effectively all of it noise. The rule above reports none of them, and
reports the one reference that had genuinely broken.

| What the line holds | Swept |
| --- | --- |
| `versions_file: ~/…/store/versions.json`, gone from a listed repo | reported |
| ``The reader is `store/versions.json` ``, naming a listed repo | reported |
| `versions_file: ~/…/store/pinned-versions.json`, the corrected path | silent |
| ``The reader is `store/pinned-versions.json` ``, the corrected citation | silent |
| `PINS = "versions.json"`, a filename literal | silent while a listed repo holds a `versions.json`, reported once none does |
| `The pins live in versions.json`, prose | silent |
| `store renamed versions.json last week`, a bare repo name | silent |
| `docs/versions.json`, where this repo holds that file | silent |
| `/srv/versions.json`, inside no listed repo | silent |
| `$UNSET_VAR/versions.json`, nothing to expand | silent while a listed repo holds a `versions.json`, reported once none does |

**A filename the change took out of use is asked about too, once nothing holds
it.** Prose cites a file by its name alone as often as by its path — "a
hand-written `ci.yml`" — and no path check reads that. So when a move deletes a
file, or renames it to a different filename, `--moves` with `--registry` also
runs the [`--name` shapes](#after-renaming-a-tool) for the old filename, here and
in every listed repo. A row there reads `→ now cross-platform.yml`.

It asks only when no file in this tree or any listed repo still has that name.
Until then the citation names something real: `main.go` leaving one repo is not
news to the others. That walk ignores a repo's `[scan] exclude` and `--type`,
because an excluded file is still a file. It skips the default exclusions, such
as `node_modules` and `.venv`, because a dependency's `ci.yml` is not the one a
citation names. The run prints the filenames it left out for that
reason. A move that keeps the filename, `docs/setup.md` to `setup.md`, asks
nothing more.

A path the path check can resolve is left to it: `/srv/ci.yml`, `~/x/ci.yml`,
or a URL ending in `ci.yml`. A path nothing here can resolve is asked, so
`c="$d/.github/workflows/ci.yml"` in a shell snippet is reported. A line the
path check already reported is not reported twice. A dotfile
such as `.markdownlint.yaml` is asked like any other. A filename no shape can
match, one with a space in it, is named in a "Not asked" line.

Retired repos are not walked, because a finding in one is not going to be fixed.
Dormant ones are swept — dormant work gets picked up, and a reference that broke
while it was quiet is exactly what nobody would otherwise find. A retired repo
can still *own* a gone path, though: a live repo holding a path into one still
holds a path that does not resolve, and the edit that fixes it is in the live
repo.

Four things stop a repo owning a gone path, and only one of them is a deliberate
skip. Retired is that one, and it stays in the count line. The other three are
the sweep failing to look — an entry naming no path, a listed repo with no
directory here, a directory or file that will not open — and each fails the run
with its own row. A tick that cannot be told from "the repo the file left was
not in the map" is the false clean this whole tool exists to avoid, so a run
that covered less than it was handed does not print one. Where the repo you are
standing in is itself unlisted, the sweep says so, because nothing it finds can
be credited to the renames you just made.

Every filter narrows the sweep as well as the local run — `--type`, `--skip-docs`,
`--test-mode` and `--exclude` all reach all of it. Each repo still reads its own
`.refcheck.toml`, with `--exclude` added on top.

`--registry` also takes `--pattern`, `--moves` and `--name`, and needs one of
them: validating another repo's `source` statements is that repo's own run, so a
registry with nothing to look for exits 2 rather than walking every listed repo
to ask it nothing.

`--pattern`, `--name` and `--moves` each ask a different question, and a run
asks one. Passing two exits 2, because answering the first would print a tick
the caller reads as covering both.

One sweep of 90 repos costs about 14 seconds for six moved paths — roughly 12
for the walk and a quarter-second per extra pattern. A run with nothing to look
for reads no files at all.

### Before running tests

```bash
# Quick validation (2 seconds vs 10+ minutes for e2e tests)
refcheck check --skip-docs
# Catches broken references early
```

### Check specific component

```bash
# Validate install/ directory only
refcheck check install/

# Check only shell scripts in apps/
refcheck check apps/ --type sh
```

### Use in CI/CD

```bash
# Strict mode - fail build on warnings
refcheck check --strict

# Regular mode - warnings don't fail build
refcheck check

# Disable warnings for legacy code
refcheck check --no-warn
```

### Detect fragile patterns

```bash
# Find paths that only work from specific directories
refcheck check  # Shows warnings for fragile relative paths

# Find variable assignments using ../ traversal
refcheck check  # Shows warnings for SCRIPT_DIR="$(cd "$DIR/../../.." && pwd)"
```

### Learn from git history

```bash
# Generate rules from git rename history (last 6 months by default)
refcheck learn-rules

# Stored per checkout at ~/.config/refcheck/repos/{repo-path-with--for-slash}/rules.json
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
time_window = "6 months"  # How far back learn-rules reads git history
```

## Output

**When errors found:**

```text
FAIL Found 2 error(s)

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

```text
WARN Found 2 warning(s)

Warnings:

Fragile to Working Directory (1):
────────────────────────────────────────────────────────────
  scripts/deploy.sh:3
    Relative path only valid from: repo root
    source scripts/helpers.sh
    → Use root directory variable (e.g., $PROJECT_ROOT, $REPO_ROOT)

Fragile to Refactoring (1):
────────────────────────────────────────────────────────────
  scripts/setup.sh:8
    SCRIPT_DIR uses relative directory traversal (../) - fragile to file moves
    → Resolve the root from an exported variable first: "${REPO_DIR:-$(git rev-parse --show-toplevel)}"
```

**When hits were set aside:**

Rows come in file order, then line order. One repo holding the old name at its
root put eleven of these above a single finding, which is the shape to expect
rather than the exception.

```text
PASS No stale references, and 3 hits set aside

3 hits matched the text and resolved to a path on disk, so none was reported:
────────────────────────────────────────────────────────────
  CLAUDE.md:132
    Found: markdownlint.json, inside .markdownlint.json
    → resolves to .markdownlint.json
  configs/prettierignore.txt:16
    Found: markdownlint.json, inside .markdownlint.json
    → resolves to .markdownlint.json
  docs/setup.md:8
    Found: markdownlint.json, inside ../.markdownlint.json
    → resolves to .markdownlint.json
```

**When all valid:**

```text
PASS All file references valid
```

## Exit codes

- `0` - All references valid, or only warnings found (default mode)
- `1` - Found errors, a path the run could not read, or warnings in strict mode
  (`--strict`)
- `2` - The run was asked for something it cannot do: a directory that is not
  there, a `--registry` that is missing or is not JSON, `--registry` with
  nothing to look for, two of `--pattern`, `--name` and `--moves` in one run, a
  `--name` that is not a tool, a tool and its subcommand, or a tool and its
  flag, or a range git
  cannot diff, such as a base
  commit a shallow clone never fetched
- `128` - `--moves` or `--moves-since` outside a git repository, which is git's
  own code for it

**Use in scripts:**

```bash
# Normal mode - warnings don't fail
if refcheck check; then
  echo "All references valid (warnings OK)"
fi

# Strict mode - warnings fail
if refcheck check --strict; then
  echo "All references valid (no errors or warnings)"
else
  echo "Issues found, fix before deploying"
  exit 1
fi
```

## Commands

| Command | Description |
| --- | --- |
| `refcheck check [PATH]` | Validate every reference in the tree, or in one directory |
| `refcheck learn-rules` | Write rules.json from git's rename history |
| `refcheck update` | Install the latest release; `--check` reports one without installing |

Bare `refcheck` prints help. Run any command with `--help` for its flags.

## Flags on `check`

| Flag | Description | Example |
| --- | --- | --- |
| `path` | Directory to check (positional) | `refcheck check install/` |
| `--pattern PATTERN` | Find old pattern | `--pattern "old/"` |
| `--name NAME` | Find a tool, or a tool and its subcommand or flag, that is gone but still named | `--name oldtool`, `--name "tool oldsub"`, `--name "tool --oldflag"` |
| `--desc DESC` | What the pattern or name became | `--desc "Now new/"` |
| `--moves` | Check what staged renames and deletions left behind | `--moves` |
| `--moves-since REF` | The same, for every move between REF and HEAD | `--moves-since origin/main` |
| `--registry PATH` | Ask the same of every repo or store the registry lists (repeatable) | `--registry ~/.config/repos.json` |
| `--type, -t TYPE` | Filter by file type | `--type sh` |
| `--skip-docs` | Skip markdown files, for both reference and pattern checks | `--skip-docs` |
| `--strict` | Treat warnings as errors (exit 1) | `--strict` |
| `--no-warn` | Disable fragile path warnings | `--no-warn` |
| `--test-mode` | Include test fixtures (normally excluded) | `--test-mode` |
| `--exclude GLOB` | Also skip paths matching this glob (repeatable) | `--exclude "build/reports/**"` |
| `--show-config` | Print the exclusions in force and where each came from | `--show-config` |
| `--version` | Show the installed version (on `refcheck` itself) | `refcheck --version` |
| `--help, -h` | Show help | `--help` |

## Smart filtering

Automatically excludes:

- **Build artifacts**: `.git`, `node_modules`, `.venv`, `__pycache__`, `.cache`,
  `site/`, `*.pyc`
- **Historical files**: `.planning/`, `.claude/metrics/`, `*.log`, `*.jsonl`,
  `CHANGELOG.md`, backups (`*.bak`, `*.backup`, `*.backup.*`, `*.orig`),
  `file-history/`, the tool caches (`.pytest_cache`,
  `.ruff_cache`, `.mypy_cache`) and coverage.py's reports (`.coverage`,
  `.coverage.*`, `coverage.json`, `coverage.xml`, `coverage.lcov`, `htmlcov/`) —
  each records what a path *was*, which is what makes a changelog entry naming
  the old location correct rather than stale
- **Recorded data**: `fixtures/`, `testdata/`, `docs/archive/` — a captured tool
  output names every file that existed when it was taken, and is fixed by
  re-running the tool, never by editing. `--test-mode` scans them anyway
- **Dynamic paths**: anything opening with `$`, temp files (`/tmp/`), home
  directories (`/root/`, `/home/`, `/Users/`) and machine state (`/etc/`).
  Whether `/etc/os-release` resolves says which OS is running the check, not
  whether the reference is good
- **Paths on another machine**: the argument to `ssh`, and to `docker exec`,
  `pct exec`, `lxc exec` or `kubectl exec` — that file is not in this tree
- **Self-references**: Usage examples in scripts referencing themselves

A `~/` path is the deployed spelling, the one a script running outside the repo
has to use. It resolves under the home directory, or where the repo tracks a
file whose path ends in it, as `configs/common/.local/shell/logging.sh` does for
`~/.local/shell/logging.sh`. The second is what makes the answer the same on a
CI runner, whose home holds nothing the repo deploys.

## A repo excludes its own generated output

The list above is what holds for any repository. Which of *this* repo's
directories hold generated output is a fact only the repo knows, so it says so
in `.refcheck.toml` at its root:

```toml
[scan]
exclude = ["build/reports/**", "*.snapshot.json"]
```

Patterns are globs matched against the repo-relative path, and `**` crosses
directory separators. They add to the built-in list rather than replacing it.

A file a tool writes names what a path was when the tool ran, so a hit inside
one is history rather than a stale reference. A test-report directory that
records a node ID per test is the usual case: deleting a test file then reports
one miss per report that ever ran it, and the count grows with every run.

Discovery walks up from the repo root and stops there, so a checkout never
inherits the config of whatever encloses it. `--exclude GLOB` adds a pattern for
a single run without declaring it, and `--show-config` prints every exclusion in
force alongside the layer that set it.

## Development

```bash
uv run pytest
```

Tests cover config parsing, rules management, file suggestions, and end-to-end
CLI behavior. The suite also runs as a pre-commit hook.

Python 3.11+. The runtime dependencies are typer and
[pyselfupdate](https://github.com/datapointchris/pyselfupdate); everything else
is stdlib.

Modular structure:

- `cli.py` - typer CLI entry point
- `config.py` - Config dataclass, TOML loading
- `checker.py` - ReferenceChecker class (core logic)
- `moves.py` - Renames and deletions read from git
- `names.py` - The shapes in which an old name is a reference rather than a word
- `registry.py` - The repos and stores on this machine, read from registries the caller names
- `sweep.py` - The move and name sweeps, run across those repos rather than one
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
