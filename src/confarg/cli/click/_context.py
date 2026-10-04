# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Convert a Click Context into a nested dict for dataclass construction."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Unpack

if TYPE_CHECKING:
    import click

    from confarg._defaults import MergeOptions

from confarg._defaults import _resolve_options
from confarg.cli import _clicklike


def merge_context(target: object, ctx: click.Context, **opts: Unpack[MergeOptions]) -> dict[str, Any]:
    """Collect and merge configuration from all sources into a raw dict.

    Same as :func:`from_context` but returns the raw merged dict instead of a
    constructed dataclass.  ``${...}`` expression strings are preserved — call
    :func:`confarg.resolve` to resolve them, then :func:`confarg.build` or
    :func:`confarg.from_dict` to construct the dataclass.

    Args:
        target: The dataclass type to construct.
        ctx: The :class:`click.Context` returned by Click during command execution.
            Obtain it inside a command with :func:`click.get_current_context`.
        **opts: The sources to read and how to read them, as for :func:`confarg.merge`;
            see :class:`confarg.MergeOptions`.  ``argv`` is the list the command was
            invoked with.

    Returns:
        A plain dict of the merged configuration, with expression strings intact.

    Config file loading order:
        Same as :func:`confarg.merge`.
    """
    return _clicklike.merge_from_ctx(target, ctx, _resolve_options("merge_context", opts))


def from_context(target: object, ctx: click.Context, **opts: Unpack[MergeOptions]) -> Any:
    """Construct a dataclass instance from a Click :class:`~click.Context`.

    Merges three sources in ascending priority order: config files, environment
    variables, then CLI arguments from the Context.  This mirrors the behaviour
    of :func:`confarg.load`.

    Only options registered by :func:`populate_command` are consumed from ``ctx``.
    Options absent from the Context (i.e. not provided by the user) fall back to
    env vars, config files, or dataclass defaults; missing required fields raise
    :class:`~confarg.exceptions.MissingFieldError`.

    Args:
        target: The dataclass type to construct.
        ctx: The :class:`click.Context` returned by Click during command execution.
            Obtain it inside a command with :func:`click.get_current_context`.
        **opts: The sources to read and how to read them, as for :func:`confarg.load`;
            see :class:`confarg.MergeOptions`.  ``argv`` is the list the command was
            invoked with.

    Returns:
        An instance of ``target`` populated from all sources.
    """
    return _clicklike.construct_from_ctx(target, ctx, _resolve_options("from_context", opts))


__all__ = ["from_context", "merge_context"]
