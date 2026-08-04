# CHANGELOG


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
