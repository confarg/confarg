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

ENV_SEPARATOR: Final[str] = "__"
"""Default separator splitting env var names into nested keys.

A double underscore so that single underscores remain usable inside
field names (``MYAPP_DB__MAX_CONNECTIONS`` → ``db.max_connections``).
"""

CONFIG_FLAG: Final[str] = "config"
"""Default name of the config-file CLI flag and env-pointer segment.

``""`` disables config-file handling entirely.
"""

LOCALS_KEYS: Final[tuple[str, str]] = ("locals", "_locals")
"""Names that may address the reserved namespace holding local variables.

Local variables are scratch values that expressions can reference as
``${locals.<name>}`` but that are not fields of the target type; the namespace
is stripped before construction.

The name is not configurable — it is derived from the target, the way a real
field named ``json`` wins over the ``.json`` force cast.  Either spelling
addresses the namespace, *unless* the target already has a field of that name:
a target with a ``locals`` field keeps it, and its local variables live under
``_locals``.  A target owning both names has no namespace at all.  Declaring
under both spellings at once is ambiguous and raises.

The question is asked at every node, not only at the root: a configuration
file's root -- and with it its ``locals:`` block -- lands wherever the file is
mounted, so a fragment included under ``db`` declares its own variables at
``db.locals`` and modifies them with ``--db.locals.<name>``.  See
``confarg._parse_cli._locals_keys_at``.

``_locals`` rather than a dunder such as ``__locals__``: the env separator is
also ``__``, so a dunder name cannot be expressed as an environment variable at
all (``PFX___LOCALS____X`` splits into ``['LOCALS', '', 'X']``).  That is why
the other reserved dunder keys — ``__root__``, ``__include__``, ``__cast__`` —
are all file-only, whereas this namespace must work in every channel.

Local variables are *declared* in configuration files and *modified* from any
channel.  Declaring is restricted because a local carries no type annotation, so
its type is the one its file format gave it — and only a self-describing format
carries one.  Once declared, an override from the env or CLI is coerced to that
type, and a name no configuration file declared is an error rather than a new
variable.
"""
