# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""JSON text to a value: the one decode of a ``.json`` document and of a JSON value a channel spells.

An object writing one key twice is refused, as the YAML loader refuses such a mapping
(:func:`confarg._files._yaml_loader`) and tomllib such a table.

Dev Notes:
    docs-dev/architecture/pipeline/deep-merge.md#a-document-writes-each-key-once
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from confarg.exceptions import ConfargError

if TYPE_CHECKING:
    from collections.abc import Sequence


def loads(
    text: str | bytes,
    action: str,
    *,
    at: Sequence[str | int] = (),
    error: type[ConfargError] = ConfargError,
) -> Any:
    """Decode the JSON *text*, refusing an object that writes one key twice.

    Args:
        text: The JSON to decode; as bytes, in any encoding JSON allows, a BOM included.
        action: What was being done, for the refusal: ``read c.json``, ``set '--d'``.
        at: The position the value lands at, which the refusal names the object from.
        error: The class the refusal is raised as, ``InvalidConfigFileError`` for a document.

    Returns:
        The decoded value.

    Raises:
        json.JSONDecodeError: If *text* is no JSON, for the caller to report or fall back on.
        UnicodeDecodeError: If *text* is bytes that no JSON encoding decodes.
        ConfargError: Of the class *error*, if an object writes one key twice.

    Dev Notes:
        The decoder hands an object's pairs to the hook with no position and no parent, so the
        first object found writing a key twice is only noted; its path is looked up once the
        whole value is decoded, which a value writing every key once never pays for.
    """
    twice: list[tuple[dict[str, Any], str]] = []

    def build(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        obj = dict(pairs)
        if len(obj) < len(pairs) and not twice:
            seen: set[str] = set()
            for key, _ in pairs:
                if key in seen:
                    twice.append((obj, key))
                    break
                seen.add(key)
        return obj

    value = json.loads(text, object_pairs_hook=build)
    if twice:
        obj, key = twice[0]
        raise error.key_written_twice(action, (key, key), path=(*at, *_path_to(obj, value)))
    return value


def _path_to(target: dict[str, Any], value: Any) -> tuple[str | int, ...]:
    """Return the path of the object *target* in the decoded *value*, found by identity."""
    stack: list[tuple[tuple[str | int, ...], Any]] = [((), value)]
    while stack:  # a loop rather than a recursion: the decoder nests deeper than Python's stack
        path, node = stack.pop()
        if node is target:
            return path
        if isinstance(node, dict):
            stack.extend(((*path, key), item) for key, item in node.items())
        elif isinstance(node, list):
            stack.extend(((*path, index), item) for index, item in enumerate(node))
    msg = "the object is part of the value it was decoded into"
    raise AssertionError(msg)
