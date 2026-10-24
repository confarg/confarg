# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""A dataclass field annotated by a data descriptor is set through what its ``__set__`` takes (FEAT-40)."""

from __future__ import annotations

import re
from typing import Any, Union

import pytest

import confarg
from confarg._types import _struct_fields, _struct_state_fields
from confarg.cli import build_static_flags
from confarg.exceptions import ConfargError, MissingFieldError, TypeCoercionError
from tests import _descriptors as _d
from tests import _generics_postponed as _postponed

_MOD = _d.__name__


class TestTheMemberIsWhatSetTakes:
    """Every channel sets the field as the type ``__set__`` takes; the state is what ``__get__`` gives."""

    @pytest.mark.parametrize(
        ("data", "built"),
        [
            pytest.param("foo*", _d.Pattern(pattern="foo*"), id="str"),
            pytest.param({"class": f"{_MOD}.Pattern", "pattern": "p"}, _d.Pattern(pattern="p"), id="tagged-locator"),
        ],
    )
    def test_a_file_value_takes_either_input(self, data: Any, built: Any) -> None:
        """A file's text and a file's tagged dict both build, the descriptor converting the text."""
        assert confarg.from_dict(_d.PartSpec, {"locate": data}).locate == built

    def test_the_member_and_the_state_read_set_and_get(self) -> None:
        """``__set__``'s value parameter types the member, ``__get__``'s return the state."""
        assert _struct_fields(_d.PartSpec)["locate"] == _d.Locator | str
        assert _struct_state_fields(_d.PartSpec)["locate"] is _d.Locator

    def test_overloads_are_joined(self) -> None:
        """An overloaded ``__set__`` takes each overload's value; ``__get__``'s class-access overload is no state."""
        assert _struct_fields(_d.Shapes)["count"] == int | str
        assert _struct_state_fields(_d.Shapes)["count"] is int

    def test_an_unannotated_descriptor_takes_and_holds_anything(self) -> None:
        """No annotation reads as ``Any``, as an unannotated constructor parameter does."""
        assert (_struct_fields(_d.Shapes)["anything"], _struct_state_fields(_d.Shapes)["anything"]) == (Any, Any)

    def test_an_unannotated_overload_joins_as_any(self) -> None:
        """Overloads taking ``int`` and an unannotated value take ``int | Any``, as a field written so does."""
        assert _struct_fields(_d.Joined)["half"] == Union[int, Any]  # the runtime union typing builds
        assert confarg.load(_d.Joined, argv=["--half", "3"], env={}).half == 3

    def test_a_descriptor_whose_methods_have_no_hints_reads_as_any(self) -> None:
        """A ``property`` subclass's ``__set__`` and ``__get__`` are C code: it takes and holds anything."""
        assert (_struct_fields(_d.Validating)["x"], _struct_state_fields(_d.Validating)["x"]) == (Any, Any)
        assert confarg.from_dict(_d.Validating, {"x": "5"}).x == 5

    def test_a_generic_descriptor_in_a_generic_dataclass(self) -> None:
        """``Wrapped[int]``'s ``Converted[T, str]`` is ``Converted[int, str]``: it takes ``int | str``."""
        assert _struct_fields(_d.Wrapped[int])["value"] == int | str
        assert confarg.from_dict(_d.Wrapped[int], {"value": "7"}).value == 7

    def test_postponed_annotations_resolve_the_descriptor_parameters(self) -> None:
        """A descriptor naming its class's ``T`` in a string annotation is read with ``T`` bound."""
        assert _struct_fields(_postponed.Counted)["count"] == int | str
        assert confarg.load(_postponed.Counted, argv=["--count", "7"], env={}).count == 7


class TestWhereTheRuleStops:
    """Only a field's own annotation naming a descriptor class is read through it, as type checkers read it."""

    def test_a_union_with_a_descriptor_class_stays_literal(self) -> None:
        """``LocatorField | None = None`` installs no descriptor; mypy, pyright and ty all refuse a str there."""
        with pytest.raises(TypeCoercionError, match=re.escape("Cannot construct LocatorField at 'optional'")):
            confarg.load(_d.Shapes, argv=[*_d.SHAPES_REQUIRED, "--optional", "x"], env={})

    def test_annotated_metadata_stays_on_the_input_type(self) -> None:
        """``Annotated[LocatorField, FieldMeta(help=...)]`` is read through the descriptor, its help kept."""
        spec = next(s for s in build_static_flags(_d.Shapes) if s.name == "helped")
        assert spec.help == "where the part is"
        assert _struct_fields(_d.Shapes)["helped"] == _d.Locator | str

    @pytest.mark.parametrize("name", ["final", "aliased"])
    def test_wrapped_metadata_stays_on_the_input_type(self, name: str) -> None:
        """Under ``Final`` or a type alias the descriptor is read alike, its ``FieldMeta`` help kept."""
        spec = next(s for s in build_static_flags(_d.Qualified) if s.name == name)
        assert spec.help == name
        assert confarg.load(_d.Qualified, argv=["--final", "f", "--aliased", "a"], env={}).aliased == _d.Pattern("a")

    def test_an_initvar_is_read_through_the_descriptor(self) -> None:
        """``InitVar[LocatorField]`` takes ``Locator | str``, as pyright and ty read it."""
        assert confarg.load(_d.Seeded, argv=["--seed", "foo*"], env={}).pattern == "foo*"


class TestTheDefault:
    """A dataclass takes the field's default from the descriptor's class access."""

    def test_a_value_on_class_access_is_the_default(self) -> None:
        """``Converted``'s ``(1, 1)`` is the default the field builds and ``--help`` shows."""
        assert confarg.load(_d.Shapes, argv=_d.SHAPES_REQUIRED, env={}).size == (1, 1)
        assert "(default: (1, 1))" in next(s for s in build_static_flags(_d.Shapes) if s.name == "size").note

    def test_the_descriptor_itself_is_no_default(self) -> None:
        """A ``__get__`` returning itself on class access leaves the field required, and the refusal says why."""
        with pytest.raises(
            MissingFieldError, match=re.escape("Its descriptor ReturnsSelf returns itself on class access")
        ):
            confarg.load(_d.SelfDefault, argv=[], env={})
        assert "default" not in (next(s for s in build_static_flags(_d.SelfDefault) if s.name == "locate").note or "")

    @pytest.mark.parametrize(
        ("tp", "descriptor"),
        [(_d.SelfDefault, "ReturnsSelf"), (_d.Validating, "Validated")],
        ids=["returns-self", "property"],
    )
    def test_a_file_alone_says_why_it_is_required(self, tp: type, descriptor: str) -> None:
        """A file-only read gives the same explanation, a ``property`` too returning itself on class access."""
        with pytest.raises(MissingFieldError, match=re.escape(f"Its descriptor {descriptor} returns itself")):
            confarg.from_dict(tp, {})


class TestReadingAndDumping:
    """A reference reads the value confarg constructs; the dump writes what the instance holds."""

    def test_a_reference_reads_the_input_as_constructed(self) -> None:
        """``${locate}`` reads ``'foo*'``: ``__set__`` converts it inside ``__init__``, after resolution."""
        assert confarg.load(_d.PartSpec, argv=["--locate", "foo*", "--kind", "k-${locate}"], env={}).kind == "k-foo*"

    def test_the_held_value_dumps_and_reads_back(self) -> None:
        """A ``Pattern`` is a ``Locator`` the input type takes back."""
        dumped = confarg.dump(_d.PartSpec(locate="foo*"))
        assert dumped == {"kind": "part", "locate": {"pattern": "foo*", "class": f"{_MOD}.Pattern"}}
        assert confarg.from_dict(_d.PartSpec, dumped) == _d.PartSpec(locate="foo*")

    def test_a_value_the_input_does_not_take_dumps_as_state(self) -> None:
        """A handle-only descriptor holds a ``Transform``: dumped as one, it does not read back."""
        dumped = confarg.dump(_d.Step(transform="resize"))
        assert dumped == {"transform": {"size": 3, "class": f"{_MOD}.Resize"}}
        with pytest.raises(TypeCoercionError):
            confarg.from_dict(_d.Step, dumped)

    def test_a_descriptor_with_no_getter_refuses_the_dump_and_says_why(self) -> None:
        """A ``__set__`` with no ``__get__`` leaves nothing to read: the refusal names the missing getter."""
        built = confarg.from_dict(_d.Unreadable, {"x": 3})
        with pytest.raises(ConfargError, match=re.escape("its descriptor WriteOnly, which has no __get__ to read")):
            confarg.dump(built)
