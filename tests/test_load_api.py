# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for the load() function signature: arg defaults, non-dataclass targets, return types."""

from __future__ import annotations

import dataclasses
import enum
import inspect
import threading
from collections.abc import Callable  # noqa: TC003  # a dataclass annotation confarg resolves at runtime
from pathlib import Path
from typing import Any, NamedTuple

import pytest

import confarg
import confarg.cli.argparse as confargargparse
import confarg.cli.click as confargclick
import confarg.cli.cyclopts as confargcyclopts
import confarg.cli.typer as confargtyper
from confarg import _defaults
from confarg._merge import ListOp, MergeDict, _deep_merge
from tests.conftest import (
    AppConfig,
    CacheConfig,
    DbConfig,
    Empty,
    Flat,
    WithDefaults,
)

# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------


class TestReturnType:
    """load() returns an instance of the target type."""

    def test_returns_correct_type(self) -> None:
        """load() returns an instance of the target dataclass."""
        result = confarg.load(WithDefaults, argv=[], env={})
        assert isinstance(result, WithDefaults)

    def test_returns_nested_types(self) -> None:
        """Nested dataclasses are correctly instantiated."""
        result = confarg.load(
            AppConfig,
            argv=["--db.host", "h", "--db.port", "1", "--db.name", "n"],
            env={},
        )
        assert isinstance(result, AppConfig)
        assert isinstance(result.db, DbConfig)
        assert isinstance(result.cache, CacheConfig)


# ---------------------------------------------------------------------------
# args parameter
# ---------------------------------------------------------------------------


class TestArgsParameter:
    """Behaviour of the args parameter."""

    def test_args_none_uses_sys_argv(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """argv=None reads from sys.argv[1:]."""
        monkeypatch.setattr(
            "sys.argv",
            ["prog", "--name", "argv_val", "--count", "1", "--rate", "0", "--verbose", "true"],
        )
        result = confarg.load(Flat, env={})
        assert result.name == "argv_val"

    def test_args_empty_list_no_cli(self) -> None:
        """argv=[] means no CLI parsing happens."""
        result = confarg.load(WithDefaults, argv=[], env={})
        assert result.name == "default"

    def test_args_explicit_list(self) -> None:
        """Explicit args list is used for parsing."""
        result = confarg.load(WithDefaults, argv=["--name", "explicit"], env={})
        assert result.name == "explicit"


# ---------------------------------------------------------------------------
# env parameter
# ---------------------------------------------------------------------------


class TestEnvParameter:
    """Behaviour of the env parameter."""

    def test_env_none_uses_os_environ(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """env=None reads from os.environ when an explicit env_prefix is set."""
        monkeypatch.setenv("MYAPP_NAME", "env_val")
        result = confarg.load(WithDefaults, argv=[], env_prefix="MYAPP_")
        assert result.name == "env_val"

    def test_env_none_disabled_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """env=None with default env_prefix=None means os.environ is not read."""
        monkeypatch.setenv("MYAPP_NAME", "should_be_ignored")
        result = confarg.load(WithDefaults, argv=[])
        assert result.name == "default"

    def test_env_empty_dict_no_env(self) -> None:
        """env={} means no env vars are read."""
        result = confarg.load(WithDefaults, argv=[], env={})
        assert result.name == "default"

    def test_env_explicit_dict(self) -> None:
        """Explicit env dict is used for parsing."""
        result = confarg.load(WithDefaults, argv=[], env={"MYAPP_NAME": "from_dict"}, env_prefix="MYAPP_")
        assert result.name == "from_dict"


# ---------------------------------------------------------------------------
# Non-dataclass targets
# ---------------------------------------------------------------------------


class TestNonDataclassTargets:
    """Using non-dataclass types as targets (with cli_prefix)."""

    def test_int_target(self) -> None:
        """Load a plain int via CLI with prefix."""
        result = confarg.load(int, argv=["--confarg", "42"], env={}, cli_prefix="confarg")
        assert result == 42

    def test_str_target(self) -> None:
        """Load a plain str via CLI with prefix."""
        result = confarg.load(str, argv=["--confarg", "hello"], env={}, cli_prefix="confarg")
        assert result == "hello"

    def test_bool_target(self) -> None:
        """Load a plain bool via CLI with prefix."""
        result = confarg.load(bool, argv=["--confarg", "true"], env={}, cli_prefix="confarg")
        assert result is True

    def test_float_target(self) -> None:
        """Load a plain float via env."""
        result = confarg.load(float, argv=[], env={"MYAPP_": "3.14"}, env_prefix="MYAPP_", cli_prefix="confarg")
        assert result == pytest.approx(3.14)


# ---------------------------------------------------------------------------
# Empty dataclass
# ---------------------------------------------------------------------------


class TestEmptyDataclass:
    """Edge case: dataclass with no fields."""

    def test_empty_dataclass(self) -> None:
        """Loading an empty dataclass succeeds."""
        result = confarg.load(Empty, argv=[], env={})
        assert isinstance(result, Empty)


# ---------------------------------------------------------------------------
# Keyword-only signature enforcement
# ---------------------------------------------------------------------------


class TestSignatureEnforcement:
    """load() keyword arguments are keyword-only (except target)."""

    def test_target_is_positional(self) -> None:
        """Target type can be passed positionally."""
        result = confarg.load(WithDefaults, argv=[], env={})
        assert isinstance(result, WithDefaults)

    def test_keyword_args_only(self) -> None:
        """Parameters after target are keyword-only (cannot be positional)."""
        # This test verifies the signature; it should raise TypeError
        # if someone tries to pass args positionally after target.
        with pytest.raises(TypeError):
            confarg.load(WithDefaults, [])  # ty: ignore[no-matching-overload]  # passing a positional list to verify keyword-only enforcement


# ---------------------------------------------------------------------------
# The one option set (REF-40)
# ---------------------------------------------------------------------------


#: Every public function that takes the merge options, vanilla and adapters alike.
_ENTRY_POINTS: list[Any] = [
    confarg.merge,
    confarg.load,
    confargargparse.merge_namespace,
    confargargparse.from_namespace,
    confargclick.merge_context,
    confargclick.from_context,
    confargtyper.merge_context,
    confargtyper.from_context,
    confargcyclopts.merge_app,
    confargcyclopts.from_app,
]


class TestMergeOptions:
    """Every front-end takes the one ``MergeOptions`` set, and refuses a key outside it."""

    @pytest.mark.parametrize("fn", _ENTRY_POINTS, ids=lambda fn: f"{fn.__module__}.{fn.__name__}")
    def test_takes_merge_options_as_its_only_keywords(self, fn: Any) -> None:
        """No entry point spells an option of its own beside ``**opts``."""
        params = inspect.signature(fn).parameters.values()
        keywords = [p for p in params if p.kind is not inspect.Parameter.POSITIONAL_OR_KEYWORD]
        assert [(p.name, p.kind) for p in keywords] == [("opts", inspect.Parameter.VAR_KEYWORD)]

    @pytest.mark.parametrize("fn", _ENTRY_POINTS, ids=lambda fn: f"{fn.__module__}.{fn.__name__}")
    def test_unknown_keyword_is_refused(self, fn: Any) -> None:
        """A misspelled option raises the TypeError Python raises for an unexpected keyword."""
        # The framework object is never reached: the options are checked first.
        args = (WithDefaults,) if fn in (confarg.merge, confarg.load) else (WithDefaults, object())
        with pytest.raises(TypeError, match=rf"^{fn.__name__}\(\) got an unexpected keyword argument 'env_prefx'$"):
            fn(*args, argv=[], env_prefx="APP_")

    def test_resolved_options_declare_the_same_keys(self) -> None:
        """The private resolved form names exactly the keys the public TypedDict declares."""
        fields = {f.name for f in dataclasses.fields(_defaults._Options)}
        assert fields == confarg.MergeOptions.__optional_keys__
        assert not confarg.MergeOptions.__required_keys__


#: The keyword the class key's spelling was once passed as, which no entry point takes now.
_UNION_TAG: dict[str, Any] = {"union_tag": "kind"}

_UNION_TAG_TAKERS: list[Any] = [
    pytest.param(lambda: confarg.merge(WithDefaults, argv=[], env={}, **_UNION_TAG), id="merge"),
    pytest.param(lambda: confarg.load(WithDefaults, argv=[], env={}, **_UNION_TAG), id="load"),
    pytest.param(lambda: confarg.build(WithDefaults, {}, **_UNION_TAG), id="build"),
    pytest.param(lambda: confarg.from_dict(WithDefaults, {}, **_UNION_TAG), id="from_dict"),
    pytest.param(lambda: confarg.resolve(WithDefaults, {}, **_UNION_TAG), id="resolve"),
    pytest.param(lambda: confarg.dump(WithDefaults(), **_UNION_TAG), id="dump"),
    pytest.param(lambda: confargargparse.make_parser(WithDefaults, argv=[], **_UNION_TAG), id="make_parser"),
]


class TestTheClassKeyIsNoOption:
    """The class key is always ``class``: no entry point takes a ``union_tag`` (REF-121)."""

    @pytest.mark.parametrize("call", _UNION_TAG_TAKERS)
    def test_union_tag_is_an_unexpected_keyword(self, call: Any) -> None:
        """Each entry point refuses it as the unknown keyword it is."""
        with pytest.raises(TypeError, match=r"unexpected keyword argument 'union_tag'"):
            call()


# ---------------------------------------------------------------------------
# A field default is the base layer (FEAT-37)
# ---------------------------------------------------------------------------


class _DefaultPair(NamedTuple):
    x: int
    y: int


_SHARED_PATH = Path("/srv")
_DEFAULT_PAIR = _DefaultPair(1, 2)


@dataclasses.dataclass
class _Defaults:
    """Defaults an expression reads, a patch applies over, or construction alone applies."""

    n: int = 42
    m: int = 0
    v: tuple[int, ...] = (0, 1)
    pt: _DefaultPair = _DEFAULT_PAIR
    d: tuple[dict[str, int], int] = ({"a": 1}, 0)
    literal: str = "$${a} and ${b}"
    sloppy_float: float = 1
    sloppy_int: int = None  # ty: ignore[invalid-assignment]  # a sloppy default the class declares
    shared: Path = _SHARED_PATH


class TestAFieldDefaultIsTheBaseLayer:
    """``build()``, ``resolve()`` and ``from_dict()`` lay the target's defaults below the data."""

    def test_resolve_reads_a_default_and_leaves_it_out(self) -> None:
        """``${n}`` reads 42; the untouched default is construction's to apply."""
        assert confarg.resolve(_Defaults, {"m": "${n}"}) == {"m": 42}

    def test_resolve_applies_a_pending_patch_over_a_default(self) -> None:
        """The pending append lands on the default, as over a lower file's list."""
        assert confarg.resolve(_Defaults, {"v": {ListOp.APPEND: [3]}}) == {"v": [0, 1, 3]}

    @pytest.mark.parametrize(
        "raw",
        [
            {"v": {ListOp.APPEND: [3]}},
            {"pt": {"y": 5}},
            {"d": {"0": {"b": 2}}},
            {"m": "${n}"},
        ],
        ids=["append", "namedtuple-name", "refinement", "expression"],
    )
    def test_the_three_steps_build_what_build_builds(self, raw: dict[Any, Any]) -> None:
        """``from_dict(resolve())`` lays the defaults again without changing what resolve applied."""
        assert confarg.from_dict(_Defaults, confarg.resolve(_Defaults, raw)) == confarg.build(_Defaults, raw)

    def test_from_dict_patches_a_default_it_does_not_resolve(self) -> None:
        """No resolution follows, so nothing is escaped and a pending op still applies."""
        assert confarg.from_dict(_Defaults, {"v": {ListOp.APPEND: [3]}}).v == (0, 1, 3)

    def test_a_default_spelled_like_an_expression_comes_out_as_written(self) -> None:
        """The escape and the expression in the default both survive byte for byte."""
        assert confarg.resolve(_Defaults, {"m": "${literal}"})["m"] == "$${a} and ${b}"
        assert confarg.build(_Defaults, {}).literal == "$${a} and ${b}"

    def test_a_default_construction_would_refuse_still_builds(self) -> None:
        """An untouched default is never built through ``construct()``: the class's object is kept."""
        built = confarg.build(_Defaults, {})
        assert built.sloppy_float == 1
        assert built.sloppy_int is None
        assert built.shared is _SHARED_PATH

    def test_from_dict_unwraps_a_non_struct_root(self) -> None:
        """``from_dict(list[int], resolve(...))`` builds what ``build()`` does (5c)."""
        raw = confarg.merge(list[int], argv=["--json", "[1, 2]"], env={})
        assert confarg.from_dict(list[int], confarg.resolve(list[int], raw)) == confarg.build(list[int], raw) == [1, 2]


class _Colour(enum.Enum):
    """An enum whose name and value are spelled apart."""

    RED = "red"


@dataclasses.dataclass
class _Dirs:
    """A section holding a registered leaf."""

    root: Path = Path("/r")
    kind: _Colour = _Colour.RED


@dataclasses.dataclass
class _Typed:
    """Leaves an expression reads as their object where construction builds one, and an ``Any`` it reads as written."""

    colour: _Colour = _Colour.RED
    again: _Colour = _Colour.RED
    other: _Colour = _Colour.RED
    ps: list[Path] = dataclasses.field(default_factory=list)
    opt: Path | None = None
    either: Path | str = ""
    anything: Any = None
    dirs: _Dirs = dataclasses.field(default_factory=_Dirs)
    out: Any = None
    same: bool = False
    real: float = 0.0
    real_or_text: float | str = ""


class TestAnExpressionReadsATypedLeaf:
    """``build()`` and ``resolve()`` read an Enum or registered leaf as its object, and write its dump form."""

    def test_resolve_writes_a_result_in_its_dump_form_and_keeps_the_rest_as_written(self) -> None:
        """Only what an expression produced is rewritten; ``RED`` stays as the source spelled it."""
        assert confarg.resolve(_Typed, {"colour": "RED", "out": "${colour}"}) == {"colour": "RED", "out": "red"}

    @pytest.mark.parametrize(
        ("raw", "out"),
        [
            ({"ps": ["/x"], "out": "${ps[0] / 'y'}"}, "/x/y"),
            ({"opt": "/x", "out": "${opt / 'y'}"}, "/x/y"),
            ({"dirs": {"root": "/x"}, "out": "${dirs.root / 'y'}"}, "/x/y"),
            ({"dirs": {"kind": "RED"}, "out": "${dirs}"}, {"root": "/r", "kind": "red"}),
        ],
        ids=["list-item", "optional", "struct-field", "subtree"],
    )
    def test_a_single_certain_type_reads_the_object(self, raw: dict[str, Any], out: Any) -> None:
        """Below a list, an optional and a struct, and through a subtree read, the leaf is its object."""
        assert confarg.resolve(_Typed, raw)["out"] == out

    def test_an_any_leaf_reads_as_written(self) -> None:
        """``Any`` leaves the string a string, as construction does."""
        with pytest.raises(confarg.exceptions.ExpressionEvalError, match="'str' and 'str'"):
            confarg.resolve(_Typed, {"anything": "/x", "out": "${anything / 'y'}"})

    def test_a_union_leaf_reads_as_the_variant_construction_picks(self) -> None:
        """``Path | str`` builds a file's ``/x`` as a ``Path``, and an expression reads that ``Path`` (BUG-230)."""
        assert confarg.resolve(_Typed, {"either": "/x", "out": "${either / 'y'}"})["out"] == "/x/y"
        assert confarg.build(_Typed, {"either": "/x"}).either == Path("/x")

    def test_an_earlier_result_is_read_as_its_object_too(self) -> None:
        """``again`` holds the dump form ``red`` once resolved, and still reads as the member ``other`` is."""
        assert confarg.build(_Typed, {"colour": "RED", "again": "${colour}", "same": "${again == other}"}).same

    @pytest.mark.parametrize(
        ("raw", "out"),
        [
            ({"real": 1, "out": "${str(real)}"}, "1.0"),
            ({"real_or_text": 1, "out": "${str(real_or_text)}"}, "1.0"),
            ({"real": "${1 + 1}", "out": "${str(real)}"}, "2.0"),
        ],
        ids=["float", "float-or-str", "an-expression-result"],
    )
    def test_a_file_int_reads_as_the_float_it_builds(self, raw: dict[str, Any], out: str) -> None:
        """A reference reads the built value: an int at a ``float`` position builds and reads ``1.0`` (BUG-154)."""
        assert confarg.build(_Typed, raw).out == out

    def test_a_value_the_type_refuses_reads_as_written(self) -> None:
        """No coercion error at resolution: the text is left for construction to refuse."""
        assert confarg.resolve(_Typed, {"colour": "purple", "out": "${colour}"})["out"] == "purple"


@dataclasses.dataclass
class _Spot:
    """A registered leaf, built from one value or, under a class key, from its fields."""

    x: int = 0


@dataclasses.dataclass
class _SubSpot(_Spot):
    """An unregistered subclass of a registered leaf, so a struct."""

    y: int = 0


@dataclasses.dataclass
class _SpotBase:
    """A struct a registered leaf subclasses."""

    x: int = 0


@dataclasses.dataclass
class _LeafSpot(_SpotBase):
    """A registered leaf subclassing a struct."""


@dataclasses.dataclass
class _Dial:
    """A registered leaf whose instances are callable."""

    x: int = 0

    def __call__(self) -> int:
        return self.x


@dataclasses.dataclass
class _Positive:
    """A registered leaf whose constructor refuses a negative x with its own exception."""

    x: int = 0

    def __post_init__(self) -> None:
        if self.x < 0:
            msg = "x must be >= 0"
            raise ValueError(msg)


@dataclasses.dataclass
class _Elsewhere:
    """A struct beside a registered leaf in a union."""

    n: int = 0


_SPOT_CALLS: list[int] = []


def _spot_x() -> int:
    """Return the x of a spot, counting each call."""
    _SPOT_CALLS.append(1)
    return 3


@dataclasses.dataclass
class _Tagged:
    """Every position a class key builds a registered leaf at, and the fields an expression writes it to."""

    origin: _Spot | None = None
    plain: _Spot = dataclasses.field(default_factory=_Spot)
    either: _Spot | _Elsewhere | None = None
    spots: list[_Spot] = dataclasses.field(default_factory=list)
    base: _SpotBase | None = None
    anything: Any = None
    dial: Callable[[], int] | None = None
    positive: _Positive | None = None
    out: Any = None
    label: str = ""
    same: bool = False


def _tag(cls: type, **fields: Any) -> dict[str, Any]:
    """Return the dict whose class key names *cls*, built from *fields*."""
    return {"class": f"{cls.__module__}.{cls.__qualname__}", **fields}


class TestAnExpressionReadsATaggedLeaf:
    """A registered leaf written as a dict whose class key names it reads as the object it builds (BUG-283)."""

    @pytest.fixture(autouse=True)
    def _register(self, leaf_registry: None) -> None:
        confarg.register_leaf_type(_Spot, lambda v: _Spot(int(v)), serialize=lambda s: str(s.x))
        confarg.register_leaf_type(_LeafSpot, lambda v: _LeafSpot(int(v)), serialize=lambda s: str(s.x))
        confarg.register_leaf_type(_Dial, lambda v: _Dial(int(v)), serialize=lambda d: str(d.x))
        confarg.register_leaf_type(_Positive, lambda v: _Positive(int(v)), serialize=lambda p: str(p.x))

    @pytest.mark.parametrize(
        ("raw", "reference"),
        [
            ({"origin": _tag(_Spot, x=3)}, "origin"),
            ({"plain": _tag(_Spot, x=3)}, "plain"),
            ({"either": _tag(_Spot, x=3)}, "either"),
            ({"spots": [_tag(_Spot, x=3), "4"]}, "spots[0]"),
            ({"base": _tag(_LeafSpot, x=3)}, "base"),
            ({"anything": _tag(_LeafSpot, x=3)}, "anything"),
        ],
        ids=["optional", "leaf", "union", "list-item", "struct-base", "any"],
    )
    def test_an_interpolation_writes_the_dump_form_of_the_leaf_the_tag_builds(
        self, raw: dict[str, Any], reference: str
    ) -> None:
        """Wherever the class key names a registered leaf, the reference reads what construction builds there."""
        assert confarg.build(_Tagged, {**raw, "label": f"at ${{{reference}}}"}).label == "at 3"

    def test_a_tagged_leaf_compares_with_the_same_leaf_spelled_by_its_value(self) -> None:
        """``${origin == plain}`` is the built ``origin == plain``, one spelled by its fields, one by its value."""
        assert confarg.build(_Tagged, {"origin": _tag(_Spot, x=3), "plain": "3", "same": "${origin == plain}"}).same

    def test_a_whole_value_reference_leaves_the_dump_form(self) -> None:
        """A pure reference leaves what the leaf dumps as, which an ``Any`` holds as text."""
        raw = {"origin": _tag(_Spot, x=3), "plain": "${origin}", "out": "${origin}", "spots": ["${origin}"]}
        assert confarg.resolve(_Tagged, raw) == {**raw, "plain": "3", "out": "3", "spots": ["3"]}
        built = confarg.build(_Tagged, raw)
        assert (built.plain, built.out, built.spots) == (_Spot(3), "3", [_Spot(3)])

    def test_a_field_below_the_tag_reads_as_the_member(self) -> None:
        """``${origin.x}`` reads the field the tagged dict holds, which is the built ``origin.x``."""
        assert confarg.build(_Tagged, {"origin": _tag(_Spot, x=3), "same": "${origin.x == 3}"}).same

    def test_an_unregistered_subclass_reads_as_its_dict(self) -> None:
        """A class key naming a subclass no registration reads builds a struct, which reads as its dict."""
        sub = _tag(_SubSpot, x=3, y=4)
        built = confarg.build(_Tagged, {"origin": sub, "plain": "${origin}", "label": "at ${origin}"})
        assert built.plain == _SubSpot(3, 4)
        assert built.label == f"at {sub}"

    def test_a_value_the_tag_refuses_reads_as_written(self) -> None:
        """No coercion error at resolution: the dict is left for construction to refuse."""
        refused = _tag(_Spot, x="zz")
        assert confarg.resolve(_Tagged, {"origin": refused, "out": "${origin}"})["out"] == refused

    def test_a_value_the_constructor_refuses_reads_as_written(self) -> None:
        """The constructor's own exception is construction's to raise, not the reading's."""
        refused = _tag(_Positive, x=-1)
        assert confarg.resolve(_Tagged, {"positive": refused, "out": "${positive}"})["out"] == refused
        with pytest.raises(ValueError, match="x must be >= 0"):
            confarg.build(_Tagged, {"positive": refused})

    def test_a_tagged_leaf_holding_a_call_reads_as_written(self) -> None:
        """The reading runs no ``call:``: an expression cannot read a call's result before construction."""
        _SPOT_CALLS.clear()
        held = _tag(_Spot, x={"call": f"{__name__}._spot_x"})
        built = confarg.build(_Tagged, {"origin": held, "label": "at ${origin}"})
        assert (built.origin, built.label, len(_SPOT_CALLS)) == (_Spot(3), f"at {held}", 1)

    def test_a_callable_position_reads_the_leaf_it_builds(self) -> None:
        """A class key at a Callable builds the registered leaf it names, which the reference reads."""
        built = confarg.build(_Tagged, {"dial": _tag(_Dial, x=3), "label": "at ${dial}"})
        assert (built.dial, built.label) == (_Dial(3), "at 3")


@dataclasses.dataclass
class _Port:
    """A section whose one field has a default."""

    p: int = 3


@dataclasses.dataclass
class _Deleted:
    """Fields a key delete may find nothing below (BUG-98)."""

    data: dict[str, int] = dataclasses.field(default_factory=dict)
    sub: _Port = dataclasses.field(default_factory=_Port)
    opt: _Port | None = None
    a: Any = None
    ld: list[dict[str, int]] = dataclasses.field(default_factory=list)
    xs: list[int] = dataclasses.field(default_factory=list)
    s: str = "s"


class TestAKeyDeleteThatMeetsNothingDeletesNothing:
    """A key delete no layer met, the defaults included, is dropped by ``build()`` (BUG-98).

    It once reached construction as the merge's sentinel, which a typed field refused as
    ``Cannot coerce _DeleteSentinel _DELETE_``, an ``Any`` built into its value, and an
    expression read.
    """

    @pytest.mark.parametrize(
        ("argv", "field", "built"),
        [
            (["--data.x-"], "data", {}),
            (["--sub.p-"], "sub", _Port(3)),
            (["--opt.p-"], "opt", None),
            (["--a.k-"], "a", None),
            (["--a.k.z-"], "a", None),
            (["--ld.0.k-"], "ld", []),
            (["--json", '{"data": {}}', "--data.x-"], "data", {}),
        ],
        ids=["dict-key", "struct-field", "optional-struct", "any-key", "any-nested", "list-item-key", "written-empty"],
    )
    def test_it_builds_as_if_not_given(self, argv: list[str], field: str, built: Any) -> None:
        """Each builds what the target builds with no flag at all, a dict a source wrote kept."""
        assert getattr(confarg.load(_Deleted, argv=argv, env={}), field) == built

    def test_the_environment_alike(self) -> None:
        """``APP_DATA__X-`` with no base builds the empty default, as ``--data.x-`` does."""
        assert confarg.load(_Deleted, argv=[], env={"APP_DATA__X-": "x"}, env_prefix="APP_").data == {}

    def test_merge_keeps_it_for_a_layer_below(self) -> None:
        """``merge()`` keeps the delete, so a dumped merge still deletes what a lower file holds (BUG-202)."""
        assert confarg.merge(_Deleted, argv=["--data.x-"], env={}) == {"data": {"x": confarg._merge.DICT_DELETE}}

    def test_an_expression_reads_the_key_as_absent(self) -> None:
        """``${data.x}`` misses, as with no flag, rather than reading the sentinel."""
        with pytest.raises(confarg.exceptions.MissingReferenceError):
            confarg.load(_Deleted, argv=["--data.x-", "--s", "${data.x}"], env={})

    def test_resolve_holds_no_delete(self) -> None:
        """``resolve()`` hands ``from_dict()`` what ``build()`` constructs from."""
        raw = confarg.merge(_Deleted, argv=["--sub.p-", "--data.x-", "--data.y", "1"], env={})
        assert confarg.resolve(_Deleted, raw) == {"data": {"y": 1}}
        assert confarg.from_dict(_Deleted, raw) == confarg.build(_Deleted, raw) == _Deleted(data={"y": 1})

    def test_an_index_delete_with_no_base_list_is_still_refused(self) -> None:
        """An index names a position, which nothing below gives it."""
        with pytest.raises(confarg.exceptions.TypeCoercionError, match="requires a base list"):
            confarg.load(_Deleted, argv=["--xs.0-"], env={})


@dataclasses.dataclass
class _ComputedLayer:
    n: int = 1
    derived: int = dataclasses.field(init=False, default=0)
    echo: int = -1

    def __post_init__(self) -> None:
        self.derived = self.n * 10


@dataclasses.dataclass
class _SeededLayer:
    n: int = 1
    seed: dataclasses.InitVar[int] = 4
    echo: int = -1

    def __post_init__(self, seed: int) -> None:
        self.n += seed


class TestOnlyAMemberIsLaid:
    """The default layer lays the defaults of the parameters a struct is built from, nothing else (FEAT-14)."""

    def test_an_init_false_default_is_not_laid(self) -> None:
        """A computed field is not data, so no reference reads its declared default as if it were built."""
        with pytest.raises(confarg.exceptions.MissingReferenceError, match="derived"):
            confarg.build(_ComputedLayer, {"n": 3, "echo": "${derived}"})

    def test_an_init_var_default_is_laid(self) -> None:
        """An ``InitVar`` is a parameter, so a reference reads its default as construction passes it."""
        assert confarg.build(_SeededLayer, {"echo": "${seed}"}).echo == 4


# ---------------------------------------------------------------------------
# A pending list op is read as the list it makes (BUG-220)
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class _Pending:
    """Lists a pending op may stand at, and fields an expression reads them into."""

    names: list[str] = dataclasses.field(default_factory=list)
    nested: list[list[str]] = dataclasses.field(default_factory=list)
    other: list[str] = dataclasses.field(default_factory=list)
    either: list[int] | dict[str, int] | None = None
    anything: Any = None
    first: str = ""
    count: int = 0


class TestAPendingOpIsReadAsItsList:
    """``build()`` applies a pending op over what lies below it before an expression reads the list."""

    @pytest.mark.parametrize(
        ("argv", "count"),
        [
            pytest.param(["--names+", "a", "b", "c"], 3, id="append-alone"),
            pytest.param(["--names", "a", "b", "--names+", "c"], 3, id="base-and-append-in-one-layer"),
            pytest.param(["--names", "a", "b", "--names.0-"], 1, id="delete-in-one-layer"),
            pytest.param(["--names.0", "x", "--names.1", "y"], 2, id="index-keyed"),
        ],
    )
    def test_len_counts_the_items(self, argv: list[str], count: int) -> None:
        """The op dict's keys were counted, two for three items."""
        assert confarg.load(_Pending, argv=[*argv, "--count", "${len(names)}"], env={}).count == count

    @pytest.mark.parametrize(
        ("argv", "first"),
        [
            pytest.param(["--names+", "a", "--first", "${names[0]}"], "a", id="first-appended"),
            pytest.param(["--names", "a", "--names+", "b", "--first", "${names[1]}"], "b", id="after-a-base"),
            pytest.param(["--names.0", "x", "--first", "${names[-1]}"], "x", id="negative-index-into-index-keys"),
        ],
    )
    def test_an_index_reads_an_item(self, argv: list[str], first: str) -> None:
        """``${names[0]}`` found no key ``0`` in the op dict."""
        assert confarg.load(_Pending, argv=argv, env={}).first == first

    def test_a_files_op_reads_as_its_list(self) -> None:
        """A file's ``__append__`` with nothing below it is the list it makes."""
        assert confarg.build(_Pending, {"names": {ListOp.APPEND: ["a"]}, "first": "${names[0]}"}).first == "a"

    def test_resolve_holds_no_pending_op(self) -> None:
        """No layer is left below, so the list is final."""
        raw = confarg.merge(_Pending, argv=["--names", "a", "--names+", "b"], env={})
        assert raw["names"] == {ListOp.BASE: ["a"], ListOp.APPEND: ["b"]}
        assert confarg.resolve(_Pending, raw) == {"names": ["a", "b"]}

    def test_from_dict_strips_and_builds_the_same(self) -> None:
        """``from_dict(resolve())`` builds what ``build()`` builds."""
        raw = confarg.merge(_Pending, argv=["--names+", "a", "--count", "${len(names)}"], env={})
        assert confarg.from_dict(_Pending, confarg.resolve(_Pending, raw)) == confarg.build(_Pending, raw)

    def test_a_union_of_a_list_and_a_dict_reads_the_list(self) -> None:
        """Only the list variant takes a list op, and construction builds it there."""
        result = confarg.load(_Pending, argv=["--either+", "1", "2", "3", "--count", "${len(either)}"], env={})
        assert (result.either, result.count) == ([1, 2, 3], 3)

    def test_an_item_appended_has_its_index_as_key(self) -> None:
        """``${key(.)}`` was refused as held by a pending op; the appended list's index is its key."""
        raw = {"nested": {ListOp.APPEND: [["${str(key(.))}"]]}}
        assert confarg.build(_Pending, raw).nested == [["0"]]

    def test_an_index_delete_with_nothing_below_is_still_refused(self) -> None:
        """An index names a position nothing below gives: construction's refusal, unchanged."""
        with pytest.raises(confarg.exceptions.TypeCoercionError, match=r"requires a base list"):
            confarg.build(_Pending, {"names": {ListOp.DELETE: [0]}})

    def test_a_scalar_append_of_an_expression_is_one_item(self) -> None:
        """A list the expression resolves to is the one item, as over a base (Q3)."""
        raw = {"other": ["x", "y"], "nested": {ListOp.APPEND: "${other}"}}
        assert confarg.build(_Pending, raw).nested == [["x", "y"]]

    def test_a_scalar_append_of_an_expression_over_a_base_is_one_item(self) -> None:
        """The merge appends it as one item over a lower file's list too."""
        raw: MergeDict = {"other": ["x", "y"], "nested": [["z"]]}
        over: MergeDict = {"nested": {ListOp.APPEND: "${other}"}}
        assert confarg.build(_Pending, _deep_merge(raw, over)).nested == [["z"], ["x", "y"]]

    def test_a_read_of_an_op_left_pending_is_refused(self) -> None:
        """At an ``Any`` no type says the op makes a list: a read is refused, never the op dict."""
        raw = {"anything": {ListOp.APPEND: [1, 2, 3]}, "count": "${len(anything)}"}
        with pytest.raises(confarg.exceptions.MissingReferenceError, match=r"anything.*list op"):
            confarg.resolve(_Pending, raw)


@dataclasses.dataclass
class _Bug266A:
    a: int = 0


class TestAMixedRootBuildsFromRootOrFields:
    """``build()`` reads a mixed root's whole value from ``__root__``, or its struct from its fields (BUG-266)."""

    def test_the_whole_value(self) -> None:
        """``__root__`` holds the value of a variant that is no struct."""
        assert confarg.build(int | _Bug266A, {"__root__": 5}) == 5
        assert confarg.build(int | _Bug266A, {"a": 3}) == _Bug266A(a=3)

    @pytest.mark.parametrize("entry", [confarg.build, confarg.from_dict], ids=["build", "from_dict"])
    def test_both_are_refused(self, entry: Any) -> None:
        """No flag or variable leaves both; a dict that holds them says nothing of which was written last."""
        with pytest.raises(confarg.exceptions.TypeCoercionError) as exc_info:
            entry(int | _Bug266A, {"__root__": 5, "a": 3})
        assert str(exc_info.value) == (
            "Cannot build int | _Bug266A at the root from the key(s) ['a']:"
            " '__root__' sets its whole value, so no key can be set beside it."
        )


class TestARootSetWholeReadsNoKeyBesideItsRoot:
    """``build()`` refuses a key beside ``__root__`` at a root that is no struct, as at a mixed one, and dropped it."""

    @pytest.mark.parametrize(
        ("target", "data", "spelled"),
        [
            pytest.param(int, {"__root__": 5, "port": 1}, "int", id="beside"),
            pytest.param(int, {"port": 1}, "int", id="alone"),
            pytest.param(list[int], {"__root__": [1], "port": 1}, "list[int]", id="list"),
        ],
    )
    def test_the_key_is_refused(self, target: Any, data: dict[str, Any], spelled: str) -> None:
        """Nothing reads the key, so a file that holds it says something no value carries."""
        with pytest.raises(confarg.exceptions.TypeCoercionError) as exc_info:
            confarg.build(target, data)
        assert str(exc_info.value) == (
            f"Cannot build {spelled} at the root from the key(s) ['port']:"
            " '__root__' sets its whole value, so no key can be set beside it."
        )

    def test_the_locals_and_an_op_stand_beside_it(self) -> None:
        """The locals namespace is no key of the value, and a pending op at the root is BUG-287's."""
        assert confarg.build(int, {"__root__": "${locals.n}", "locals": {"n": 5}}) == 5
        assert confarg.build(list[int], {"__root__": [5], ListOp.APPEND: [3]}) == [5]


@dataclasses.dataclass
class _Bug284:
    client: Any = None
    other: Any = None
    name: str = "app"
    label: str = ""


class TestBuildKeepsTheObjectsItIsHanded:
    """An expression anywhere in the data copies none of the objects ``build()`` is handed (BUG-284)."""

    def test_an_object_is_the_callers_own(self) -> None:
        """With an expression or without, an ``Any`` field holds the object handed in."""
        client = object()
        assert confarg.build(_Bug284, {"client": client}).client is client
        assert confarg.build(_Bug284, {"client": client, "label": "${name}"}).client is client

    def test_a_reference_reads_the_object_built(self) -> None:
        """``${client}`` reads what the field is built as, the object handed in."""
        client = object()
        built = confarg.build(_Bug284, {"client": client, "other": "${client}"})
        assert built.client is client
        assert built.other is client

    def test_an_object_copy_refuses_builds(self) -> None:
        """A lock, which ``copy.deepcopy`` refuses, is handed on as it is."""
        lock = threading.Lock()
        built = confarg.build(_Bug284, {"client": lock, "label": "${name}"})
        assert built == _Bug284(client=lock, label="app")

    def test_resolve_shares_what_no_expression_is_written_in(self) -> None:
        """``resolve()`` returns a new dict holding the caller's own parts where nothing resolved."""
        db = {"host": "h"}
        data = {"client": {"db": db}, "label": "${name}"}
        resolved = confarg.resolve(_Bug284, data)
        assert resolved["client"] is data["client"]
        assert resolved is not data
