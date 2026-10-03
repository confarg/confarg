# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Convert an argparse Namespace into a nested dict for dataclass construction."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Unpack

if TYPE_CHECKING:
    import argparse

    from confarg._defaults import MergeOptions, _Options

from confarg._defaults import _resolve_options
from confarg.cli._collect import _construct_from_merged, _merge_from_flat
from confarg.cli._prefix import PREFIX_ATTR, resolve_prefix


def merge_namespace(target: object, ns: argparse.Namespace, **opts: Unpack[MergeOptions]) -> dict[str, Any]:
    """Collect and merge configuration from all sources into a raw dict.

    Same as :func:`from_namespace` but returns the raw merged dict instead of a
    constructed dataclass.  ``${...}`` expression strings are preserved — call
    :func:`confarg.resolve` to resolve them, then :func:`confarg.build` or
    :func:`confarg.from_dict` to construct the dataclass.

    Args:
        target: The dataclass type to construct.
        ns: The Namespace returned by ``ArgumentParser.parse_args()``.
        **opts: The sources to read and how to read them, as for :func:`confarg.merge`;
            see :class:`confarg.MergeOptions`.  ``argv`` is the list ``parse_args()``
            parsed.

    Returns:
        A plain dict of the merged configuration, with expression strings intact.

    Config file loading order:
        Same as :func:`confarg.merge`.
    """
    return _merge_namespace(target, ns, _resolve_options("merge_namespace", opts))


def _merge_namespace(target: object, ns: argparse.Namespace, options: _Options) -> dict[str, Any]:
    """Merge every source into a raw dict; :func:`merge_namespace` with its options resolved."""
    flat = vars(ns)
    # argparse hands us no reference to the parser, so populate_parser left the prefix
    # it registered with on the Namespace itself.
    cli_prefix = resolve_prefix(flat.get(PREFIX_ATTR), options.cli_prefix)
    return _merge_from_flat(flat, target, options, cli_prefix=cli_prefix, binds_runs=True)


def from_namespace(target: object, ns: argparse.Namespace, **opts: Unpack[MergeOptions]) -> Any:
    """Construct a dataclass instance from an argparse :class:`~argparse.Namespace`.

    Merges three sources in ascending priority order: config files, environment
    variables, then CLI arguments from the Namespace.  This mirrors the
    behaviour of :func:`confarg.load`.

    Only fields registered by :func:`populate_parser` are consumed from ``ns``.
    Fields absent from the Namespace fall back to env vars, config files, or
    dataclass defaults; missing required fields raise
    :class:`~confarg.exceptions.MissingFieldError`.

    Args:
        target: The dataclass type to construct.
        ns: The Namespace returned by ``ArgumentParser.parse_args()``.
        **opts: The sources to read and how to read them, as for :func:`confarg.load`;
            see :class:`confarg.MergeOptions`.  ``argv`` is the list ``parse_args()``
            parsed.

    Returns:
        An instance of ``target`` populated from all sources.
    """
    options = _resolve_options("from_namespace", opts)
    return _construct_from_merged(target, _merge_namespace(target, ns, options), options.union_tag)
