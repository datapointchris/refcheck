# refcheck

refcheck finds what a move, a rename or a deletion left behind. That is a
`source` or `bash` target that does not resolve, an old path still named after a
move, and an old tool, subcommand or flag name still in use. It ships as a
pre-commit hook.

A reference breaks in the file that was not edited. Move `b.sh` and the stale
`source b.sh` sits in `a.sh`, which is nowhere in the changeset. So refcheck
reads the whole tree on every run. It asks the filesystem and git, not the text.
grep finds the string and cannot say whether the path around it exists.
shellcheck lints the shell inside one script and reads none of the markdown,
YAML and code that also name a path.

A false clean is worse than a false positive, because it certifies the rot. A
run that covered less than it was handed fails rather than printing a tick. A
checker is also worth exactly its false-positive rate. Documentation, history
and another machine's paths are read behind guards that keep them quiet.

## Install

```bash
uv tool install --index https://pypi.ichrisbirch.com/simple/ refcheck
refcheck update   # later: reinstall at the latest release
```

Every release is published to that package index. Name it on the install.
Without it uv asks PyPI, where `refcheck` is a different project. uv records the
index beside the tool, which is where `refcheck update` reads it back. A branch
install carries no release version, so `refcheck update` refuses it.

A run at a terminal checks for a newer release at most once a day. It prints one
line to stderr when it is behind. `NO_AUTO_UPDATE` silences it.

As a pre-commit hook, in `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/datapointchris/refcheck
    rev: v2.7.10
    hooks:
      - id: refcheck
        args: [--moves]
```

Each release rewrites that `rev:` line, so it names the latest tag.

## Starting from scratch

```bash
refcheck --version                 # the release installed, and the commit it was built from
cd path/to/repo                    # the repo root, which refcheck takes to be the repo
refcheck check                     # every source and bash target resolved; exit 1 names each miss
refcheck check --show-config       # what the scan skipped, and which layer skipped it

git mv lib/log.sh lib/logging.sh   # any staged rename or deletion
refcheck check --moves             # every file still naming lib/log.sh, in any file type

pre-commit install                 # with the hook block above in .pre-commit-config.yaml
pre-commit run refcheck            # the hook asks --moves of the index: PASS once nothing names an old path
```

**Run it from the repo root.** refcheck takes the directory it runs in as the
repo, and a relative `source` target hangs off that directory.
`cd docs && refcheck check` reads `docs` as a repo of its own. It can pass over
a broken reference that `refcheck check docs/` from the root reports. Narrow
with the path argument, never with `cd`.

The first `refcheck check` on an older repo may print warnings beside the
errors. Warnings exit 0. `--strict` fails on them and `--no-warn` drops them.

`--moves` reads git, so it exits 128 outside a repository. The hook is the same
`refcheck check --moves`, run on every commit.

## The grammar

`check` is the tool. `learn-rules` and `update` maintain it.

`refcheck check` with no question validates every `source` and `bash` target in
the tree, and warns on fragile paths. Three flags each ask a different question
instead: `--pattern`, `--moves` (or `--moves-since`) and `--name`. A run asks
one. Passing two exits 2, because answering the first would print a tick read as
covering both.

`--registry` widens a question to every repo a registry lists. It needs one of
the three, because validating another repo's `source` statements is that repo's
own run. The filters `--type`, `--skip-docs`, `--test-mode` and `--exclude`
narrow every tree the run reads, swept repos included.

A `check` flag given at the root is refused with the call that runs it.
`refcheck --pattern x` answers `refcheck check --pattern x`.

Exit codes:

- `0`: clean, or only warnings without `--strict`. A set-aside hit never fails.
- `1`: an error, a path the run could not read, a listed repo the sweep could
  not reach, or a warning under `--strict`.
- `2`: refused before the scan. That is a directory that is not there, a
  `--registry` that cannot be read as one, `--registry` with no question, two
  questions in one run, a `--name` that is not a name, or a range git cannot
  diff.
- `128`: `--moves`, `--moves-since` or `learn-rules` outside a git repository,
  which is git's own code for it.

## Which surface answers which question

| Ask | Surface | Reads |
| --- | --- | --- |
| Does every `source` and `bash` target still resolve | `check` | shell files and markdown, against the filesystem |
| Which paths break the next time something moves | `check`, its warnings | shell files |
| What still names the paths I just moved | `check --moves` | the renames and deletions staged in git, then every file |
| What still names the paths this branch moved | `check --moves-since <base>` | git's renames and deletions since `<base>`, then every file |
| What still names an old path I type in | `check --pattern` | every file, each hit resolved on disk |
| Where is a renamed tool, subcommand or flag still named | `check --name` | every file, judged by the shape of the line |
| What did a move or a rename break in other repos | `--registry` beside any of the three | every repo the registry lists |
| What did the scan skip | `check --show-config` | the built-ins, `.refcheck.toml` and `--exclude` |
| What did a missing file probably become | `learn-rules` | git's rename history |
| Is a newer release out | `update --check` | GitHub releases |

## `check` — a `source` or `bash` target is resolved on disk, not matched as text

```bash
refcheck check               # the whole repo: errors, then warnings
refcheck check install/      # one directory, still anchored at the repo root
refcheck check --strict      # a warning fails the run too, for CI
```

refcheck reads shell and markdown. Shell is a `.sh`, `.bash`, `.zsh` or `.ksh`
file, or a file with no suffix whose shebang names `sh`, `bash`, `zsh`, `ksh` or
`dash`. Markdown is read because a usage example goes stale exactly the way code
does. `--skip-docs` leaves it out.

Inside markdown, a fence tagged `bash`, `sh`, `shell`, `zsh`, `ksh`, `console`,
`shellsession` or `shell-session` holds shell. So does an untagged fence. A
fence tagged with another language is never read as shell. A `yaml` sample of a
tool's report is not an invocation, however much its `bash some/path.sh` line
looks like one.

Errors exit 1:

- A `source` or `.` target that is not there, quoted or not.
- A `bash` or `sh` invocation of a `.sh` file that is not there.
- A path the run was handed and could not read: a directory that will not list,
  or a file that will not open.

Warnings exit 0 unless `--strict`:

- A relative `source` path that resolves from some of the repo root, the
  script's directory and the directory above it, but not from all three.
- A `*_DIR` variable built by `../` traversal, as in
  `ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"`, which breaks when the file
  moves.

```text
FAIL Found 1 error(s) and 1 warning(s)

Errors:
────────────────────────────────────────────────────────────

Broken Source Command (1):
────────────────────────────────────────────────────────────
  install.sh:4
    Missing: $SCRIPT_DIR/lib/missing.sh → /path/to/repo/lib/missing.sh
    → Verify path exists or update reference

Warnings:
────────────────────────────────────────────────────────────

Fragile Traversal Path (1):
────────────────────────────────────────────────────────────
  scripts/ci/deploy.sh:2
    ROOT_DIR uses relative directory traversal (../) - fragile to file moves
    → Resolve the root from an exported variable first: "${REPO_DIR:-$(git rev-parse --show-toplevel)}"

HINT 1 broken reference(s) came up with no suggestions.
     'refcheck learn-rules' reads git's rename history to improve them.
```

**A path hangs off one of three anchors.** A `~` path hangs off the home
directory. An absolute path is itself. Anything else hangs off the repo root. A
`~/` path is the deployed spelling, the one a script running outside the repo
has to use. It also resolves when the repo tracks a file ending in the same
segments: `home/.local/lib/log.sh` satisfies `~/.local/lib/log.sh`. A CI
runner's home holds nothing the repo deploys, so this keeps its answer the same
as a desk that ran the install. A file sharing only the basename does not count.

**Two variables are resolved.** `$SCRIPT_DIR` is the script's directory when the
script sets it from `BASH_SOURCE` with `cd … && pwd`. `$DOTFILES_DIR` is the
directory `$(cd "$SCRIPT_DIR/../.." && pwd)` names when the script derives it
that way. It is the repo root when the script defaults it as
`${DOTFILES_DIR:-$HOME/dotfiles}`. In markdown, `$DOTFILES_DIR` is always the
repo root. `$SCRIPT_DIR` stays unresolved there, because a doc has no one script
for it to be relative to. A path behind any other variable is skipped rather
than guessed. A miss prints both forms, as above.

**Documentation widens the guards and never skips the line.** Markdown, a `#`
comment and an `echo` or `printf` line are documentation. There, a path whose
leading directory the repo lacks is read as another project's tree. So
`source child.sh` in a page explaining `set -e` stays quiet. A placeholder name
is skipped too: `toolname.sh`, `{tool}-plugins.sh`, `my-script.sh`. A
documented path under a directory the repo still has is reported, because that
is the stale reference worth catching. In code, `bash script.sh` is a real
invocation and has to resolve.

**Another machine's paths are not this tree's.** A path under `/tmp/`,
`/root/`, `/home/`, `/Users/`, `/etc/`, `/opt/` or `/srv/` is skipped. Whether
`/etc/os-release` resolves says which OS ran the check, not whether the
reference is good. A line that hands its command to `ssh`, `docker exec`,
`kubectl exec`, `lxc exec`, `pct exec` or `su - … -c` is skipped too, because
the file it names is on another host.

**A run that covered less than it was handed fails.** A directory that will not
list, or a file that will not open, is a finding. Three things are not
shortfalls. A subtree the exclusions skip is never entered. A file deleted
mid-run left nothing to miss. A file that is not UTF-8 text still arrived. A
directory named on the command line and not there exits 2, since walking it
would pass every check over nothing.

## `--moves` — git names the old paths, so the hook asks while fixing them is free

```bash
refcheck check --moves                       # the renames and deletions you have staged
refcheck check --moves-since origin/main     # every move the branch made, for CI
```

`--moves` reads the renames and deletions git recorded, through
`git diff --diff-filter=RD -M`. It asks of each old path what `--pattern` asks.
The answer covers every file type: markdown, YAML, Dockerfiles and code alike. A
path that came back is skipped, since it is not stale. A bare filename with no
directory is skipped too, because inside one repo it is too generic to be
evidence. `--registry` asks it anyway.

git also records what each path became. A hit spelling that path is a repair the
run can prove, so it is not listed. Every other hit that resolves on disk is
set aside and listed, as `--pattern` does.

**The hook asks it on every commit.** `args: [--moves]` is what makes the hook
worth having. Without it the hook validates `source` and `bash` targets, which on
a clean repo finds nothing most days. With it, every staged rename and deletion
is checked for what still names the old path. Add `--strict` to the args to fail
on warnings too.

The hook scans the whole repository, never the staged files. It sets
`pass_filenames: false` and `always_run: true`, because the stale reference sits
in the file that was not edited.

`pre-commit run --from-ref A --to-ref B` stages nothing, and neither does the
pre-push stage. Both export the range as `PRE_COMMIT_FROM_REF` and
`PRE_COMMIT_TO_REF`. `--moves` then reads that range instead of the index. That
is how CI runs the same hook over a pushed branch.

A range git cannot diff exits 2 rather than reading as no moves. A base commit a
shallow clone never fetched is the usual case.

A renamed tool, subcommand or flag is not a file git moves, so the hook never
asks `--name`. Run it by hand when that change lands.

## `--pattern` — a hit whose path is on disk is listed, never reported

```bash
refcheck check --pattern "old/path/" --desc "now new/path/"   # what still names a path you moved
```

Each hit is widened to the whole path token around it. A substring cannot tell a
stale reference from a longer correct path that ends the same way.
`--pattern boards/arm` matches `config/boards/arm/` right after the move that
made it correct. So a token that resolves on disk is set aside, and listed with
the path it resolved to. A token that does not resolve is reported. A hit
standing alone as its whole token is reported too, so `--pattern oldname` finds
`Run oldname`.

Existence is weak evidence. Where the old name is still on disk somewhere, every
mention of it resolves and every mention is set aside. The list lets you decide
whether each one was repaired or is waiting to be cleaned up. Expect it to
outnumber the findings in a repo still holding the old name.

```text
PASS No stale references, and 1 hit set aside

1 hit matched the text and resolved to a path on disk, so none was reported:
────────────────────────────────────────────────────────────
  docs/lint.md:1
    Found: markdownlint.json, inside .markdownlint.json
    → resolves to .markdownlint.json
```

The list covers the resolver's guesses, not every occurrence of the string. A
hit inside a URL is dropped, because a URL names no file whatever the tree
holds. A file the scan never opened is not listed either. `--show-config` prints
every exclusion in force.

Two spellings of one name are not ordered. `--pattern .markdownlint.json` finds
nothing on a line spelling it without the dot. `--pattern markdownlint.json`
finds both. Sweep for the shortest form the rename left behind.

`--pattern` matches inside longer words, which is right for a path. A renamed
tool goes to `--name`.

## `--name` — a name counts only in a shape the English word never takes

```bash
refcheck check --name oldtool --desc "now newtool"   # a renamed or removed tool
refcheck check --name "tool oldsub"                  # a subcommand, once per subcommand
refcheck check --name "tool --oldflag"               # a root flag that moved or went away
refcheck check --name "tool sub --oldflag"           # a subcommand's flag, once per subcommand that carried it
```

Matching the bare word buries the references in English whenever the old name is
also a word, because most lines holding it use the word. So a hit counts only in
a shape that kind of line does not take when it means the word:

| Line | Shape | Example |
| --- | --- | --- |
| Any | A code span opening on it | `` `oldtool` ``, `` `oldtool check` ``, `` `oldtool`'s `` |
| Any | A quoted literal holding only it | `"oldtool"`, `['oldtool', 'batch']` |
| Any | A path segment | `~/.local/bin/oldtool`, `src/oldtool/main.py`, `oldtool.db`, `oldtool.storage` |
| Any | Bold, or a table cell, holding only it | `**oldtool**`, `\| oldtool \|` |
| Code or config | An import, or a value that is only it | `import oldtool`, `name: oldtool` |
| Code or config | A list item | `[othertool, oldtool]`, `-F oldtool,othertool` |
| Code or config | A line opening on it in aligned columns | `oldtool     SQLite · CLI` |
| Shell | The whole word, outside a comment | `oldtool batch`, `uv tool install oldtool`, `if oldtool check; then` |

A shell line is one in a shell file, or in a markdown fence tagged as shell or
untagged. Prose is markdown outside its fences, and `.txt`, `.rst`, `.adoc`,
`.org`, `.html`, `.htm` and `.tex` files. Every other line is code or config.
That is what keeps a docstring opening on the word from reading as a command.

No shape reaches the name in running prose, as in "across othertool, oldtool and
anothertool". Nothing on that line tells the tool from the word, so that one is
left for you to find.

Two kinds of hit are correct and reported anyway. The renamed tool's own repo
names its former name on purpose, in migration code and its history. Where the
old name lives on as a subcommand or a key of the tool that absorbed it,
`newtool oldtool`, every mention of that live name is reported too. Read both
rather than fixing them. A `[scan] exclude` in that repo's `.refcheck.toml`
quiets them. Each row prints the line it was found on, so a hit can be judged
without opening the file.

**A subcommand** can also be an English phrase, so its shapes depend on the
line:

| Line | Shape | Example |
| --- | --- | --- |
| Code, config or shell | The words in order, comments included, with or without an installed path ahead of the tool | `tool oldsub --json`, `f'tool oldsub failed: {e}'`, `ExecStart=/usr/bin/tool oldsub`, `"$HOME/go/bin/tool" oldsub` |
| Any | Consecutive quoted items of an argument list | `["tool", "oldsub"]`, `exec.Command("/usr/bin/tool", "oldsub")` |
| Code or config | Consecutive items of a bracketed list, quoted or not | `command: [tool, oldsub, --json]` |
| Any | A code span opening on it, a quoted literal, bold or a table cell holding only it | `` `tool oldsub` ``, `"tool oldsub"`, `**tool oldsub**` |

A flag between the two, `tool --json oldsub`, is not matched. Neither is a
caller passing the tool and its arguments in separate fields. A line holding
`tool` or `oldsub` alone is never reported.

**A flag** takes a subcommand's shapes. Other flags may stand before it, so a
removed flag is found behind the ones the tool kept: `tool --json --oldflag`. A
word between the tool and the flag that is not itself a flag is taken for a
subcommand. So `tool check --oldflag`, the corrected call, is not matched. A
flag after a value, as in `tool --type md --oldflag`, is not matched either,
because nothing tells the value from a subcommand.

A subcommand's own flag is named with the subcommand. The name fixes the command
path, so any argument may stand before the flag. `--name "tool check --strict"`
matches `tool check src/ --type md --strict`. The command ends at a `|`, `;`,
`&`, a comment or the end of a code span, so `tool check src/ | grep --strict`
is not matched. A flag several subcommands carry is named once per subcommand.
`--name "tool --strict"` finds none of them, because it reads each
`tool check --strict` as the corrected call.

A positional argument that moved, `tool src/` becoming `tool check src/`, names
nothing a shape can match. That one is left for you to find.

With `--registry`, the sweep leaves out the tree the local run read, so nothing
in it is printed twice. A run narrowed to one directory still sweeps the rest of
its repo when the registry lists that repo.

## `--registry` — a reference into another repo is judged by the filesystem, not the string

```bash
refcheck check --moves-since origin/main --registry repos.json            # what the branch's moves broke elsewhere
refcheck check --name oldtool --registry repos.json --registry dirs.json  # every listed repo still naming it
```

A rename is answerable in the repo that made it and unanswerable everywhere
else. `--registry` closes that gap. It asks the same question of every repo a
registry lists, driven by the renames git already recorded.

The registry is named at the call site. refcheck never goes looking for one,
because one machine's registry lists a different set of repos from another's.
Any JSON naming repo paths works: a bare array of entries, or an object holding
them under `repos` or `stores`. An object's `exclude_paths` list is honored.

```json
{
  "exclude_paths": ["~/src/third-party"],
  "repos": [
    {"name": "web-app", "path": "~/src/web-app", "status": "active"},
    {"name": "old-thing", "path": "~/src/old-thing", "status": "retired"}
  ]
}
```

`--registry` repeats. A directory two files list is walked once, under the name
the first file gives it. An unset `$XDG_DATA_HOME`, `$XDG_CONFIG_HOME`,
`$XDG_STATE_HOME` or `$XDG_CACHE_HOME` in a path takes the base-directory spec's
default rather than staying literal text.

**A hit is reported only when the path it names sits inside a listed repo and is
not there.** A reference from one repo into another either spells a location or
names the repo. Code spells it: an absolute path, a `~`, or a variable holding
one. Prose names it as `<repo-name>/path/inside-it`, because a document does not
know where that repo is checked out. Both forms resolve to a directory, so the
answer is the filesystem's, not the string's. That makes a pattern as loose as a
bare `versions.json` safe to sweep. Across many repos, nearly every hit on a
bare basename is noise. This rule reports none of those, and reports the
reference that broke.

A token is repo-qualified only when the scanned repo has no directory of its
first segment. Repo names and directory names collide constantly: `docs`,
`assets`, `tools`. So the scanned repo answers first. Only a path it cannot
answer for goes to the repo its first segment names.

The two halves take different forms of one path. **Is it there** is the
kernel's question, so it gets the path as written, the one a program reading
that line would open. **Whose is it** compares strings, so both sides get their
symlinks and `..` walked out. Flatten before asking the kernel and a file on
disk is reported gone. Compare an unwalked path and a real file lands outside
the repo holding it.

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

**A filename the change took out of use is asked too, once nothing holds it.**
Prose cites a file by its name alone as often as by its path, as in "a
hand-written `ci.yml`". No path check reads that. So when a move deletes a file,
or renames it to a different filename, `--moves` with `--registry` also runs the
`--name` shapes for the old filename. It runs them here and in every listed
repo. A row there reads `→ now cross-platform.yml`.

It asks only once no file in this tree or any listed repo has that name. Until
then the citation names something real: `main.go` leaving one repo is not news
to the others. That walk ignores a repo's `[scan] exclude` and `--type`, because
an excluded file is still a file. It skips the built-in excluded directories
that `--show-config` lists, such as `node_modules` and `.venv`. A dependency's
`ci.yml` is not the one a citation names. The run prints the filenames it left
out for that reason. A move that keeps the filename, `docs/setup.md` to
`setup.md`, asks nothing more.

A path the path check can resolve is left to it: `/srv/ci.yml`, `~/x/ci.yml`, or
a URL ending in `ci.yml`. A path nothing here can resolve is asked, so
`c="$d/.github/workflows/ci.yml"` in a shell snippet is reported. A line the
path check already reported is not reported twice. A dotfile such as
`.markdownlint.yaml` is asked like any other. A filename no shape can match, one
holding a space, is named in a "Not asked" line.

**Retired repos are the one deliberate skip.** A finding in one is not going to
be fixed, so it is not walked. The count line says how many were skipped.
Dormant repos are swept. Dormant work gets picked up, and a reference that broke
while it was quiet is what nobody would otherwise find. A retired repo can still
own a gone path. A live repo holding a path into one holds a path that does not
resolve, and the fix lands in the live repo.

Everything else that shrinks the sweep fails the run with its own row: an entry
naming no path, a listed repo with no directory here, a directory or file that
will not open. Where the repo you are standing in is itself unlisted, the sweep
says so. Nothing it finds can then be credited to the renames you just made.

Every filter reaches every swept repo. Each swept repo still reads its own
`.refcheck.toml`, with `--exclude` added on top. A change that moved nothing
prints `Nothing moved, so no repo was swept` and reads no other repo.

## `learn-rules` — learned renames suggest a fix and detect nothing

```bash
refcheck learn-rules     # write this checkout's rules.json from git's rename history
```

Learned rules feed only the **Possible matches** line under a broken `source` or
`bash` reference. That is why refcheck mentions them only when a finding came up
with no suggestion. To catch what a move left behind, reach for `--moves`. It
reads the change you are making, not history describing moves already
reconciled.

The rules land at `$XDG_CONFIG_HOME/refcheck/repos/<path>/rules.json`, where
`<path>` is the checkout's absolute path with each `/` written as `--`.
`~/.config` stands in for an unset `$XDG_CONFIG_HOME`. The user config sets how
far back the history is read:

```toml
# $XDG_CONFIG_HOME/refcheck/config.toml, or ~/.config/refcheck/config.toml
[learn]
time_window = "6 months"  # the default, handed to git log --since
```

## Exclusions — history is skipped, and each repo names its own generated output

```bash
refcheck check --show-config                  # every exclusion in force, and the layer that set it
refcheck check --exclude "build/reports/**"   # one more pattern, for one run
refcheck check --test-mode                    # read the recorded fixtures too
```

The built-in list holds what is true of any repository: version control and
dependency directories, tool caches, Cargo's build directory (a `target` beside a
`Cargo.toml`), logs, changelogs, backups, coverage output, and recorded fixtures (`fixtures/`, `testdata/`, `docs/archive/`). Each records
what a path *was*. A changelog entry naming the old location is correct rather
than stale. A captured tool output names every file that existed when it was
taken. It is fixed by re-running the tool, never by editing. A file with a NUL
byte near its start is binary and is skipped, the heuristic git uses. A
symlinked directory is not followed.

Which of *this* repo's directories hold generated output is a fact only the repo
knows. It says so in `.refcheck.toml` at its root:

```toml
[scan]
exclude = ["build/reports/**", "*.snapshot.json"]
```

Patterns are globs matched against the repo-relative path, and `**` crosses
directory separators. They add to the built-in list rather than replacing it. A
test-report directory that records a node ID per test is the usual case.
Deleting a test file reports one miss per report that ever ran it, and the count
grows with every run.

refcheck reads the nearest `.refcheck.toml` at or above the directory it runs
in, and stops at the git root. A checkout never inherits the config of whatever
encloses it.

## Development

```bash
uv run pytest
```

The suite also runs as a pre-commit hook on any commit staging a Python file.
The CLI tests run `refcheck` from `PATH`. Under `uv run` that is the editable
install in `.venv`. A bare `pytest` on a machine with refcheck installed tests
the installed release instead.

The runtime dependencies are typer and
[pyselfupdate](https://github.com/datapointchris/pyselfupdate). Everything else
is the standard library.

This repo's own refcheck hook runs the release `.pre-commit-config.yaml` pins,
so a change to the checker does not check its own commit.
