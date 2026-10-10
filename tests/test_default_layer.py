# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Unit tests for _default_layer: which defaults are laid under the data, and where."""

from __future__ import annotations

import copy
import enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NamedTuple

import pytest

from confarg import _defaults
from confarg._default_layer import drop_untouched, lay_defaults
from confarg._merge import ListOp

_TAG = _defaults.UNION_TAG


class _Color(enum.Enum):
    RED = "red"


class _Pair(NamedTuple):
    x: int = 1
    y: int = 2


_PAIR = _Pair()


@dataclass
class _Leaves:
    """One default of each leaf kind, a tuple, a namedtuple and the kinds that are not laid."""

    n: int = 42
    f: float = 0.5
    b: bool = True
    s: str = "plain"
    e: str = "${HOME}"
    none: int | None = None
    color: _Color = _Color.RED
    path: Path = Path("/tmp")  # a default value, nothing is written there
    t: tuple[int, int] = (0, 0)
    pair: _Pair = _PAIR
    xs: list[int] = field(default_factory=lambda: [1])
    required: int = field(default=0)


@dataclass
class _Inner:
    """A struct whose fields all have defaults."""

    port: int = 80


@dataclass
class _NeedsHost:
    """A struct with a field that has no default."""

    host: str
    port: int = 80


@dataclass
class _Outer:
    """A required all-default struct, a required needy one, a factory default."""

    inner: _Inner
    needy: _NeedsHost
    made: _Inner = field(default_factory=lambda: _Inner(port=1))


@dataclass
class _Base:
    """A struct a tag dispatches below."""

    size: int = 1


@dataclass
class _Wide(_Base):
    """A subclass with its own default."""

    size: int = 9


@dataclass
class _HoldsBase:
    """A field whose class a tag selects."""

    shape: _Base = field(default_factory=_Base)


@dataclass
class _Other:
    """A second struct, for a union."""

    size: int = 5


@dataclass
class _HoldsUnion:
    """Optional and multi-variant union fields."""

    opt: _Inner | None = None
    either: _Inner | _Other | None = None


@dataclass
class _HoldsList:
    """Struct items below a list, a dict and a tuple field."""

    items: list[_Inner] = field(default_factory=list)
    by_name: dict[str, _Inner] = field(default_factory=dict)
    t: tuple[int, ...] = (0, 1)


def _lay(target: Any, data: dict[Any, Any], *, for_resolution: bool = True) -> tuple[dict[Any, Any], set[Any]]:
    laid = lay_defaults(target, data, _TAG, for_resolution=for_resolution)
    return laid.data, set(laid.untouched)


class TestWhatIsLaid:
    """Tier 1: a value the class declares, read without running code."""

    def test_leaves_tuples_and_namedtuples_are_laid_untouched(self) -> None:
        """Each leaf as it is, a tuple and a namedtuple as their positional list."""
        data, untouched = _lay(_Leaves, {})
        assert data == {
            "n": 42,
            "f": 0.5,
            "b": True,
            "s": "plain",
            "e": "$${HOME}",
            "none": None,
            "color": _Color.RED,
            "path": Path("/tmp"),  # the default above
            "t": [0, 0],
            "pair": [1, 2],
            "required": 0,
        }
        assert untouched == {(k,) for k in data}

    def test_a_string_is_escaped_only_for_resolution(self) -> None:
        """``from_dict()`` resolves nothing, so it lays nothing it would have to escape."""
        data, untouched = _lay(_Leaves, {"t": {ListOp.APPEND: [1]}}, for_resolution=False)
        assert data == {"t": [0, 0, 1]}
        assert untouched == set()

    def test_a_factory_is_never_called(self) -> None:
        """``default_factory`` is tier 2: not laid, not run."""

        def refuse() -> list[int]:
            raise AssertionError

        @dataclass
        class _Factory:
            xs: list[int] = field(default_factory=refuse)

        assert _lay(_Factory, {}) == ({}, set())

    def test_a_tuple_of_instances_is_not_laid(self) -> None:
        """A struct instance is tier 3, inside a tuple too."""

        @dataclass
        class _HoldsInstances:
            pair: tuple[_Inner, _Inner] = (_Inner(), _Inner())

        assert _lay(_HoldsInstances, {}) == ({}, set())


class TestWhereItIsLaid:
    """Below the nodes construction builds as one known class, and nowhere else."""

    def test_a_required_all_default_struct_is_laid_whole(self) -> None:
        """Construction builds it from ``{}``, so its class's defaults are what it holds."""
        data, untouched = _lay(_Outer, {})
        assert data == {"inner": {"port": 80}}
        assert untouched == {("inner",)}

    def test_a_present_node_gets_its_classs_defaults(self) -> None:
        """Below a node the data holds, every absent field with a default is laid."""
        data, untouched = _lay(_Outer, {"needy": {"host": "h"}, "made": {}})
        assert data["needy"] == {"host": "h", "port": 80}
        assert data["made"] == {"port": 80}
        assert ("needy", "port") in untouched

    def test_a_tag_lays_the_tagged_classs_defaults(self) -> None:
        """The class construction will build, not the annotation's."""
        data, _ = _lay(_HoldsBase, {"shape": {_TAG: f"{__name__}._Wide"}})
        assert data["shape"]["size"] == 9

    @pytest.mark.parametrize(
        "tag",
        ["${kind}", "no.such.Module", f"{__name__}._Other"],
        ids=["expression", "unimportable", "no-subclass"],
    )
    def test_an_uncertain_tag_lays_nothing(self, tag: str) -> None:
        """Where construction will refuse or the class is unknown, nothing is laid below."""
        node = {_TAG: tag}
        data, _ = _lay(_HoldsBase, {"shape": node})
        assert data["shape"] is node

    def test_an_optional_struct_gets_its_defaults(self) -> None:
        """The one non-None variant is certain."""
        data, _ = _lay(_HoldsUnion, {"opt": {}})
        assert data["opt"] == {"port": 80}

    def test_a_multi_variant_union_lays_nothing_without_a_tag(self) -> None:
        """Structural matching reads the keys, so no variant is certain."""
        data, _ = _lay(_HoldsUnion, {"either": {}})
        assert data["either"] == {}

    def test_a_tag_selects_one_variant(self) -> None:
        """A tag naming a subclass of exactly one variant lays that class's defaults."""
        data, _ = _lay(_HoldsUnion, {"either": {_TAG: f"{__name__}._Other"}})
        assert data["either"]["size"] == 5

    def test_containers_are_walked(self) -> None:
        """A list item, an appended item and a dict value each get the item's defaults."""
        data, untouched = _lay(
            _HoldsList,
            {"items": {ListOp.APPEND: [{}]}, "by_name": {"a": {}}},
        )
        assert data["items"] == {ListOp.APPEND: [{"port": 80}]}
        assert data["by_name"] == {"a": {"port": 80}}
        assert ("items", ListOp.APPEND, 0, "port") in untouched

    def test_a_carried_base_is_left_as_it_is(self) -> None:
        """A ``__base__`` replaces what lies below: the default is not combined with it."""
        node = {ListOp.BASE: [5], ListOp.APPEND: [6]}
        data, _ = _lay(_HoldsList, {"t": node})
        assert data["t"] == node

    def test_a_pin_is_left_as_it_is(self) -> None:
        """A cast pin is a value, read by construction."""
        pin = {_defaults.CAST_KEY: "int", _defaults.VALUE_KEY: 5}
        data, _ = _lay(_HoldsList, {"t": pin})
        assert data["t"] is pin

    def test_the_data_is_never_mutated(self) -> None:
        """Every node is copied where something is laid, and only there."""
        given = {"items": [{}], "t": {ListOp.APPEND: [2]}}
        kept = copy.deepcopy(given)
        _lay(_HoldsList, given)
        assert given == kept

    def test_a_non_struct_target_is_walked_below_its_root_key(self) -> None:
        """``__root__`` holds a non-struct target's value."""
        data, untouched = _lay(list[_Inner], {_defaults.ROOT_KEY: [{}]})
        assert data == {_defaults.ROOT_KEY: [{"port": 80}]}
        assert untouched == {(_defaults.ROOT_KEY, 0, "port")}

    def test_a_dict_target_lays_nothing(self) -> None:
        """No declaration, no default."""
        given = {"a": 1}
        assert _lay(dict[str, Any], given) == (given, set())


class TestDropUntouched:
    """What was laid untouched is taken out again, never by mutation."""

    def test_the_laid_defaults_come_back_out(self) -> None:
        """Laying then dropping gives the data back, a patched default kept."""
        laid = lay_defaults(_HoldsList, {"items": [{}], "t": {ListOp.APPEND: [2]}}, _TAG, for_resolution=True)
        assert drop_untouched(laid.data, laid.untouched) == {"items": [{}], "t": [0, 1, 2]}
