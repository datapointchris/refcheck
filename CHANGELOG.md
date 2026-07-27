# CHANGELOG


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
