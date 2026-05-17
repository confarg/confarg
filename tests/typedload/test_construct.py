# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Unit tests for _construct_struct_dispatch inheritance inference."""

from dataclasses import dataclass

import pytest

from confarg._types import _StrToken
from confarg.exceptions import AmbiguousUnionError
from confarg.typedload._construct import _construct_struct_dispatch

# Each scenario uses its own base class so __subclasses__() does not bleed across tests.


@dataclass
class _UniqueBase:
    """Base whose subclasses have disjoint required fields."""


@dataclass
class _UniqueChild1(_UniqueBase):
    x: str


@dataclass
class _UniqueChild2(_UniqueBase):
    y: int


@dataclass
class _FallbackBase:
    """Base whose only subclass requires a field absent from the data."""


@dataclass
class _FallbackChild(_FallbackBase):
    required_field: str


@dataclass
class _AmbigBase:
    """Base with two subclasses that both match the same data structurally."""


@dataclass
class _AmbigChildA(_AmbigBase):
    z: str


@dataclass
class _AmbigChildB(_AmbigBase):
    z: str


class TestConstructStructDispatchInheritance:
    """_construct_struct_dispatch infers subclass when union_tag is absent."""

    def test_unique_match_selects_subclass(self) -> None:
        """Unique structural match selects the correct subclass."""
        result = _construct_struct_dispatch(_UniqueBase, {"x": _StrToken("hello")}, "", "class")
        assert isinstance(result, _UniqueChild1)
        assert result.x == "hello"

    def test_no_subclass_fields_falls_back_to_base(self) -> None:
        """No matching subclass falls back to constructing the base class."""
        result = _construct_struct_dispatch(_FallbackBase, {}, "", "class")
        assert result == _FallbackBase()

    def test_ambiguous_subclasses_raises(self) -> None:
        """Multiple structurally-matching subclasses raise AmbiguousUnionError."""
        with pytest.raises(AmbiguousUnionError):
            _construct_struct_dispatch(_AmbigBase, {"z": _StrToken("v")}, "", "class")
