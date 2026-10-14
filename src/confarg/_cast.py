# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Canonical force-cast resolution shared by the vanilla parser, the CLI adapters, and env.

A force-cast is an explicit suffix on a flag key or env-var segment that pins how the
following value is interpreted, bypassing the type-directed "magic":

- ``.str`` / ``.int`` / ``.float`` / ``.bool`` — pin a scalar leaf type (overrides the
  union "stealing rule").
- ``.json`` — parse the value as JSON, storing the decoded structure raw.

This module defines *which* names are casts, *what value* each produces, whether the field's
type admits the cast at all (:func:`holds_the_cast` — a cast names one of the types the field
itself holds), and how the objects a root ``json`` cast decodes fold in under the fields
(:func:`fold_root_json`). Whether a trailing segment is a cast at all (vs. a real field of the
same name) is decided by :func:`confarg._parse_cli.detect_force_cast`.

Dev Notes:
    docs-dev/architecture/cli-parsing/casts-and-reserved-words.md#force-casts
"""

from __future__ import annotations

import json
from typing import Any

from confarg._merge import MergeAt, MergeDict, _deep_merge, _merge_within_source
from confarg._types import _is_union, _Pinned, _resolve_type, _StrToken, _union_args_no_none
from confarg.exceptions import ConfargError, TypeCoercionError

JSON_CAST_NAME = "json"

SCALAR_CAST_TYPES: dict[str, type] = {"str": str, "int": int, "float": float, "bool": bool}

_SCALAR_CAST_NAMES: dict[type, str] = {tp: name for name, tp in SCALAR_CAST_TYPES.items()}

#: Every recognized force-cast suffix (scalar casts plus ``json``).
FORCE_CAST_NAMES: frozenset[str] = frozenset({*SCALAR_CAST_TYPES, JSON_CAST_NAME})


def resolve_forced_value(cast_name: str, raw: str, *, flag: str = "") -> Any:
    """Produce the stored value for an explicit ``.<cast>`` suffix.

    Scalar casts yield a :class:`_Pinned` token (deferred single-type coercion that
    bypasses union stealing); ``json`` decodes the value immediately and stores the
    structure raw, raising on invalid JSON.

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


def holds_the_cast(field_tp: Any, cast_tp: Any) -> bool:
    """Return whether *field_tp* holds *cast_tp* among the types it accepts.

    The one admission rule every cast asks, on every channel: a leaf field holds
    its own type, a union what its variants hold, and ``Any`` everything, so a
    union holding ``Any`` holds every cast. A cast naming anything else would
    place a value the field's type does not accept — an int where the config
    asked for a ``tuple[int, int]`` — so it is refused, by construction reading a
    pin and by the CLI detecting and registering a cast flag alike.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-cast-names-a-type-the-field-holds.md#a-cast-names-a-type-the-field-holds
    """
    field_tp = _resolve_type(field_tp)
    if _is_union(field_tp):
        return any(holds_the_cast(v, cast_tp) for v in _union_args_no_none(field_tp))
    return field_tp is Any or field_tp == cast_tp


def fold_root_json(data: MergeDict, root_json: list[MergeDict], root: MergeAt) -> MergeDict:
    """Fold the objects root ``json`` casts decoded in as a base under *data*.

    The one fold every channel's root cast goes through -- vanilla's ``--json``, the
    adapters' and the environment's ``<PREFIX>JSON``: the fields *data* holds refine the
    injected objects, and of several objects the later wins.  The objects and the fields
    are one source, so a field's delete stays in the result and deletes in the layers below
    as well.  Only a struct-like root folds; a scalar root's cast writes the value itself,
    by each channel's own rule.

    Args:
        data: The values the channel collected at fields.
        root_json: The decoded root objects, earliest first.
        root: Where the merge stands at the configuration root, which reads its type.

    Returns:
        *data* when there is nothing to fold, otherwise a new merged dict.

    Dev Notes:
        docs-dev/architecture/cli-parsing/casts-and-reserved-words.md#force-casts
        docs-dev/architecture/pipeline/deep-merge.md#a-delete-within-one-source-deletes-below-it-too
    """
    if not root_json:
        return data
    base: MergeDict = {}
    for obj in root_json:
        base = _deep_merge(base, obj, at=root)
    return _merge_within_source(base, data, at=root)


def cast_name_for_type(tp: type) -> str:
    """Name the pinned type the way a file spells it, for the ``__cast__`` key.

    The inverse of :func:`type_for_cast_name`: a scalar cast keeps the name
    :data:`SCALAR_CAST_TYPES` gives it, and any other pinned type — a registered leaf,
    which only the file spelling can produce — is named by its ``__name__``.

    Args:
        tp: The type carried by a :class:`~confarg._types._Pinned`.

    Returns:
        The cast name that reads the same value back.

    Dev Notes:
        docs-dev/architecture/types/stealing-rule.md#cast-pinning-in-files
    """
    return _SCALAR_CAST_NAMES.get(tp) or tp.__name__


def type_for_cast_name(name: str) -> type:
    """Return the type a file's ``__cast__`` key names.

    The inverse of :func:`cast_name_for_type`: a scalar cast name, or the ``__name__`` of a
    registered leaf type.

    Raises:
        TypeCoercionError: If *name* is neither, listing the names that are.

    Dev Notes:
        docs-dev/architecture/types/stealing-rule.md#cast-pinning-in-files
    """
    # Lazy: typedload's package init imports _construct, which imports this module.
    from confarg.typedload._coerce import _LEAF_COERCIONS  # noqa: PLC0415  # import cycle

    tp = SCALAR_CAST_TYPES.get(name) or next((t for t in _LEAF_COERCIONS if getattr(t, "__name__", None) == name), None)
    if tp is None:
        valid = sorted(SCALAR_CAST_TYPES) + sorted(
            t.__name__ for t in _LEAF_COERCIONS if t not in SCALAR_CAST_TYPES.values()
        )
        msg = f"Unknown __cast__ type: {name!r}. Valid: {valid}"
        raise TypeCoercionError(msg)
    return tp
