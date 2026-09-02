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

    (valid / 'remote-exec.sh').write_text(
        '#!/usr/bin/env bash\n'
        'pct exec 100 -- su - deploy -c "cd ~/dotfiles && bash install.sh"\n'
        'ssh deploy@build-host bash /opt/remote-only.sh\n'
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
def dotfiles_dir():
    """The dotfiles repo, or None where it is not checked out.

    The existence check has to come first: subprocess raises rather than
    returning non-zero when `cwd` does not exist, so without it the None branch
    below is unreachable and every real-world test errors instead of skipping
    on a machine without ~/dotfiles — which is every CI runner.
    """
    repo = Path.home() / 'dotfiles'
    if not repo.is_dir():
        return None

    result = subprocess.run(
        ['git', 'rev-parse', '--show-toplevel'],
        capture_output=True,
        text=True,
        cwd=repo,
    )
    if result.returncode == 0:
        return Path(result.stdout.strip())
    return None
