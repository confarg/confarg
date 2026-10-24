# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""A parameterized generic class is a struct whose type parameters are bound (FEAT-13)."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Any

import pytest

import confarg
from confarg.cli import build_static_flags
from confarg.exceptions import AmbiguousUnionError, TypeCoercionError
from tests import _generics as _g
from tests import _generics_postponed as _postponed
from tests.conftest import make_target

_MOD = _g.__name__


@dataclass
class _Same:
    u: _g.Box[int] | _g.Box[str]


@dataclass
class _Twins:
    """Two variants a tag naming ``_TwinChild`` subclasses, of two classes: still ambiguous."""

    u: _TwinA | _TwinB


@dataclass
class _TwinA:
    item: int = 0


@dataclass
class _TwinB:
    item: int = 0


@dataclass
class _TwinChild(_TwinA, _TwinB):
    pass


class TestMembersReadTheirBinding:
    """Every member reads its type with the class's parameters bound, from a file as from argv."""

    def test_a_file_value_is_coerced_by_the_bound_type(self) -> None:
        """A file's ``3`` builds ``Box[int]``'s item, and its quoted ``'3'`` is refused as an int field refuses it."""
        assert confarg.from_dict(_g.Holder, {"b": {"item": 3}}).b == _g.Box(item=3)
        with pytest.raises(TypeCoercionError, match=re.escape("Cannot coerce str '3' to int at 'b.item'")):
            confarg.from_dict(_g.Holder, {"b": {"item": "3"}})

    def test_a_reused_legacy_typevar_is_bound_per_declaring_class(self) -> None:
        """``LegacyWrap[int]`` binds its base's ``LegacyT`` to ``list[int]`` and its own to ``int``."""
        built = confarg.from_dict(_g.LegacyWrap[int], {"item": [1, 2], "extra": 3})
        assert built == _g.LegacyWrap(item=[1, 2], extra=3)
        with pytest.raises(TypeCoercionError, match=re.escape("at 'item'")):
            confarg.from_dict(_g.LegacyWrap[int], {"item": 1})

    def test_a_plain_class_binds_its_constructor_parameters(self) -> None:
        """A handwritten ``__init__``'s ``T`` is bound as the class's own parameter."""
        assert confarg.from_dict(_g.Handwritten[int], {"item": 1, "items": [2]}) == _g.Handwritten(1, [2])
        with pytest.raises(TypeCoercionError, match=re.escape("at 'items[0]'")):
            confarg.from_dict(_g.Handwritten[int], {"item": 1, "items": ["a"]})

    def test_a_generic_namedtuple(self) -> None:
        """``Point[float]`` reads its fields as floats."""
        assert confarg.from_dict(_g.Holder, {"b": {"item": 0}, "point": {"x": 1, "y": 2}}).point == _g.Point(1.0, 2.0)

    def test_a_typevartuple_splices_its_arguments(self) -> None:
        """``Dims[int, str]`` types ``tuple[*Ts]`` as ``tuple[int, str]``, fixed length included."""
        assert confarg.from_dict(_g.Dims[int, str], {"dims": [1, "a"]}) == _g.Dims(dims=(1, "a"))
        with pytest.raises(TypeCoercionError):
            confarg.from_dict(_g.Dims[int, str], {"dims": [1, "a", 2]})

    def test_an_unbound_typevartuple_reads_any_number_of_anything(self) -> None:
        """A bare ``Dims`` reads ``tuple[*Ts]`` as ``tuple[Any, ...]``."""
        assert confarg.from_dict(_g.Dims, {"dims": [1, "a", None]}) == _g.Dims(dims=(1, "a", None))

    def test_a_paramspec_types_a_callable(self) -> None:
        """``Fn[[int]]`` types its field as ``Callable[[int], int]``, which a dotted path fills."""
        assert confarg.from_dict(_g.Fn[[int]], {"fn": "builtins.abs"}) == _g.Fn(fn=abs)


class TestATagBindsTheClassItNames:
    """A tag names a class; the declared type binds its parameters through its bases."""

    def test_a_subclass_binding_its_base_to_a_container_of_its_own(self) -> None:
        """``Listed[T](Tagged[list[T]])`` under ``Tagged[list[int]]`` is ``Listed[int]``."""
        built = confarg.from_dict(_g.Tagged[list[int]], {"class": f"{_MOD}.Listed", "item": [1]})
        assert built == _g.Listed(item=[1])
        with pytest.raises(TypeCoercionError, match=re.escape("at 'item[0]'")):
            confarg.from_dict(_g.Tagged[list[int]], {"class": f"{_MOD}.Listed", "item": ["a"]})

    @pytest.mark.parametrize(
        ("declared", "named"),
        [
            pytest.param(_g.Tagged[int], "Listed", id="list-of-T-is-no-int"),
            pytest.param(_g.Tagged[str], "IntTagged", id="int-is-no-str"),
        ],
    )
    def test_a_subclass_whose_bases_fix_another_argument_is_refused(self, declared: Any, named: str) -> None:
        """A tag never loosens the declared type: a checker refuses ``Listed(...)`` as a ``Tagged[int]``."""
        with pytest.raises(TypeCoercionError, match=re.escape(f"is not a subclass of {declared!r}.")):
            confarg.from_dict(declared, {"class": f"{_MOD}.{named}", "item": [1]})

    def test_a_tag_naming_the_declared_class_keeps_its_binding(self) -> None:
        """``class: Tagged`` under ``Tagged[int]`` builds ``Tagged[int]``, never a bare ``Tagged``."""
        data = {"b": {"item": 0}, "tagged": {"class": f"{_MOD}.Tagged", "item": "x"}}
        with pytest.raises(TypeCoercionError, match=re.escape("Cannot coerce str 'x' to int at 'tagged.item'")):
            confarg.from_dict(_g.Holder, data)

    def test_a_tag_naming_no_subclass_is_refused(self) -> None:
        """An unrelated class is refused, the field's parameterized type named."""
        data = {"b": {"item": 0}, "tagged": {"class": f"{_MOD}.Box", "item": 1}}
        with pytest.raises(TypeCoercionError, match=re.escape(f"not a subclass of {_MOD}.Tagged[int]")):
            confarg.from_dict(_g.Holder, data)


class TestAGenericParameterizedApiece:
    """``Box[int] | Box[str]``: one class, two bindings, told apart by the value."""

    @pytest.mark.parametrize(("item", "built"), [(3, 3), ("x", "x")])
    def test_a_tag_naming_the_class_builds_the_first_binding_that_takes_the_value(self, item: Any, built: Any) -> None:
        """``class: Box`` tries ``Box[int]``, then ``Box[str]``."""
        assert confarg.from_dict(_Same, {"u": {"class": f"{_MOD}.Box", "item": item}}).u == _g.Box(item=built)

    @pytest.mark.parametrize("item", [3, "x"])
    def test_it_dumps_and_reads_back(self, item: Any) -> None:
        """The dump picks the variant by what the instance holds, not by its class alone."""
        dumped = confarg.dump(_Same(u=_g.Box(item=item)))
        assert dumped == {"u": {"item": item}}
        assert confarg.from_dict(_Same, dumped).u == _g.Box(item=item)

    def test_two_classes_a_tag_subclasses_stay_ambiguous(self) -> None:
        """Only one class parameterized apiece shares a tag; two classes a subclass inherits are still ambiguous."""
        with pytest.raises(AmbiguousUnionError, match="matches multiple union variants"):
            confarg.from_dict(_Twins, {"u": {"class": f"{__name__}._TwinChild", "item": 1}})


class TestReadingAndRegistration:
    """Expressions and flag registration read the bound types too."""

    def test_an_expression_reads_a_bound_leaf_as_its_value(self) -> None:
        """``${b.item + 1}`` computes on the int ``Box[int]`` builds."""
        built = confarg.load(_g.Holder, argv=["--b.item", "3", "--pair.key", "k${b.item + 1}"], env={})
        assert built.pair == _g.Pair(key="k4")

    def test_a_flag_is_described_by_its_bound_type(self) -> None:
        """``--help`` shows ``INT`` where a parameter is bound to int, ``ANY`` where nothing binds it."""
        metavars = {s.name: s.metavar for s in build_static_flags(_g.Holder)}
        assert (metavars["b.item"], metavars["bare.item"], metavars["ic.item"], metavars["tagged.item"]) == (
            "INT",
            "ANY",
            "INT",
            "INT",
        )

    def test_the_tag_flag_of_a_generic_base_lists_its_subclasses(self) -> None:
        """A parameterized base with subclasses registers its tag flag as a class does."""
        tag = next(s for s in build_static_flags(_g.Holder) if s.name == "tagged.class")
        assert "'Tagged'" in (tag.note or "")


def _defined(source: str) -> Any:
    """Return the last class *source* defines, a syntax Python 3.12 does not parse."""
    namespace: dict[str, Any] = {"dataclass": dataclass}
    exec(source, namespace)  # PEP 696 syntax is a SyntaxError before 3.13
    return [v for v in namespace.values() if isinstance(v, type)][-1]


@pytest.mark.skipif(sys.version_info < (3, 13), reason="PEP 696 type parameter defaults need Python 3.13")
class TestADefaultedParameter:
    """A bare generic reads a parameter's PEP 696 default, as a type checker does."""

    def test_a_typevar_default(self) -> None:
        """A bare ``D`` with ``T = int`` reads ``item`` as an int."""
        cls = _defined("@dataclass\nclass D[T = int]:\n    item: T\n")
        with pytest.raises(TypeCoercionError, match=re.escape("Cannot coerce str 'x' to int at 'item'")):
            confarg.from_dict(cls, {"item": "x"})

    def test_a_typevartuple_default(self) -> None:
        """A bare ``D`` with ``*Ts = *tuple[int, ...]`` reads ``tuple[*Ts]`` as ``tuple[int, ...]``."""
        cls = _defined("@dataclass\nclass D[*Ts = *tuple[int, ...]]:\n    dims: tuple[*Ts]\n")
        assert confarg.load(cls, argv=["--dims", "1", "2"], env={}).dims == (1, 2)

    def test_a_builtins_subclass_reads_the_default_as_a_struct_does(self) -> None:
        """``_builtin_args`` binds with the same defaults: a bare ``Scores`` is a ``dict[str, int]``."""
        scores = _defined("class Scores[V = int](dict[str, V]):\n    pass\n")
        with pytest.raises(TypeCoercionError, match=re.escape("Cannot coerce str 'x' to int at 's.a'")):
            confarg.from_dict(make_target("s", scores), {"s": {"a": "x"}})


class TestPostponedAnnotations:
    """Under ``from __future__ import annotations``, a method names its class's parameters in strings."""

    def test_a_constructor_resolves_its_class_parameters(self) -> None:
        """``__init__(self, item: T)``'s ``'T'`` is the class's own, not ``Any`` for want of a global."""
        with pytest.raises(TypeCoercionError, match=re.escape("Cannot coerce str 'x' to int at 'item'")):
            confarg.from_dict(_postponed.Handwritten[int], {"item": "x"})
