# CHANGELOG


## v0.7.0 (2026-09-02)

### Bug Fixes

- **checker**: Read a fenced block as shell only where its tag says so
  ([`a4fa8c1`](https://github.com/datapointchris/refcheck/commit/a4fa8c186786cace668554324413a4e36540390f))

A doc that prints refcheck's own output inside a fence had that output read back as source code. A
  ```yaml block showing `bash tests/helpers.sh` as a finding resolves against a tests/ directory the
  repo really has, so every guard downstream passes it through and refcheck reports itself.

An explicit tag naming another language is now the only thing that puts a block out of scope. A bare
  fence stays scanned, because an untagged block is very commonly shell and prose is where a stale
  reference survives longest. Measured across the 94 repos the registry lists: no finding gained,
  none lost.

- **pattern**: Resolve a path token rooted at a shell variable
  ([`54cc4f3`](https://github.com/datapointchris/refcheck/commit/54cc4f31a0b136027c27af062f0967d60bfc9326))

A token like $REPO_ROOT/homelab-hosts.json has no literal path to test, so it resolved to nothing
  and every repaired assignment in a test file came back as a surviving reference to the old name.

The variable segment is dropped and the remainder resolved. A stale $REPO_ROOT/hosts.json still
  resolves to nothing and is still reported, which is the half a rename sweep exists for.

- **pattern**: Resolve bare-name hits and relative links before reporting them
  ([`ac0d58e`](https://github.com/datapointchris/refcheck/commit/ac0d58e21679f7ea08e5cfbf93d6dba8233a8cd8))

A rename whose new name ends in the old one puts the pattern inside every site that was just
  repaired. tools.json became fleet-built-tools.json and --pattern tools.json reported eighteen hits
  on a clean tree, fourteen of them the corrected references.

The token resolution written for path patterns already answers this and returned early on any
  pattern with no slash, which is every bare filename. A hit standing alone as its own token is
  still reported, so --pattern backmeup still finds 'Run backmeup'.

A markdown link spells its target relative to the file holding it, so a token is now resolved
  against that file's directory as well as the root. Trailing dots are stripped and leading ones are
  not: strip('.') turned ../a.json into the absolute /a.json and .github into a github that is not
  there, so both resolved to nothing and were reported.

- **sweep**: Ask the kernel about the path as written, not a rewritten one
  ([`1b7a727`](https://github.com/datapointchris/refcheck/commit/1b7a7273727f0c4f63995469746392d1f3360efa))

Flattening a token before testing whether it exists answers about a different file. A traversal
  passing through a symlink resolves to a real file, and rewriting it lexically first asked about a
  path beside the link that is not there — so a reference the consumer can open came back reported.
  That trades a miss in the safe direction for a false positive in the direction this check cannot
  afford, and it is the one thing that decides whether the sweep is worth running at all.

The two halves are answered by different authorities and now get different forms of the path.
  Existence is the kernel's, so it asks about the path as written, which is the one a program
  reading that line would open. Containment is a string comparison, so it asks about the path with
  its symlinks and '..' walked out, and the repo paths it is compared against are walked out too.

Resolving both sides also closes a gap that was documented rather than fixed: a repo reached through
  a symlinked parent, or declared in the registry at a link, is now credited to the repo that holds
  the file instead of to nobody. The self-exclusion compares physical roots for the same reason.

Five cases pin it, one per half, each failing when its half is reversed.

- **sweep**: Ask the kernel about the path as written, not a rewritten one
  ([#2](https://github.com/datapointchris/refcheck/pull/2),
  [`89e0e39`](https://github.com/datapointchris/refcheck/commit/89e0e3985436344b64e30a6114aeb7d06eb7321c))

refcheck reports a file that is on disk as gone. `_on_this_filesystem` flattens a path token with
  `os.path.normpath` before testing whether it exists, and a path reaching through a symlink
  resolves somewhere the flattened form does not name. The check then asks about a different file,
  finds nothing there, and reports a reference the consumer can open.

## What to look at

`refcheck/checker.py` — `_on_this_filesystem` returns the token as written. Nothing may rewrite it
  before `.exists()` sees it, because that is the path a program reading the line would open.

`refcheck/checker.py` — `_reaches_a_gone_path_in` computes `os.path.realpath` separately, for
  containment only. The two tests deliberately receive different forms of the same path. Check that
  the existence test never sees the resolved one and the containment test never sees the raw one.

`refcheck/checker.py` — `physical_root` is a second attribute beside `root_dir`, not a replacement.
  `root_dir` stays as given because every file the walk yields is built from it and `relative_to`
  would stop matching; only the cross-repo self-exclusion uses the resolved form.

`refcheck/sweep.py` — the ownership map is keyed by `os.path.realpath` of each repo path, so both
  sides of the containment comparison are walked out on the same basis. A registry may name a repo
  at a symlink.

`refcheck/registry.py` — `_expand` no longer flattens. It was flattening to make containment
  lexically safe, and containment no longer works lexically.

## How it was verified

`uv run pytest` — 178 passed.

The reproduction runs as pasted and ends in refcheck's own output. It is carried in full rather than
  described because a description of it already failed a reader: built from prose, the shape came
  out with the link pointing at a subdirectory of the listed repo, where `link/..` agrees with the
  flattened form and nothing fires.

```bash T=$(mktemp -d) mkdir -p "$T"/{repo,elsewhere,consumer}

# The renaming repo. versions.json moves, so --moves-since yields it as a pattern. git -C "$T/repo"
  init -q . git -C "$T/repo" config user.email t@t git -C "$T/repo" config user.name t printf '{}\n'
  > "$T/repo/versions.json" git -C "$T/repo" add -A && git -C "$T/repo" commit -qm 'add versions'
  git -C "$T/repo" mv versions.json pinned-versions.json git -C "$T/repo" commit -qm 'rename
  versions.json'

# A file one level ABOVE repo/, and a link pointing OUT of repo/ so that # link/.. lands on $T
  rather than back on repo/. printf '{}\n' > "$T/versions.json" ln -s "$T/elsewhere" "$T/repo/link"

# The consumer names a path that opens. printf "versions_file: $T/repo/link/../versions.json\n" >
  "$T/consumer/config.yml"

cat > "$T/registry.json" <<JSON {"repos": [{"name": "repo", "path": "$T/repo", "status": "active"},
  {"name": "consumer", "path": "$T/consumer", "status": "active"}]} JSON

cd "$T/repo" && refcheck --moves-since HEAD~1 --registry "$T/registry.json" ```

Before this change, against a token `os.path.exists` reports present:

```text ❌ Found 1 stale reference(s) in 1 of 2 repos

consumer (/tmp/tmp.Fg6oUfwgWe/consumer) ────────────────────────────────────────────────────────────
  /tmp/tmp.Fg6oUfwgWe/consumer/config.yml:1 Gone from repo: versions.json → now pinned-versions.json

exit 1 ```

After it:

```text ✅ No repo names a path that moved — 2 repos, 1 moved path(s)

exit 0 ```

Two things about the shape, both necessary. The token has to contain a `..`, because that is the
  only rewrite `normpath` performs that can change which file a path names — dropping a `.` or
  collapsing a `//` resolves to the same file either way. And the link has to point out of the
  directory holding it, so that `link/..` lands somewhere other than `repo/` and the two forms name
  different files: `$T/versions.json`, which exists, against `$T/repo/versions.json`, which does
  not. A link into a subdirectory of `repo/` cannot reproduce it, because `repo/link/../sub/x`
  flattens to `repo/sub/x`, which is where the file already is.

Five halves, each proved able to fail by reversing it alone:

- flattening the token before the existence test fails
  `test_a_traversal_through_a_symlink_is_not_reported_when_the_file_is_there` and one other -
  containment on the unwalked path fails four cases, including
  `test_a_traversal_still_lands_inside_the_repo_it_names` - keying the ownership map by the declared
  path fails `test_a_repo_whose_declared_path_is_a_symlink_still_owns_its_files` - comparing the
  self-exclusion against the declared root fails
  `test_a_repo_does_not_report_its_own_missing_path_through_a_symlink`

Before that last case existed, keying the map by the declared path passed every symlink test in the
  suite. Four tests about symlinks, none of which established the thing they were about.

Measured against a real 93-repo registry sweeping six moved paths: 0 hits across 90 repos, 14.0s as
  the median of three runs. Unchanged, so walking symlinks out costs nothing measurable.

## What changes

A path reaching through a symlink no longer reports a file that is on disk. That is the whole point.

A repo reached through a symlinked parent is now credited rather than missed, and so is a repo the
  registry declares at a symlink. Both were documented as known gaps and are closed.

Some findings move and two classes go quiet, and the second is the surprise. A finding through a
  symlink is credited to the repo that physically holds the file rather than to the one the
  flattened path lexically lands in, so a report can change which repo it names.

Two classes stop being reported at all: a token whose path runs through a **broken symlink**, and a
  token through a link into a directory **no listed repo holds**. Both were charged to whichever
  repo the flattened path lexically landed in, which never held the file, so the new silence is
  correct — it is the misattribution this change exists to end. It is still a sweep that used to say
  something and now says nothing. A reader diffing two runs would otherwise read it as a reference
  somebody fixed.

Those two need no `..`. Their paths do not open either way, so the existence test agrees before and
  after and what moved is containment — `realpath` walks the path out of every listed repo, and
  nothing is left to charge. Only the false positive needs a `..`, because that is the only rewrite
  `normpath` performs that can make the existence test itself disagree. All three arrive in the same
  column of a sweep's output, which is why they are worth telling apart here.

## Decisions, and what they rejected

- **The existence test and the containment test get different forms of the path** — different things
  answer them. Existence is the kernel's answer, so it asks about the path as written. Containment
  is a string comparison, so it asks about the path with its symlinks and `..` walked out, as do the
  repo paths it is compared against. *Rejected*: flattening lexically before the existence test,
  which is the defect being fixed. *Rejected*: comparing the unwalked path, which places a real file
  outside every repo that holds it.

- **`realpath` for containment rather than `normpath`** — both silence the false positive.
  `normpath` additionally credits the finding to a repo that never held the file, and leaves a
  symlinked parent uncredited. *Rejected*: resolving only the token while the repo paths stayed
  lexical, which is the same drift in a third direction.

## What this does not do

Nothing in the registry on the machine this was measured against declares a repo at a symlink, so
  that half of the change is exercised only by the suite.

Completes the reporting rule introduced in https://github.com/datapointchris/refcheck/pull/1.

## The review

https://github.com/datapointchris/refcheck/pull/2#pullrequestreview-5026786734 — 0 correctness, 1
  breaks a rule, 1 rule proposed, 1 design.

Breaks a written rule: 1. fixed — both strings are gone. The results are labelled by what changed
  rather than by where the change sits, and the closing reference is bare.

Should be a rule: 1. the instance is fixed — the block now sets `$T`, initialises the repo, renames
  through `git mv` so `--moves-since` yields the pattern, writes the registry, and ends in
  refcheck's own output on both sides. The rule itself is not mine to write.

Design: 1. fixed — **What changes** now names both classes that go quiet, the broken symlink and the
  link into a directory no listed repo holds. I measured both rather than taking them: reported
  against `repoA` before, silent after.

- **sweep**: Let a retired repo own a gone path, and count what it could not read
  ([`34870af`](https://github.com/datapointchris/refcheck/commit/34870afb121666e541a70346b39f0d99c8abd4d9))

Four defects a review found, three of them one question asked in the wrong place.

The ownership map was built from the walk list, so a live repo's reference into a retired repo was
  dropped. Which repos are walked is a policy question about where a fix would land; which repos can
  own a gone path is a factual question about where files live. The recorded decision was about the
  first and this line applied it to the second. A live repo holding a path into a retired one still
  holds a path that does not resolve, and the edit that fixes it is in the live repo. The map is now
  every listed repo on disk, while the walk list still drops the retired. Absent repos stay out of
  both, because nothing in one exists and every reference into it would hit.

Nothing in 164 tests separated those two behaviours, so nothing established the decision. Three
  cases now do, one per way a repo can leave the map.

A path token carrying '..' reached a listed repo through a traversal and was credited to nobody:
  exists walks the traversal and is_relative_to reads the text, so the two halves of the rule
  disagreed about where the path was. Both sides now flatten lexically.

A registry entry naming no path was dropped where nothing could count it. Six entries of which four
  are unusable swept two repos and printed a tick. They now travel to the result and get a row
  beside the retired and the absent.

Four things stop a repo owning a gone path and only two of them printed, so a tick could not be told
  from 'the repo the file left was not in the map'. All four get a row, and where the repo the run
  is standing in is itself unlisted the sweep says so — nothing it finds could be credited to those
  renames.

- **sweep**: Narrow every repo by the same filters as the local run
  ([`637ac9a`](https://github.com/datapointchris/refcheck/commit/637ac9af1b504105e181c569886e5b8dc7bdea8f))

--type, --test-mode and --exclude reached the tree refcheck was standing in and stopped there, so
  --type py --registry read every file in ninety repos. A flag reaching part of the work and
  silently not the rest is the failure a narrowing flag has, because it is designed against the case
  it was invented for and the case it cannot answer is the one nobody looks at.

Each repo still reads its own declared exclusions, with the flag's added on top. Which of a repo's
  directories hold generated output is a fact only that repo knows, and it stays that way across
  ninety of them.

### Chores

- Sync the generated configs to toolchain 18
  ([`a5fd8eb`](https://github.com/datapointchris/refcheck/commit/a5fd8eb7c3db88a03aa0156943b1a5ecd5c6326b))

Both stamped files come from the fleet's version declaration: the pre-commit config and the
  generated workflow. Nothing here is a repo decision.

Stamp 18 carries the refcheck hook at v0.6.0, a codespell exclude widened to go.mod, and — on a
  private repo — runs-on naming the self-hosted pool with the actionlint config that declares the
  label.

- Sync the generated configs to toolchain 19
  ([`cf7a48b`](https://github.com/datapointchris/refcheck/commit/cf7a48bad76ca35af63e479843a26af2e6b98dd0))

Both stamped files come from the fleet's version declaration: the pre-commit config and the
  generated workflow. Nothing here is a repo decision.

Stamp 19 passes --allow-parallel-runners to golangci-lint. A repo with two Go components runs two
  Lint jobs at once, and on a single self-hosted box the second one dies on the shared cache lock
  before linting anything.

- **precommit**: Drop the commit-branding hook
  ([`9df2718`](https://github.com/datapointchris/refcheck/commit/9df2718ac41346259af01af9e6a2eec7e7a01d84))

Claude Code suppresses its own commit and PR attribution through its attribution setting, which
  resolves an empty string to no trailer at all. A hook that strips the trailer afterwards has
  nothing left to remove.

### Features

- **sweep**: Check every repo a registry lists for a path that moved
  ([`e9beb97`](https://github.com/datapointchris/refcheck/commit/e9beb978c2fbea1ac55b0c49921cf0b07e4ba618))

A rename is answerable in the repo that made it and unanswerable everywhere else. --moves reads
  git's own rename history and can only ask the tree it is standing in, so a consumer in another
  repo keeps a path that no longer resolves and nothing ever looks at it.

--registry names the repos to ask. The caller hands the path over and refcheck never goes looking
  for one, because a check resolving its own subject measures whatever the environment answers at
  that moment.

The reporting rule is what makes a pattern as loose as a basename safe. A reference from one repo
  into another cannot be relative, so the token is expanded and the answer comes from the
  filesystem: a hit counts only when the path it names sits inside a listed repo and is not there.
  Six registry files renamed at a repo root hit 152 lines across 90 repos on the bare basename; the
  rule reports none of them and reports the one reference that had broken. A sweep of 90 repos costs
  about 14 seconds for six moved paths.

Two defects blocked it and are fixed here.

A '~'-rooted token was joined to the repo root, which builds a path that cannot exist, so every
  corrected cross-repo reference came back as a hit. Expansion is tried first and never on its own,
  leaving the root-relative candidates to answer for a variable pointing elsewhere.

The binary sniff opened a repo-relative path from the working directory, so scanning a repo you are
  not standing in read 'not binary' off the OSError and pattern-matched a 30 MB executable as text.
  Anchoring it at the root cut the sweep from 54 seconds to 14.

Bare filenames stay out of the in-repo check and are asked for by the sweep, where an absolute path
  settles them without the pattern carrying any weight.

- **sweep**: Check every repo a registry lists for a path that moved
  ([#1](https://github.com/datapointchris/refcheck/pull/1),
  [`8f2f956`](https://github.com/datapointchris/refcheck/commit/8f2f956bf85f25b7c8e40c28d95fb9fc922cefee))

A rename is answerable in the repo that made it and unanswerable everywhere else. `--moves` reads
  git's own rename history and can only ask the tree it is standing in, so a consumer in another
  repo keeps a path that no longer resolves and nothing ever looks at it. `--registry` names the
  repos to ask, and the same rename history drives the sweep.

## What to look at

`refcheck/checker.py` — `_reaches_a_gone_path_in` is the reporting rule and the reason this is
  shippable at all. A basename swept over 90 repos is far too loose as a string match, so the rule
  is not a string match: the token is expanded through `~` and the environment, and a hit counts
  only when the absolute path it names sits inside a listed repo and is not on disk. Check that a
  token which cannot be expanded, or which reaches no listed repo, falls out.

`refcheck/checker.py` — `_path_tokens_around` is extracted from `_pattern_hit_still_resolves`, which
  it now shares with the rule above. The URL guard and the begins-the-token case moved with it;
  check they still read the same in the old caller.

`refcheck/checker.py` — the `_on_this_filesystem` branch inside `_pattern_hit_still_resolves` is
  tried first and deliberately falls through on a miss. A short-circuiting version passes every test
  in this diff except `test_pattern_falls_back_when_a_variable_points_somewhere_else`, and
  introduces a false positive on a corrected reference behind a variable pointing elsewhere.

`refcheck/suggestions.py` — one line, and it is the performance and correctness fix. Check the
  argument really is repo-relative at every call site.

`refcheck/registry.py` — two document shapes are accepted. Check the refusals distinguish an
  unreadable file, malformed JSON, no `repos` list, and an empty one.

`refcheck/sweep.py` — check that an empty pattern set returns before any repo is walked, and that a
  repo is counted as scanned only if it was.

`refcheck/moves.py` — `include_bare_names` defaults to false, so the in-repo check is unchanged.
  `cli.py` reads git once with it true and filters for the local pass.

`637ac9a` — `--type`, `--test-mode` and `--exclude` reached the local run and stopped there. Check
  that a repo's own `.refcheck.toml` still applies underneath the flag's excludes rather than being
  replaced by them.

`34870af` — `sweep.py` now builds the ownership map from every listed repo on disk and the walk list
  from the swept ones. Check the two are genuinely different sets and that absent repos stay out of
  both.

## How it was verified

`uv run pytest` — 173 passed, up from 120.

Each new behaviour was proved able to fail, by reverting its fix and re-running:

- reverting the `~` expansion fails `test_pattern_expands_a_home_rooted_token_before_resolving_it` -
  short-circuiting it instead of falling through fails
  `test_pattern_falls_back_when_a_variable_points_somewhere_else` - reverting the binary-check
  anchor fails `test_pattern_skips_a_binary_in_a_repo_that_is_not_the_working_directory` - restoring
  the bare-name filter makes `test_reports_a_consumer_left_holding_the_old_path` report `0 moved
  path(s)`, which is exactly the failure this feature exists to fix - dropping the filters from the
  sweep's checkers fails `test_file_type_reaches_the_sweep` and
  `test_an_exclude_glob_reaches_the_sweep` - building the ownership map from the walk list fails
  `test_a_reference_into_a_retired_repo_is_still_reported` - building it from every listed repo
  regardless of disk fails `test_a_reference_into_a_repo_this_machine_lacks_is_not_reported` -
  removing the lexical flattening fails `test_a_traversal_still_lands_inside_the_repo_it_names`

Measured against a real 93-repo registry, sweeping six registry files renamed at a repo root —
  `tools.json`, `versions.json`, `stores.json`, `hosts.json`, `machines.json`, `schedule.json`.
  Through `main`'s checker those six return 149 hits across 7 of 90 repos, none of them a stale
  cross-repo reference. The rule in this diff returns 0. Reconstructing one consumer holding
  `~/<store>/versions.json` against the real store, where only `pinned-versions.json` is present,
  returns exactly that one hit and credits it to the repo the file left.

Cost of one sweep of 90 repos: 12.5s for one moved path, 14.0s for six as the median of three runs,
  19.3s for thirty. `main`'s checker takes 54.6s over the same six. A run with no moved path reads
  no files and returns in under 0.01s.

## What changes

`--registry PATH` is new and composes with `--moves`, `--moves-since` and `--pattern`. Without one
  of those three it exits 2 rather than walking every listed repo to ask it nothing.

A stale reference found in any swept repo exits 1, the same as a local finding.

Retired repos are not walked, on the grounds that a finding in one will not be fixed. Dormant ones
  are. A retired repo can still own a gone path, though — a live repo holding a path into one still
  holds a path that does not resolve, and the fix is in the live repo.

Four things stop a repo owning a gone path and each gets its own row: never listed, listed but
  unreadable, listed and retired, listed and not on disk. Where the repo the run is standing in is
  itself unlisted, the sweep says so on its own line, because nothing it finds can be credited to
  the renames just made.

`--type`, `--skip-docs`, `--test-mode` and `--exclude` narrow the sweep as well as the local run.
  Each swept repo still reads its own `.refcheck.toml`, with `--exclude` added on top.

Sweep findings print absolute paths. Every other refcheck run prints relative to the tree you are
  standing in, and this one stands in none of them.

Two existing behaviours change outside the sweep. A `~`-rooted or variable-rooted path token in any
  `--pattern` run is now expanded and tested against the filesystem before the root-relative
  fallback, so a corrected reference into another repo stops being reported. And the binary-content
  check is anchored at the root being scanned, so `refcheck <other-dir>` no longer reads binaries in
  that directory as text — which is where the 54s to 14s came from.

## Decisions, and what they rejected

- **The reporting rule is filesystem existence, not pattern shape** — a reference from one repo into
  another cannot be relative, because the file is not in that tree. That makes a basename safe to
  sweep on. *Rejected*: requiring the pattern to carry a directory, which is the in-repo rule and
  yields nothing for a file renamed at a repo root. *Rejected*: substituting the new name into the
  token and requiring the result to exist, which proves a rename but says nothing about a deletion.

- **Bare names are filtered in-repo and asked for by the sweep** — the two runs have different
  evidence available, so they get different filters. In the renaming repo a bare name is a substring
  with nothing behind it; across repos an absolute path settles it.

- **The registry is a parameter, never resolved** — a check that resolves its own subject measures
  whatever the environment answers, and one machine's registry lists a different set of repos from
  another's.

- **Retired repos are skipped and visibility is ignored** — a private repo's broken reference is as
  broken as a public one's, while a retired repo's will not be fixed. Measured on the real registry,
  retired repos produced no hits either way, so this is a rule about what a finding is worth rather
  than a measured noise reduction.

- **`--registry` with no moved path is exit 2** — validating another repo's `source` statements is
  that repo's own run, so there is nothing for the flag to mean on its own.

- **The walk list and the ownership map are different sets** — one answers where a fix would land
  and the other where files live, and conflating them dropped every reference into a retired repo.
  *Rejected*: sweeping retired repos too, which would report findings nobody will act on.

- **Traversals are flattened lexically, not resolved** — `os.path.normpath` makes the containment
  test agree with the existence test beside it. *Rejected*: `Path.resolve`, which follows symlinks
  and would move a repo out of the home the registry declared for it.

## What this does not do

Deletions are swept on the same rule as renames, so a deleted file is found only where a consumer
  names it by a path inside a listed repo. A consumer naming it through a deployed path outside
  every listed repo is not reached.

A reference behind a variable this process does not carry is not expanded and so is not swept. It is
  silently not-found rather than reported, which is the safe direction but is a real gap.

Containment is lexical, so a repo reached through a symlinked parent is not credited.
  `~/link/versions.json` where `link` points into a listed repo names a real file in that repo and
  the sweep places it outside every one of them. Same safe direction, same real gap.

Nothing validates that a *deployed* config path still resolves. A registry entry's path is the
  checkout, and a file deployed elsewhere from it is out of scope here.

## The review

https://github.com/datapointchris/refcheck/pull/1#pullrequestreview-5026620675 — 2 correctness, 1
  breaks a rule, 0 rules proposed, 1 design.

Correctness: 1. fixed — `34870af` 2. fixed — `34870af`

Breaks a written rule: 1. fixed — `34870af`

Design: 1. fixed — `34870af`


## v0.6.0 (2026-08-24)

### Chores

- **pyproject**: Raise assertion verbosity instead of test verbosity
  ([`04cbed1`](https://github.com/datapointchris/refcheck/commit/04cbed15d626a758abbe756f724a387087dcd5c3))

A failing assertion truncated its diff and printed "use -vv to show", so the reader re-ran the whole
  suite to see it. addopts = "-vv" answered that by raising test-list verbosity as well, which is a
  different question: a green run printed a line per test and said nothing. verbosity_assertions
  raises only the half that was wanted.

Written by the forge pyproject die.

### Continuous Integration

- Regenerate validate.yml at toolchain 16
  ([`744c13c`](https://github.com/datapointchris/refcheck/commit/744c13c2f7357092b8c5df75679546c90bb66cdc))

Catches this repo up with the version manifest: StyLua pinned to a release rather than latest, a
  reworded bats discovery note, and double quotes in the node block. Only the blocks this repo
  declares are affected.

Triggers and job structure are unchanged.

### Features

- Let a repo declare which of its paths hold generated output
  ([`2813b79`](https://github.com/datapointchris/refcheck/commit/2813b798285a5b27ac67f6ab3dcbd505dad6597b))

The built-in exclusions cover what holds for any repository: logs, changelogs, tool caches. Which of
  a given repo's directories hold generated output is a fact only that repo knows, and a file a tool
  wrote names what a path was when it ran, so a hit inside one is history rather than a stale
  reference. Hardcoding one repo's layout would put private structure in the tool and still miss the
  next repo.

A repo declares its own in .refcheck.toml at the root:

[scan] exclude = ["build/reports/**"]

Patterns add to the built-in list rather than replacing it. Discovery walks up from the repo root
  and stops there, so a checkout does not inherit the config of whatever encloses it.

--exclude adds a pattern for a single run without declaring it. --show-config prints every exclusion
  in force with the layer that set it.

The per-user config path now resolves through XDG_CONFIG_HOME instead of a hardcoded ~/.config, and
  the filtering section of the README names the tool caches it was already excluding.


## v0.5.2 (2026-08-14)

### Bug Fixes

- Look for a tilde path under home, not under the repo
  ([`c1f7447`](https://github.com/datapointchris/refcheck/commit/c1f7447dfb323fd8049f0bb6030240a5dae18dd8))

A `~/` reference is neither absolute nor repo-relative, and it was treated as the second — joined
  onto the repo root to produce `<repo>/~/…`, which cannot exist for any input. So every tilde
  reference was reported missing on every run, whether or not it resolved.

Measured on dotfiles: tests/apps/all-apps.sh sources three deployed shell libraries by their
  ~/.local/shell/ paths. All three resolve. All three were reported, on every commit, for as long as
  the hook has run. That is this tool spending its entire value on noise — it is worth exactly its
  false-positive rate, and three standing errors is what teaches a reader to skim past the findings
  that are real.

Three anchors now, in one helper rather than the branch written twice. The tilde spelling is the
  *deployed* one, which is what a script running outside the repo has to use, so it is not a variant
  of a repo-relative path and cannot be rewritten into one.

Not skipped as machine state, which is how DYNAMIC_PATH_PATTERNS treats /home/ and /Users/. Those
  describe a filesystem this process did not create; ~/.local/shell/logging.sh is deployed by the
  repo being checked, so it is exactly the kind of reference this exists to validate. Skipping would
  have cleared the noise the same way and caught nothing.

The test that matters is the one on a tilde path that is not there. A false-positive fix and a
  blindness look identical on paths that resolve.


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
