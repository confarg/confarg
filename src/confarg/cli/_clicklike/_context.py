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
    from confarg._defaults import _Options

from confarg.cli._collect import _construct_from_merged, _merge_from_flat
from confarg.cli._prefix import PREFIX_ATTR, resolve_prefix

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


def merge_from_ctx(target: object, ctx: Any, options: _Options) -> dict[str, Any]:
    """Flatten ``ctx`` and run the shared merge tail; see the adapters' merge_context."""
    cli_prefix = resolve_prefix(registered_prefix(ctx), options.cli_prefix)
    return _merge_from_flat(flat_from_ctx(ctx), target, options, cli_prefix=cli_prefix, binds_runs=False)


def construct_from_ctx(target: object, ctx: Any, options: _Options) -> Any:
    """Merge ``ctx`` and construct ``target``; see the adapters' from_context."""
    return _construct_from_merged(target, merge_from_ctx(target, ctx, options), options.union_tag)
