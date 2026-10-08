"""Tests for telling a renamed tool's old name apart from the same word in a sentence.

The name in these tests is `relate`, because it is a real English verb. A name
nobody would write in prose would pass every test below whatever the matcher did.
"""

import pytest

from refcheck.checker import ReferenceChecker
from refcheck.names import LineKind
from refcheck.names import NameShapes

SHAPES = NameShapes.of('relate')


class TestShapesThatNameTheToolOnAnyLine:
    @pytest.mark.parametrize(
        'line',
        [
            'Use `relate` for this.',
            "`relate`'s eval reaches its own tables",
            'Run `relate check --json` first.',
            'tool = "relate"',
            'cd ~/tools/relate',
            'Set in src/relate/storage.py',
            'saved to ~/shart/relate/relate.db',
            'from relate.storage import open_db',
            'relate/main.py holds the CLI',
            'docs_url: "https://github.com/someone/relate"',
            '| **relate** | SQLite | CLI |',
            '| SQLite | relate | CLI |',
        ],
    )
    def test_in_prose(self, line):
        assert SHAPES.names_it(line, LineKind.PROSE)


class TestShapesThatNameTheToolInCode:
    @pytest.mark.parametrize(
        'line',
        [
            'import relate',
            'from relate import storage',
            '  - name: relate',
            'tool = relate',
            'see_also: [indy, relate, doit]',
            'forge exec -F relate,nomad -- <cmd>',
            'forge exec -F nomad,relate -- <cmd>',
            '  relate     SQLite · CLI     content synthesis',
        ],
    )
    def test_in_another_language(self, line):
        assert SHAPES.names_it(line, LineKind.ANOTHER_LANGUAGE)

    @pytest.mark.parametrize(
        'line',
        [
            'relate batch ./urls.txt',
            '$ relate deltas',
            'cat urls | relate batch -',
            'out=$(relate show 3)',
            'uv tool install relate',
            'command -v relate >/dev/null',
            'which relate',
            'sudo relate check',
            'if relate check; then',
            'for f in *; do relate "$f"; done',
            'RELATE=1 relate go',
            'exec relate',
            'nohup relate six &',
            'xargs relate < list',
            "rg -e '\\b(indy|relate|syncer)\\b'",
        ],
    )
    def test_on_a_shell_line(self, line):
        assert SHAPES.names_it(line, LineKind.SHELL)


class TestTheWordStaysSilent:
    @pytest.mark.parametrize(
        'line',
        [
            'How do the pieces relate across repos?',
            'relate across repos, and how they share state.',
            'These correlate closely.',
            'it relates to the earlier rule',
            '`digest relate` grades a saved analysis',
            'the relate-ish helpers',
            'a sentence ending on relate.',
            'myrelate/config is another tool',
            'Example: relate',
        ],
    )
    def test_in_prose(self, line):
        assert not SHAPES.names_it(line, LineKind.PROSE)

    @pytest.mark.parametrize(
        'line',
        [
            '    relate them to each other later.',
            '  relate records across tables.',
            'relate to one another is the question.',
            '# how the parts relate',
            'across indy, relate, syncer and dectl',
        ],
    )
    def test_in_another_language(self, line):
        assert not SHAPES.names_it(line, LineKind.ANOTHER_LANGUAGE)

    @pytest.mark.parametrize(
        'line',
        [
            'make build  # so the parts relate',
            '# relate the two before running',
            'digest related --json',
        ],
    )
    def test_on_a_shell_line_in_a_comment_or_a_longer_word(self, line):
        assert not SHAPES.names_it(line, LineKind.SHELL)


COMMAND = NameShapes.of('forge status')


class TestAToolAndItsSubcommand:
    @pytest.mark.parametrize(
        ('line', 'kind'),
        [
            ('1. forge status — project descriptions, planning state', LineKind.ANOTHER_LANGUAGE),
            ("        logger.warning(f'forge status failed: {e}')", LineKind.ANOTHER_LANGUAGE),
            ("            ['forge', 'status'],", LineKind.ANOTHER_LANGUAGE),
            ('{Name: "repos", Command: []string{"forge", "status", "--json"}},', LineKind.ANOTHER_LANGUAGE),
            ('For where each project stands: `forge status`.', LineKind.PROSE),
            ('They were one tool, and forge status swept the portfolio.', LineKind.PROSE),
            ('forge  status --json | jq .', LineKind.SHELL),
            ('make all  # then forge status', LineKind.SHELL),
        ],
    )
    def test_is_named_on_every_kind_of_line(self, line, kind):
        assert COMMAND.names_it(line, kind)

    @pytest.mark.parametrize(
        'line',
        [
            'forge reports its status per repo',
            'the forge status-line widget',
            'reforge status',
            'forge statuses',
            '`forge` is the tool',
            'status: forge',
        ],
    )
    def test_other_uses_of_either_word_stay_silent(self, line):
        for kind in LineKind:
            assert not COMMAND.names_it(line, kind)

    def test_whitespace_between_the_words_is_one_name(self):
        assert NameShapes.of('forge   status').name == 'forge status'


class TestCheckNames:
    def found(self, temp_dir, files, **options):
        for name, text in files.items():
            (temp_dir / name).write_text(text)
        checker = ReferenceChecker(root_dir=temp_dir, **options)
        checker.check_names({'relate': 'now digest'})
        return [(str(issue.file), issue.line_num) for issue in checker.issues]

    def test_a_row_carries_the_line_it_found(self, temp_dir):
        (temp_dir / 'README.md').write_text('Use `relate` here, `relate` there.\nHow do these relate?\n')
        checker = ReferenceChecker(root_dir=temp_dir)

        checker.check_names({'relate': 'now digest'})

        assert [(str(i.file), i.line_num, i.message, i.suggestion) for i in checker.issues] == [
            ('README.md', 1, 'Found: Use `relate` here, `relate` there.', 'now digest'),
        ]

    def test_no_description_leaves_no_suggestion(self, temp_dir):
        (temp_dir / 'README.md').write_text('Use `relate`.\n')
        checker = ReferenceChecker(root_dir=temp_dir)

        checker.check_names({'relate': ''})

        assert checker.issues[0].suggestion is None

    def test_a_shell_fence_reports_a_command_and_prose_does_not(self, temp_dir):
        assert self.found(temp_dir, {'guide.md': 'relate across repos\n\n```bash\nrelate batch x\n```\n'}) == [('guide.md', 4)]

    def test_a_script_reports_a_command_and_a_text_file_does_not(self, temp_dir):
        files = {'run.sh': 'relate batch x\n', 'notes.txt': 'relate across repos\n', 'doc.md': '```yaml\nrelate: x\n```\n'}

        assert self.found(temp_dir, files) == [('run.sh', 1)]

    def test_an_extensionless_script_is_shell_by_its_shebang(self, temp_dir):
        files = {'deploy': '#!/usr/bin/env bash\nrelate batch x\n', 'COMMIT_TEMPLATE': 'relate to the existing behavior.\n'}

        assert self.found(temp_dir, files) == [('deploy', 2)]

    def test_python_and_yaml_prose_is_not_a_command(self, temp_dir):
        files = {
            'model.py': 'def f():\n    """Load both.\n\n    relate them to each other later.\n    """\n',
            'config.yaml': 'description: >\n  relate records across tables.\n',
        }

        assert self.found(temp_dir, files) == []

    def test_skip_docs_leaves_markdown_out(self, temp_dir):
        assert self.found(temp_dir, {'README.md': 'Use `relate`.\n'}, skip_docs=True) == []
