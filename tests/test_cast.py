# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Unit tests for the canonical force-cast helpers shared by every input path."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

import pytest

from confarg._cast import FORCE_CAST_NAMES, SCALAR_CAST_TYPES, resolve_forced_value
from confarg._parse_cli import detect_force_cast
from confarg._types import _Pinned
from confarg.exceptions import ConfargError


@dataclass
class _Config:
    rate_limits: tuple[int | None, int | None] = (0, 0)
    json: int = 0  # a field literally named after a cast word
    d: dict[str, int] = dataclasses.field(default_factory=dict)
    data: Any = None


def test_force_cast_names_include_scalars_and_json() -> None:
    """The cast family is exactly the four scalar pins plus json."""
    assert {*SCALAR_CAST_TYPES, "json"} == FORCE_CAST_NAMES


@pytest.mark.parametrize(("name", "tp"), SCALAR_CAST_TYPES.items())
def test_resolve_scalar_cast_pins_type(name: str, tp: type) -> None:
    """A scalar cast defers coercion via a _Pinned token carrying the target type."""
    pinned = resolve_forced_value(name, "5")
    assert isinstance(pinned, _Pinned)
    assert pinned.tp is tp
    assert pinned.value == "5"


def test_resolve_json_cast_decodes_structure() -> None:
    """A json cast decodes immediately and stores the raw structure."""
    assert resolve_forced_value("json", '{"a": 1}') == {"a": 1}
    assert resolve_forced_value("json", "[null, 5]") == [None, 5]
    assert resolve_forced_value("json", "null") is None


def test_resolve_json_cast_invalid_raises() -> None:
    """Invalid JSON hard-errors, surfacing the flag name in the message."""
    with pytest.raises(ConfargError, match="Invalid JSON for"):
        resolve_forced_value("json", "not json", flag="--db.json")


def test_detect_cast_on_collection_field() -> None:
    """.json on a collection field is a cast; the parent path is returned without it."""
    assert detect_force_cast(["rate_limits", "json"], _Config, "class") == (["rate_limits"], "json")


def test_detect_real_field_named_json_wins() -> None:
    """A field literally named json is a field access, not a cast."""
    assert detect_force_cast(["json"], _Config, "class") == (["json"], None)


def test_detect_dict_key_named_json_wins() -> None:
    """On a dict field, .json names a key, so it is not treated as a cast."""
    assert detect_force_cast(["d", "json"], _Config, "class") == (["d", "json"], None)


def test_detect_json_on_any_field_is_cast() -> None:
    """.json on an Any-typed field is a cast (the field has no member named json)."""
    assert detect_force_cast(["data", "json"], _Config, "class") == (["data"], "json")


def test_detect_non_cast_suffix_is_untouched() -> None:
    """A trailing segment that is not a cast word is returned unchanged."""
    assert detect_force_cast(["data", "host"], _Config, "class") == (["data", "host"], None)


@dataclass
class _NoJson:
    host: str = ""


def test_detect_root_json_cast() -> None:
    """A bare --json at the root (no json field) is the whole-config JSON cast: empty path."""
    assert detect_force_cast(["json"], _NoJson, "class") == ([], "json")


def test_detect_root_real_json_field_wins() -> None:
    """A root struct that really has a ``json`` field keeps --json as a field access."""
    assert detect_force_cast(["json"], _Config, "class") == (["json"], None)


@pytest.mark.parametrize("name", sorted(SCALAR_CAST_TYPES))
def test_detect_root_scalar_cast_is_ignored(name: str) -> None:
    """Root-level scalar casts have no struct to attach to, so they are left untouched."""
    assert detect_force_cast([name], _NoJson, "class") == ([name], None)
