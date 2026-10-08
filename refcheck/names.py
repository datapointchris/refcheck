"""Where an old name appears as a reference to the thing, rather than as a word.

A renamed tool leaves its old name behind in prose, commands, config and paths,
and none of those is a path refcheck can resolve. Matching the bare word instead
buries the references in English whenever the old name is also a word, because
most lines holding it use the word.

So which shapes count depends on what kind of text the line is. Each shape is one
that text of that kind does not take when it means the English word:

- Any line: a code span opening on it (`relate`, `relate check`), a quoted
  literal holding only it ("relate"), a path segment (~/tools/relate, relate.db,
  relate.storage), bold holding only it, or a table cell holding only it.
- A line of code or config: also an import of it, a value that is only it
  (`name: relate`), an item in a bracketed list ([indy, relate]) or a comma list
  with no spaces (-F relate,nomad), and a line opening on it in aligned columns.
- A line a shell would run: the whole word anywhere outside a comment, because a
  shell line holds commands and their arguments, not sentences.

What none of them reaches is the name in running prose, as in "across indy, relate
and syncer". Nothing on such a line tells the tool from the verb, so it is left to
a reader.

A name of several words is a tool and its subcommand, as in `forge brief`. On a
line of code, config or shell, the words in order count, comments included, and so
does an installed path ahead of the tool (/usr/bin/forge brief). In prose the
phrase may be English (`learning plan`), so it counts only in a single name's
shapes: a code span, a quoted literal, bold or a table cell. On every line it also
counts as consecutive quoted items of an argument list, `["forge", "brief"]`.
"""

import re
from dataclasses import dataclass
from enum import Enum

NAME_WORD = re.compile(r'\w[\w.-]*')


class LineKind(Enum):
    """What a line of a scanned file holds, as far as a reference check cares."""

    PROSE = 'prose'
    SHELL = 'shell'
    ANOTHER_LANGUAGE = 'another language'


@dataclass(frozen=True)
class NameShapes:
    """The compiled shapes for one name, one pattern per kind of line."""

    anywhere: re.Pattern
    in_code: re.Pattern
    in_shell: re.Pattern
    first_word: str

    @classmethod
    def of(cls, name: str) -> 'NameShapes':
        words = name.split()
        if len(words) > 1:
            return cls.of_command(words)
        return cls.of_word(name, directory=True)

    @classmethod
    def of_filename(cls, filename: str) -> 'NameShapes':
        """The shapes for a filename: a tool's, less a directory of that name.

        A filename ends a path and never leads one, so `ci.yml/` is not it.
        """
        return cls.of_word(filename, directory=False)

    @classmethod
    def of_word(cls, name: str, directory: bool) -> 'NameShapes':
        word = re.escape(name)
        alone = rf'(?<![\w./$-]){word}(?![\w-])'
        leading = rf'| (?<![\w./-]){word}(?=/[\w.])          # a leading segment' if directory else ''
        segments = rf"""
            | (?<=/){word}(?![\w-])                 # a segment after a slash
            {leading}
            """
        anywhere = re.compile(
            rf"""
              `{word}(?=[`\s])                      # opens a code span
            | (["']){word}\1                        # is the whole of a quoted literal
            {segments}
            | (?<![\w./-]){word}(?=\.[A-Za-z]\w*)   # a file stem or a module prefix
            | \*\*{word}\*\* | __{word}__           # bold holding only it
            | \|\s*{word}\s*\|                      # a table cell holding only it
            """,
            re.VERBOSE,
        )
        in_code = re.compile(
            rf"""
              ^\s*(?:import|from)\s+{word}(?![\w-])     # an import of it
            | [:=]\s*{word}\s*(?:\#.*)?$                # a value that is only it
            | \[(?:[^\]\n]*,)?\s*{word}\s*[,\]]         # an item in a bracketed list
            | (?<![\w./$-]){word}(?=,[\w.-])            # a comma list, no spaces,
            | (?<=[\w.-],){word}(?![\w-])               #   at either end of a comma
            | ^\s*{word}\s{{2,}}\S                      # opens a line of aligned columns
            """,
            re.VERBOSE,
        )
        in_shell = re.compile(alone)
        return cls(anywhere=anywhere, in_code=in_code, in_shell=in_shell, first_word=name)

    @classmethod
    def of_command(cls, words: list[str]) -> 'NameShapes':
        """The shapes for a tool and its subcommand, `forge brief`."""
        tool, *rest = (re.escape(word) for word in words)
        tail = ''.join(rf'\s+{word}' for word in rest) + r'(?![\w-])'
        installed = r'(?:[\w.~${}/-]*/)?'
        quoted_installed = r'(?:[^"\'\s]*/)?'
        argv = r'\s*,\s*'.join([rf'["\']{quoted_installed}{tool}["\']', *(rf'["\']{word}["\']' for word in rest)])
        anywhere = re.compile(
            rf"""
              `{installed}{tool}{tail}                  # opens a code span
            | (?P<quote>["']){tool}{tail}(?P=quote)     # is the whole of a quoted literal
            | \*\*{tool}{tail}\*\*                      # bold holding only it
            | \|\s*{tool}{tail}\s*\|                    # a table cell holding only it
            | {argv}                                    # consecutive items of an argument list
            """,
            re.VERBOSE,
        )
        in_code = re.compile(rf'(?<![\w.$-]){tool}["\']?{tail}')
        return cls(anywhere=anywhere, in_code=in_code, in_shell=re.compile(r'(?!)'), first_word=words[0])

    def names_it(self, line: str, kind: LineKind) -> bool:
        """Whether this line refers to the thing the name named."""
        if self.first_word not in line:
            return False
        if self.anywhere.search(line):
            return True
        if kind is LineKind.PROSE:
            return False
        if self.in_code.search(line):
            return True
        return kind is LineKind.SHELL and bool(self.in_shell.search(without_comment(line)))


def without_comment(line: str) -> str:
    """A shell line up to its comment, which is prose a shell never runs.

    A `#` opens a comment only outside quotes and at the start of a word, so
    `"#tag"` and `${#arr}` stay part of the command.
    """
    quote = ''
    for index, char in enumerate(line):
        if quote:
            if char == quote:
                quote = ''
        elif char in '\'"':
            quote = char
        elif char == '#' and (index == 0 or line[index - 1].isspace()):
            return line[:index]
    return line
