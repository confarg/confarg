# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Typer adapter: populate commands from dataclass types and construct them back."""

try:
    # Availability check; typer is an optional dependency.  The two private names are
    # checked here rather than only where they are used, so a typer too old to vendor
    # its own click fails with this message instead of a bare ImportError on a
    # private module (docs-dev/architecture/04-cli-adapters.md#the-clicklike-seam).
    import typer as _typer  # noqa: F401
    import typer._types  # noqa: F401
    from typer.core import TyperOption  # noqa: F401
except ImportError as exc:
    msg = "confarg.cli.typer requires typer>=0.27: pip install 'typer>=0.27'"
    raise ImportError(msg) from exc

from confarg.cli.typer._completion import setup_completion
from confarg.cli.typer._context import from_context, merge_context
from confarg.cli.typer._register import load_flags_into_command, populate_command

__all__ = [
    "from_context",
    "load_flags_into_command",
    "merge_context",
    "populate_command",
    "setup_completion",
]
