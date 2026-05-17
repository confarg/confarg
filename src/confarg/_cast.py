# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Canonical force-cast resolution shared by the vanilla parser, the CLI adapters, and env.

A force-cast is an explicit suffix on a flag key or env-var segment that pins how the
following value is interpreted, bypassing the type-directed "magic":

- ``.str`` / ``.int`` / ``.float`` / ``.bool`` — pin a scalar leaf type (overrides the
  union "stealing rule").
- ``.json`` — parse the value as JSON, storing the decoded structure raw.

This module is the single source of truth for *which* names are casts and *what value*
each produces, so ``confarg.load`` and every backend produce byte-identical results.
The parse-path decision of *whether* a trailing segment is a cast (vs. a real field of
the same name) lives in :func:`confarg._parse_cli.detect_force_cast`, which needs the
argv parser's type-walk helpers.
"""

from __future__ import annotations

import json
from typing import Any

from confarg._types import _Pinned, _StrToken
from confarg.exceptions import ConfargError

JSON_CAST_NAME = "json"

SCALAR_CAST_TYPES: dict[str, type] = {"str": str, "int": int, "float": float, "bool": bool}

#: Every recognized force-cast suffix (scalar casts plus ``json``).
FORCE_CAST_NAMES: frozenset[str] = frozenset({*SCALAR_CAST_TYPES, JSON_CAST_NAME})


def resolve_forced_value(cast_name: str, raw: str, *, flag: str = "") -> Any:
    """Produce the stored value for an explicit ``.<cast>`` suffix.

    Scalar casts yield a :class:`_Pinned` token (deferred single-type coercion that
    bypasses union stealing); ``json`` decodes the value immediately and stores the
    structure raw, hard-erroring on invalid JSON — an explicit request deserves a loud
    failure rather than a silent fallback.

    Args:
        cast_name: One of :data:`FORCE_CAST_NAMES`.
        raw: The raw string value provided on the CLI or in the environment.
        flag: Human-readable flag/key name, used only in the JSON error message.

    Returns:
        A ``_Pinned`` for scalar casts, or the decoded JSON value for ``json``.

    Raises:
        ConfargError: If ``cast_name`` is ``json`` and ``raw`` is not valid JSON.
    """
    if cast_name == JSON_CAST_NAME:
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            label = flag or "value"
            msg = f"Invalid JSON for {label}: {e}"
            raise ConfargError(msg) from e
    return _Pinned(SCALAR_CAST_TYPES[cast_name], _StrToken(raw))
