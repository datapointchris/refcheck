"""Tests for reading the repo registry the caller names."""

import json

import pytest

from refcheck import registry


def write(path, document):
    path.write_text(json.dumps(document))
    return path


class TestShapes:
    """Both registry layouts in use are read the same way."""

    def test_reads_an_object_holding_repos(self, temp_dir):
        (temp_dir / 'a').mkdir()
        path = write(temp_dir / 'reg.json', {'repos': [{'name': 'a', 'path': str(temp_dir / 'a'), 'status': 'active'}]})

        repos = registry.load(path)

        assert [repo.name for repo in repos] == ['a']
        assert repos[0].path == temp_dir / 'a'

    def test_reads_a_bare_array(self, temp_dir):
        path = write(temp_dir / 'reg.json', [{'name': 'a', 'path': str(temp_dir / 'a'), 'status': 'active'}])

        assert [repo.name for repo in registry.load(path)] == ['a']

    def test_expands_a_home_relative_path(self, temp_dir, monkeypatch):
        monkeypatch.setenv('HOME', str(temp_dir))
        path = write(temp_dir / 'reg.json', {'repos': [{'name': 'a', 'path': '~/a'}]})

        assert registry.load(path)[0].path == temp_dir / 'a'

    def test_falls_back_to_the_directory_name(self, temp_dir):
        path = write(temp_dir / 'reg.json', {'repos': [{'path': str(temp_dir / 'unnamed')}]})

        assert registry.load(path)[0].name == 'unnamed'


class TestExcludePaths:
    """The registry's own declaration of what it keeps but does not own."""

    def test_drops_a_repo_under_an_excluded_path(self, temp_dir):
        path = write(
            temp_dir / 'reg.json',
            {
                'exclude_paths': [str(temp_dir / 'refs')],
                'repos': [
                    {'name': 'mine', 'path': str(temp_dir / 'mine')},
                    {'name': 'vuetify', 'path': str(temp_dir / 'refs' / 'vuetify')},
                ],
            },
        )

        assert [repo.name for repo in registry.load(path)] == ['mine']

    def test_drops_the_excluded_path_itself(self, temp_dir):
        path = write(
            temp_dir / 'reg.json',
            {
                'exclude_paths': [str(temp_dir / 'refs')],
                'repos': [{'name': 'refs', 'path': str(temp_dir / 'refs')}, {'name': 'mine', 'path': str(temp_dir / 'mine')}],
            },
        )

        assert [repo.name for repo in registry.load(path)] == ['mine']


class TestRefusals:
    """A registry that is not one says so rather than sweeping nothing."""

    def test_missing_file(self, temp_dir):
        with pytest.raises(registry.RegistryError, match='cannot read'):
            registry.load(temp_dir / 'absent.json')

    def test_invalid_json(self, temp_dir):
        (temp_dir / 'reg.json').write_text('{not json')

        with pytest.raises(registry.RegistryError, match='not valid JSON'):
            registry.load(temp_dir / 'reg.json')

    def test_no_list_of_repos(self, temp_dir):
        path = write(temp_dir / 'reg.json', {'owner': 'someone'})

        with pytest.raises(registry.RegistryError, match='no list of repos'):
            registry.load(path)

    def test_an_empty_list_is_refused(self, temp_dir):
        """A sweep over zero repos would report a clean machine it never read."""
        path = write(temp_dir / 'reg.json', {'repos': []})

        with pytest.raises(registry.RegistryError, match='names no repos'):
            registry.load(path)

    def test_an_entry_with_no_path_is_dropped(self, temp_dir):
        path = write(temp_dir / 'reg.json', {'repos': [{'name': 'a'}, {'name': 'b', 'path': str(temp_dir / 'b')}]})

        assert [repo.name for repo in registry.load(path)] == ['b']


class TestWhatIsSwept:
    def test_retired_is_left_out(self, temp_dir):
        assert not registry.Repo(name='a', path=temp_dir, status='retired').is_swept

    def test_dormant_is_swept(self, temp_dir):
        """Dormant work gets picked up; a reference that broke while it was quiet is the point."""
        assert registry.Repo(name='a', path=temp_dir, status='dormant').is_swept

    def test_a_repo_with_no_status_is_swept(self, temp_dir):
        assert registry.Repo(name='a', path=temp_dir, status='').is_swept
