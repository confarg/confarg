# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Machinery shared by the click and typer adapters.

Typer vendors its own copy of click, so its command, context, option and choice
classes are unrelated to the real click ones even though the APIs match.  Everything
that does not name one of those classes lives here, and each adapter supplies only
the classes its framework spells differently.

This package imports neither click nor typer, so importing one adapter does not drag
the other's dependency in.

Dev Notes:
    docs-dev/architecture/04-cli-adapters.md#the-clicklike-seam
"""

from confarg.cli._clicklike._completion import partial_argv_from_env, setup_completion
from confarg.cli._clicklike._context import (
    construct_from_ctx,
    flat_from_ctx,
    merge_from_ctx,
    registered_prefix,
)
from confarg.cli._clicklike._options import (
    DottedNameMixin,
    ExpressionTolerantChoiceMixin,
    option_kwargs,
)
from confarg.cli._clicklike._register import load_flags_into_command, populate_command

__all__ = [
    "DottedNameMixin",
    "ExpressionTolerantChoiceMixin",
    "construct_from_ctx",
    "flat_from_ctx",
    "load_flags_into_command",
    "merge_from_ctx",
    "option_kwargs",
    "partial_argv_from_env",
    "populate_command",
    "registered_prefix",
    "setup_completion",
]
