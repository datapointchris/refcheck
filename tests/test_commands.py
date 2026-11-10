"""The shape of the command surface: `check`, the `config` and `rules` namespaces and `update`.

Self-update is a subcommand rather than a flag for the same reason `check` is
a verb: it does work of its own and modifies none of the others, and
`--update` would read as a modifier of whichever command it sat on. Bare
`refcheck` prints help because the scan takes flags of its own, which is what
disqualifies a bare default from standing in for a command.
"""

import re
import subprocess
from pathlib import Path

import typer
import yaml

from refcheck.main import app

REPO = Path(__file__).parent.parent

# Rich styles the help, and whether it does depends on the terminal it thinks it
# has: a local run pipes into a non-tty and gets plain text, while CI forces
# color on. So `Usage: refcheck` arrives with escape sequences between the two
# words, and `--check` arrives with them between the dashes and the name.
ANSI = re.compile(r'\x1b\[[0-9;]*m')


def run(*args, cwd=None) -> subprocess.CompletedProcess:
    result = subprocess.run(['refcheck', *args], capture_output=True, text=True, cwd=cwd)
    return subprocess.CompletedProcess(
        result.args,
        result.returncode,
        ANSI.sub('', result.stdout),
        ANSI.sub('', result.stderr),
    )


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


# A command printed for a person to run: in rich bold, a code span or single
# quotes in the source, or on a line of a shell fence in the README.
# A word running into a `/` or a `.` is a path argument, not a subcommand.
WORDS = r'((?: [a-z][\w-]*(?![\w/.-]))+)'
PRINTED_IN_SOURCE = re.compile(rf"(?:\[b\]|`|')refcheck{WORDS}")
SHELL_FENCE = re.compile(r'^```(?:bash|sh)\n(.*?)^```', re.MULTILINE | re.DOTALL)
PRINTED_IN_FENCE = re.compile(rf'^refcheck{WORDS}', re.MULTILINE)


def printed_commands():
    for source in sorted((REPO / 'src' / 'refcheck').glob('*.py')):
        for match in PRINTED_IN_SOURCE.finditer(source.read_text()):
            yield source.name, match.group(1).split()
    readme = (REPO / 'README.md').read_text()
    for fence in SHELL_FENCE.finditer(readme):
        for match in PRINTED_IN_FENCE.finditer(fence.group(1)):
            yield 'README.md', match.group(1).split()
    for match in PRINTED_IN_SOURCE.finditer(readme):
        yield 'README.md', match.group(1).split()


def test_every_command_it_prints_is_in_the_command_tree():
    """A hint naming a command that was renamed sends its reader to an error."""
    tree = typer.main.get_command(app)
    missing = []
    walked = 0
    for source, words in printed_commands():
        walked += 1
        command = tree
        for word in words:
            subcommands = getattr(command, 'commands', None)
            if subcommands is None:
                break
            if word not in subcommands:
                missing.append(f'{source}: refcheck {" ".join(words)}')
                break
            command = subcommands[word]

    assert walked > 20
    assert missing == []


def test_version_is_a_root_option(tmp_path):
    """It belongs to refcheck itself, so it answers without naming a command."""
    result = run('--version', cwd=tmp_path)

    assert result.returncode == 0
    assert result.stdout.startswith('refcheck ')


def test_the_hook_entry_runs_the_check():
    """.pre-commit-hooks.yaml names the invocation, and bare refcheck no longer scans."""

    hooks = yaml.safe_load((Path(__file__).parent.parent / '.pre-commit-hooks.yaml').read_text())

    assert hooks[0]['entry'] == 'refcheck check'


# The error panel draws a border down each side of the message and wraps it to
# the terminal, so a long corrected call can arrive split across two rows.
def error_text(result: subprocess.CompletedProcess) -> str:
    return ' '.join(result.stderr.replace('│', ' ').replace('╭', ' ').replace('╰', ' ').split())


def test_a_scan_flag_at_the_root_names_the_call_under_check(tmp_path):
    """The scan flags belong to check, so refcheck refuses them and spells the call that runs them."""
    result = run('--moves-since', 'origin/main', cwd=tmp_path)

    assert result.returncode == 2
    assert '--moves-since belongs to check: refcheck check --moves-since origin/main' in error_text(result)


def test_a_scan_flag_beside_a_command_names_only_the_flag(tmp_path):
    """With a command in the call, the rest of it is not all check's, so only the flag is moved."""
    result = run('--moves', 'rules', 'learn', cwd=tmp_path)

    assert result.returncode == 2
    assert '--moves belongs to check: refcheck check --moves' in error_text(result)
    assert 'check --moves rules' not in error_text(result)


def test_a_flag_no_command_takes_gets_the_plain_refusal(tmp_path):
    result = run('--no-such-flag', cwd=tmp_path)

    assert result.returncode == 2
    assert 'No such option: --no-such-flag' in error_text(result)
    assert 'belongs to check' not in error_text(result)
