"""Where an old name appears as a reference to the thing, rather than as a word.

A renamed tool leaves its old name behind in prose, in commands and in paths, and
none of those is a path refcheck can resolve. Matching the bare word instead buries
the references in English: `relate` is also a verb, and measured across one
documentation set it was 47 hits of which 8 named the tool.

So a hit counts only in a shape that names a thing. Each shape is one a sentence
using the word as English does not take:

- a code span opening on it: `relate`, `relate check`, `relate`'s
- a quoted literal holding only it: "relate", ['relate', ...]
- a path segment: ~/tools/relate, src/relate/storage.py, relate.db, relate.storage
- command position, on a line a shell would run: relate check, x | relate, $(relate),
  and one alternative of a grep -E list such as (indy|relate|syncer)

What none of them reaches is the name in running prose, as in "across indy, relate
and syncer". No shape separates that from the verb, so it is left to a reader.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class NameShapes:
    """The compiled shapes for one name."""

    name: str
    anywhere: re.Pattern
    in_a_command: re.Pattern

    @classmethod
    def of(cls, name: str) -> 'NameShapes':
        word = re.escape(name)
        anywhere = re.compile(
            rf"""
              `{word}(?=[`\s])                      # opens a code span
            | (["']){word}\1                        # is the whole of a quoted literal
            | (?<=/){word}(?![\w-])                 # a segment after a slash
            | (?<![\w./-]){word}(?=/[\w.])          # a leading segment
            | (?<![\w./-]){word}(?=\.[A-Za-z]\w*)   # a file stem or a module prefix
            """,
            re.VERBOSE,
        )
        in_a_command = re.compile(
            rf"""
            (?: ^\s*(?:\$\s+)?    # opens the line, after any prompt
              | [|;&(]\s*         # follows a pipe, a separator or a subshell
            )
            {word}(?=[\s|;&)]|$)  # and ends at a word break a shell or a
                                  # grep -E alternation would also end it at
            """,
            re.VERBOSE,
        )
        return cls(name=name, anywhere=anywhere, in_a_command=in_a_command)

    def names_it(self, line: str, runs_as_shell: bool) -> bool:
        """Whether this line refers to the thing the name named.

        Command position is asked only of a line a shell would run. In prose a
        line opening on the word is a wrapped sentence, and `relate` starting one
        is the verb.
        """
        if self.name not in line:
            return False
        if self.anywhere.search(line):
            return True
        return runs_as_shell and bool(self.in_a_command.search(line))
