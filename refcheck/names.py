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

A name of several words is a tool and its subcommand, as in `forge brief`. Two
words in that order are not English on any line, so the phrase counts wherever it
stands, prose and comments included. It also counts as consecutive quoted items
of an argument list, `["forge", "brief"]`, which is how code runs it.
"""

import re
from dataclasses import dataclass
from enum import Enum


class LineKind(Enum):
    """What a line of a scanned file holds, as far as a reference check cares."""

    PROSE = 'prose'
    SHELL = 'shell'
    ANOTHER_LANGUAGE = 'another language'


@dataclass(frozen=True)
class NameShapes:
    """The compiled shapes for one name, one pattern per kind of line."""

    name: str
    anywhere: re.Pattern
    in_code: re.Pattern
    in_shell: re.Pattern
    first_word: str

    @classmethod
    def of(cls, name: str) -> 'NameShapes':
        words = name.split()
        if len(words) > 1:
            return cls.of_command(words)
        word = re.escape(name)
        alone = rf'(?<![\w./$-]){word}(?![\w-])'
        anywhere = re.compile(
            rf"""
              `{word}(?=[`\s])                      # opens a code span
            | (["']){word}\1                        # is the whole of a quoted literal
            | (?<=/){word}(?![\w-])                 # a segment after a slash
            | (?<![\w./-]){word}(?=/[\w.])          # a leading segment
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
        return cls(name=name, anywhere=anywhere, in_code=in_code, in_shell=in_shell, first_word=name)

    @classmethod
    def of_command(cls, words: list[str]) -> 'NameShapes':
        """The shapes for a tool and its subcommand, `forge brief`."""
        escaped = [re.escape(word) for word in words]
        joined = r'\s+'.join(escaped)
        phrase = rf'(?<![\w./$-]){joined}(?![\w-])'
        argv = r'\s*,\s*'.join(rf'(?P<q{index}>["\']){word}(?P=q{index})' for index, word in enumerate(escaped))
        never = re.compile(r'(?!)')
        return cls(
            name=' '.join(words),
            anywhere=re.compile(f'{phrase}|{argv}'),
            in_code=never,
            in_shell=never,
            first_word=words[0],
        )

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
