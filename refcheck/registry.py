"""The repos on this machine, read from a registry the caller names.

refcheck never goes looking for this file. The path arrives as `--registry`,
because a check is two halves — the code measuring and the thing measured — and
resolving the second from a variable or a `$HOME` path measures whatever the
environment answers at that moment. One machine's registry lists one set of
repos and another's lists a different set, so the subject is named at the call
site and the sweep reads what it was handed.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path


class RegistryError(Exception):
    """The named registry is not a registry, said so it can be acted on."""


@dataclass(frozen=True)
class Repo:
    """One repo the registry lists, at the path this machine keeps it."""

    name: str
    path: Path
    status: str

    @property
    def is_swept(self) -> bool:
        """A retired repo is not going to be edited, so a finding in one is noise.

        Dormant is not the same thing and is swept: dormant work gets picked up,
        and a reference that broke while it was quiet is exactly what nobody
        would otherwise find. Visibility decides nothing — a private repo's
        broken reference is as broken as a public one's.
        """
        return self.status != 'retired'

    @property
    def is_on_disk(self) -> bool:
        return self.path.is_dir()


@dataclass(frozen=True)
class Registry:
    """What a registry file listed, and what in it could not be read.

    An entry naming no path is a third outcome beside the repos that were fine
    and the ones that were not, so it travels rather than being dropped where
    nothing can count it. Six entries of which four are unusable would otherwise
    sweep two repos and print a tick, and the caller has no way to tell that
    from a machine holding two.
    """

    repos: list[Repo]
    unusable: list[str]


def load(registry_path: Path) -> Registry:
    """Every repo the registry lists, minus the paths it excludes itself.

    Two shapes are accepted because two are in use: a bare array of entries, and
    an object holding them under `repos` alongside the machine's search and
    exclude paths. `exclude_paths` is the registry's own declaration of what it
    keeps but does not own — third-party clones read for reference — so it is
    applied here rather than left to a flag.
    """
    try:
        document = json.loads(registry_path.read_text(encoding='utf-8'))
    except OSError as error:
        raise RegistryError(f'cannot read {registry_path}: {error}') from error
    except json.JSONDecodeError as error:
        raise RegistryError(f'{registry_path} is not valid JSON: {error}') from error

    if isinstance(document, dict):
        entries = document.get('repos')
        excluded = [_expand(path) for path in document.get('exclude_paths', [])]
    else:
        entries = document
        excluded = []

    if not isinstance(entries, list):
        raise RegistryError(f'{registry_path} holds no list of repos')

    repos = []
    unusable = []
    for position, entry in enumerate(entries):
        if not isinstance(entry, dict):
            unusable.append(f'entry {position} is a {type(entry).__name__}, not an object')
            continue
        if not entry.get('path'):
            unusable.append(f'{entry.get("name") or f"entry {position}"} names no path')
            continue
        path = _expand(entry['path'])
        if any(path == home or path.is_relative_to(home) for home in excluded):
            continue
        repos.append(Repo(name=entry.get('name') or path.name, path=path, status=entry.get('status', '')))

    if not repos:
        raise RegistryError(f'{registry_path} names no repos')

    return Registry(repos=repos, unusable=unusable)


def _expand(path: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(path)))
