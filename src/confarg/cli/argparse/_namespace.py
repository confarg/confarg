# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Convert an argparse Namespace into a nested dict for dataclass construction."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Unpack

if TYPE_CHECKING:
    import argparse
    from collections.abc import Mapping

    from confarg._defaults import MergeOptions, _Options
    from confarg._merge import ListOp, MergeDict

from confarg._defaults import _resolve_options
from confarg.cli._collect import _construct_from_merged, _merge_from_flat
from confarg.cli._prefix import PREFIX_ATTR, resolve_prefix
from confarg.cli._sources import REGISTRATION_ATTR, Registration, reconcile


def _options(ns: argparse.Namespace, caller: str, opts: Mapping[str, Any]) -> _Options:
    """Return *caller*'s options: what *ns*'s registration read, with *opts* beside them (:func:`reconcile`)."""
    return _resolve_options(caller, reconcile(_registration(ns), opts, caller))


def _registration(ns: argparse.Namespace) -> Registration | None:
    """Return what ``populate_parser`` recorded on *ns*, None for a parser confarg did not populate."""
    return getattr(ns, REGISTRATION_ATTR, None)


def merge_namespace(target: object, ns: argparse.Namespace, **opts: Unpack[MergeOptions]) -> dict[str | ListOp, Any]:
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
        A plain dict of the merged configuration, with expression strings intact. A list
        operation that only ``build()`` can apply stays in it, keyed by a
        :class:`confarg.ListOp`.

    Config file loading order:
        Same as :func:`confarg.merge`.
    """
    return _merge_namespace(target, ns, _options(ns, "merge_namespace", opts))


def _merge_namespace(target: object, ns: argparse.Namespace, options: _Options) -> MergeDict:
    """Merge every source into a raw dict; :func:`merge_namespace` with its options resolved."""
    registration = _registration(ns)
    return _merge_from_flat(
        {key: value for key, value in vars(ns).items() if key != REGISTRATION_ATTR},
        target,
        options,
        cli_prefix=_namespace_prefix(ns, options),
        binds_runs=True,
        runs=None if registration is None else registration.runs,
    )


def _namespace_prefix(ns: argparse.Namespace, options: _Options) -> str:
    """Return the prefix *ns*'s flags were registered under, reconciled with the one passed."""
    # argparse hands us no reference to the parser, so populate_parser left the prefix
    # it registered with on the Namespace itself.
    return resolve_prefix(vars(ns).get(PREFIX_ATTR), options.cli_prefix)


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
    options = _options(ns, "from_namespace", opts)
    merged = _merge_namespace(target, ns, options)
    return _construct_from_merged(target, merged, options.union_tag, _namespace_prefix(ns, options))
