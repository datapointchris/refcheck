"""The shape of the command surface: three verbs, and bare invocation shows help.

Every fleet tool spells self-update as a subcommand, and `check` is a verb for
the same reason `learn-rules` is — both do work, and neither is a modifier of
the other. Bare `refcheck` prints help because the scan takes flags of its own,
which is what disqualifies a bare default from standing in for a command.
"""

import subprocess


def run(*args, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run(['refcheck', *args], capture_output=True, text=True, cwd=cwd)


def test_bare_invocation_shows_help(tmp_path):
    """Not a scan of the current directory, which is what a bare default would run."""
    result = run(cwd=tmp_path)

    assert 'Usage: refcheck' in result.stdout
    assert 'check' in result.stdout


def test_check_is_the_verb_that_scans(tmp_path):
    (tmp_path / 'run.sh').write_text('#!/usr/bin/env bash\nsource lib/gone.sh\n')

    result = run('check', cwd=tmp_path)

    assert result.returncode == 1
    assert 'lib/gone.sh' in result.stdout


def test_update_is_a_verb(tmp_path):
    """Asked for its help rather than run, so the suite reaches no network."""
    result = run('update', '--help', cwd=tmp_path)

    assert result.returncode == 0
    assert '--check' in result.stdout


def test_learn_rules_is_a_verb(tmp_path):
    result = run('learn-rules', '--help', cwd=tmp_path)

    assert result.returncode == 0
    assert 'rules.json' in result.stdout


def test_version_is_a_root_option(tmp_path):
    """It belongs to refcheck itself, so it answers without naming a command."""
    result = run('--version', cwd=tmp_path)

    assert result.returncode == 0
    assert result.stdout.startswith('refcheck ')


def test_the_retired_flags_are_gone(tmp_path):
    """Each of these is a verb now, and a flag that still parsed would be a second spelling."""
    for flag in ('--update', '--learn-rules'):
        result = run('check', flag, cwd=tmp_path)
        assert result.returncode == 2, flag


def test_the_hook_entry_runs_the_check():
    """.pre-commit-hooks.yaml names the invocation, and bare refcheck no longer scans."""
    from pathlib import Path

    import yaml

    hooks = yaml.safe_load((Path(__file__).parent.parent / '.pre-commit-hooks.yaml').read_text())

    assert hooks[0]['entry'] == 'refcheck check'
