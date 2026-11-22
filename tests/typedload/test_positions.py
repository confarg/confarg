"""The one reader and speller of a fixed-length sequence's position, in ``_types`` (REF-105)."""

from collections import namedtuple
from types import GenericAlias
from typing import Annotated, Any, NamedTuple

import pytest

from confarg._parse_cli import _advance_field_type
from confarg._types import _fixed_position, _position_key, _position_spellings, _position_type


class _Pt(NamedTuple):
    x: int
    y: str
    z: float = 0.0


class _Gen[T](NamedTuple):
    a: T
    b: int


_Bare = namedtuple("_Bare", ["p", "q"])  # an untyped namedtuple is one of the shapes read

type _PtAlias = _Pt
type _PairAlias = tuple[int, str]

_FIXED: list[tuple[Any, int]] = [
    (tuple[int, str], 2),
    (tuple[int], 1),
    (_Pt, 3),
    (_Bare, 2),
    (_Gen[int], 2),
    (_PtAlias, 3),
    (_PairAlias, 2),
    (Annotated[_Pt, "m"], 3),
    (Annotated[tuple[int, str], "m"], 2),
]


class TestPositionKey:
    """The key a position is written under, the inverse of ``_fixed_position``."""

    def test_a_namedtuple_names_its_fields_and_a_tuple_its_indices(self) -> None:
        """A field's name, an index as ``str()`` writes it."""
        assert [_position_key(_Pt, i) for i in range(3)] == ["x", "y", "z"]
        assert [_position_key(tuple[int, str], i) for i in range(2)] == ["0", "1"]
        assert [_position_key(_Gen[int], i) for i in range(2)] == ["a", "b"]

    def test_a_position_past_the_arity_is_spelled_as_an_index(self) -> None:
        """A base longer than the arity keeps the keys construction then refuses (the merge's spelling)."""
        assert _position_key(_Pt, 3) == "3"
        assert _position_key(tuple[int, str], 2) == "2"

    @pytest.mark.parametrize(("tp", "arity"), _FIXED)
    def test_the_key_reads_back_as_its_position(self, tp: Any, arity: int) -> None:
        """Each position's key names that position."""
        assert [_fixed_position(tp, _position_key(tp, i)) for i in range(arity)] == list(range(arity))


class TestPositionType:
    """The type at a key of a fixed-length sequence, however the type is wrapped."""

    @pytest.mark.parametrize(
        ("tp", "key", "expected"),
        [
            (_Pt, "x", int),
            (_Pt, "1", str),
            (_Pt, "-1", float),
            (_Pt, "-3", int),
            (_Pt, "01", None),
            (_Pt, "nope", None),
            (_Pt, "3", None),
            (tuple[int, str], "1", str),
            (tuple[int, str], "-2", int),
            (tuple[int, str], "x", None),
            (_Gen[int], "a", int),
            (_PtAlias, "y", str),
            (_PairAlias, "0", int),
            (Annotated[_Pt, "m"], "z", float),
            (Annotated[tuple[int, str], "m"], "-1", str),
            (list[int], "0", None),
        ],
    )
    def test_the_type_at_a_key(self, tp: Any, key: Any, expected: Any) -> None:
        """A name or an index within the arity types its position; any other key types none."""
        assert _position_type(tp, key) == expected

    @pytest.mark.parametrize("tp", [_PtAlias, Annotated[_Pt, "m"]])
    def test_the_walk_types_a_wrapped_namedtuple_as_its_resolved_type_does(self, tp: Any) -> None:
        """The walk read an unresolved wrapper's fields apart: ``Any``, or a ``TypeError`` for an alias."""
        assert [_advance_field_type(tp, key) for key in ("0", "y", "-1")] == [int, str, float]


class TestPositionSpellings:
    """The index spellings of a position, derived from the range ``_fixed_position`` reads."""

    def test_the_positive_spelling_comes_first(self) -> None:
        """Registration lists ``str(i)`` before the negative spelling."""
        assert _position_spellings(3, 0) == ["0", "-3"]
        assert _position_spellings(3, 2) == ["2", "-1"]

    @pytest.mark.parametrize("n", range(7))
    def test_a_string_is_a_spelling_exactly_where_the_reader_reads_it(self, n: int) -> None:
        """No odd form is a spelling, and every form the reader reads is."""
        tp = GenericAlias(tuple, (int,) * n)
        candidates = [str(j) for j in range(-n - 3, n + 3)] + ["01", "+0", "-0", "007", " 1", "1_0"]
        for i in range(n):
            read = {s for s in candidates if _fixed_position(tp, s) == i}
            assert read == set(_position_spellings(n, i))
