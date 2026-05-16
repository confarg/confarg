# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from typing import Final

UNION_TAG: Final[str] = "class"
"""The default field name used as a discriminator tag in unions."""

ENV_PREFIX: Final[str | None] = None
"""The default environment variable prefix.

``None`` means environment variable parsing is disabled by default.
Set an explicit prefix (e.g. ``"MYAPP_"``) to enable env var reading.
"""
