# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The argv a host framework parses, which is not always the argv the user typed.

Vanilla reads argv itself, so it honors every spelling the CLI grammar allows.  A
framework parses on its own terms and rejects what its option model cannot express, so
the token is dropped before the framework sees it and the scans that *do* need it keep
reading the original argv.  What a dropped token meant is read back off that argv here
too, so the drop and its meaning stay one decision.

Dev Notes:
    docs-dev/architecture/cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from confarg.exceptions import ConfargError

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence


def _bare_occurrence(argv: Sequence[str], i: int) -> bool:
    """Return whether the token at *i* is a flag occurrence carrying no item.

    An occurrence carries an item when a token follows it that
    :func:`~confarg._parse_cli._looks_like_flag` calls a value -- vanilla's own split, so
    the frameworks consume exactly the tokens vanilla consumes, a dash-prefixed item
    (``--tags+ -8``) included.  A ``--<flag>=<value>`` token carries its item by
    construction; it reads as bare here but names ``<flag>=<value>``, which matches no
    flag name, so nothing acts on it.

    Dev Notes:
        docs-dev/architecture/cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare
    """
    # Imported here: a module-level import would create a load-time import cycle.
    from confarg._parse_cli import _looks_like_flag  # noqa: PLC0415

    return _looks_like_flag(argv[i]) and (i + 1 == len(argv) or _looks_like_flag(argv[i + 1]))


def drop_bare_occurrences(argv: Sequence[str], stands_bare: Collection[str]) -> list[str]:
    """Return *argv* without the occurrences of a stands-bare flag that carry no item.

    Args:
        argv: The tokens the user typed, in order.
        stands_bare: Dotted flag names (no ``--``) whose specs set
            :attr:`~confarg.cli.FlagSpec.stands_bare`.

    Returns:
        A new list of tokens for the framework to parse.

    Dev Notes:
        docs-dev/architecture/cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare
    """
    if not stands_bare:
        return list(argv)
    return [tok for i, tok in enumerate(argv) if not (_bare_occurrence(argv, i) and tok[2:] in stands_bare)]


def refuse_bare_occurrences(argv: Sequence[str], refuses_bare: Collection[str]) -> None:
    """Raise :class:`~confarg.exceptions.ConfargError` on a bare occurrence of a flag in *refuses_bare*.

    The refusing counterpart of :func:`drop_bare_occurrences`: a flag whose bare
    occurrence is a missing value is dropped from no argv, so a framework that reads
    one as an implicit value asserts the moment it meets a real token. The occurrence
    is refused off the argv the user typed, before the framework parses -- raising
    the missing-value error vanilla's own scan raises.

    Args:
        argv: The tokens the user typed, in order.
        refuses_bare: Dotted flag names (no ``--``) whose specs set
            :attr:`~confarg.cli.FlagSpec.refuses_bare`.

    Raises:
        ConfargError: If *argv* spells a bare occurrence of one of those flags.

    Dev Notes:
        docs-dev/architecture/cli-adapters/whole-value-flags.md#whole-value-flags
    """
    for i, tok in enumerate(argv):
        if _bare_occurrence(argv, i) and tok[2:] in refuses_bare:
            raise ConfargError.missing_value(tok)


def spelled_flag_names(argv: Sequence[str]) -> set[str]:
    """Return the names of the flags *argv* spells, ``--k=v`` and ``--k v`` alike.

    Args:
        argv: The tokens the user typed, in order.

    Returns:
        Dotted flag names (no ``--``), each spelled at least once.

    Dev Notes:
        docs-dev/architecture/cli-adapters/model.md#argv-is-the-only-writer
    """
    # Imported here: a module-level import would create a load-time import cycle.
    from confarg._parse_cli import _looks_like_flag, _normalize_eq_args  # noqa: PLC0415

    return {tok[2:] for tok in _normalize_eq_args(argv) if _looks_like_flag(tok)}
