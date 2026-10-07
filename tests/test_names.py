"""Tests for telling a renamed tool's old name apart from the same word in a sentence.

The name in these tests is `relate`, because it is a real English verb. A name
nobody would write in prose would pass every test below whatever the matcher did.
"""

import pytest

from refcheck.checker import ReferenceChecker
from refcheck.names import NameShapes

SHAPES = NameShapes.of('relate')


class TestShapesThatNameTheTool:
    @pytest.mark.parametrize(
        'line',
        [
            'Use `relate` for this.',
            "`relate`'s eval reaches its own tables",
            'Run `relate check --json` first.',
            "subprocess.run(['relate', 'batch'])",
            'tool = "relate"',
            'cd ~/tools/relate',
            'Set in src/relate/storage.py',
            'saved to ~/shart/relate/relate.db',
            'from relate.storage import open_db',
            'relate/main.py holds the CLI',
            'docs_url: "https://github.com/someone/relate"',
        ],
    )
    def test_in_any_file(self, line):
        assert SHAPES.names_it(line, runs_as_shell=False)

    @pytest.mark.parametrize(
        'line',
        [
            'relate batch ./urls.txt',
            '  relate status',
            '$ relate deltas',
            'cat urls | relate batch -',
            'out=$(relate show 3)',
            'make && relate resume',
            "rg -e '\\b(indy|relate|syncer)\\b'",
            'relate',
        ],
    )
    def test_in_command_position_on_a_shell_line(self, line):
        assert SHAPES.names_it(line, runs_as_shell=True)


class TestTheWordInASentenceStaysSilent:
    @pytest.mark.parametrize(
        'line',
        [
            'How do the pieces relate across repos?',
            'These correlate closely.',
            'it relates to the earlier rule',
            '`digest relate` grades a saved analysis',
            'the relate-ish helpers',
            'a sentence ending on relate.',
            'myrelate/config is another tool',
        ],
    )
    def test_on_any_line(self, line):
        assert not SHAPES.names_it(line, runs_as_shell=True)

    def test_a_line_opening_on_the_word_is_a_sentence_in_prose(self):
        """A wrapped paragraph puts any word at the start of a line."""
        assert not SHAPES.names_it('relate across repos, and how they share state.', runs_as_shell=False)

    def test_a_subcommand_named_after_the_old_tool_is_not_command_position(self):
        assert not SHAPES.names_it('digest relate 42', runs_as_shell=True)


class TestWhichLinesAShellWouldRun:
    """Command position is only asked of a shell line, so the classification is half the rule."""

    def kinds(self, temp_dir, name, text):
        path = temp_dir / name
        path.write_text(text)
        checker = ReferenceChecker(root_dir=temp_dir)
        return [(line.strip(), kind.value) for _, line, kind in checker.classified_lines(path, checker.lines_of(path))]

    def test_markdown_prose_is_prose_and_a_shell_fence_is_shell(self, temp_dir):
        text = 'relate across repos\n\n```bash\nrelate batch x\n```\n\n```yaml\nrelate: x\n```\n'

        assert self.kinds(temp_dir, 'doc.md', text) == [
            ('relate across repos', 'prose'),
            ('', 'prose'),
            ('relate batch x', 'shell'),
            ('', 'prose'),
            ('relate: x', 'another language'),
        ]

    def test_a_script_is_shell_throughout(self, temp_dir):
        assert self.kinds(temp_dir, 'run.sh', 'relate batch x\n') == [('relate batch x', 'shell')]

    def test_a_text_file_is_prose_throughout(self, temp_dir):
        assert self.kinds(temp_dir, 'notes.txt', 'relate across repos\n') == [('relate across repos', 'prose')]


class TestCheckNames:
    def test_reports_each_line_once_with_the_description(self, temp_dir):
        (temp_dir / 'README.md').write_text('Use `relate` here, `relate` there.\nHow do these relate?\n')
        checker = ReferenceChecker(root_dir=temp_dir)

        checker.check_names({'relate': 'now digest'})

        assert [(str(issue.file), issue.line_num, issue.message, issue.suggestion) for issue in checker.issues] == [
            ('README.md', 1, 'Names relate', 'now digest'),
        ]

    def test_a_shell_fence_reports_command_position_and_prose_does_not(self, temp_dir):
        (temp_dir / 'guide.md').write_text('relate across repos\n\n```bash\nrelate batch x\n```\n')
        checker = ReferenceChecker(root_dir=temp_dir)

        checker.check_names({'relate': 'now digest'})

        assert [issue.line_num for issue in checker.issues] == [4]

    def test_skip_docs_leaves_markdown_out(self, temp_dir):
        (temp_dir / 'README.md').write_text('Use `relate`.\n')
        checker = ReferenceChecker(root_dir=temp_dir, skip_docs=True)

        checker.check_names({'relate': 'now digest'})

        assert checker.issues == []
