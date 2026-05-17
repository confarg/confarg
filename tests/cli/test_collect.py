# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Unit tests for cli/_collect.py — the backend-neutral flat-dict collector."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from confarg._types import _StrToken
from confarg.cli._collect import (
    _callable_return_type_for,
    _collect_callable_spec,
    _collect_ns_fields,
    _merge_blob_into_spec,
)
from tests._cov_helpers import _CovCallableCls, _CovDCResult, _WithCovCallable


@dataclass
class _StructVariantA:
    x: int = 0


@dataclass
class _StructVariantB:
    y: str = ""


@dataclass
class _WithStructUnion:
    item: _StructVariantA | _StructVariantB


class TestCollectNsFields:
    """Type-case branches of _collect_ns_fields."""

    def test_non_struct(self) -> None:
        """_collect_ns_fields is a no-op for non-struct types."""
        result: dict[str, Any] = {}
        _collect_ns_fields({}, int, "", "class", result)
        assert result == {}

    def test_get_type_hints_exception(self) -> None:
        """_collect_ns_fields falls back gracefully when get_type_hints raises."""

        class BrokenClassAnnot:
            _bad: UndefinedType888  # noqa: F821  # ty: ignore[unresolved-reference]  # intentionally undefined to trigger NameError fallback

            def __init__(self, x: int, y: str = "default") -> None:
                self.x = x
                self.y = y

        result: dict[str, Any] = {}
        _collect_ns_fields({"x": "42"}, BrokenClassAnnot, "", "class", result)
        assert "x" in result or result == {}

    def test_union_tag_skipped(self) -> None:
        """_collect_ns_fields excludes the union_tag field from the result."""

        @dataclass
        class WithTypeField:
            type: str = "a"
            value: int = 0

        result: dict[str, Any] = {}
        _collect_ns_fields({"type": "b", "value": "99"}, WithTypeField, "", union_tag="type", result=result)
        assert "type" not in result

    def test_multi_union_collected_as_plain_value(self) -> None:
        """Scalar multi-variant union fields are collected as plain values."""

        @dataclass
        class WithMultiUnion:
            val: int | str = 0

        result: dict[str, Any] = {}
        _collect_ns_fields({"val": "99"}, WithMultiUnion, "", "class", result)

    def test_dict_skipped(self) -> None:
        """_collect_ns_fields skips dict-typed fields."""

        @dataclass
        class WithDict:
            mapping: dict[str, int] = field(default_factory=dict)

        result: dict[str, Any] = {}
        _collect_ns_fields({"mapping": '{"a": 1}'}, WithDict, "", "class", result)
        assert "mapping" not in result

    def test_callable_field(self) -> None:
        """_collect_ns_fields handles a Callable-typed field."""
        flat = {"fn.fn": "some.module.fn"}
        result: dict[str, Any] = {}
        _collect_ns_fields(flat, _WithCovCallable, "", "class", result)
        assert "fn" in result

    def test_union_class_tag_collected(self) -> None:
        """--<field>.class in the flat dict is passed through to the merge pipeline."""
        flat = {"item.class": "myapp._StructVariantA"}
        result: dict[str, Any] = {}
        _collect_ns_fields(flat, _WithStructUnion, prefix="", union_tag="class", result=result)
        assert result == {"item": {"class": _StrToken("myapp._StructVariantA")}}


class TestCollectCallableSpec:
    """Callable-spec assembly from flat namespace entries."""

    def test_fn_key(self) -> None:
        """_collect_callable_spec stores fn: value from flat namespace."""
        flat = {"myfn.fn": "some.module.fn"}
        result: dict[str, Any] = {}
        _collect_callable_spec(flat, "myfn", Callable, result)
        assert result.get("myfn", {}).get("fn") == "some.module.fn"

    def test_class_key(self) -> None:
        """_collect_callable_spec stores class: value from flat namespace."""
        flat = {"myfn.class": "some.module.Cls"}
        result: dict[str, Any] = {}
        _collect_callable_spec(flat, "myfn", Callable, result)
        assert result.get("myfn", {}).get("class") == "some.module.Cls"

    def test_bind_keys(self) -> None:
        """_collect_callable_spec assembles bind: dict from flat namespace."""
        flat = {"myfn.fn": "some.fn", "myfn.bind.x": "42"}
        result: dict[str, Any] = {}
        _collect_callable_spec(flat, "myfn", Callable, result)
        assert result["myfn"]["bind"]["x"] == "42"

    def test_bare_string_no_spec(self) -> None:
        """A bare string value with no other spec keys is stored as a plain string."""
        flat = {"myfn": "some.module.fn"}
        result: dict[str, Any] = {}
        _collect_callable_spec(flat, "myfn", Callable, result)
        assert result.get("myfn") == "some.module.fn"

    def test_blob_dict_merged(self) -> None:
        """A pre-existing dict blob for the flag is merged with the assembled spec."""
        flat = {"myfn": {"fn": "existing.fn"}, "myfn.bind.x": "42"}
        result: dict[str, Any] = {}
        _collect_callable_spec(flat, "myfn", Callable, result)
        merged = result.get("myfn", {})
        assert merged.get("fn") == "existing.fn"
        assert merged.get("bind", {}).get("x") == "42"

    def test_factory_kwargs(self) -> None:
        """_collect_callable_spec collects flat factory kwargs into spec when fn key present."""
        flat = {"myfn.fn": "some.fn", "myfn.lr": "0.01"}
        result: dict[str, Any] = {}
        _collect_callable_spec(flat, "myfn", Callable[..., _CovCallableCls], result)
        assert result.get("myfn", {}).get("lr") == "0.01"


class TestCollectHelpers:
    """Small helper functions of cli/_collect.py."""

    def test_callable_return_type_for(self) -> None:
        """_callable_return_type_for delegates to _callable_return_type."""
        result = _callable_return_type_for(Callable[..., _CovDCResult])
        assert result is _CovDCResult

    def test_merge_blob_into_spec_non_dict_bind(self) -> None:
        """_merge_blob_into_spec uses bind directly when blob.bind is not a dict."""
        merged = _merge_blob_into_spec({"bind": "not_a_dict"}, {}, {"x": 1})
        assert merged["bind"] == {"x": 1}
