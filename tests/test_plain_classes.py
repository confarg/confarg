# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for plain (non-dataclass) class support."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, MutableMapping, MutableSequence, Sequence
from dataclasses import dataclass

import pytest

import confarg
from confarg._types import _init_defaults, _init_fields, _is_plain_class

# ---------------------------------------------------------------------------
# Minimal plain classes mimicking an albumentations-style transform hierarchy
# ---------------------------------------------------------------------------


class Transform:
    """Base transform."""

    def __init__(self, p: float = 1.0) -> None:
        self.p = p


class RandomCrop(Transform):
    def __init__(self, height: int, width: int, p: float = 1.0) -> None:
        super().__init__(p)
        self.height = height
        self.width = width


class HorizontalFlip(Transform):
    def __init__(self, p: float = 0.5) -> None:
        super().__init__(p)


class Compose(Transform):
    def __init__(self, transforms: list[Transform], p: float = 1.0) -> None:
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
    epochs: int
    transform: Transform


@dataclass
class UnionConfig:
    transform: RandomCrop | HorizontalFlip


# ---------------------------------------------------------------------------
# Unit tests for _types helpers
# ---------------------------------------------------------------------------


class TestIsPlainClass:
    def test_plain_class_detected(self) -> None:
        assert _is_plain_class(Transform)

    def test_dataclass_not_plain(self) -> None:
        assert not _is_plain_class(TrainingConfig)

    def test_str_not_plain(self) -> None:
        assert not _is_plain_class(str)

    def test_int_not_plain(self) -> None:
        assert not _is_plain_class(int)

    def test_list_not_plain(self) -> None:
        assert not _is_plain_class(list)

    def test_enum_not_plain(self) -> None:
        import enum

        class Color(enum.Enum):
            RED = 1

        assert not _is_plain_class(Color)

    def test_path_not_plain(self) -> None:
        from pathlib import Path

        assert not _is_plain_class(Path)


class TestInitFields:
    def test_random_crop_fields(self) -> None:
        fields = _init_fields(RandomCrop)
        assert set(fields) == {"height", "width", "p"}

    def test_compose_fields(self) -> None:
        fields = _init_fields(Compose)
        assert set(fields) == {"transforms", "p"}


class TestInitDefaults:
    def test_random_crop_defaults(self) -> None:
        defs = _init_defaults(RandomCrop)
        assert defs == {"p": 1.0}

    def test_horizontal_flip_defaults(self) -> None:
        defs = _init_defaults(HorizontalFlip)
        assert defs == {"p": 0.5}

    def test_compose_defaults(self) -> None:
        defs = _init_defaults(Compose)
        assert defs == {"p": 1.0}


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestPlainClassConstruction:
    def test_construct_simple(self) -> None:
        result = confarg.from_dict(
            TrainingConfig,
            {"epochs": 5, "transform": {"height": 256, "width": 256, "class": "tests.test_plain_classes.RandomCrop"}},
        )
        assert isinstance(result.transform, RandomCrop)
        assert result.transform.height == 256
        assert result.transform.width == 256

    def test_construct_uses_default(self) -> None:
        result = confarg.from_dict(
            TrainingConfig, {"epochs": 5, "transform": {"class": "tests.test_plain_classes.HorizontalFlip"}}
        )
        assert isinstance(result.transform, HorizontalFlip)
        assert result.transform.p == pytest.approx(0.5)

    def test_construct_nested_compose(self) -> None:
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
        result = confarg.from_dict(TrainingConfig, data)
        assert isinstance(result.transform, Compose)
        assert len(result.transform.transforms) == 2
        assert isinstance(result.transform.transforms[0], RandomCrop)
        assert isinstance(result.transform.transforms[1], HorizontalFlip)
        assert result.transform.transforms[1].p == pytest.approx(0.3)

    def test_construct_union_disambiguation(self) -> None:
        result = confarg.from_dict(
            UnionConfig, {"transform": {"class": "tests.test_plain_classes.HorizontalFlip", "p": 0.2}}
        )
        assert isinstance(result.transform, HorizontalFlip)
        assert result.transform.p == pytest.approx(0.2)

    def test_unknown_field_raises(self) -> None:
        with pytest.raises(confarg.TypeCoercionError):
            confarg.from_dict(
                TrainingConfig,
                {"epochs": 1, "transform": {"class": "tests.test_plain_classes.HorizontalFlip", "unknown": 99}},
            )

    def test_missing_required_field_raises(self) -> None:
        with pytest.raises(confarg.ConfargError):
            confarg.from_dict(
                TrainingConfig,
                {"epochs": 1, "transform": {"class": "tests.test_plain_classes.RandomCrop", "height": 10}},
            )


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestPlainClassSerialization:
    def test_serialize_simple(self) -> None:
        cfg = TrainingConfig(epochs=5, transform=RandomCrop(height=256, width=256))
        result = confarg.dump(cfg)
        assert result["transform"]["height"] == 256
        assert result["transform"]["width"] == 256

    def test_serialize_subclass_emits_tag(self) -> None:
        cfg = TrainingConfig(epochs=5, transform=HorizontalFlip(p=0.4))
        result = confarg.dump(cfg)
        assert result["transform"]["class"] == "tests.test_plain_classes.HorizontalFlip"
        assert result["transform"]["p"] == pytest.approx(0.4)

    def test_roundtrip(self) -> None:
        cfg = TrainingConfig(epochs=7, transform=RandomCrop(height=64, width=64, p=0.9))
        serialized = confarg.dump(cfg)
        restored = confarg.from_dict(TrainingConfig, serialized)
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
        """The dict-centric workflow: merge → interpolate → construct; dump_dict_file the dict."""
        raw = {"epochs": 3, "transform": {"p": 0.8}}
        resolved = confarg.interpolate(raw)
        cfg = confarg.construct(TrainingConfig, resolved)
        assert cfg.epochs == 3
        assert isinstance(cfg.transform, Transform)
        assert cfg.transform.p == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class TestPlainClassCli:
    def test_cli_leaf_param(self) -> None:
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
    def test_env_leaf_param(self) -> None:
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
    def __init__(self, items: Sequence[str]) -> None:
        self.items = items


class MutableHolder:
    def __init__(self, items: MutableSequence[int]) -> None:
        self.items = items


class IterableHolder:
    def __init__(self, items: Iterable[float]) -> None:
        self.items = items


class MappingHolder:
    def __init__(self, data: Mapping[str, int]) -> None:
        self.data = data


class MutableMappingHolder:
    def __init__(self, data: MutableMapping[str, str]) -> None:
        self.data = data


@dataclass
class AbstractCollectionConfig:
    holder: ItemHolder


class TestAbstractCollectionTypes:
    def test_sequence_param(self) -> None:
        result = confarg.construct(ItemHolder, {"items": ["a", "b", "c"]})
        assert result.items == ["a", "b", "c"]

    def test_mutable_sequence_param(self) -> None:
        result = confarg.construct(MutableHolder, {"items": [1, 2, 3]})
        assert result.items == [1, 2, 3]

    def test_iterable_param(self) -> None:
        result = confarg.construct(IterableHolder, {"items": [1.0, 2.5]})
        assert result.items == [1.0, 2.5]

    def test_mapping_param(self) -> None:
        result = confarg.construct(MappingHolder, {"data": {"x": 1, "y": 2}})
        assert result.data == {"x": 1, "y": 2}

    def test_mutable_mapping_param(self) -> None:
        result = confarg.construct(MutableMappingHolder, {"data": {"k": "v"}})
        assert result.data == {"k": "v"}

    def test_sequence_in_nested_plain_class(self) -> None:
        result = confarg.construct(
            AbstractCollectionConfig,
            {"holder": {"items": ["x", "y"]}},
        )
        assert isinstance(result.holder, ItemHolder)
        assert result.holder.items == ["x", "y"]
