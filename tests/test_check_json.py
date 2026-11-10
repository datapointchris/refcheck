"""check --json, validated against the schema the data catalog publishes for it."""

import json
import subprocess
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

SCHEMA = json.loads((Path(__file__).resolve().parents[1] / 'schemas' / 'check.schema.json').read_text())


def git(repo: Path, *args: str) -> None:
    subprocess.run(['git', *args], cwd=repo, capture_output=True, check=True)


@pytest.fixture
def moved_repo(tmp_path, monkeypatch):
    """A staged rename one line here and one line in a listed repo still name, beside a warning and a set-aside hit."""
    monkeypatch.setenv('HOME', str(tmp_path))
    repo = tmp_path / 'upstream'
    (repo / 'lib').mkdir(parents=True)
    (repo / 'bin').mkdir()
    git(repo, 'init')
    git(repo, 'config', 'user.email', 'test@test.com')
    git(repo, 'config', 'user.name', 'Test')
    (repo / 'lib' / 'log.sh').write_text('log() { :; }\n')
    (repo / 'bin' / 'run.sh').write_text('#!/usr/bin/env bash\nsource lib/log.sh\nLIB_DIR="$(cd "$(dirname "$0")/../lib" && pwd)"\n')
    (repo / '.markdownlint.json').write_text('{}\n')
    (repo / 'lint.md').write_text('Configured in .markdownlint.json\n')
    git(repo, 'add', 'lib/log.sh', 'bin/run.sh', '.markdownlint.json', 'lint.md')
    git(repo, 'commit', '-m', 'init')
    git(repo, 'mv', 'lib/log.sh', 'lib/logging.sh')

    consumer = tmp_path / 'consumer'
    consumer.mkdir()
    (consumer / 'use.sh').write_text(f'source {repo}/lib/log.sh\n')
    registry = tmp_path / 'repos.json'
    registry.write_text(json.dumps([{'name': 'upstream', 'path': str(repo)}, {'name': 'consumer', 'path': str(consumer)}]))
    return repo, registry


@pytest.mark.parametrize(
    ('args', 'question'),
    [
        ([], 'references'),
        (['--pattern', 'markdownlint.json'], 'pattern'),
        (['--moves', '--registry', '{registry}'], 'moves'),
    ],
)
def test_the_report_matches_its_published_schema(moved_repo, args, question):
    repo, registry = moved_repo

    result = subprocess.run(
        ['refcheck', 'check', '--json', *(arg.format(registry=registry) for arg in args)],
        cwd=repo,
        capture_output=True,
        text=True,
    )

    document = json.loads(result.stdout)
    Draft7Validator(SCHEMA).validate(document)
    assert document['question'] == question
    assert document['exit_code'] == result.returncode
