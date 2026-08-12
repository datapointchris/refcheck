# CHANGELOG


## v0.5.1 (2026-08-12)

### Bug Fixes

- Read every spelling of a source statement
  ([`4a8da9e`](https://github.com/datapointchris/refcheck/commit/4a8da9e9323d85870458545c915ef4e095522733))

Two spellings resolved before: a quoted argument, and one led by a variable. Shell writes `source
  lib/x.sh` and `. lib/x.sh` far more often, so a markdown file citing a moved script that way
  passed clean — which made half of the claim that this hook validates source and bash targets in
  markdown false.

`.` is the dangerous half, being the commonest character in prose, so it is matched only in command
  position: opening a line, after a shell separator, or after `then`/`else`/`do`. An English full
  stop always follows a word, never a separator. Accepting a preceding space instead would read
  `find . lib/` as sourcing lib/.

A bare argument gets one test a quoted one does not. It has to carry a separator or a shell suffix
  before it is resolved, which is what stops "the source of truth" and "we do . nothing" from
  becoming paths, and it ends on a path character so a trailing comma in prose is not part of the
  filename. check_script_references gets that second half for free from its `.sh` anchor, which a
  sourced file need not carry.

Unquoted `source $DIR/lib/x.sh` captured from the slash on and reported `/lib/x.sh` — a path nobody
  wrote, that would pass silently on a machine holding one at the root. It now resolves through the
  symbol table like the quoted form, and is skipped when the variable is unknown.

/etc joins the machine-state paths that are never repo content. theme and font both run `.
  /etc/os-release` behind a Linux guard, and each already carries a comment that it is absent on
  macOS, so matching the dot form put both one platform away from being reported.

The README's sample output borrowed `tests/`, a directory this repo has, to illustrate a fictional
  `scripts/deploy.sh`. Naming `scripts/` throughout lets the existing leading-directory guard
  recognise the whole block as illustrative.

Measured across 85 repos: output is byte-identical either way, and the new forms fire on 21 real
  lines that the existing guards already handle.

- **tests**: Hide the caller's git env from fixtures
  ([`c7f18bb`](https://github.com/datapointchris/refcheck/commit/c7f18bb1e5955142dcbe5e35da59d55f6ded2278))

Git exports GIT_DIR and GIT_INDEX_FILE to the hooks it runs, and this suite is one of them. Both
  beat directory discovery, so a fixture's `git init` never created a `.git` in its temp directory —
  it reinitialized the repository being committed — and the `git add` that followed wrote the
  fixture's files into that repository's index.

Measured on a clone: 29 tracked files replaced by a single .gitkeep, after which the commit that ran
  the hook died with `invalid object ... for '.gitkeep'`, because the blob had gone to a directory
  that was already deleted. Every commit here was doing it, and the damage happened before any
  assertion ran.

A session fixture strips the whole GIT_ prefix rather than the two known offenders, because
  GIT_WORK_TREE, GIT_OBJECT_DIRECTORY and GIT_COMMON_DIR redirect the same operations, and the
  fixtures supply every git setting they need. Doing it once at session scope also covers the call
  sites in the test files, which shell out to git directly.

The regression test runs the move suite as a subprocess with a hook's environment pointed at a
  scratch repository, then asserts that repository still tracks its own file.

### Build System

- **precommit**: Resync to forge toolchain 14
  ([`299eda1`](https://github.com/datapointchris/refcheck/commit/299eda1a9e89e78ea6d5b2b67bbffb2a621af08e))

Picks up the new refcheck block, so the tool now runs on its own commits. Also carries the
  .editorconfig comment's correction from toolchain 12, which this repo had not resynced since 11.


## v0.5.0 (2026-08-10)

### Bug Fixes

- Make subtree exclusion patterns reach every depth
  ([`b1cd398`](https://github.com/datapointchris/refcheck/commit/b1cd3987fbd8c7579ef3d25f674c8e8cfacb2fd4))

Path.match reads `**` as a single component, so every `dir/**` exclusion only covered the files
  sitting directly in that directory. `.planning/**` skipped `.planning/top.md` and scanned
  `.planning/design/notes.md` right beside it; `.claude/metrics/**` and `site/**` had the same hole.

Match with both matchers, because the patterns are two kinds. `*.log` and `CHANGELOG.md` name a file
  wherever it sits, which is Path.match's right-anchored semantics and has to stay. `dir/**` names a
  subtree, which is fnmatch over the posix string — anchored at the root, with `*` free to cross
  separators.

full_match would do this alone but arrived in 3.13, and the floor here is 3.11.

- Stop reporting invocations a script only documents
  ([`f0efdde`](https://github.com/datapointchris/refcheck/commit/f0efddecdd1a7ee3defe1de4ff6652fbb594dd2c))

A shell script explains itself in two places — a `#` comment and a usage string it echoes — and
  neither is a reference to anything. logsift's run-and-summarize.sh produced seven errors that way,
  every one of them a line illustrating how to call the script.

The judgment already existed: describes_another_tree treats a bare filename as illustrative and
  requires a real leading directory, names_a_placeholder skips stand-in stems. Both were gated on
  the file being markdown. Widen the gate to any documentation context and apply the same two guards
  there.

Deliberately not a blanket skip of comments: a comment naming a directory the repo has is still a
  stale reference and is still reported, which is what check_relative_path_fragility's comment
  handling was careful to preserve. Only the leading command decides, so `bash x.sh && echo done`
  remains a real invocation.

This also subsumes the narrower self-reference exemption it replaces.

### Features

- Check what staged renames and deletions left behind
  ([`d40cc51`](https://github.com/datapointchris/refcheck/commit/d40cc51bf3c980f787b53a1e2b3aebce6da5beea))

--moves reads `git diff --cached --diff-filter=RD -M` and runs a pattern check per old path;
  --moves-since does the same over a range, for CI. The old path no longer has to be typed in, and
  the check fires at the moment the move is made, when fixing it is free.

This is the half of refcheck worth putting on a pre-commit hook. Measured across the 49 active
  repos: the source/bash checks found nothing, because the portfolio is already clean, while
  replaying six months of renames found real breakage — three live `uv run cli/log_viewer.py` call
  sites in ichrisbirch's ops tool, and a documented build command in shadows naming a cmd/ directory
  that no longer exists. A pattern is language-agnostic, which is why it sees an invocation
  `bash`/`source` matching cannot.

Learned rules were the alternative and are strictly worse here: they detect nothing on their own,
  feeding only the suggestion text under a finding, and six months of history mostly describes moves
  already reconciled. A diff needs no stored state and cannot go stale.

Three filters, each from a false positive in that replay. Only old paths with a directory, since
  `main.go` is too generic to be evidence. Skip a path that exists again. And exclude the two file
  kinds that record what a path *was* rather than what should exist — CHANGELOG.md, and captured
  tool output under fixtures/ and testdata/, which together were 226 of the 280 hits fleet-wide.

check_patterns walks the tree once for the whole set, so the cost no longer scales with the size of
  the move.

### Refactoring

- Mention learned rules only where they would have helped
  ([`6acd93d`](https://github.com/datapointchris/refcheck/commit/6acd93d64c43bb713a7a011ee8fa5713972a4b2a))

The hint printed on every clean run, which across the 49 active repos meant 48 repos told to go do
  maintenance for a feature with no finding behind it. Learned rules feed exactly one thing — the
  "Possible matches" line under a broken reference — so that is where the offer belongs: after a run
  that found references it could not suggest a replacement for. A clean run is now one line.

The staleness warning goes with it. It nagged toward a refresh whose only payoff was better
  suggestion text, and its threshold was configurable, which made a knob out of a prompt nobody
  benefits from acting on.

That leaves stale_threshold, show_no_rules_hint, parse_duration_to_days, get_rules_age_days and
  ReferenceChecker.get_rules with no callers. The config loader reads named keys and ignores the
  rest, so an existing config.toml carrying the two removed ones still loads.


## v0.4.1 (2026-08-08)

### Bug Fixes

- **update**: Use pyselfupdate's updater instead of a copy
  ([`ffc28e4`](https://github.com/datapointchris/refcheck/commit/ffc28e46171e01792cd6e80bd013cb9a26493997))

selfupdate.py carried a hand-copied run_update whose stated reason was that pyselfupdate.typercmd
  'pulls in typer, and refcheck's CLI is argparse'. The CLI is typer now, so the premise is gone and
  the copy can be imported.

The copy had drifted into the bug typercmd exists to prevent: it fetched the changelog after
  update() had already replaced this interpreter's environment. That is the syncer 4.0.0 failure
  verbatim -- a lazy import resolved against packages the new release had just deleted. It flushed
  stdout in acknowledgement of the hazard but still made a network call on the far side of the
  install. typercmd orders every network read before the install and exits without unwinding.

--version becomes an eager callback, which is what cli-design.md asks of a Python CLI, rather than a
  bool read at the top of the command body.

Requires the pyselfupdate[typer] extra, which costs nothing now that typer is a direct dependency.


## v0.4.0 (2026-08-08)

### Features

- **cli**: Give refcheck colored, sectioned help
  ([`a2c7db0`](https://github.com/datapointchris/refcheck/commit/a2c7db07a19b2c9bbf70139588a9af85879ccd6a))

argparse rendered monochrome help under its plumbing-named 'positional arguments:' / 'options:'
  headings, so refcheck did not meet the section-grouping rule in cli-design.md. Typer is the fleet
  standard for a standalone Python CLI and groups options through rich_help_panel. rich-argparse was
  the alternative and would only have half-solved it: a one-line formatter_class swap colors
  argparse in place but keeps its headings.

Options now group as Scope / Filters / Pattern search / Severity / Maintenance, the description says
  what the tool is for and why it reads the whole tree, and each example names the situation it
  answers. The error-vs-warning contract moved out of a wall of epilog text into its own section.

The command surface is unchanged: a single Typer command keeps the flat parser, every flag and the
  positional path keep their names, and -h works via help_option_names. The pre-commit hook entry
  stays a bare 'refcheck'.

feat, not refactor: the help is user-visible, and refactor would mean the change never ships.


## v0.3.9 (2026-08-07)

### Bug Fixes

- Exclude run logs from pattern scanning
  ([`b5c8edc`](https://github.com/datapointchris/refcheck/commit/b5c8edc064b199c03ebc06680e03e0b7d4dbdc01))

A .log file is a transcript of what existed when it ran, the same class of artifact as the .jsonl
  event logs already excluded. Renaming a tool reported a miss against a gitignored test log after
  every live reference was updated.


## v0.3.8 (2026-08-07)

### Bug Fixes

- Validate references in markdown, not just shell
  ([`bd0205d`](https://github.com/datapointchris/refcheck/commit/bd0205dcea4bf0b1effd6bee403e4d4d17b8d8b5))

check_source_statements and check_script_references globbed **/*.sh, so prose was never read.
  `refcheck docs/` in dotfiles reported "all file references valid" over five copies of `source
  "$DOTFILES_DIR/install/common/lib/error-handling.sh"` naming a path no code had used in months. A
  false clean is worse than a false positive because it certifies the rot as checked.

Scanning prose needed four suppressions to stay quiet enough to trust, measured across seven repos:

- Prose has no assignments to parse, so $DOTFILES_DIR is seeded with the repo root. Without it every
  documented source failed to resolve and was skipped. $SCRIPT_DIR stays unresolved: there is no one
  script for it to be relative to. - A reference is only ours to validate when its leading directory
  is one this repo has. Docs quote other people's trees constantly, and a bare filename anchors to
  nothing. A rename under a directory we still have is preserved, which is the case that matters. -
  Documentation placeholders (toolname.sh, {tool}-plugins.sh) name files never meant to exist. Prose
  only: `bash script.sh` is a real invocation in a shell script. - A fence opener carrying
  attributes runs nothing.

Also fixes a pre-existing regex bug the wider scan exposed: `source` lacked a word boundary, so
  `resource "aws_lambda_function"` and newsboat's `urls-source "freshrss"` both parsed as source
  statements. Shell rarely writes either, so only prose surfaced it.

Filtering one listing rather than globbing per suffix is what makes a single-file argument work;
  find_files ignores its pattern there, so two globs scanned the file twice and --skip-docs could
  not exclude it.

After: 10 findings in dotfiles, all genuine, and zero across homelab, ichrisbirch, docs, forge,
  syncer and refcheck itself.

### Chores

- **lint**: Disable SC1091/SC1090 from the forge toolchain
  ([`be7d723`](https://github.com/datapointchris/refcheck/commit/be7d723796f3c91364c978300a592742ec4f7282))

### Documentation

- Describe markdown checking and its suppressions
  ([`ee15231`](https://github.com/datapointchris/refcheck/commit/ee152318d88524df33204f5aa8d6c844a904e2e0))

The README said refcheck validated source and script references without saying which files it read,
  which was accurate right up until it started reading prose. Records what is now scanned, the two
  variable rules that differ in prose, and why a reference to another project's tree is quiet.


## v0.3.7 (2026-08-06)

### Bug Fixes

- Exclude tool caches from the scan
  ([`8fc572a`](https://github.com/datapointchris/refcheck/commit/8fc572a1bc57a71556f0748af439e0706c65853f))

A sweep for "appcore" after extracting it from dotfiles returned 21 hits: one real reference in the
  docs and twenty in .pytest_cache/v/cache/nodeids, which holds a node ID per collected test and is
  rewritten by the next pytest run.

Same category as the .jsonl exclusion already here — a cache records what a path *was*, not what
  should exist — so .pytest_cache, .ruff_cache and .mypy_cache join the default excludes. The ratio
  is the whole point: a real finding buried twenty deep is a finding nobody reads, and false
  positives are why this tool went unused before.


## v0.3.6 (2026-08-04)

### Bug Fixes

- **pattern**: Never report a hit inside a URL
  ([`fd3f0f7`](https://github.com/datapointchris/refcheck/commit/fd3f0f75e9a6db914ff483095294c3bdb26dc9e8))

`:` is not a path character, so left-expansion of a matched token stops just after a URL scheme's
  `//` and the whole host+path is treated as a file reference. `--pattern docs/claude-code` reported
  every link to docs.anthropic.com/en/docs/claude-code/hooks as a moved path.

Skip a hit whose expansion butts up against `:`. Per-hit, so a stale path on the same line as a URL
  is still reported.


## v0.3.5 (2026-08-04)

### Bug Fixes

- Report the update in the verb that ran it
  ([`01b0947`](https://github.com/datapointchris/refcheck/commit/01b0947082da06d9b37351bcf2f3d197b563ba65))

refcheck copies the report format rather than importing run_update, so it kept saying "upgraded" and
  "upgrade failed" after pyselfupdate was fixed. The flag is --update; one flag, one vocabulary.


## v0.3.4 (2026-08-03)

### Bug Fixes

- **pattern**: Stop reporting hits inside paths that resolve
  ([`7ee2f86`](https://github.com/datapointchris/refcheck/commit/7ee2f8606f34f8eee67282c15d5ea418c401c8bd))

--pattern did a plain substring test, so after moving boards/ under config/ it reported
  `config/boards/arm/...` — the three files the move had just corrected — as stale references to
  boards/arm.

A substring cannot distinguish a stale path from a correct longer one ending the same way, so
  resolve the surrounding token instead: a hit inside a path that exists on disk is not reported,
  and one that does not resolve still is. Prefixing a stale path with a directory that does not
  exist does not launder it.

### Chores

- **toolchain**: Adopt the generated configs and CI
  ([`524ce37`](https://github.com/datapointchris/refcheck/commit/524ce377d79e8603980fb18b9d0f6aacc6af6342))

Brings the repo onto forge toolchain manifest 11.

bandit, refurb and pyupgrade drop out: pyupgrade is ruff's UP rules, already selected, and the other
  two are the manifest's deliberate narrowing to the rule set every repo actually runs.


## v0.3.3 (2026-08-03)

### Bug Fixes

- Stop scanning binary files and append-only event logs
  ([`b4e74cd`](https://github.com/datapointchris/refcheck/commit/b4e74cdafca2d6b423a17ea33bcb976e3774a0c7))

A --pattern sweep of ~/dev reported 31 misses. Twenty-nine were inside indy.db — 1.4 GB of SQLite
  read as text, because the binary check was a suffix list and .db was not on it. The other nine
  were a 197 MB devstats event log recording every file a hook had ever checked.

Binary detection is now the NUL-byte-in-first-block heuristic git uses, so it holds for formats
  nobody thought to enumerate. Event logs are excluded by pattern instead: they are text, and they
  record what a path *was* rather than what should exist, so a hit in one is history, not a
  reference.

Same query now reports zero. This tool is only worth running if its output can be trusted at a
  glance, and 31 false positives is how it stopped being run.

### Documentation

- Flush dormant markdownlint violations
  ([`f773898`](https://github.com/datapointchris/refcheck/commit/f773898b18082f5a2734504ddc81cbd0b35dd1e1))

markdownlint only runs on the files a commit touches, so unmodified docs accumulate violations
  invisibly. The toolchain sync bumps markdownlint to v0.47, which added MD060, and runs --all-files
  — surfacing every one of them at once, in the middle of an unrelated change.

Table separators are normalized to the compact `| --- |` style MD060 expects, which --fix cannot
  repair; everything else is markdownlint --fix. CHANGELOG.md is excluded instead of normalized:
  semantic-release regenerates it on every release, so any fix there is undone and comes back as a
  rebase conflict.


## v0.3.2 (2026-07-31)

### Bug Fixes

- **tests**: Skip the real-world tests instead of erroring without dotfiles
  ([`08fe89a`](https://github.com/datapointchris/refcheck/commit/08fe89a2fa1766fcbea1a72a67ea64ad3644e3d1))

The fixture ran `git rev-parse` with cwd set to ~/dotfiles and returned None when that failed, but
  subprocess raises rather than returning non-zero when cwd does not exist -- so the None branch was
  unreachable and all 11 tests errored on any machine without the repo checked out. They passed here
  only because this machine has one.

Checking the directory exists first makes the skip reachable, which is what the tests already
  expect.


## v0.3.1 (2026-07-31)

### Bug Fixes

- **ci**: Run ruff and pytest without depending on repo dev deps
  ([`36d30e3`](https://github.com/datapointchris/refcheck/commit/36d30e3dda535c54a11a1359abc97b90c143e526))

`uv run ruff` resolved ruff from the repo's own dependencies, so a repo that treats ruff as a fleet
  tool rather than a project dependency failed to spawn the binary instead of linting. ruff now runs
  through uvx at the version its pre-commit hook pins; pytest is supplied with --with so a real test
  suite is never silently skipped; and mypy's guard tests for the dependency by import, since the
  [tool.mypy] section it used to look for is now in every repo.

Regenerated by `forge dies run maintenance/sync-ci.sh`.

### Code Style

- Apply the standard ruff config across the python code
  ([`37d0e4c`](https://github.com/datapointchris/refcheck/commit/37d0e4cfbf6a8f514390cb46cdf8ea55d9b76b8a))

First pass under the fleet config now that CI lints the whole repo rather than only staged files:
  single quotes, one import per line, and the auto-fixable findings.

Four are not formatting: three loops that built a boolean by early-returning True become any() or a
  direct return of the condition.


## v0.3.0 (2026-07-31)

### Chores

- **config**: Adopt the standard ruff and pyright config
  ([`6340d4c`](https://github.com/datapointchris/refcheck/commit/6340d4cdfeba754df4b956cd0457b71a74803bcb))

Synced from forge pyproject template: isort, per-file-ignores and the ruff formatter settings now
  match the portfolio, and a [tool.pyright] section replaces the editor LSP settings that were
  suppressing every diagnostic.

- **config**: Record the keys the pyproject sync owns
  ([`d5c7031`](https://github.com/datapointchris/refcheck/commit/d5c703128e706bf1759c96fcafe840ac33bf9709))

forge now writes [tool.forge] managed, listing the exact keys the standard sets. Deletion on a later
  sync is scoped to that record, so dropping a key from the template retracts it here without having
  to guess which settings belong to this project.

Purely additive: nothing else in this file changed.

### Documentation

- Document consuming refcheck as a pre-commit hook
  ([`c02b26b`](https://github.com/datapointchris/refcheck/commit/c02b26b4efd825a742165f14471779be72c25f74))

Covers the pinned repo/rev block and why the hook scans the whole repository instead of the staged
  files.

### Features

- **ci**: Add the standard validation workflow
  ([`24c5786`](https://github.com/datapointchris/refcheck/commit/24c5786d0ede564f79dfdef15169b2eb5d77c3eb))

Nothing checked this repo as a whole. pre-commit only sees staged files, so a change to a shared
  module or to the lint config itself passed locally and the breakage surfaced whenever some
  unrelated commit happened to touch an affected file -- which is how a config sync deleted a repo's
  bugbear exemptions and went unnoticed until 57 errors appeared in an endpoint commit days later.

Generated by `forge dies run maintenance/sync-ci.sh`.


## v0.2.1 (2026-07-27)

### Bug Fixes

- Don't resolve paths handed to a remote or container executor
  ([`a440a55`](https://github.com/datapointchris/refcheck/commit/a440a55ab1b4d414a3cd10d3382d094e4a99024e))

A command passed to pct exec, lxc/docker/kubectl exec, ssh or su -c runs on a filesystem this
  process cannot see, so its paths were never ours to resolve. homelab's only reported error was
  `bash install.sh` inside a `pct exec ... su - chris -c` string, pointing at a script in a
  container.

Same reasoning as DYNAMIC_PATH_PATTERNS: not a broken reference, just not local.


## v0.2.0 (2026-07-27)

### Features

- Ship a .pre-commit-hooks.yaml so repos can consume refcheck
  ([`b446831`](https://github.com/datapointchris/refcheck/commit/b4468315cbdd89954dba34a15886a3c4b4ec5130))

Makes refcheck a pre-commit hook repository, so a consuming repo pins `repo:
  https://github.com/datapointchris/refcheck` at a rev instead of declaring a local hook against
  whatever version happens to be installed on that machine.

The hook always scans the whole repo rather than the staged files: a reference breaks in the file
  that was not edited, so filtering to the changeset would miss the class of bug it exists to catch.


## v0.1.2 (2026-07-27)

### Bug Fixes

- Don't warn about fragile paths inside comments
  ([`068c7b9`](https://github.com/datapointchris/refcheck/commit/068c7b950447bbf6a5411e8fbc2c441895be00ae))

A `source` in a usage comment has no working directory to be fragile about, so the cwd-fragility
  warning had nothing to say about it. Both of homelab's fragile-path warnings were usage
  docstrings. Broken-reference errors still scan comments, because a stale path in a usage example
  is exactly the drift this tool exists to catch.


## v0.1.1 (2026-07-27)

### Bug Fixes

- Stop a filename list reading as a script invocation
  ([`a97ef0c`](https://github.com/datapointchris/refcheck/commit/a97ef0cd1eff9bf473bdbc3f3dd15e0cf3cff006))

The bash/sh pattern had no left boundary, so in `for f in functions.sh aliases.sh` the trailing "sh"
  of the first filename plus the second matched as `sh aliases.sh`, reporting a broken reference to
  a script that was never invoked. This was both of dotfiles' reported errors.


## v0.1.0 (2026-07-27)

### Chores

- Add .planning to gitignore
  ([`218d29b`](https://github.com/datapointchris/refcheck/commit/218d29b19041b94761e3a5debe82e037f5741219))

- Add .planning to gitignore
  ([`ac98f95`](https://github.com/datapointchris/refcheck/commit/ac98f9544f93cc91a25a76ad1f5fc2b13df7c265))

- Deduplicate .planning gitignore entry
  ([`1bdea6b`](https://github.com/datapointchris/refcheck/commit/1bdea6bb9688db4fadcbadea3050134322e1d9da))

- **precommit**: Use $HOME for the commit-message hook path
  ([`4c0e4fd`](https://github.com/datapointchris/refcheck/commit/4c0e4fd9de2b826e2abee16b5207e362f9a2e7b6))

A literal /Users/chris or /home/chris only resolves on one of the two machines this repo is
  committed from. forge generates this hook now, so matching its portable entry keeps the next sync
  a no-op.

### Continuous Integration

- Add pre-commit config
  ([`4aaee5a`](https://github.com/datapointchris/refcheck/commit/4aaee5a9e1b056025b051c5643a96a5bf054eeef))

- Release on push to main with python-semantic-release
  ([`5d6b799`](https://github.com/datapointchris/refcheck/commit/5d6b799ffe37a20355dbfe6311edb282063fdaf5))

refcheck was the only tool installed from a GitHub URL with no tags and no releases, so its version
  was a hand-maintained literal that nothing verified. Adopts the standard Python release workflow
  from dev/release-standards.md, with the package name hardcoded in build_command because
  python-semantic-release sets no $PACKAGE_NAME.

### Features

- Add --version and self-update from GitHub releases
  ([`9a8b1c7`](https://github.com/datapointchris/refcheck/commit/9a8b1c7cf192eaab8cd76cfae5d45a43ac5bc07d))

Brings refcheck in line with the other Python tools: an installed version readable from package
  metadata rather than a second literal in __init__.py that nothing kept in sync, and pyselfupdate
  behind --update plus a once-a-day notice when a newer release exists. The reporting strings are
  copied from pyselfupdate.typercmd rather than imported, which would drag typer into an argparse
  CLI.

The repo's pre-commit config had never run against the Python source, so bringing it up also meant
  clearing what the hooks flag: implicit Optional defaults and missing annotations for mypy, open()
  calls converted to Path.open()/read_text() for refurb, two bare `except Exception: pass` blocks
  narrowed to the errors they actually mean, a dead tomli fallback import removed from inside a
  function, and ruff-format across the tree. The tool configs those hooks read were missing from
  pyproject entirely.
