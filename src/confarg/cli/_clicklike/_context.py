# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Context flattening and the merge tail, shared by the click and typer adapters.

Dev Notes:
    docs-dev/architecture/cli-adapters/clicklike-seam.md#the-clicklike-seam
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

    from confarg._defaults import _Options
    from confarg._merge import MergeDict

from confarg._defaults import _resolve_options
from confarg.cli._collect import _construct_from_merged, _merge_from_flat
from confarg.cli._prefix import PREFIX_ATTR, resolve_prefix
from confarg.cli._sources import REGISTRATION_ATTR, Registration, reconcile

#: Name of the ``ParameterSource`` member meaning "the user typed it on argv".
#: Compared by name rather than by identity because typer ships its own copy of the
#: enum, and a member of one is never a member of the other
#: (docs-dev/architecture/cli-adapters/clicklike-seam.md#the-clicklike-seam).
_COMMANDLINE = "COMMANDLINE"


def flat_from_ctx(ctx: Any) -> dict[str, Any]:
    """Return only the user-typed params from a framework Context.

    Uses the framework's ``get_parameter_source`` to tell values the user typed on
    the command line from those that came from defaults or other sources, so a
    framework default never enters the CLI layer at CLI priority.  Non-empty tuples
    (from ``multiple=True`` options) are converted to lists.

    Dev Notes:
        docs-dev/architecture/cli-adapters/model.md#only-user-typed-values
    """
    result: dict[str, Any] = {}
    for k, v in ctx.params.items():
        source = ctx.get_parameter_source(k)
        if getattr(source, "name", None) != _COMMANDLINE:
            continue
        result[k] = list(v) if isinstance(v, tuple) else v
    return result


def registered_prefix(ctx: Any) -> str | None:
    """Return the prefix ``populate_command`` registered with, or None if it did not.

    Read off the options rather than the command, so it still resolves when the
    params were copied onto a different command.
    """
    for param in ctx.command.params:
        prefix = getattr(param, PREFIX_ATTR, None)
        if prefix is not None:
            return prefix
    return None


def registration(ctx: Any) -> Registration | None:
    """Return what ``populate_command`` recorded on ``ctx``'s options, None if it did not populate them."""
    command = getattr(ctx, "command", None)
    for param in getattr(command, "params", ()):
        found = getattr(param, REGISTRATION_ATTR, None)
        if found is not None:
            return found
    return getattr(command, REGISTRATION_ATTR, None)


def ctx_options(ctx: Any, caller: str, opts: Mapping[str, Any]) -> _Options:
    """Return *caller*'s options: what ``ctx``'s registration read, with *opts* beside them (:func:`reconcile`)."""
    return _resolve_options(caller, reconcile(registration(ctx), opts, caller))


def ctx_prefix(ctx: Any, options: _Options) -> str:
    """Return the prefix ``ctx``'s options were registered under, reconciled with the one passed."""
    return resolve_prefix(registered_prefix(ctx), options.cli_prefix)


def merge_from_ctx(target: object, ctx: Any, options: _Options) -> MergeDict:
    """Flatten ``ctx`` and run the shared merge tail; see the adapters' merge_context."""
    found = registration(ctx)
    return _merge_from_flat(
        flat_from_ctx(ctx),
        target,
        options,
        cli_prefix=ctx_prefix(ctx, options),
        binds_runs=False,
        runs=None if found is None else found.runs,
    )


def construct_from_ctx(target: object, ctx: Any, options: _Options) -> Any:
    """Merge ``ctx`` and construct ``target``; see the adapters' from_context."""
    merged = merge_from_ctx(target, ctx, options)
    return _construct_from_merged(target, merged, options.union_tag, ctx_prefix(ctx, options))
