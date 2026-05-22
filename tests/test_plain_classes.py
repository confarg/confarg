# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for plain (non-dataclass) class support."""

from __future__ import annotations

import enum
from collections.abc import Iterable, Mapping, MutableMapping, MutableSequence, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

import confarg
from confarg._types import _init_defaults, _init_fields, _is_plain_class

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
            TrainingConfig, {"epochs": 5, "transform": {"class": "tests.test_plain_classes.HorizontalFlip"}}
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
            UnionConfig, {"transform": {"class": "tests.test_plain_classes.HorizontalFlip", "p": 0.2}}
        )
        assert isinstance(result.transform, HorizontalFlip)
        assert result.transform.p == pytest.approx(0.2)

    def test_unknown_field_raises(self) -> None:
        """Test that an unknown field in the dict raises TypeCoercionError."""
        with pytest.raises(confarg.TypeCoercionError):
            confarg.build(
                TrainingConfig,
                {"epochs": 1, "transform": {"class": "tests.test_plain_classes.HorizontalFlip", "unknown": 99}},
            )

    def test_missing_required_field_raises(self) -> None:
        """Test that a missing required field raises ConfargError."""
        with pytest.raises(confarg.ConfargError):
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
        with pytest.raises(confarg.ConfargError, match="y"):
            confarg.dump(w)

    def test_dict_centric_roundtrip(self) -> None:
        """The dict-centric workflow: merge → resolve → from_dict; dump_dict_file the dict."""
        raw = {"epochs": 3, "transform": {"p": 0.8}}
        resolved = confarg.resolve(raw)
        cfg = confarg.from_dict(TrainingConfig, resolved)
        assert cfg.epochs == 3
        assert isinstance(cfg.transform, Transform)
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
            args=[
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
            args=["--epochs", "2"],
            env={"TRANSFORM__CLASS": "tests.test_plain_classes.HorizontalFlip", "TRANSFORM__P": "0.6"},
            env_prefix="",
        )
        assert isinstance(result.transform, HorizontalFlip)
        assert result.transform.p == pytest.approx(0.6)


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
