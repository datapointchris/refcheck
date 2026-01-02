"""Tests for suggestions module."""

from pathlib import Path

import pytest

from refcheck.suggestions import FileSuggestions


class TestFileSuggestions:
    """Tests for FileSuggestions class."""

    @pytest.fixture
    def suggestions(self, temp_dir):
        return FileSuggestions(
            root_dir=temp_dir,
            exclude_dirs={".git", "node_modules"},
            exclude_patterns=["*.pyc"],
        )

    def test_should_skip_file_excludes_dirs(self, suggestions):
        assert suggestions.should_skip_file(Path(".git/config"))
        assert suggestions.should_skip_file(Path("node_modules/package/index.js"))
        assert not suggestions.should_skip_file(Path("src/main.py"))

    def test_should_skip_file_excludes_patterns(self, suggestions):
        assert suggestions.should_skip_file(Path("src/main.pyc"))
        assert not suggestions.should_skip_file(Path("src/main.py"))

    def test_should_skip_file_excludes_binary_extensions(self, suggestions):
        assert suggestions.should_skip_file(Path("lib/module.so"))
        assert suggestions.should_skip_file(Path("build/app.o"))
        assert suggestions.should_skip_file(Path("lib/lib.dylib"))

    def test_build_file_index(self, temp_dir, suggestions):
        (temp_dir / "src").mkdir()
        (temp_dir / "src" / "main.py").touch()
        (temp_dir / "src" / "utils.py").touch()
        (temp_dir / "README.md").touch()

        index = suggestions.build_file_index()

        assert Path("src/main.py") in index
        assert Path("src/utils.py") in index
        assert Path("README.md") in index

    def test_build_file_index_caches(self, temp_dir, suggestions):
        (temp_dir / "file.txt").touch()

        index1 = suggestions.build_file_index()
        index2 = suggestions.build_file_index()

        assert index1 is index2

    def test_find_similar_files_basename_match(self, temp_dir, suggestions):
        (temp_dir / "lib").mkdir()
        (temp_dir / "lib" / "utils.sh").touch()

        similar = suggestions.find_similar_files("old/path/utils.sh", {})

        assert any("utils.sh" in s and "basename match" in s for s in similar)

    def test_find_similar_files_name_variant(self, temp_dir, suggestions):
        (temp_dir / "my-script.sh").touch()

        similar = suggestions.find_similar_files("my_script.sh", {})

        assert any("my-script.sh" in s and "name variant" in s for s in similar)

    def test_find_similar_files_underscore_to_hyphen(self, temp_dir, suggestions):
        (temp_dir / "some_file.py").touch()

        similar = suggestions.find_similar_files("some-file.py", {})

        assert any("some_file.py" in s and "name variant" in s for s in similar)

    def test_find_similar_files_directory_mapping(self, temp_dir, suggestions):
        (temp_dir / "new" / "path").mkdir(parents=True)
        (temp_dir / "new" / "path" / "script.sh").touch()

        rules = {"directory_mappings": {"old/path/": "new/path/"}}
        similar = suggestions.find_similar_files("old/path/script.sh", rules)

        assert any("new/path/script.sh" in s and "known mapping" in s for s in similar)

    def test_find_similar_files_file_mapping(self, temp_dir, suggestions):
        (temp_dir / "new-name.sh").touch()

        rules = {"file_mappings": {"old-name.sh": "new-name.sh"}}
        similar = suggestions.find_similar_files("path/old-name.sh", rules)

        assert any("new-name.sh" in s and "known mapping" in s for s in similar)

    def test_find_similar_files_limits_results(self, temp_dir, suggestions):
        for i in range(10):
            (temp_dir / f"update{i}.sh").touch()

        similar = suggestions.find_similar_files("update.sh", {})

        assert len(similar) <= 5
