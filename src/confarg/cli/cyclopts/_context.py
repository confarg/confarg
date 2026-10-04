# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Parse a cyclopts App invocation and construct a dataclass from all sources."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any, Unpack

if TYPE_CHECKING:
    import cyclopts

    from confarg._defaults import MergeOptions, _Options

from confarg._defaults import _resolve_options
from confarg._parse_cli import _collect_config_file_pairs
from confarg.cli._argv import drop_bare_occurrences, refuse_bare_occurrences
from confarg.cli._collect import _construct_from_merged, _merge_from_flat
from confarg.cli._prefix import PREFIX_ATTR, resolve_prefix, strip_argv_prefix
from confarg.cli.cyclopts._register import _app_meta


def _run_command(command: Any, bound: Any) -> Any:
    """Call *command* with its bound arguments; return the result."""
    return command(*bound.args, **bound.kwargs) if bound is not None else command()


def merge_app(target: object, app: cyclopts.App, **opts: Unpack[MergeOptions]) -> dict[str, Any]:
    """Collect and merge configuration from all sources into a raw dict.

    Same as :func:`from_app` but returns the raw merged dict instead of a
    constructed dataclass.  ``${...}`` expression strings are preserved — call
    :func:`confarg.resolve` to resolve them, then :func:`confarg.build` or
    :func:`confarg.from_dict` to construct the dataclass.

    Like :func:`from_app`, this function calls :meth:`~cyclopts.App.parse_args`
    and will call :func:`sys.exit` if ``--help`` or ``--version`` was requested.

    :func:`populate_app` must have been called on *app* before calling this
    function.

    Args:
        target: The dataclass type to construct.
        app: The cyclopts :class:`~cyclopts.App` populated by
            :func:`populate_app`.
        **opts: The sources to read and how to read them, as for :func:`confarg.merge`;
            see :class:`confarg.MergeOptions`.  ``argv`` is the token list *app* parses.

    Returns:
        A plain dict of the merged configuration, with expression strings intact.

    Config file loading order:
        Same as :func:`confarg.merge`.
    """
    return _merge_app(target, app, _resolve_options("merge_app", opts))


def _merge_app(target: object, app: cyclopts.App, options: _Options) -> dict[str, Any]:
    """Parse *app*'s argv and merge every source; :func:`merge_app` with its options resolved."""
    meta = _app_meta.get(id(app))

    # Parse CLI tokens; exits on errors (exit_on_error=True by default).  cyclopts is
    # handed the argv without the bare occurrences of a flag that takes zero *or* more
    # items: it reads one as an implicit empty container and then asserts when that
    # meets a real token.  A fixed-arity flag cannot drop its bare occurrence -- the
    # occurrence is a missing value, not a no-op -- so it is refused instead, before
    # cyclopts parses, with confarg's own error.  Both scans read the argv the user
    # typed (docs-dev/architecture/cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare).
    prefix = resolve_prefix(meta.get(PREFIX_ATTR) if meta else None, options.cli_prefix)
    tokens = options.argv
    if options.config_flag:
        # A bare --config[.subpath] must be refused before cyclopts parses it, with
        # confarg's own error rather than the framework's implicit-token assertion.
        _collect_config_file_pairs(
            strip_argv_prefix(tokens, prefix),
            options.config_flag,
            target,
            options.union_tag,
        )
    refuse_bare_occurrences(tokens, meta["refuses_bare"] if meta else ())
    command, bound, _ = app.parse_args(
        drop_bare_occurrences(tokens, meta["stands_bare"] if meta else ()),
    )

    confarg_fn = meta["command"] if meta else None
    if command is not confarg_fn:
        # --help, --version, or another special command: execute and exit.
        result = _run_command(command, bound)
        sys.exit(result if isinstance(result, int) else 0)

    # Extract CLI-provided values from the bound arguments.
    # Filter out None (= not provided by user) just as the synthetic fn would.
    name_map: dict[str, str] = meta["name_map"] if meta else {}
    raw: dict[str, Any] = {k: v for k, v in bound.arguments.items() if v is not None}
    flat: dict[str, Any] = {name_map.get(k, k): v for k, v in raw.items()}

    return _merge_from_flat(flat, target, options, cli_prefix=prefix, binds_runs=True)


def from_app(target: object, app: cyclopts.App, **opts: Unpack[MergeOptions]) -> Any:
    """Parse CLI arguments and construct a dataclass from all sources.

    Calls :meth:`~cyclopts.App.parse_args` on *app* to parse *argv*, then
    merges CLI values with config files and environment variables — in the
    same priority order as :func:`confarg.load` — and returns the
    constructed dataclass.

    If ``--help`` or ``--version`` was requested, this function handles the
    output and calls :func:`sys.exit` as expected; the caller never receives
    a return value in that case.

    :func:`populate_app` must have been called on *app* before calling this
    function.

    Args:
        target: The dataclass type to construct.
        app: The cyclopts :class:`~cyclopts.App` populated by
            :func:`populate_app`.
        **opts: The sources to read and how to read them, as for :func:`confarg.load`;
            see :class:`confarg.MergeOptions`.  ``argv`` is the token list *app* parses.

    Returns:
        An instance of *target* populated from all sources.
    """
    options = _resolve_options("from_app", opts)
    return _construct_from_merged(target, _merge_app(target, app, options), options.union_tag)


__all__ = ["from_app", "merge_app"]
