"""Shared fixtures for refcheck tests."""

import json
import subprocess
import tempfile
from pathlib import Path

import pytest


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

    (src / 'self-ref.sh').write_text('#!/usr/bin/env bash\n# Usage: bash self-ref.sh\necho "Self-referencing file"\n')

    valid = temp_dir / 'valid'
    valid.mkdir()
    (valid / 'clean.sh').write_text('#!/usr/bin/env bash\necho "No source or bash commands"\necho "Just plain shell script"\n')

    (valid / 'filename-list.sh').write_text('#!/usr/bin/env bash\nfor f in functions.sh aliases.sh; do\n  echo "$f"\ndone\n')

    (valid / 'remote-exec.sh').write_text(
        '#!/usr/bin/env bash\n'
        'pct exec 100 -- su - chris -c "cd ~/dotfiles && bash install.sh"\n'
        'ssh chris@10.0.0.1 bash /opt/remote-only.sh\n'
    )

    lib = valid / 'lib'
    lib.mkdir()
    (lib / 'helpers.sh').write_text('#!/usr/bin/env bash\necho "helpers"\n')
    (valid / 'documented-usage.sh').write_text(
        '#!/usr/bin/env bash\n# Usage:\n#   source valid/lib/helpers.sh\necho "the source above is documentation"\n'
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
    """Get the dotfiles directory for real-world tests."""
    result = subprocess.run(
        ['git', 'rev-parse', '--show-toplevel'],
        capture_output=True,
        text=True,
        cwd=Path.home() / 'dotfiles',
    )
    if result.returncode == 0:
        return Path(result.stdout.strip())
    return None
