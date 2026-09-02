"""Shared fixtures for refcheck tests."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(scope='session', autouse=True)
def detached_from_the_calling_git():
    """Hide any inherited git environment from every subprocess a test spawns.

    Git exports GIT_DIR and GIT_INDEX_FILE to the hooks it runs, and this suite
    is one of them — it runs under pre-commit. Those two beat directory
    discovery, so `git init` in a fixture's temp directory reinitialized the
    *real* repository and never created a `.git` in the temp directory at all,
    and the `git add` that followed wrote the fixture's files into the real
    index. Measured on a clone: 29 tracked files replaced by a single .gitkeep,
    and the commit that ran the hook then died with `invalid object ... for
    '.gitkeep'` because the blob had gone to a directory that no longer existed.

    Stripping the whole GIT_ prefix rather than the two known offenders is
    deliberate: GIT_WORK_TREE, GIT_OBJECT_DIRECTORY and GIT_COMMON_DIR redirect
    the same operations, and the fixtures supply every setting they need.
    """
    inherited = {name: value for name, value in os.environ.items() if name.startswith('GIT_')}
    for name in inherited:
        del os.environ[name]
    yield
    os.environ.update(inherited)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_git_repo(temp_dir):
    """Create a temporary git repository."""
    subprocess.run(['git', 'init'], cwd=temp_dir, capture_output=True, check=True)
    subprocess.run(
        ['git', 'config', 'user.email', 'test@test.com'],
        cwd=temp_dir,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ['git', 'config', 'user.name', 'Test'],
        cwd=temp_dir,
        capture_output=True,
        check=True,
    )
    (temp_dir / '.gitkeep').touch()
    subprocess.run(['git', 'add', '.'], cwd=temp_dir, capture_output=True, check=True)
    subprocess.run(
        ['git', 'commit', '-m', 'Initial commit'],
        cwd=temp_dir,
        capture_output=True,
        check=True,
    )
    yield temp_dir


@pytest.fixture
def test_fixtures(temp_dir):
    """Create standard test fixtures matching bash tests."""
    src = temp_dir / 'src'
    docs = temp_dir / 'docs'
    src.mkdir()
    docs.mkdir()

    (src / 'good.sh').write_text(
        '#!/usr/bin/env bash\n'
        'source "$DOTFILES_DIR/platforms/common/.local/shell/logging.sh"\n'
        'bash "$DOTFILES_DIR/install.sh"\n'
        'echo "This file has valid references"\n'
    )

    (src / 'broken-source.sh').write_text('#!/usr/bin/env bash\nsource "/nonexistent/file.sh"\necho "This has a broken source"\n')

    (src / 'broken-script.sh').write_text('#!/usr/bin/env bash\nbash /nonexistent/script.sh\necho "This has a broken script reference"\n')

    (src / 'old-pattern.sh').write_text(
        '#!/usr/bin/env bash\n# Reference to old path: management/tests/verify.sh\necho "Has old pattern"\n'
    )

    (docs / 'readme.md').write_text('# Documentation\nReference to management/tests/ in docs\n')

    # docs/ is asserted clean by TestDirectoryFiltering, so prose that is meant
    # to fail lives in its own directory.
    stale_docs = temp_dir / 'stale-docs'
    stale_docs.mkdir()
    (stale_docs / 'stale-source.md').write_text(
        '# Architecture\n\nEvery installer starts with:\n\n```bash\nsource "$DOTFILES_DIR/valid/gone.sh"\nbash valid/also-gone.sh\n```\n'
    )

    (docs / 'placeholders.md').write_text(
        '# Adding an installer\n\n'
        'Create the file, then:\n\n'
        '```bash\n'
        'bash install/github-releases/toolname.sh\n'
        'bash install/plugins/{tool}-plugins.sh\n'
        'source "$DOTFILES_DIR/shell/my-library.sh"\n'
        'bash script.sh\n'
        '```\n'
    )

    (docs / 'live-source.md').write_text('# Using the helpers\n\n```bash\nsource "$DOTFILES_DIR/valid/lib/helpers.sh"\n```\n')

    (docs / 'other-trees.md').write_text(
        '# Shell semantics\n\n'
        '```bash\n'
        'source child.sh\n'
        'bash ./test/mylib_test.sh\n'
        '```\n\n'
        '```hcl\n'
        'resource "aws_lambda_function" "notifier" {}\n'
        '```\n\n'
        '```bash file=nowhere/deploy.sh\n'
        'echo hi\n'
        '```\n\n'
        'Newsboat config: `urls-source "freshrss"`\n'
    )

    # A rename inside a directory the repo still has stays reportable — that is
    # the case describes_another_tree must not swallow.
    (stale_docs / 'renamed-dir.md').write_text('# Tests\n\n```bash\nbash valid/gone/runner.sh\n```\n')

    (src / 'self-ref.sh').write_text('#!/usr/bin/env bash\n# Usage: bash self-ref.sh\necho "Self-referencing file"\n')

    valid = temp_dir / 'valid'
    valid.mkdir()
    (valid / 'clean.sh').write_text('#!/usr/bin/env bash\necho "No source or bash commands"\necho "Just plain shell script"\n')

    (valid / 'filename-list.sh').write_text('#!/usr/bin/env bash\nfor f in functions.sh aliases.sh; do\n  echo "$f"\ndone\n')

    # One line per REMOTE_EXECUTION_PATTERNS entry, each naming a path that is
    # not here. Sharing a line between two patterns hides the second: whichever
    # matches first is the reason the line passes, so the other can be deleted
    # with the suite still green.
    (valid / 'remote-exec.sh').write_text(
        '#!/usr/bin/env bash\n'
        'pct exec 100 -- bash /opt/container-only.sh\n'
        'lxc exec web -- bash /opt/lxc-only.sh\n'
        'docker exec api bash /opt/docker-only.sh\n'
        'kubectl exec worker -- bash /opt/kube-only.sh\n'
        'ssh deploy@build-host bash /opt/remote-only.sh\n'
        'su - deploy -c "bash /opt/other-user-only.sh"\n'
    )

    lib = valid / 'lib'
    lib.mkdir()
    (lib / 'helpers.sh').write_text('#!/usr/bin/env bash\necho "helpers"\n')
    (valid / 'documented-usage.sh').write_text(
        '#!/usr/bin/env bash\n# Usage:\n#   source valid/lib/helpers.sh\necho "the source above is documentation"\n'
    )

    # The two shapes that reported seven misses from a single file: a header
    # block illustrating invocations, and a usage function echoing them back.
    # Neither names anything meant to exist here.
    (valid / 'documented-invocations.sh').write_text(
        '#!/usr/bin/env bash\n'
        '# Examples:\n'
        '#   bash install.sh\n'
        '#   ✅ CORRECT: bash management/run-and-summarize.sh "task install"\n'
        '#   source shell/lib.sh\n'
        'echo "  bash install.sh"\n'
        'printf "usage: bash management/run-and-summarize.sh <command>\\n"\n'
    )

    # The same two contexts naming a directory this repo has. Documentation goes
    # stale exactly the way code does, so these stay reportable — widening the
    # guard must not become a blanket skip of comments and echoes.
    (stale_docs / 'documented-stale.sh').write_text(
        '#!/usr/bin/env bash\n#   bash valid/gone/runner.sh\necho "then run: bash valid/gone/runner.sh"\n'
    )

    return temp_dir


@pytest.fixture
def suggestion_fixtures(temp_dir):
    """Create fixtures for suggestion tests."""
    suggestions = temp_dir / 'suggestions'
    suggestions.mkdir()

    (suggestions / 'update.sh').touch()
    (suggestions / 'update_helper.sh').touch()
    (suggestions / 'my-script.sh').touch()

    (suggestions / 'broken-with-similar.sh').write_text('#!/usr/bin/env bash\nbash nonexistent/update.sh\n')

    (suggestions / 'broken-variant.sh').write_text('#!/usr/bin/env bash\nbash nonexistent/my_script.sh\n')

    return temp_dir


@pytest.fixture
def config_dir(temp_dir, monkeypatch):
    """Create a temporary config directory."""
    config_path = temp_dir / '.config' / 'refcheck'
    config_path.mkdir(parents=True)
    monkeypatch.setenv('HOME', str(temp_dir))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(temp_dir / '.config'))
    return config_path


@pytest.fixture
def rules_file(config_dir):
    """Create a rules file for testing."""
    from datetime import datetime

    repos_dir = config_dir / 'repos' / 'test-repo'
    repos_dir.mkdir(parents=True)
    rules_path = repos_dir / 'rules.json'

    rules = {
        '_metadata': {
            'generated': datetime.now().isoformat()[:19],
            'time_window': '6 months',
            'commits_analyzed': 10,
        },
        'directory_mappings': {'old/path/': 'new/path/'},
        'file_mappings': {'old-file.sh': 'new-file.sh'},
    }

    rules_path.write_text(json.dumps(rules, indent=2))
    return rules_path


@pytest.fixture
def deployed_repo(tmp_path, monkeypatch):
    """A git repository shaped like one refcheck is pointed at in anger.

    Built here rather than read off the machine. Seven tests used to run
    against whatever `~/dotfiles` happened to hold, which made the suite's
    result a property of the machine — green where that directory existed,
    skipped where it did not, and red whenever a tree this repository does not
    control grew a stale reference of its own.

    It carries what those seven need and nothing else: a clean shell directory,
    a fixtures directory holding a reference that does not resolve, and a
    rename in its history for `learn-rules` to read. HOME points at `tmp_path`
    so the rules file lands under the test's own directory instead of the
    caller's config.
    """
    monkeypatch.setenv('HOME', str(tmp_path))
    repo = tmp_path / 'deployed'
    (repo / 'apps').mkdir(parents=True)
    (repo / 'shell').mkdir()

    def git(*args):
        subprocess.run(['git', *args], cwd=repo, capture_output=True, check=True)

    git('init')
    git('config', 'user.email', 'test@test.com')
    git('config', 'user.name', 'Test')

    (repo / 'shell' / 'logging.sh').write_text('#!/usr/bin/env bash\necho "logging"\n')
    (repo / 'apps' / 'run.sh').write_text('#!/usr/bin/env bash\nsource "$DOTFILES_DIR/shell/logging.sh"\n')
    git('add', '-A')
    git('commit', '-m', 'add the shell library')

    # A rename in the history is the whole input to learn-rules, so a fixture
    # without one exercises the command and asserts on an empty result.
    git('mv', 'shell/logging.sh', 'shell/log.sh')
    (repo / 'apps' / 'run.sh').write_text('#!/usr/bin/env bash\nsource "$DOTFILES_DIR/shell/log.sh"\n')
    git('add', '-A')
    git('commit', '-m', 'rename the shell library')

    # Under fixtures/ on purpose: it is excluded by default, so reaching it at
    # all is what --test-mode is for.
    variables = repo / 'tests' / 'fixtures' / 'variables'
    variables.mkdir(parents=True)
    (variables / 'broken.sh').write_text(
        '#!/usr/bin/env bash\nSCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\nsource "$SCRIPT_DIR/absent-helper.sh"\n'
    )

    return repo
