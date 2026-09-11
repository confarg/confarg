# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Default values of the keywords shared by ``confarg.load`` and every CLI adapter.

Always reference these constants instead of repeating the literals, so the four front-ends
cannot drift apart.

Agent Notes:
    architecture/10-design-decisions.md
"""

from __future__ import annotations

from typing import Final

UNION_TAG: Final[str] = "class"
"""Default discriminator field name for union variants.

Agent Notes:
    architecture/10-design-decisions.md#union_tag-defaults-to-class
"""

ENV_PREFIX: Final[str | None] = None
"""The default environment variable prefix.

``None`` disables environment variable parsing. Set an explicit prefix (e.g. ``"MYAPP_"``)
to enable it, or ``""`` to read every variable.

Agent Notes:
    architecture/10-design-decisions.md#environment-variables-off-by-default
"""

ENV_SEPARATOR: Final[str] = "__"
"""Default separator splitting env var names into nested keys.

``MYAPP_DB__MAX_CONNECTIONS`` → ``db.max_connections``.
"""

CONFIG_FLAG: Final[str] = "config"
"""Default name of the config-file CLI flag and env-pointer segment.

``""`` disables config-file handling entirely.
"""

LOCALS_KEYS: Final[tuple[str, str]] = ("locals", "_locals")
"""Names that may address the reserved namespace holding local variables.

Local variables are scratch values that expressions reference as ``${locals.<name>}`` but
that are not fields of the target type; the namespace is stripped before construction.
Either spelling addresses the namespace unless the target has a field of that name, in
which case the other spelling is used; a target owning both names has no namespace.
See ``confarg._parse_cli._locals_keys_at``.

Agent Notes:
    architecture/08-locals.md
"""
