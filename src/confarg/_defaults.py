# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from __future__ import annotations

from typing import Final

UNION_TAG: Final[str] = "class"
"""Default discriminator field name for union variants.

``"class"`` is a Python keyword, so it can never clash with a dataclass
field name — this is the intentional reason for the choice.
"""

ENV_PREFIX: Final[str | None] = None
"""The default environment variable prefix.

``None`` means environment variable parsing is disabled by default.
Set an explicit prefix (e.g. ``"MYAPP_"``) to enable env var reading.

An empty prefix (``""``) is intentionally not the default: env vars are
global and shared across all processes, so reading *all* of them without a
filter would be unsafe in any multi-app environment.
"""
