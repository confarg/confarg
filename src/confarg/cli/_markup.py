# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Escape plain help text for the help formats a framework reads as markup.

Dev Notes:
    docs-dev/architecture/cli-adapters/framework-specifics.md#help-text-is-format-neutral
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

#: Every ASCII punctuation character: CommonMark and reStructuredText both read a backslash
#: before one as that character, literally.
_ASCII_PUNCTUATION = re.compile(r"([!-/:-@\[-`{-~])")

#: A colon that could open a rich emoji code (``:warning:``): one with a second colon after it
#: and no whitespace between.
_EMOJI_CODE_OPENER = re.compile(r":(?=\S*?:)")

#: A style-less markup tag pair: rich replaces emoji codes in each run of text between two
#: tags, so this pair after a code's opening colon keeps the code from being read, and prints
#: nothing.  rich's markup has no escape for an emoji code.
_EMPTY_TAGS = "[none][/none]"


def _escape_punctuation(text: str) -> str:
    """Return *text* with a backslash before each ASCII punctuation character."""
    return _ASCII_PUNCTUATION.sub(r"\\\1", text)


def _escape_rich_markup(text: str) -> str:
    """Return *text* with every rich markup tag and emoji code escaped."""
    from rich.markup import escape  # noqa: PLC0415  # rich ships with the frameworks that need it

    escaped = escape(text)
    if text.endswith("\\") and not text.endswith("\\\\"):
        # escape() doubles a lone trailing backslash, for markup appended after it; the
        # note ends the help, so nothing is.
        escaped = escaped[:-1]
    return _EMOJI_CODE_OPENER.sub(f":{_EMPTY_TAGS}", escaped)


def escape_percent(text: str) -> str:
    """Return *text* with each ``%`` doubled, as argparse reads help as a ``%``-format string."""
    return text.replace("%", "%%")


def help_escape(help_format: str | None) -> Callable[[str], str] | None:
    """Return what turns plain text into *help_format* so it prints as written, ``None`` for plain text.

    Args:
        help_format: The format the framework renders help in, spelled as cyclopts'
            ``help_format`` and typer's ``rich_markup_mode`` spell it; ``None`` and
            ``"plaintext"`` are plain text.
    """
    if help_format in {"markdown", "md", "restructuredtext", "rst"}:
        return _escape_punctuation
    if help_format == "rich":
        return _escape_rich_markup
    return None
