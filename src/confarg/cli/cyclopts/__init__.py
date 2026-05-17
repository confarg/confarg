# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""cyclopts adapter for confarg."""

try:
    import cyclopts as _cyclopts  # noqa: F401  # availability check; cyclopts is an optional dependency
except ImportError as exc:
    msg = "confarg.cli.cyclopts requires cyclopts: pip install cyclopts"
    raise ImportError(msg) from exc

from confarg.cli.cyclopts._context import from_app, merge_app
from confarg.cli.cyclopts._register import load_flags_into_app, populate_app

__all__ = [
    "from_app",
    "load_flags_into_app",
    "merge_app",
    "populate_app",
]
