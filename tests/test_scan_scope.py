"""Which files a scan reads."""

from pathlib import Path

import pytest

from refcheck.scan_scope import ScanScope


@pytest.fixture
def scope(temp_dir):
    return ScanScope(root_dir=temp_dir, exclude_dirs={'.git', 'node_modules'}, exclude_patterns=[])


def test_an_excluded_directory_name_excludes_every_file_under_it(scope):
    assert scope.should_skip_file(Path('.git/config'))
    assert scope.should_skip_file(Path('node_modules/package/index.js'))
    assert not scope.should_skip_file(Path('src/main.py'))


def test_subtree_patterns_reach_every_depth(temp_dir):
    """Path.match reads `**` as one component, so a subtree two levels down needs fnmatch to match."""
    scope = ScanScope(root_dir=temp_dir, exclude_dirs=set(), exclude_patterns=['build/reports/**', '**/fixtures/**'])
    assert scope.should_skip_file(Path('build/reports/top.json'))
    assert scope.should_skip_file(Path('build/reports/a/b.json'))
    assert scope.should_skip_file(Path('build/reports/a/deep/nested.json'))
    assert scope.should_skip_file(Path('tests/stats/fixtures/tool_outputs/tokei.json'))
    assert not scope.should_skip_file(Path('mybuild/reports/notes.md'))
    assert not scope.should_skip_file(Path('src/main.py'))


def test_bare_filename_patterns_match_at_any_depth(temp_dir):
    scope = ScanScope(root_dir=temp_dir, exclude_dirs=set(), exclude_patterns=['CHANGELOG.md', '*.log'])
    assert scope.should_skip_file(Path('CHANGELOG.md'))
    assert scope.should_skip_file(Path('docs/CHANGELOG.md'))
    assert scope.should_skip_file(Path('run/deep/output.log'))
    assert not scope.should_skip_file(Path('docs/changes.md'))


def test_binary_suffixes_are_skipped_without_opening_the_file(scope):
    assert scope.should_skip_file(Path('lib/module.so'))
    assert scope.should_skip_file(Path('build/app.o'))
    assert scope.should_skip_file(Path('lib/lib.dylib'))


def test_binary_content_is_skipped_whatever_the_extension(temp_dir, scope):
    """A multi-gigabyte SQLite database with no telling suffix produced 29 of 31 hits for one --pattern query."""
    (temp_dir / 'index.db').write_bytes(b'SQLite format 3\x00' + b'\x01\x02\x03' * 100)
    (temp_dir / 'notes.md').write_text('# Notes\n\nA reference to src/main.py.\n')

    assert scope.should_skip_file(Path('index.db'))
    assert not scope.should_skip_file(Path('notes.md'))


def test_a_missing_file_is_not_treated_as_binary(scope):
    assert not scope.should_skip_file(Path('does-not-exist.md'))
