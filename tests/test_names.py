"""Tests for telling a renamed tool's old name apart from the same word in a sentence.

The name in these tests is `connect`, because it is a real English verb. A name
nobody would write in prose would pass every test below whatever the matcher did.
"""

import pytest

from refcheck.checker import ReferenceChecker
from refcheck.names import LineKind
from refcheck.names import NameShapes

SHAPES = NameShapes.of('connect')


class TestShapesThatNameTheToolOnAnyLine:
    @pytest.mark.parametrize(
        'line',
        [
            'Use `connect` for this.',
            'Run `connect check --json` first.',
            'tool = "connect"',
            'cd ~/src/connect',
            'from connect.storage import open_db',
            'connect/main.py holds the CLI',
            'docs_url: "https://github.com/someone/connect"',
            '| **connect** | SQLite | CLI |',
            '| SQLite | connect | CLI |',
        ],
    )
    def test_in_prose(self, line):
        assert SHAPES.names_it(line, LineKind.PROSE)


class TestShapesThatNameTheToolInCode:
    @pytest.mark.parametrize(
        'line',
        [
            'import connect',
            'from connect import storage',
            '  - name: connect',
            'tool = connect',
            'see_also: [othertool, connect, anothertool]',
            'tool exec -F connect,othertool -- <cmd>',
            'tool exec -F othertool,connect -- <cmd>',
            '  connect     SQLite · CLI     content synthesis',
        ],
    )
    def test_in_another_language(self, line):
        assert SHAPES.names_it(line, LineKind.ANOTHER_LANGUAGE)

    @pytest.mark.parametrize(
        'line',
        [
            'connect batch ./urls.txt',
            'out=$(connect show 3)',
            'uv tool install connect',
            'if connect check; then',
            "rg -e '\\b(othertool|connect|anothertool)\\b'",
        ],
    )
    def test_on_a_shell_line(self, line):
        assert SHAPES.names_it(line, LineKind.SHELL)


class TestTheWordStaysSilent:
    @pytest.mark.parametrize(
        'line',
        [
            'How do the pieces connect across repos?',
            '`othertool connect` grades a saved analysis',
            'a sentence ending on connect.',
            'myconnect/config is another tool',
            'Example: connect',
        ],
    )
    def test_in_prose(self, line):
        assert not SHAPES.names_it(line, LineKind.PROSE)

    def test_in_a_comma_list_with_spaces(self):
        assert not SHAPES.names_it('across othertool, connect, anothertool and newtool', LineKind.ANOTHER_LANGUAGE)

    @pytest.mark.parametrize(
        'line',
        [
            'make build  # so the parts connect',
            '# connect the two before running',
            'othertool connected --json',
        ],
    )
    def test_on_a_shell_line_in_a_comment_or_a_longer_word(self, line):
        assert not SHAPES.names_it(line, LineKind.SHELL)


COMMAND = NameShapes.of('tool oldsub')


class TestAToolAndItsSubcommand:
    @pytest.mark.parametrize(
        ('line', 'kind'),
        [
            ("        logger.warning(f'tool oldsub failed: {e}')", LineKind.ANOTHER_LANGUAGE),
            ("            ['tool', 'oldsub'],", LineKind.ANOTHER_LANGUAGE),
            ('{Name: "repos", Command: []string{"tool", "oldsub", "--json"}},', LineKind.ANOTHER_LANGUAGE),
            ('For where each project stands: `tool oldsub`.', LineKind.PROSE),
            ('Run `~/go/bin/tool oldsub --json` first.', LineKind.PROSE),
            ('the old command was "tool oldsub"', LineKind.PROSE),
            ('| **tool oldsub** | removed |', LineKind.PROSE),
            ('| tool oldsub | removed |', LineKind.PROSE),
            ('tool  oldsub --json | jq .', LineKind.SHELL),
            ('make all  # then tool oldsub', LineKind.SHELL),
            ('ExecStart=/usr/bin/tool oldsub', LineKind.ANOTHER_LANGUAGE),
            ('exec.Command("/usr/bin/tool", "oldsub")', LineKind.ANOTHER_LANGUAGE),
            ('"$HOME/go/bin/tool" oldsub --json', LineKind.SHELL),
        ],
    )
    def test_is_named_on_every_kind_of_line(self, line, kind):
        assert COMMAND.names_it(line, kind)

    def test_the_phrase_in_running_prose_stays_silent(self):
        assert not NameShapes.of('release notes').names_it('The release notes list every change.', LineKind.PROSE)

    @pytest.mark.parametrize(
        'line',
        [
            'tool reports its oldsub per repo',
            'the tool oldsub-line widget',
            'retool oldsub',
            'tool oldsubs',
            '`tool` is the command',
            'oldsub: tool',
            'my-tool oldsub',
            'tool.oldsub',
            'tool --json oldsub',
        ],
    )
    def test_other_uses_of_either_word_stay_silent(self, line):
        for kind in LineKind:
            assert not COMMAND.names_it(line, kind)


NAMESPACED = NameShapes.of('task feed:pull')


class TestASubcommandWithNamespaces:
    @pytest.mark.parametrize(
        ('line', 'kind'),
        [
            ('task feed:pull', LineKind.SHELL),
            ('task feed:pull -- --since 2d', LineKind.SHELL),
            ('Run `task feed:pull` first.', LineKind.PROSE),
            ('  cmds: [task feed:pull]', LineKind.ANOTHER_LANGUAGE),
            ('feed: task feed:pull', LineKind.ANOTHER_LANGUAGE),
        ],
    )
    def test_is_named_on_every_kind_of_line(self, line, kind):
        assert NAMESPACED.names_it(line, kind)

    @pytest.mark.parametrize('line', ['task feed:pull:all', 'task feed:puller', 'task feed:pull-all', 'task feed'])
    def test_a_longer_or_shorter_name_stays_silent(self, line):
        for kind in LineKind:
            assert not NAMESPACED.names_it(line, kind)

    def test_an_old_plain_subcommand_is_not_found_inside_a_namespaced_one(self):
        old = NameShapes.of('task feed')
        assert old.names_it('task feed -- -v', LineKind.SHELL)
        assert not old.names_it('task feed:pull', LineKind.SHELL)
        assert not old.names_it('Run `task feed:pull` first.', LineKind.PROSE)


FLAG = NameShapes.of('refcheck --pattern')


class TestAToolAndItsFlag:
    """A root flag that moved under a subcommand, called the old way."""

    @pytest.mark.parametrize(
        ('line', 'kind'),
        [
            ('''      - cmd: "refcheck --pattern 'old/path/' --desc 'Now new/path/'"''', LineKind.ANOTHER_LANGUAGE),
            ('  `refcheck --pattern "<old>" --desc "<new>"` sweeps one that is not.', LineKind.PROSE),
            ('refcheck --pattern=old/ --no-warn', LineKind.SHELL),
            ('subprocess.run(["refcheck", "--pattern", old])', LineKind.ANOTHER_LANGUAGE),
            ('~/.local/bin/refcheck --pattern old/', LineKind.SHELL),
        ],
    )
    def test_the_old_call_is_named(self, line, kind):
        assert FLAG.names_it(line, kind)

    @pytest.mark.parametrize(
        'line',
        [
            'refcheck check --pattern old/',
            '`refcheck check --pattern "<old>"` sweeps one that is not.',
            'refcheck --pattern-file list.txt',
            'refcheck --patterns',
            'subprocess.run(["refcheck", "check", "--pattern", old])',
        ],
    )
    def test_the_corrected_call_and_other_flags_stay_silent(self, line):
        for kind in LineKind:
            assert not FLAG.names_it(line, kind)

    @pytest.mark.parametrize(
        ('line', 'kind'),
        [
            ('tool --json --legacy', LineKind.SHELL),
            ('tool -v --legacy', LineKind.SHELL),
            ('Run `tool --json --legacy` first.', LineKind.PROSE),
            ('args: ["tool", "--json", "--legacy"]', LineKind.ANOTHER_LANGUAGE),
        ],
    )
    def test_a_removed_flag_is_named_after_a_kept_one(self, line, kind):
        assert NameShapes.of('tool --legacy').names_it(line, kind)

    def test_a_word_before_the_flag_is_a_subcommand_and_stays_silent(self):
        for kind in LineKind:
            assert not NameShapes.of('tool --legacy').names_it('tool check --json --legacy', kind)

    @pytest.mark.parametrize(
        ('line', 'kind'),
        [
            ('refcheck check --strict src/', LineKind.SHELL),
            ('refcheck check --no-warn --strict', LineKind.SHELL),
            ('["refcheck", "check", "--strict"]', LineKind.ANOTHER_LANGUAGE),
        ],
    )
    def test_a_subcommands_own_flag_is_named(self, line, kind):
        assert NameShapes.of('refcheck check --strict').names_it(line, kind)

    @pytest.mark.parametrize(
        ('line', 'kind'),
        [
            ('tool sub parser-fix --oldflag b.md', LineKind.SHELL),
            ('tool sub "$slug" --timeout 30 --oldflag b.md', LineKind.SHELL),
            ('Run `tool sub parser-fix --oldflag b.md` next.', LineKind.PROSE),
            ('subprocess.run(["tool", "sub", slug, "--oldflag", str(brief)])', LineKind.ANOTHER_LANGUAGE),
        ],
    )
    def test_a_subcommands_flag_is_named_behind_its_arguments(self, line, kind):
        assert NameShapes.of('tool sub --oldflag').names_it(line, kind)

    @pytest.mark.parametrize(
        'line',
        [
            'tool sub parser-fix | tee --oldflag',
            'tool sub parser-fix; echo --oldflag',
            'tool sub parser-fix 2>&1 --oldflag',
            'tool sub parser-fix # then --oldflag',
            'tool sub parser-fix --oldflag-file b.md',
            'Run `tool sub parser-fix` with `--oldflag`.',
            'run(["tool", "sub", slug]); log(["--oldflag"])',
            'tool new parser-fix --oldflag b.md',
        ],
    )
    def test_a_flag_outside_the_subcommands_command_stays_silent(self, line):
        for kind in LineKind:
            assert not NameShapes.of('tool sub --oldflag').names_it(line, kind)

    def test_a_tools_flag_behind_a_value_stays_silent(self):
        for kind in LineKind:
            assert not NameShapes.of('tool --legacy').names_it('tool --type md --legacy', kind)


class TestCheckNames:
    def found(self, temp_dir, files, **options):
        for name, text in files.items():
            (temp_dir / name).write_text(text)
        checker = ReferenceChecker(root_dir=temp_dir, **options)
        checker.check_names({'connect': 'now newtool'})
        return [(str(issue.file), issue.line_num) for issue in checker.issues]

    def test_a_row_carries_the_line_it_found(self, temp_dir):
        (temp_dir / 'README.md').write_text('Use `connect` here, `connect` there.\nHow do these connect?\n')
        checker = ReferenceChecker(root_dir=temp_dir)

        checker.check_names({'connect': 'now newtool'})

        assert [(str(i.file), i.line_num, i.message, i.suggestion) for i in checker.issues] == [
            ('README.md', 1, 'Found: Use `connect` here, `connect` there.', 'now newtool'),
        ]

    def test_no_description_leaves_no_suggestion(self, temp_dir):
        (temp_dir / 'README.md').write_text('Use `connect`.\n')
        checker = ReferenceChecker(root_dir=temp_dir)

        checker.check_names({'connect': ''})

        assert checker.issues[0].suggestion is None

    def test_a_shell_fence_reports_a_command_and_prose_does_not(self, temp_dir):
        assert self.found(temp_dir, {'guide.md': 'connect across repos\n\n```bash\nconnect batch x\n```\n'}) == [('guide.md', 4)]

    def test_a_script_reports_a_command_and_a_text_file_does_not(self, temp_dir):
        files = {'run.sh': 'connect batch x\n', 'notes.txt': 'connect across repos\n', 'doc.md': '```yaml\nconnect: x\n```\n'}

        assert self.found(temp_dir, files) == [('run.sh', 1)]

    def test_an_extensionless_script_is_shell_by_its_shebang(self, temp_dir):
        files = {'deploy': '#!/usr/bin/env bash\nconnect batch x\n', 'COMMIT_TEMPLATE': 'connect to the existing behavior.\n'}

        assert self.found(temp_dir, files) == [('deploy', 2)]

    def test_python_and_yaml_prose_is_not_a_command(self, temp_dir):
        files = {
            'model.py': 'def f():\n    """Load both.\n\n    connect them to each other later.\n    """\n',
            'config.yaml': 'description: >\n  connect records across tables.\n',
        }

        assert self.found(temp_dir, files) == []

    def test_skip_docs_leaves_markdown_out(self, temp_dir):
        assert self.found(temp_dir, {'README.md': 'Use `connect`.\n'}, skip_docs=True) == []
