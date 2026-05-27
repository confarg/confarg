# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Click adapter: populate commands from dataclass types and construct them back."""

try:
    import click as _click  # noqa: F401  # availability check; click is an optional dependency
except ImportError as exc:
    msg = "confarg.cli.click requires click: pip install click"
    raise ImportError(msg) from exc

from confarg.cli.click._completion import setup_completion
from confarg.cli.click._context import from_context
from confarg.cli.click._register import load_flags_into_command, populate_command

__all__ = [
    "from_context",
    "load_flags_into_command",
    "populate_command",
    "setup_completion",
]
