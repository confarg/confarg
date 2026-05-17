# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Unit tests for _construct_struct_dispatch inheritance behaviour."""

from dataclasses import dataclass

import pytest

from confarg._types import _StrToken, _UnionSeqToken
from confarg.exceptions import TypeCoercionError
from confarg.typedload._construct import _construct_struct_dispatch, construct

# Each scenario uses its own base class so __subclasses__() does not bleed across tests.


@dataclass
class _BaseWithSubs:
    """Base whose subclasses have disjoint required fields."""


@dataclass
class _Sub1(_BaseWithSubs):
    x: str


@dataclass
class _Sub2(_BaseWithSubs):
    y: int


@dataclass
class _BaseNoSubs:
    """Base with no subclasses — can be constructed directly."""

    value: int = 0


class TestConstructStructDispatch:
    """_construct_struct_dispatch raises when subclasses exist but no union_tag is given."""

    def test_subclasses_without_tag_raises(self) -> None:
        """When a struct has subclasses and no union_tag is present, raise TypeCoercionError."""
        with pytest.raises(TypeCoercionError, match="discriminator"):
            _construct_struct_dispatch(_BaseWithSubs, {"x": _StrToken("hello")}, "", "class")

    def test_subclasses_with_tag_constructs(self) -> None:
        """When the union_tag is present, the named subclass is constructed."""
        result = _construct_struct_dispatch(
            _BaseWithSubs,
            {"class": f"{__name__}._Sub1", "x": _StrToken("hello")},
            "",
            "class",
        )
        assert isinstance(result, _Sub1)
        assert result.x == "hello"

    def test_no_subclasses_constructs_directly(self) -> None:
        """When the struct has no subclasses, it is constructed directly without a tag."""
        result = _construct_struct_dispatch(_BaseNoSubs, {}, "", "class")
        assert result == _BaseNoSubs()


class TestUnionSeqTokenFallback:
    """A _UnionSeqToken (a lone CLI token) falls back to the sequence variant.

    A plain _StrToken (env/config scalar) does not — gating the fallback to the
    CLI-only marker keeps env/config strict.
    """

    def test_unmatched_scalar_fills_sequence_variant(self) -> None:
        """Bool rejects 'hello', so the marked token fills list[str] as ['hello']."""
        assert construct(bool | list[str], _UnionSeqToken("hello")) == ["hello"]

    def test_matched_scalar_keeps_scalar_priority(self) -> None:
        """'true' matches the bool variant first; no list wrapping happens."""
        assert construct(bool | list[str], _UnionSeqToken("true")) is True

    def test_plain_strtoken_does_not_fall_back(self) -> None:
        """A plain _StrToken (env/config scalar) stays strict: no sequence fallback."""
        with pytest.raises(TypeCoercionError):
            construct(bool | list[str], _StrToken("hello"))


class _TypeStealTarget:
    """Module-level class used as a dotted-path target for str | type stealing tests."""


class TestUnionTypeRefStealing:
    """A type-ref variant participates in the stealing rule, taking priority over str.

    Regression: _coerce_scalar_variants coerced each variant with _coerce_leaf, which
    cannot build a type ref, so str always stole a str | type union. It now delegates
    to the canonical scalar constructor, letting `type` win.
    """

    def test_bare_builtin_steals_over_str(self) -> None:
        """'int' resolves to the int class for str | type, not the string 'int'."""
        assert construct(str | type, _StrToken("int")) is int

    def test_dotted_path_steals_over_str(self) -> None:
        """A dotted class path resolves to the class for str | type, not the string."""
        path = f"{_TypeStealTarget.__module__}.{_TypeStealTarget.__qualname__}"
        assert construct(str | type, _StrToken(path)) is _TypeStealTarget

    def test_unresolvable_value_falls_back_to_str(self) -> None:
        """A value that is no importable type stays a str (str is the least-priority variant)."""
        assert construct(str | type, _StrToken("not.a.real.class")) == "not.a.real.class"

    def test_constrained_type_ref_steals_over_str(self) -> None:
        """A type[Base] variant also steals: a subclass dotted path resolves to the class."""
        assert construct(str | type[_TypeStealTarget], _StrToken("int")) == "int"  # int not a subclass → str wins
        path = f"{_TypeStealTarget.__module__}.{_TypeStealTarget.__qualname__}"
        assert construct(str | type[_TypeStealTarget], _StrToken(path)) is _TypeStealTarget
