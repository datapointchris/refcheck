# refcheck

refcheck finds what a move, a rename or a deletion left behind. That covers a
`source` or `bash` target that does not resolve, an old path still named
after a move, and an old tool, subcommand or flag name. It ships as a
pre-commit hook. With `--moves`, the hook reads the staged renames and
deletions out of git and asks what still names each old path.

## A run that covered less than it was handed fails

A false clean is worse than a false positive, because it certifies the rot.
Every path the walk cannot read goes through `note_unreadable` and fails the
run with exit 1. A directory named on the command line and not there exits 2.
Walking it would pass every check over nothing. A range git cannot diff raises
`UnreadableChange` and exits 2 rather than reading as no moves. A sweep that
could not reach a listed repo prints no tick (`SweepResult.unreached`).

These are not shortfalls, and counting one fails a run that missed nothing:

- **A subtree the exclusions skip.** `_descend` prunes it during the walk, so
  an unreadable `node_modules` never reaches `note_unreadable`.
- **A path deleted between the walk and the read.** Nothing is left in it to
  miss.
- **A file that is not UTF-8.** Its bytes arrived. Naming every binary would
  bury the findings.

Retired repos are the one deliberate skip in a sweep. In `print_results`, each
block runs on its own condition and none returns early. A run can be clean,
have set hits aside and have failed to read a path, all at once.

## The tool is worth exactly its false-positive rate

Most built-in exclusions and guards in `checker.py` carry a comment naming the
measured false positive that put them there. A new one carries its incident
the same way.

Documentation context widens the guards and never skips the line.
`documents_rather_than_runs` counts markdown, a `#` comment and an
`echo`/`printf` line as documentation. There, a placeholder stem is skipped. A
path whose leading directory the repo lacks is read as another project's tree
(`describes_another_tree`). A documented path under a directory the repo still
has is still reported, because that is the stale reference worth catching.

A false-positive fix and a blindness look identical on paths that resolve. A
test of a new guard pairs the case that goes quiet with the case that must
still fire.

## Each question judges a hit by different evidence

`ReferenceChecker` holds every judgment about one tree. `sweep.py` builds one
per listed repo. `names.py` holds the name shapes, `moves.py` reads git, and
`cli.py` decides which questions a run asks.

- **`source` and `bash` targets** resolve through `anchor`. A `~` path hangs
  off home, an absolute path is itself, and anything else hangs off the repo
  root. `resolves` also accepts a `~/` path when a file in the repo ends in the
  same segments, because a CI runner's home holds nothing the repo deploys.
  These checks read markdown and every file `kind_of_file` reads as shell
  (`declares_shell`). A file with no suffix is opened for its shebang, and is
  read only when that names a shell.
- **`--pattern` and `--moves` in this tree** widen each hit to its whole path
  token (`_resolved_hits`). A token that resolves on disk is set aside and
  listed, never reported. A substring cannot tell a stale reference from a
  longer correct path. A hit that opens its own token is reported. A hit
  inside a URL is dropped. The rename record `--moves` carries decides only
  which set-aside hits are listed, never what is reported.
- **`--registry`** reports a hit only when the path it names sits inside a
  listed repo and is not there (`_reaches_a_gone_path_in`). That rule is what
  makes a bare basename safe to sweep.
- **`--name`** resolves nothing. The shape is the whole judgment, and the
  shapes that count depend on whether the line is prose, shell or code
  (`NameShapes.names_it`). Shell is what a file declares by suffix or shebang,
  never the fallback (`kind_of_file`). A name in running prose is never
  matched.

In markdown, a fence tagged with another language is never read as shell. An
untagged fence is shell.

A bare filename is too generic to be evidence inside one repo, so `--moves`
drops it there. The sweep asks it anyway, because an absolute path settles it.
An old filename cited alone is asked only with `--registry`. It is asked only
once no file in this tree or a listed repo holds that name (`held_filenames`).

Learned rules detect nothing. They feed only the "Possible matches" line under
a broken `source` or `bash` reference.

## Existence and containment take different forms of one path

The existence test asks the kernel about the path as written. That is the path
a program reading the line would open. The containment test compares
`os.path.realpath` forms on both sides, the token and every repo home.
Flattening before the existence test reports a file that is on disk. Comparing
an unwalked path places a real file outside the repo holding it.
`ReferenceChecker.root_dir` stays as given, because every file the walk yields
is built from it. `physical_root` is the walked-out copy.

The repo maps split the same way. `homes_by_path` and `homes_by_name` hold
every listed repo on disk, retired ones included. A live repo's path into a
retired one is still broken, and the fix lands in the live repo. The walk list
drops retired repos. A repo absent from this machine is in neither map, since
every reference into it would hit. `homes_by_name` is built on its own rather
than inverted, because two declared paths can resolve to one directory.

A token shaped `<repo-name>/path` names another repo only when the scanned
repo has no directory of that first segment (`_is_this_repos_own`). Registry
names and ordinary directory names such as `docs` collide constantly.

Every narrowing flag reaches every swept repo. Each swept repo still reads its
own `.refcheck.toml`. The registry is always named with `--registry`. The tool
never discovers one, because one machine's registry lists a different set of
repos from another's.

## Exclusions match two ways and prune during the walk

`_matches_exclusion` tries `Path.match` and `fnmatch` on every pattern.
`Path.match` is right-anchored, which fits `*.log` and `CHANGELOG.md`. It reads
`**` as one component. Alone, it lets `.planning/**` exclude
`.planning/top.md` and scan `.planning/design/notes.md`. `fnmatch` over the
POSIX path covers subtrees. `should_skip_directory` matches a subtree pattern
with a trailing slash, so `build/**` prunes `build` itself.

The built-in list holds what is true of any repository: logs, changelogs, tool
caches, backups, coverage output and recorded fixtures. Each records what a
path was, so a hit in one is history. A directory one repo generates belongs in
that repo's `.refcheck.toml`, never in the built-ins. `find_repo_config` stops
at the git root, so a checkout never inherits an enclosing tree's config.

## The suite runs inside a git hook

pre-commit runs `uv run pytest` on any commit staging a Python file. Git
exports `GIT_DIR` and `GIT_INDEX_FILE` to its hooks. Both outrank directory
discovery. Left in place, a fixture's `git init` reinitializes the repository
being committed, and its `git add` replaces that repository's index. The
session fixture `detached_from_the_calling_git` in `tests/conftest.py` strips
every `GIT_` and `PRE_COMMIT_` variable. `tests/test_suite_isolation.py` holds
it in place.

- **The CLI tests run `refcheck` from `PATH`.** Under `uv run`, that is the
  editable install in `.venv`. A bare `pytest` on a machine with refcheck
  installed tests the installed release instead.
- **Fixtures build their trees under `tmp_path`, with `HOME` pointed there.**
  A test reading a directory on the machine makes its result a property of
  that machine. The user config and the rules files sit under
  `$XDG_CONFIG_HOME` when it is set, so the autouse `config_follows_home`
  unsets it and both follow `HOME`.
- **A fixture or docstring names a placeholder tool, never a real one.** A real
  tool's old name written here is a hit in every cross-repo sweep for that
  rename.
- **A test must fail when its fix is reverted.** A test can pass for a reason
  other than the one it names. A fixture line two patterns match tests only
  the first. An assertion its caller's filter already satisfies tests nothing.

## This repo is checked by a released refcheck

The refcheck hook in `.pre-commit-config.yaml` runs the release that file pins,
fetched from GitHub. A change to the checker does not check its own commit.

That hook reads this repo's markdown, the README included. A `source` or `bash`
example in prose or a shell fence is checked like code. An illustrative path
in one uses a leading directory this repo lacks, such as `scripts/`, so the
leading-directory guard reads it as another project's tree. A sample of
refcheck's own output goes in a `text` fence, which is never read as shell.

`.pre-commit-config.yaml`, `validate.yml` and the tool configs whose first line
is a marker comment are generated outside this repo. Only their `# > custom:`
sections are this repo's, and the pytest hook lives in one. In
`pyproject.toml`, the tool keys the managed-key record lists belong to the same
generator.

## Releases come from commits on main

`release.yml` runs `validate.yml` and then python-semantic-release, through a
shared reusable workflow. There is no changelog file. Release notes live in the
GitHub release body. The version lives only in `pyproject.toml` and is read at
run time through `importlib.metadata`.

The release rewrites the `rev:` line in the README's pre-commit example, so
that pin is never bumped by hand. A consumer pins a rev, so a change to
`.pre-commit-hooks.yaml` reaches nobody until they bump.
`test_the_hook_entry_runs_the_check` pins the hook's entry.

The hook sets `pass_filenames: false` and `always_run: true`. A reference
breaks in the file that was not edited, so a scan of the staged files would
miss the whole class of bug.

## Typer's private Click is imported on purpose

`cli.py` imports `Context`, `NoSuchOption` and `TyperGroup` from
`typer._click` and `typer.core`. Typer bundles its own copy of Click. It
exports no public path to these names, so a Typer upgrade can move them.
`RootGroup` uses them to answer a `check` flag given at the root with the call
that runs it.
