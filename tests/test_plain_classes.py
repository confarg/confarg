# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for plain (non-dataclass) class support."""

from __future__ import annotations

import enum
import gc
import inspect
import weakref
from collections.abc import Iterable, Mapping, MutableMapping, MutableSequence, Sequence  # noqa: TC003
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NamedTuple

import pytest

import confarg
from confarg import _types
from confarg._types import (
    _dc_fields,
    _init_defaults,
    _init_fields,
    _init_params,
    _is_plain_class,
    _is_struct,
    _namedtuple_fields,
    _struct_subclasses,
    _var_params,
)
from confarg.cli._spec import _get_field_docstrings
from confarg.typedload._construct import _call_with_var_positional

# ---------------------------------------------------------------------------
# Minimal plain classes mimicking an albumentations-style transform hierarchy
# ---------------------------------------------------------------------------


class Transform:
    """Base transform."""

    def __init__(self, p: float = 1.0) -> None:
        """Initialize Transform with probability."""
        self.p = p


class RandomCrop(Transform):
    """Random crop transform."""

    def __init__(self, height: int, width: int, p: float = 1.0) -> None:
        """Initialize RandomCrop with crop dimensions and probability."""
        super().__init__(p)
        self.height = height
        self.width = width


class HorizontalFlip(Transform):
    """Horizontal flip transform."""

    def __init__(self, p: float = 0.5) -> None:
        """Initialize HorizontalFlip with probability."""
        super().__init__(p)


class Compose(Transform):
    """Compose transform: applies a list of transforms in order."""

    def __init__(self, transforms: list[Transform], p: float = 1.0) -> None:
        """Initialize Compose with a list of transforms and probability."""
        super().__init__(p)
        self.transforms = transforms


class _MissingAttrClass:
    """Stores x but intentionally omits self.y — used to test _serialize_struct error."""

    def __init__(self, x: int, y: int) -> None:
        self.x = x


@dataclass
class _MissingAttrWrapper:
    inner: _MissingAttrClass


@dataclass
class TrainingConfig:
    """Training configuration with epoch count and a transform."""

    epochs: int
    transform: Transform


@dataclass
class UnionConfig:
    """Configuration with a union of transform types."""

    transform: RandomCrop | HorizontalFlip


# ---------------------------------------------------------------------------
# Unit tests for _types helpers
# ---------------------------------------------------------------------------


class TestIsPlainClass:
    """Tests for the _is_plain_class helper."""

    def test_plain_class_detected(self) -> None:
        """Test that a plain class is detected as such."""
        assert _is_plain_class(Transform)

    def test_dataclass_not_plain(self) -> None:
        """Test that a dataclass is not considered a plain class."""
        assert not _is_plain_class(TrainingConfig)

    def test_str_not_plain(self) -> None:
        """Test that str is not considered a plain class."""
        assert not _is_plain_class(str)

    def test_int_not_plain(self) -> None:
        """Test that int is not considered a plain class."""
        assert not _is_plain_class(int)

    def test_list_not_plain(self) -> None:
        """Test that list is not considered a plain class."""
        assert not _is_plain_class(list)

    def test_enum_not_plain(self) -> None:
        """Test that an Enum subclass is not considered a plain class."""

        class Color(enum.Enum):
            RED = 1

        assert not _is_plain_class(Color)

    def test_path_not_plain(self) -> None:
        """Test that pathlib.Path is not considered a plain class."""
        assert not _is_plain_class(Path)


class TestInitFields:
    """Tests for the _init_fields helper."""

    def test_random_crop_fields(self) -> None:
        """Test that RandomCrop __init__ fields are extracted correctly."""
        fields = _init_fields(RandomCrop)
        assert set(fields) == {"height", "width", "p"}

    def test_compose_fields(self) -> None:
        """Test that Compose __init__ fields are extracted correctly."""
        fields = _init_fields(Compose)
        assert set(fields) == {"transforms", "p"}


class TestInitDefaults:
    """Tests for the _init_defaults helper."""

    def test_random_crop_defaults(self) -> None:
        """Test that RandomCrop __init__ defaults are extracted correctly."""
        defs = _init_defaults(RandomCrop)
        assert defs == {"p": 1.0}

    def test_horizontal_flip_defaults(self) -> None:
        """Test that HorizontalFlip __init__ defaults are extracted correctly."""
        defs = _init_defaults(HorizontalFlip)
        assert defs == {"p": 0.5}

    def test_compose_defaults(self) -> None:
        """Test that Compose __init__ defaults are extracted correctly."""
        defs = _init_defaults(Compose)
        assert defs == {"p": 1.0}


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestPlainClassConstruction:
    """Tests for constructing plain classes via from_dict."""

    def test_construct_simple(self) -> None:
        """Test that a simple plain class is constructed correctly via from_dict."""
        result = confarg.build(
            TrainingConfig,
            {"epochs": 5, "transform": {"height": 256, "width": 256, "class": "tests.test_plain_classes.RandomCrop"}},
        )
        assert isinstance(result.transform, RandomCrop)
        assert result.transform.height == 256
        assert result.transform.width == 256

    def test_construct_uses_default(self) -> None:
        """Test that default parameter values are used when not provided."""
        result = confarg.build(
            TrainingConfig,
            {"epochs": 5, "transform": {"class": "tests.test_plain_classes.HorizontalFlip"}},
        )
        assert isinstance(result.transform, HorizontalFlip)
        assert result.transform.p == pytest.approx(0.5)

    def test_construct_nested_compose(self) -> None:
        """Test that a nested Compose with multiple transforms is constructed correctly."""
        data = {
            "epochs": 3,
            "transform": {
                "class": "tests.test_plain_classes.Compose",
                "transforms": [
                    {"class": "tests.test_plain_classes.RandomCrop", "height": 128, "width": 128},
                    {"class": "tests.test_plain_classes.HorizontalFlip", "p": 0.3},
                ],
            },
        }
        result = confarg.build(TrainingConfig, data)
        assert isinstance(result.transform, Compose)
        assert len(result.transform.transforms) == 2
        assert isinstance(result.transform.transforms[0], RandomCrop)
        assert isinstance(result.transform.transforms[1], HorizontalFlip)
        assert result.transform.transforms[1].p == pytest.approx(0.3)

    def test_construct_union_disambiguation(self) -> None:
        """Test that a union type is disambiguated via the class tag in from_dict."""
        result = confarg.build(
            UnionConfig,
            {"transform": {"class": "tests.test_plain_classes.HorizontalFlip", "p": 0.2}},
        )
        assert isinstance(result.transform, HorizontalFlip)
        assert result.transform.p == pytest.approx(0.2)

    def test_unknown_field_raises(self) -> None:
        """Test that an unknown field in the dict raises TypeCoercionError."""
        with pytest.raises(confarg.exceptions.TypeCoercionError):
            confarg.build(
                TrainingConfig,
                {"epochs": 1, "transform": {"class": "tests.test_plain_classes.HorizontalFlip", "unknown": 99}},
            )

    def test_missing_required_field_raises(self) -> None:
        """Test that a missing required field raises ConfargError."""
        with pytest.raises(confarg.exceptions.ConfargError):
            confarg.build(
                TrainingConfig,
                {"epochs": 1, "transform": {"class": "tests.test_plain_classes.RandomCrop", "height": 10}},
            )


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestPlainClassSerialization:
    """Tests for serializing plain classes via dump."""

    def test_serialize_simple(self) -> None:
        """Test that a simple plain class is serialized to a dict correctly."""
        cfg = TrainingConfig(epochs=5, transform=RandomCrop(height=256, width=256))
        result = confarg.dump(cfg)
        assert result["transform"]["height"] == 256
        assert result["transform"]["width"] == 256

    def test_serialize_subclass_emits_tag(self) -> None:
        """Test that a subclass instance is serialized with a class tag."""
        cfg = TrainingConfig(epochs=5, transform=HorizontalFlip(p=0.4))
        result = confarg.dump(cfg)
        assert result["transform"]["class"] == "tests.test_plain_classes.HorizontalFlip"
        assert result["transform"]["p"] == pytest.approx(0.4)

    def test_roundtrip(self) -> None:
        """Test that a plain class serializes and deserializes back to the same object."""
        cfg = TrainingConfig(epochs=7, transform=RandomCrop(height=64, width=64, p=0.9))
        serialized = confarg.dump(cfg)
        restored = confarg.build(TrainingConfig, serialized)
        assert restored.epochs == 7
        assert isinstance(restored.transform, RandomCrop)
        assert restored.transform.height == 64
        assert restored.transform.p == pytest.approx(0.9)

    def test_dump_plain_class_instance_raises(self) -> None:
        """dump() must reject plain-class instances with a clear TypeError."""
        with pytest.raises(TypeError, match="plain class"):
            confarg.dump(RandomCrop(height=64, width=64))

    def test_dump_plain_class_missing_attribute_raises(self) -> None:
        """_serialize_struct must raise ConfargError when an __init__ param is not stored."""
        w = _MissingAttrWrapper(inner=_MissingAttrClass(x=1, y=2))
        with pytest.raises(confarg.exceptions.ConfargError, match="y"):
            confarg.dump(w)

    def test_dict_centric_roundtrip(self) -> None:
        """The dict-centric workflow: merge → resolve → from_dict; dump_dict_file the dict."""
        raw = {"epochs": 3, "transform": {"class": "tests.test_plain_classes.HorizontalFlip", "p": 0.8}}
        resolved = confarg.resolve(TrainingConfig, raw)
        cfg = confarg.from_dict(TrainingConfig, resolved)
        assert cfg.epochs == 3
        assert isinstance(cfg.transform, HorizontalFlip)
        assert cfg.transform.p == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class TestPlainClassCli:
    """Tests for CLI integration with plain classes."""

    def test_cli_leaf_param(self) -> None:
        """Test that CLI args correctly set plain class parameters."""
        result = confarg.load(
            TrainingConfig,
            argv=[
                "--epochs",
                "10",
                "--transform.p",
                "0.7",
                "--transform.class",
                "tests.test_plain_classes.HorizontalFlip",
            ],
            env={},
        )
        assert result.epochs == 10
        assert isinstance(result.transform, HorizontalFlip)
        assert result.transform.p == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# Env var integration
# ---------------------------------------------------------------------------


class TestPlainClassEnv:
    """Tests for env var integration with plain classes."""

    def test_env_leaf_param(self) -> None:
        """Test that env vars correctly set plain class parameters."""
        result = confarg.load(
            TrainingConfig,
            argv=["--epochs", "2"],
            env={"MYAPP_TRANSFORM__CLASS": "tests.test_plain_classes.HorizontalFlip", "MYAPP_TRANSFORM__P": "0.6"},
            env_prefix="MYAPP_",
        )
        assert isinstance(result.transform, HorizontalFlip)
        assert result.transform.p == pytest.approx(0.6)


# ---------------------------------------------------------------------------
# The whole-value token, across the three channels
# ---------------------------------------------------------------------------


@dataclass
class WholeValueConfig:
    """Dataclass whose plain-class field takes a whole object in one token."""

    transform: HorizontalFlip = field(default_factory=HorizontalFlip)


class TestPlainClassWholeValue:
    """A plain class takes a whole ``{...}`` value from every channel (BUG-39)."""

    BLOB = '{"p": 0.25}'

    def test_env_takes_the_whole_value(self) -> None:
        """The env channel JSON-decodes the blob into the plain class's parameters."""
        cfg = confarg.load(WholeValueConfig, argv=[], env={"P_TRANSFORM": self.BLOB}, env_prefix="P_")
        assert cfg.transform.p == pytest.approx(0.25)

    def test_file_takes_the_whole_value(self, tmp_path: Path) -> None:
        """A config file mapping builds the same object."""
        path = tmp_path / "c.json"
        path.write_text('{"transform": {"p": 0.25}}', encoding="utf-8")
        cfg = confarg.load(WholeValueConfig, argv=[], env={}, files=[path])
        assert cfg.transform.p == pytest.approx(0.25)

    def test_cli_takes_the_whole_value(self) -> None:
        """The CLI spelling of the same blob is not the one channel that refuses it."""
        cfg = confarg.load(WholeValueConfig, argv=["--transform", self.BLOB], env={})
        assert cfg.transform.p == pytest.approx(0.25)

    def test_the_three_channels_merge_alike(self) -> None:
        """All three spellings produce the identical merged dict."""
        cli = confarg.merge(WholeValueConfig, argv=["--transform", self.BLOB], env={})
        env = confarg.merge(WholeValueConfig, argv=[], env={"P_TRANSFORM": self.BLOB}, env_prefix="P_")
        assert cli == env == {"transform": {"p": 0.25}}


# ---------------------------------------------------------------------------
# Abstract collection types in __init__ annotations
# ---------------------------------------------------------------------------


class ItemHolder:
    """Plain class holding a sequence of strings."""

    def __init__(self, items: Sequence[str]) -> None:
        """Initialize ItemHolder with a sequence of items."""
        self.items = items


class MutableHolder:
    """Plain class holding a mutable sequence of ints."""

    def __init__(self, items: MutableSequence[int]) -> None:
        """Initialize MutableHolder with a mutable sequence of items."""
        self.items = items


class IterableHolder:
    """Plain class holding an iterable of floats."""

    def __init__(self, items: Iterable[float]) -> None:
        """Initialize IterableHolder with an iterable of items."""
        self.items = items


class MappingHolder:
    """Plain class holding a mapping of str to int."""

    def __init__(self, data: Mapping[str, int]) -> None:
        """Initialize MappingHolder with a mapping."""
        self.data = data


class MutableMappingHolder:
    """Plain class holding a mutable mapping of str to str."""

    def __init__(self, data: MutableMapping[str, str]) -> None:
        """Initialize MutableMappingHolder with a mutable mapping."""
        self.data = data


@dataclass
class AbstractCollectionConfig:
    """Dataclass wrapping a plain class with abstract collection fields."""

    holder: ItemHolder


class TestAbstractCollectionTypes:
    """Tests for abstract collection types (Sequence, Mapping, etc.) in plain class __init__."""

    def test_sequence_param(self) -> None:
        """Test that Sequence[str] param is constructed from a list."""
        result = confarg.from_dict(ItemHolder, {"items": ["a", "b", "c"]})
        assert result.items == ["a", "b", "c"]

    def test_mutable_sequence_param(self) -> None:
        """Test that MutableSequence[int] param is constructed from a list."""
        result = confarg.from_dict(MutableHolder, {"items": [1, 2, 3]})
        assert result.items == [1, 2, 3]

    def test_iterable_param(self) -> None:
        """Test that Iterable[float] param is constructed from a list."""
        result = confarg.from_dict(IterableHolder, {"items": [1.0, 2.5]})
        assert result.items == [1.0, 2.5]

    def test_mapping_param(self) -> None:
        """Test that Mapping[str, int] param is constructed from a dict."""
        result = confarg.from_dict(MappingHolder, {"data": {"x": 1, "y": 2}})
        assert result.data == {"x": 1, "y": 2}

    def test_mutable_mapping_param(self) -> None:
        """Test that MutableMapping[str, str] param is constructed from a dict."""
        result = confarg.from_dict(MutableMappingHolder, {"data": {"k": "v"}})
        assert result.data == {"k": "v"}

    def test_sequence_in_nested_plain_class(self) -> None:
        """Test that Sequence fields work in a plain class nested inside a dataclass."""
        result = confarg.from_dict(
            AbstractCollectionConfig,
            {"holder": {"items": ["x", "y"]}},
        )
        assert isinstance(result.holder, ItemHolder)
        assert result.holder.items == ["x", "y"]


class TestAnyIsNotAPlainClass:
    """``typing.Any`` must never be mistaken for a plain class / struct.

    Since Python 3.11 ``typing.Any`` is a subclassable class, so it otherwise slips
    through ``_is_plain_class``. That made env treat an ``Any`` field as a struct and
    JSON-parse brace values while the CLI kept them as strings.
    """

    def test_any_is_not_a_plain_class(self) -> None:
        """The predicate rejects typing.Any outright."""
        from typing import Any  # noqa: PLC0415

        from confarg._types import _is_struct, _resolve_struct  # noqa: PLC0415

        assert _is_plain_class(Any) is False
        assert _is_struct(Any) is False
        assert _resolve_struct(Any) is None

    def test_real_plain_class_still_detected(self) -> None:
        """The Any guard is narrow: genuine plain classes remain plain classes."""
        assert _is_plain_class(Transform) is True


# ---------------------------------------------------------------------------
# One signature walk, cached per class (REF-48)
# ---------------------------------------------------------------------------


class _Gapped:
    def __init__(self, a: int = 1, b: int = 2, *rest: int) -> None:
        self.a, self.b, self.rest = a, b, rest


class _PositionalOnlyWithRest:
    def __init__(self, a: int, /, *rest: int) -> None:
        self.a, self.rest = a, rest


class TestInitParams:
    """Every plain-class question reads one cached walk of ``__init__``'s signature."""

    def test_signature_is_walked_once_per_class(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Detection, fields, defaults, ``*args`` and construction share one walk."""

        class Fresh:
            def __init__(self, x: int, *rest: int, **extra: int) -> None:
                self.x, self.rest, self.extra = x, rest, extra

        walks: list[object] = []
        signature = inspect.signature
        monkeypatch.setattr(inspect, "signature", lambda obj, **kw: walks.append(obj) or signature(obj, **kw))

        assert _is_plain_class(Fresh)
        assert set(_init_fields(Fresh)) == {"x", "rest", "extra"}
        assert _init_defaults(Fresh) == {"rest": [], "extra": {}}
        assert _var_params(Fresh).names == {"rest", "extra"}
        built = confarg.build(Fresh, {"x": 1, "rest": [2, 3], "extra": {"k": 4}})
        assert (built.x, built.rest, built.extra) == (1, (2, 3), {"k": 4})
        assert walks == [Fresh.__init__]

    def test_field_mappings_are_read_only(self) -> None:
        """A cached mapping is shared between callers, so it refuses a write."""
        with pytest.raises(TypeError):
            _init_fields(Compose)["p"] = int  # ty: ignore[invalid-assignment]  # the write must fail
        with pytest.raises(TypeError):
            _dc_fields(TrainingConfig)["lr"] = int  # ty: ignore[invalid-assignment]  # the write must fail

    def test_var_param_defaults_are_fresh_per_call(self) -> None:
        """``*args`` and ``**kwargs`` default to a new ``[]`` and ``{}`` every time, never a cached one."""

        class Variadic:
            def __init__(self, *rest: int, **extra: int) -> None:
                self.rest, self.extra = rest, extra

        first, second = _init_defaults(Variadic), _init_defaults(Variadic)
        assert first["rest"] is not second["rest"]
        assert first["extra"] is not second["extra"]

    def test_unresolved_annotation_is_retried(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A forward reference reads as Any until its name exists, then as the type it names."""

        class Pending:
            def __init__(
                self,
                x: _NotYetDefined,  # noqa: F821  # ty: ignore[unresolved-reference]  # monkeypatched in below
            ) -> None:
                self.x = x

        assert dict(_init_fields(Pending)) == {"x": Any}
        monkeypatch.setitem(globals(), "_NotYetDefined", int)
        assert dict(_init_fields(Pending)) == {"x": int}

    def test_record_lists_positional_names(self) -> None:
        """The names a positional argument fills, in order; ``self`` and the variadics excluded."""
        params = _init_params(_Gapped)
        assert params.positional == ("a", "b")
        assert params.required == frozenset()

    def test_positional_only_parameter_before_args(self) -> None:
        """A positional-only parameter is passed by position ahead of ``*args``."""
        built = confarg.build(_PositionalOnlyWithRest, {"a": 1, "rest": [2, 3]})
        assert (built.a, built.rest) == (1, (2, 3))

    def test_positional_gap_goes_by_keyword(self) -> None:
        """A later positional value never slides into an earlier unfilled parameter."""
        built = _call_with_var_positional(_Gapped, {"b": 5}, "rest", {})
        assert (built.a, built.b, built.rest) == (1, 5, ())

    def test_positional_gap_before_args_is_refused(self) -> None:
        """No call reaches ``*args`` past an unfilled positional parameter."""
        with pytest.raises(TypeError, match="positional parameter 'a' is unset"):
            _call_with_var_positional(_Gapped, {"b": 5, "rest": [6]}, "rest", {})


# ---------------------------------------------------------------------------
# Cached as long as the class lives, struct test included (REF-92)
# ---------------------------------------------------------------------------


class TestPerClassCache:
    """Every per-class answer is cached for as long as its class lives, and no longer."""

    def test_cached_class_is_collectable(self) -> None:
        """A class asked every cached question is still garbage-collected once dropped."""

        def ask_everything() -> list[weakref.ref[type]]:
            class Plain:
                def __init__(self, x: int, *rest: int) -> None:
                    self.x, self.rest = x, rest

            @dataclass
            class Data:
                y: int = 0
                """The y."""

            class Pair(NamedTuple):
                a: int
                b: str

            for cls in (Plain, Data, Pair):
                _is_struct(cls)
            _init_params(Plain)
            _init_fields(Plain)
            _dc_fields(Data)
            _namedtuple_fields(Pair)
            _get_field_docstrings(Data)
            return [weakref.ref(Plain), weakref.ref(Data), weakref.ref(Pair)]

        refs = ask_everything()
        gc.collect()
        assert [r() for r in refs] == [None, None, None]

    def test_struct_test_runs_once_per_class(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The subclass scan asks each subclass's shape once, however often the scan runs."""

        class Base:
            def __init__(self, p: float = 1.0) -> None:
                self.p = p

        class Child(Base):
            def __init__(self, q: int, p: float = 1.0) -> None:
                super().__init__(p)
                self.q = q

        asked: list[type] = []
        is_plain_class = _types._is_plain_class
        monkeypatch.setattr(_types, "_is_plain_class", lambda tp: asked.append(tp) or is_plain_class(tp))

        assert _is_struct(Base)
        assert _is_struct(Base)
        assert _struct_subclasses(Base) == [Child]
        assert _struct_subclasses(Base) == [Child]
        assert asked == [Base, Child]
