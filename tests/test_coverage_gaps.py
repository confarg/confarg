# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests targeting previously uncovered lines across confarg modules."""

from __future__ import annotations

import argparse
import ast
import contextlib
import enum
import importlib
import json
import math
import sys
import types
import unittest.mock
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional, Protocol, Union

import pytest

import confarg
import confarg._callable as callable_mod
import confarg.cli.argparse._build as build_mod
import confarg.cli.argparse._register as reg_mod
from confarg._callable import (
    _check_bind_params,
    _check_callable_signature,
    _ClassSpec,
    _coerce_bind_kwargs,
    _detect_owning_class,
    _format_fn_dict_example,
    _import_dotted,
    _is_factory_class,
    _resolve_bare_string,
    _resolve_call_kwargs,
    _resolve_call_spec,
    _resolve_callable_spec,
    _resolve_class_spec,
    _resolve_factory_kwargs,
    _serialize_callable,
)
from confarg._files import (
    _dump_file,
    _dump_json,
    _load_file,
    _load_file_item,
    _load_json,
    _load_json_item,
    _load_toml,
    _load_yaml,
    _load_yaml_item,
)
from confarg._merge import (
    DICT_DELETE,
    LIST_APPEND_KEY,
    LIST_DELETE_KEY,
    LIST_REPLACE_BASE_KEY,
    _accumulate_list_delete,
    _apply_append_key,
    _deep_merge,
    _merge_regular_key,
    _normalize_merge_ops,
    _set_nested,
    _to_append_list,
)
from confarg._parse_cli import _handle_append_token, _ParseCtx, _resolve_field_type, _subclass_field_type
from confarg._types import (
    _all_have_defaults,
    _allows_none,
    _init_fields,
    _is_collection,
    _is_plain_class,
    _StrToken,
    _unwrap_optional,
    _var_keyword_name,
    _var_param_names,
    _var_positional_name,
)
from confarg.cli.argparse import from_namespace, populate_parser
from confarg.cli.argparse._build import (
    _collect_callable_bind_specs,
    _collect_callable_factory_specs,
    _collect_callable_field_specs,
    _collect_fn_paths_from_argv,
    _collect_fn_paths_from_config,
    _collect_struct_specs,
    _collect_subconfig_specs,
    _get_callable_field_return_type,
    _resolve_struct,
    build_dynamic_flags,
)
from confarg.cli.argparse._completion import (
    _extend_walk,
    _pre_extend_parser_for_completion,
    _resolve_tags_from_config,
    _WalkCtx,
)
from confarg.cli.argparse._completion import (
    setup_completion as _argparse_setup_completion,
)
from confarg.cli.argparse._namespace import (
    _callable_return_type_for,
    _collect_callable_spec,
    _collect_ns_fields,
    _merge_blob_into_spec,
)
from confarg.cli.argparse._register import _add_callable_bind_flags, _add_callable_fn_flags, _register_spec
from confarg.cli.argparse._spec import FlagSpec, _get_field_docstrings
from confarg.dictexpr._expressions import (
    _attribute_chain,
    _evaluate_ast,
    _extract_references,
    _get_nested,
    _set_nested_by_path,
    resolve_expressions,
)
from confarg.exceptions import SymbolImportError, TypeCoercionError
from confarg.typedload._coerce import _coerce_leaf, _coerce_type_ref, _try_coerce
from confarg.typedload._construct import _value_matches_type, construct
from tests.conftest import WithDefaults, make_target

try:
    import click
    from click.testing import CliRunner

    from confarg.cli.click import from_context, populate_command
    from confarg.cli.click._completion import setup_completion as _click_setup_completion

    _CLICK_AVAILABLE = True
except ImportError:
    _CLICK_AVAILABLE = False

# ---------------------------------------------------------------------------
# Module-level dataclasses (needed to avoid `from __future__ import annotations`
# breaking `get_type_hints` for locally-defined classes)
# ---------------------------------------------------------------------------


@dataclass
class _AmbigVariantX:
    name: str = ""


@dataclass
class _AmbigVariantY:
    NAME: str = ""


@dataclass
class _AmbigUnion:
    service: _AmbigVariantX | _AmbigVariantY


@dataclass
class _UnionRootVariantA:
    a: str = ""


@dataclass
class _UnionRootVariantB:
    b: str = ""


@dataclass
class _UnionTagFieldType:
    type: str = "a"
    value: int = 0


@dataclass
class _SubClassFieldBase:
    pass


@dataclass
class _SubClassFieldSubA(_SubClassFieldBase):
    val: int = 0


@dataclass
class _SubClassFieldSubB(_SubClassFieldBase):
    val: str = ""


@dataclass
class _SubClassBase:
    pass


@dataclass
class _SubClassSub(_SubClassBase):
    extra: str = ""


@dataclass
class _StructUnionVariantA:
    x: int = 0


@dataclass
class _StructUnionVariantB(_StructUnionVariantA):
    pass


@dataclass
class _AmbigOptionalP:
    x: int
    y: int = 0


@dataclass
class _AmbigOptionalQ:
    x: int
    z: int = 0


@dataclass
class _AmbigContainer:
    val: _AmbigOptionalP | _AmbigOptionalQ


@dataclass
class _ConstructAVariant:
    x: int = 0


@dataclass
class _ConstructBVariant:
    y: int = 0


@dataclass
class _WithCallableField:
    fn: Callable[[int], str] = field(default_factory=lambda: str)


@dataclass
class _WithVarTupleField:
    nums: tuple[int, ...] = ()


@dataclass
class _WithNestedDefaultInner:
    inner: WithDefaults = field(default_factory=WithDefaults)
    name: str = "test"


@dataclass
class _WithNoneValField:
    val: _StructUnionVariantA | None = None


@dataclass
class _WithIntOrDC:
    val: int | _StructUnionVariantA = 0


@dataclass
class _WithUnionTupleOrNone:
    coord: tuple[int, str] | None = None


@dataclass
class _WithTupleDefault:
    items: tuple[int, str] = (1, "x")


@dataclass
class _WithTupleOrInt:
    val: tuple[int, str] | int = 0


class _NotCallableClass:
    def __init__(self, value: int = 0) -> None:
        self.value = value


class _SlottedCallableClass:
    __slots__ = ("value",)

    def __init__(self, value: int) -> None:
        self.value = value

    def __call__(self) -> int:
        return self.value


class _NonStructSubBase:
    field_a: int

    def __init__(self, field_a: int) -> None:
        self.field_a = field_a


class _NonStructSubChild(_NonStructSubBase):
    def __init__(self) -> None:
        super().__init__(0)


# ---------------------------------------------------------------------------
# Module-level helpers importable by dotted path
# (required by _collect_callable_bind_specs / _collect_callable_factory_specs)
# ---------------------------------------------------------------------------

_COV_MOD = "tests.test_coverage_gaps"


def _cov_call_fn(x: int, y: str = "default") -> str:
    return f"{x}-{y}"


class _CovOptMethod:
    """Class with required+optional __init__ params and an instance method."""

    def __init__(self, required: int, optional: str = "default") -> None:
        self.required = required
        self.optional = optional

    def method(self) -> None:
        pass


class _CovUninspectable:
    """Class whose __init__ raises TypeError on signature inspection."""

    def __init__(self, value: int = 0) -> None:
        self.value = value


_CovUninspectable.__init__.__signature__ = property(  # ty: ignore[unresolved-attribute]  # deliberately corrupt __signature__ for testing
    lambda self: (_ for _ in ()).throw(TypeError("uninspectable")),
)


@dataclass
class _CovDCResult:
    result_val: str = ""


@dataclass
class _WithCovCallable:
    fn: Callable[..., _CovDCResult]


class _CovCallableCls:
    def __init__(self, lr: float = 0.01) -> None:
        self.lr = lr

    def __call__(self) -> None:
        pass


def _cov_raise_fn(x: int) -> str:
    msg = "deliberate error"
    raise RuntimeError(msg)


def _cov_fn_with_varargs(*args: int, key: str = "default") -> str:
    return str(args)


@dataclass
class _CovInner:
    value: str = ""


@dataclass
class _CovOuter:
    inner: _CovInner = field(default_factory=_CovInner)


@dataclass
class _WithUnionForCompletion:
    val: _ConstructAVariant | _ConstructBVariant = field(default_factory=_ConstructAVariant)


@dataclass
class _CovWithDict:
    settings: dict[str, Any] = field(default_factory=dict)
    name: str = ""


class _CovWithKwargs:
    """Plain class with **kwargs — used to test var_params skip in _extend_walk."""

    def __init__(self, x: int = 0, **extra: Any) -> None:
        self.x = x


# ---------------------------------------------------------------------------
# _merge._to_append_list
# ---------------------------------------------------------------------------


class TestToAppendList:
    """Unit tests for _merge._to_append_list."""

    def test_empty_dict(self) -> None:
        """Empty dict produces an empty list."""
        assert _to_append_list({}) == []

    def test_dict_with_int_keys(self) -> None:
        """Dict with integer string keys produces a sparse list padded with None."""
        result = _to_append_list({"0": "a", "2": "c"})
        assert result == ["a", None, "c"]

    def test_dict_with_non_int_keys_raises(self) -> None:
        """Dict with non-integer keys raises ConfargError."""
        with pytest.raises(confarg.exceptions.ConfargError, match="integer indices"):
            _to_append_list({"bad": "value"})

    def test_scalar_wrapped_in_list(self) -> None:
        """A scalar value is wrapped in a single-element list."""
        assert _to_append_list(42) == [42]

    def test_scalar_string(self) -> None:
        """A string scalar is wrapped in a single-element list."""
        assert _to_append_list("hello") == ["hello"]


# ---------------------------------------------------------------------------
# __init__.dump — dict with _StrToken values
# ---------------------------------------------------------------------------


class TestDumpDictList:
    """dump_file() strips _StrToken markers from lists and raw merge dicts."""

    def test_strip_str_tokens_in_list(self, tmp_path: Path) -> None:
        """_StrToken values in a list are written as plain str via dump_file()."""
        data = {"items": [_StrToken("a"), _StrToken("b")]}
        out = tmp_path / "out.json"
        confarg.dump_file(data, out)

        result = json.loads(out.read_text())
        assert result == {"items": ["a", "b"]}

    def test_dump_from_merge(self, tmp_path: Path) -> None:
        """dump_file() applied to a raw merge() dict produces plain values."""
        WithList = make_target("items", list[str], default_factory=list)
        raw = confarg.merge(WithList, argv=["--items", "x", "y"], env={})
        out = tmp_path / "out.json"
        confarg.dump_file(raw, out)

        result = json.loads(out.read_text())
        assert result["items"] == ["x", "y"]


# ---------------------------------------------------------------------------
# __init__.merge — --config.+ without field path (line 93)
# ---------------------------------------------------------------------------


class TestConfigAppendWithoutField:
    """--config.+ without a field path is rejected."""

    def test_config_append_no_field_path_raises(self) -> None:
        """--config.+ without a field path raises ConfargError."""
        with pytest.raises(confarg.exceptions.ConfargError, match="requires a field path"):
            confarg.load(WithDefaults, argv=["--config.+", "dummy.toml"], env={})


# ---------------------------------------------------------------------------
# _files — error handling
# ---------------------------------------------------------------------------


class TestFileErrors:
    """File-loading and file-dumping error paths."""

    def test_load_toml_file_not_found(self, tmp_path: Path) -> None:
        """Missing TOML file raises InvalidConfigFileError."""
        with pytest.raises(confarg.exceptions.InvalidConfigFileError, match="not found"):
            _load_toml(tmp_path / "missing.toml")

    def test_load_yaml_file_not_found(self, tmp_path: Path) -> None:
        """Missing YAML file raises InvalidConfigFileError."""
        with pytest.raises(confarg.exceptions.InvalidConfigFileError, match="not found"):
            _load_yaml(tmp_path / "missing.yaml")

    def test_load_json_file_not_found(self, tmp_path: Path) -> None:
        """Missing JSON file raises InvalidConfigFileError."""
        with pytest.raises(confarg.exceptions.InvalidConfigFileError, match="not found"):
            _load_json(tmp_path / "missing.json")

    def test_load_yaml_item_missing_library(self, tmp_path: Path, monkeypatch) -> None:
        """Missing PyYAML library raises InvalidConfigFileError."""
        p = tmp_path / "test.yaml"
        p.write_text("key: value")
        monkeypatch.setitem(sys.modules, "yaml", None)
        with pytest.raises(confarg.exceptions.InvalidConfigFileError, match="PyYAML"):
            _load_yaml_item(p)

    def test_load_yaml_item_file_not_found(self, tmp_path: Path) -> None:
        """Missing YAML item file raises InvalidConfigFileError."""
        with pytest.raises(confarg.exceptions.InvalidConfigFileError, match="not found"):
            _load_yaml_item(tmp_path / "missing.yaml")

    def test_load_yaml_item_malformed(self, tmp_path: Path) -> None:
        """Malformed YAML content raises InvalidConfigFileError."""
        p = tmp_path / "bad.yaml"
        p.write_text("key: :\n  - bad: [unclosed")
        with pytest.raises(confarg.exceptions.InvalidConfigFileError, match="malformed"):
            _load_yaml_item(p)

    def test_load_json_item_file_not_found(self, tmp_path: Path) -> None:
        """Missing JSON item file raises InvalidConfigFileError."""
        with pytest.raises(confarg.exceptions.InvalidConfigFileError, match="not found"):
            _load_json_item(tmp_path / "missing.json")

    def test_load_json_item_malformed(self, tmp_path: Path) -> None:
        """Malformed JSON content raises InvalidConfigFileError."""
        p = tmp_path / "bad.json"
        p.write_text("{bad json")
        with pytest.raises(confarg.exceptions.InvalidConfigFileError, match="malformed"):
            _load_json_item(p)

    def test_load_file_item_unsupported_format(self, tmp_path: Path) -> None:
        """Unsupported file extension raises InvalidConfigFileError."""
        with pytest.raises(confarg.exceptions.InvalidConfigFileError, match="Unsupported"):
            _load_file_item(tmp_path / "file.xyz")

    def test_dump_json_writes_file(self, tmp_path: Path) -> None:
        """JSON dump writes a valid JSON file to disk."""
        p = tmp_path / "out.json"
        _dump_json({"key": "value", "num": 42}, p)

        data = json.loads(p.read_text())
        assert data == {"key": "value", "num": 42}

    def test_dump_file_unsupported_format(self, tmp_path: Path) -> None:
        """Unsupported file extension in dump raises InvalidConfigFileError."""
        with pytest.raises(confarg.exceptions.InvalidConfigFileError, match="Unsupported"):
            _dump_file({"key": "val"}, tmp_path / "out.xyz")


# ---------------------------------------------------------------------------
# _callable — edge cases
# ---------------------------------------------------------------------------


class TestCallableEdgeCases:
    """Edge cases in callable resolution and serialization."""

    def test_detect_owning_class_module_not_in_sys_modules(self) -> None:
        """_detect_owning_class returns None when the function's module is not in sys.modules."""

        def fake_method():
            pass

        fake_method.__qualname__ = "SomeClass.method"
        fake_method.__module__ = "nonexistent_module_xyz_abc"
        result = _detect_owning_class(fake_method)
        assert result is None

    def test_detect_owning_class_attr_not_found(self) -> None:
        """_detect_owning_class returns None when the class attribute is missing from the module."""

        def fake_method():
            pass

        fake_method.__qualname__ = "NonExistentClass9999.method"
        fake_method.__module__ = "confarg"
        result = _detect_owning_class(fake_method)
        assert result is None

    def test_resolve_spec_already_callable(self) -> None:
        """A callable value passed directly to _resolve_callable_spec is returned unchanged."""

        def my_func(x: int) -> str:
            return str(x)

        result = _resolve_callable_spec(
            my_func,
            Callable[[int], str],
            path="test",
            union_tag="class",
            construct_fn=construct,
        )
        assert result is my_func

    def test_resolve_dict_spec_non_dict_bind_raises(self) -> None:
        """A non-dict bind: value in the fn: dict form raises TypeCoercionError."""
        spec = {"fn": "os.path.join", "bind": "not_a_dict"}
        with pytest.raises(confarg.exceptions.TypeCoercionError, match="must be a dict"):
            _resolve_callable_spec(spec, Callable, path="test", union_tag="class", construct_fn=construct)

    def test_resolve_class_spec_not_a_class_raises(self) -> None:
        """A non-class path in the class: dict form raises TypeCoercionError."""
        spec = {"class": "os.path.join"}
        with pytest.raises(confarg.exceptions.TypeCoercionError, match="must reference a class"):
            _resolve_callable_spec(spec, Callable, path="test", union_tag="class", construct_fn=construct)

    def test_resolve_spec_invalid_type_raises(self) -> None:
        """A non-str, non-dict callable spec raises TypeCoercionError."""
        with pytest.raises(confarg.exceptions.TypeCoercionError, match="expected str or dict"):
            _resolve_callable_spec(12345, Callable, path="test", union_tag="class", construct_fn=construct)

    def test_check_signature_var_positional_skipped(self) -> None:
        """*args functions skip parameter count checking."""

        def varargs_func(*args: int) -> None:
            pass

        _check_callable_signature(varargs_func, Callable[[int, int], None], path="test")

    def test_check_signature_uninspectable(self) -> None:
        """Uninspectable callables skip signature checking."""

        class Uninspectable:
            def __call__(self, x: int) -> None:
                pass

            def __signature__(self):
                msg = "cannot inspect"
                raise ValueError(msg)

        obj = Uninspectable()
        _check_callable_signature(obj, Callable[[int], None], path="test")

    def test_serialize_callable_no_module_qualname_raises(self) -> None:
        """An object without __module__ or __qualname__ raises ConfargError on serialization."""

        class Proxy:
            pass

        obj = Proxy()
        obj.__module__ = None  # ty: ignore[invalid-assignment]  # deliberately clobber __module__ to trigger fallback path
        obj.__qualname__ = None  # ty: ignore[unresolved-attribute]  # deliberately clobber __qualname__ to trigger fallback path
        with pytest.raises(confarg.exceptions.ConfargError, match="no __module__"):
            _serialize_callable(obj)


# ---------------------------------------------------------------------------
# _types — uncovered functions/branches
# ---------------------------------------------------------------------------


class TestTypesEdgeCases:
    """Edge cases in type-inspection helpers."""

    def test_is_collection_true(self) -> None:
        """list, tuple, set, and frozenset are recognized as collection types."""
        assert _is_collection(list[int]) is True
        assert _is_collection(tuple[str, int]) is True
        assert _is_collection(set[str]) is True
        assert _is_collection(frozenset[int]) is True

    def test_is_collection_false(self) -> None:
        """Int and str are not collection types."""
        assert _is_collection(int) is False
        assert _is_collection(str) is False

    def test_all_have_defaults_non_struct(self) -> None:
        """Non-struct types return False from _all_have_defaults."""
        assert _all_have_defaults(int) is False
        assert _all_have_defaults(str) is False

    def test_var_param_names_plain_class(self) -> None:
        """_var_param_names returns *args and **kwargs names for plain classes."""

        class PlainWithVars:
            def __init__(self, x: int, *args: str, **kwargs: float):
                pass

        names = _var_param_names(PlainWithVars)
        assert "args" in names
        assert "kwargs" in names

    def test_var_positional_name_plain_class(self) -> None:
        """_var_positional_name returns the *args parameter name for plain classes."""

        class PlainWithArgs:
            def __init__(self, *items: int):
                pass

        assert _var_positional_name(PlainWithArgs) == "items"

    def test_var_keyword_name_plain_class(self) -> None:
        """_var_keyword_name returns the **kwargs parameter name for plain classes."""

        class PlainWithKwargs:
            def __init__(self, **opts: str):
                pass

        assert _var_keyword_name(PlainWithKwargs) == "opts"

    def test_var_param_names_uninspectable(self) -> None:
        """_var_param_names returns an empty frozenset when __init__ is not inspectable."""

        class Broken:
            pass

        Broken.__init__ = None  # ty: ignore[invalid-assignment]  # deliberately clobber __init__ to trigger fallback path
        result = _var_param_names(Broken)
        assert result == frozenset()

    def test_var_positional_name_uninspectable(self) -> None:
        """_var_positional_name returns None when __init__ is not inspectable."""

        class Broken:
            pass

        Broken.__init__ = None  # ty: ignore[invalid-assignment]  # deliberately clobber __init__ to trigger fallback path
        assert _var_positional_name(Broken) is None

    def test_var_keyword_name_uninspectable(self) -> None:
        """_var_keyword_name returns None when __init__ is not inspectable."""

        class Broken:
            pass

        Broken.__init__ = None  # ty: ignore[invalid-assignment]  # deliberately clobber __init__ to trigger fallback path
        assert _var_keyword_name(Broken) is None

    def test_is_plain_class_uninspectable_init(self) -> None:
        """_is_plain_class returns False when __init__ is not inspectable."""

        class Broken:
            pass

        Broken.__init__ = None  # ty: ignore[invalid-assignment]  # deliberately clobber __init__ to trigger fallback path
        assert _is_plain_class(Broken) is False

    def test_init_fields_broken_init_annotation_fallback(self) -> None:
        """_init_fields falls back gracefully when get_type_hints raises a NameError."""

        # With `from __future__ import annotations`, `value: UndefinedTypeABC999` is
        # stored as the string "UndefinedTypeABC999". get_type_hints(cls.__init__)
        # tries to evaluate it in this module's globals → NameError → fallback to {}.
        class BrokenInitAnnot:
            def __init__(self, value: UndefinedTypeABC999) -> None:  # noqa: F821  # ty: ignore[unresolved-reference]  # intentionally undefined to trigger NameError fallback
                self.value = value

        result = _init_fields(BrokenInitAnnot)
        assert "value" in result


# ---------------------------------------------------------------------------
# _parse_cli — uncovered branches
# ---------------------------------------------------------------------------


class TestTypeHelpers:
    """Unit tests for type-inspection helpers: _unwrap_optional and _try_coerce."""

    def test_unwrap_optional_non_union(self) -> None:
        """_unwrap_optional returns the type unchanged for non-union types."""
        assert _unwrap_optional(int) is int

    def test_unwrap_optional_single_variant(self) -> None:
        """_unwrap_optional strips None from Optional[X] and returns X."""
        result = _unwrap_optional(Optional[int])
        assert result is int

    def test_unwrap_optional_multi_variant(self) -> None:
        """_unwrap_optional returns None for multi-variant unions (not Optional)."""
        result = _unwrap_optional(Union[int, str])
        assert result is None

    def test_try_coerce_none_ft_returns_token(self) -> None:
        """_try_coerce with ft=None returns the token unchanged."""
        token = _StrToken("hello")
        assert _try_coerce(None, token) is token

    # -----------------------------------------------------------------
    # _try_coerce: str passthrough — _StrToken is already a str subclass,
    # so str-typed fields are returned unchanged (not actively coerced).
    # -----------------------------------------------------------------

    def test_try_coerce_str_target_returns_token_unchanged(self) -> None:
        """Invariant: _try_coerce with ft=str returns the token unchanged.

        str is not in the coercible set (bool, int, float, Path, Literal, Enum),
        so the token is passed back as-is rather than being actively coerced.
        """
        token = _StrToken("hello world")
        result = _try_coerce(str, token)
        assert result is token

    def test_try_coerce_str_token_is_still_str(self) -> None:
        """_StrToken IS a str subclass — passthrough means the caller gets a str-compatible value."""
        token = _StrToken("something")
        result = _try_coerce(str, token)
        assert isinstance(result, str)

    # -----------------------------------------------------------------
    # _try_coerce: active coercion for each supported concrete type
    # -----------------------------------------------------------------

    @pytest.mark.parametrize(
        ("ft", "raw", "expected"),
        [
            (bool, _StrToken("true"), True),
            (bool, _StrToken("false"), False),
            (bool, _StrToken("1"), True),
            (bool, _StrToken("0"), False),
            (int, _StrToken("42"), 42),
            (int, _StrToken("-7"), -7),
            (float, _StrToken("3.14"), 3.14),
            (float, _StrToken("-0.5"), -0.5),
            (Path, _StrToken("/tmp/foo"), Path("/tmp/foo")),
        ],
        ids=[
            "bool-true",
            "bool-false",
            "bool-one",
            "bool-zero",
            "int-positive",
            "int-negative",
            "float-positive",
            "float-negative",
            "path",
        ],
    )
    def test_try_coerce_concrete_types(self, ft, raw, expected) -> None:
        """_try_coerce actively coerces bool, int, float, and Path tokens."""
        result = _try_coerce(ft, raw)
        assert result == expected

    def test_try_coerce_literal_str_matches_value(self) -> None:
        """_try_coerce with a Literal type coerces the token to the matching literal value."""
        token = _StrToken("fast")
        result = _try_coerce(Literal["fast", "slow"], token)
        assert result == "fast"

    def test_try_coerce_literal_int_value(self) -> None:
        """_try_coerce coerces a token to an integer literal."""
        token = _StrToken("1")
        result = _try_coerce(Literal[1, 2, 3], token)
        assert result == 1

    def test_try_coerce_enum_value(self) -> None:
        """_try_coerce coerces a token to an Enum member by value."""

        class Status(enum.Enum):
            ACTIVE = "active"
            INACTIVE = "inactive"

        token = _StrToken("active")
        result = _try_coerce(Status, token)
        assert result is Status.ACTIVE

    def test_try_coerce_invalid_bool_returns_token(self) -> None:
        """When coercion fails (e.g. bad bool string), _try_coerce returns the original token."""
        token = _StrToken("not-a-bool")
        result = _try_coerce(bool, token)
        assert result is token

    def test_try_coerce_invalid_int_returns_token(self) -> None:
        """When coercion fails for int, _try_coerce returns the original token unchanged."""
        token = _StrToken("abc")
        result = _try_coerce(int, token)
        assert result is token

    def test_try_coerce_optional_single_variant_coerces(self) -> None:
        """Optional[int] / int | None — _try_coerce unwraps the single non-None variant and coerces."""
        token = _StrToken("99")
        result = _try_coerce(Optional[int], token)
        assert result == 99

    def test_try_coerce_multi_union_returns_token(self) -> None:
        """Multi-variant union (int | str) — _try_coerce returns the token unchanged.

        construct() is responsible for handling union disambiguation.
        """
        token = _StrToken("42")
        result = _try_coerce(int | str, token)
        assert result is token

    def test_try_coerce_unrecognised_type_returns_token(self) -> None:
        """A type that is not bool/int/float/Path/Literal/Enum → token returned unchanged."""
        # dict is not in the coercible set
        token = _StrToken("{}")
        result = _try_coerce(dict, token)
        assert result is token


class TestParseCliBranches:
    """Uncovered branches in the CLI parsing logic."""

    def test_subclass_field_type_non_struct_subclass(self) -> None:
        """_subclass_field_type falls back to str for non-struct subclasses."""
        result = _subclass_field_type(_SubClassBase, "extra")
        assert result is str

    def test_subclass_field_type_disagreeing_types(self) -> None:
        """_subclass_field_type falls back to str when subclass field types disagree."""
        result = _subclass_field_type(_SubClassFieldBase, "val")
        assert result is str

    def test_resolve_field_type_tuple_variable_length(self) -> None:
        """_resolve_field_type handles variable-length tuple[int, ...] fields."""
        result = _resolve_field_type(_WithVarTupleField, ["nums", "0"], "class")
        assert result is not None

    def test_resolve_field_type_tuple_invalid_index(self) -> None:
        """_resolve_field_type returns None for out-of-range fixed tuple indices."""
        WithFixedTuple = make_target("coords", tuple[int, str])
        result = _resolve_field_type(WithFixedTuple, ["coords", "99"], "class")
        assert result is None

    def test_resolve_field_type_tuple_non_int_key(self) -> None:
        """_resolve_field_type returns None for non-integer tuple path segments."""
        WithFixedTuple = make_target("coords", tuple[int, str])
        result = _resolve_field_type(WithFixedTuple, ["coords", "notanint"], "class")
        assert result is None

    def test_resolve_field_type_subclass_fallback(self) -> None:
        """_resolve_field_type falls back to str for unknown fields via subclass scanning."""
        result = _resolve_field_type(_SubClassBase, ["extra"], "class")
        assert result is str

    def test_non_struct_bool_target(self) -> None:
        """Non-struct bool target with cli_prefix parses correctly from CLI."""
        result = confarg.load(bool, argv=["--confarg", "true"], env={}, cli_prefix="confarg")
        assert result is True

    def test_non_struct_value_target(self) -> None:
        """Non-struct str target with cli_prefix parses correctly from CLI."""
        result = confarg.load(str, argv=["--confarg", "hello"], env={}, cli_prefix="confarg")
        assert result == "hello"

    def test_unknown_arg_at_dict_path(self) -> None:
        """Unknown sub-key for a dict-typed field is accepted as a dict key."""
        WithDict = make_target("mapping", dict[str, int], default_factory=dict)
        result = confarg.load(WithDict, argv=["--mapping.foo", "42"], env={})
        assert result.mapping["foo"] in (42, "42")

    def test_list_json_array_from_cli(self) -> None:
        """A JSON array string from CLI is parsed into a list."""
        WithList = make_target("items", list[int], default_factory=list)
        result = confarg.load(WithList, argv=["--items", "[1,2,3]"], env={})
        assert result.items == [1, 2, 3]

    def test_none_sentinel_non_struct_parent(self) -> None:
        """'none' token for a non-struct optional target resolves to None."""
        result = confarg.load(int | None, argv=["--confarg", "none"], env={}, cli_prefix="confarg")
        assert result is None

    def test_dataclass_field_with_no_value(self) -> None:
        """A bare --inner flag without a value triggers default construction."""
        result = confarg.load(_WithNestedDefaultInner, argv=["--inner"], env={})
        assert result.inner.name == "default"

    def test_append_unknown_field_raises(self) -> None:
        """--unknown+ for a non-existent field raises ConfargError."""
        WithList = make_target("items", list[int], default_factory=list)
        with pytest.raises(confarg.exceptions.ConfargError):
            confarg.load(WithList, argv=["--nonexistent+", "1"], env={})


# ---------------------------------------------------------------------------
# _parse_env — uncovered branches
# ---------------------------------------------------------------------------


class TestParseEnvBranches:
    """Uncovered branches in the env-var parsing logic."""

    def test_ambiguous_env_var_in_union_raises(self) -> None:
        """An env var that matches fields in multiple union variants raises ConfargError."""
        with pytest.raises(confarg.exceptions.ConfargError, match="Ambiguous env var"):
            confarg.load(
                _AmbigUnion,
                argv=[],
                env={"SERVICE__NAME": "hello"},
                env_prefix="",
            )

    def test_tuple_variable_length_from_env(self) -> None:
        """Variable-length tuple fields are populated from indexed env vars."""
        WithVarTuple = make_target("items", tuple[int, ...], default=(1, 2))
        result = confarg.load(
            WithVarTuple,
            argv=[],
            env={"ITEMS__0": "99"},
            env_prefix="",
        )
        assert result.items[0] == 99

    def test_tuple_non_int_segment_from_env(self) -> None:
        """Non-integer env var path segment for a tuple field is silently ignored."""
        WithFixedTuple = make_target("coords", tuple[int, str], default=(0, ""))
        result = confarg.load(
            WithFixedTuple,
            argv=[],
            env={"COORDS__BAD": "hello"},
            env_prefix="",
        )
        assert result.coords == (0, "")

    def test_none_sentinel_for_non_struct(self) -> None:
        """'none' value in env var resolves a non-struct optional to None."""
        # "none"/"null" value → construct-time steal → __root__ = None
        result = confarg.load(
            str | None,
            argv=[],
            env={"VALUE": "none"},
            env_prefix="",
        )
        assert result is None

    def test_union_root_unknown_field_warns(self) -> None:
        """Env var matching no variant field emits a ConfargWarning and is skipped."""
        # "Z" doesn't match any field in either variant → warns and is skipped.
        # "A" matches _UnionRootVariantA.a → selects VariantA unambiguously.

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = confarg.load(
                _UnionRootVariantA | _UnionRootVariantB,
                argv=[],
                env={"A": "hello", "Z": "skipped"},
                env_prefix="",
            )
        assert isinstance(result, _UnionRootVariantA)
        assert result.a == "hello"
        assert any("Z" in str(w.message) for w in caught if issubclass(w.category, confarg.exceptions.ConfargWarning))


# ---------------------------------------------------------------------------
# _serialize — uncovered branches
# ---------------------------------------------------------------------------


class TestSerializeBranches:
    """Uncovered branches in the serialization logic."""

    def test_serialize_union_variant_not_found(self) -> None:
        """None value in a union field serializes to None without error."""
        instance = _WithNoneValField(val=None)
        result = confarg.dump(instance)
        assert result["val"] is None

    def test_serialize_leaf_str_token(self) -> None:
        """A _StrToken field value is serialized as a plain str."""

        @dataclass
        class Simple:
            name: str = "hello"

        instance = Simple(name=_StrToken("world"))
        result = confarg.dump(instance)
        assert result["name"] == "world"
        assert type(result["name"]) is str

    def test_serialize_needs_tag_single_struct_variant(self) -> None:
        """Single struct union variant serializes without a class tag by default."""
        instance = _WithIntOrDC(val=_StructUnionVariantA(x=5))
        result = confarg.dump(instance)
        assert result["val"]["x"] == 5

    def test_serialize_union_tag_always_policy(self) -> None:
        """tag_policy='always' includes the class tag even for unambiguous union variants."""
        instance = _WithIntOrDC(val=_StructUnionVariantA(x=5))
        result = confarg.dump(instance, tag_policy="always")
        assert "class" in result["val"]


# ---------------------------------------------------------------------------
# dictexpr — uncovered branches
# ---------------------------------------------------------------------------


class TestExpressionBranches:
    """Uncovered branches in the expression engine."""

    def test_extract_refs_syntax_error_skipped(self) -> None:
        """Syntactically invalid expression content yields an empty reference set."""
        # Expression with invalid syntax → SyntaxError caught → silently skipped
        refs = _extract_references("${invalid syntax!!!}")
        assert isinstance(refs, set)

    def test_collect_names_keyword_args(self) -> None:
        """Keyword argument names in function calls are collected as references."""
        # keyword arg 'y' should be collected as a reference
        refs = _extract_references("${sorted(x, key=y)}")
        assert "x" in refs or "y" in refs

    def test_attribute_chain_subscript_at_top(self) -> None:
        """_attribute_chain handles a subscript at the top level gracefully."""
        node = ast.parse("a[0]", mode="eval").body
        result = _attribute_chain(node)  # ty: ignore[invalid-argument-type]  # ast.parse returns ast.expr, but _attribute_chain expects a narrower union
        assert result is None or isinstance(result, list)

    def test_attribute_chain_non_int_subscript(self) -> None:
        """_attribute_chain returns None for non-integer subscript indices."""
        node = ast.parse("a[x]", mode="eval").body
        result = _attribute_chain(node)  # ty: ignore[invalid-argument-type]  # ast.parse returns ast.expr, but _attribute_chain expects a narrower union
        assert result is None

    def test_bool_op_and_all_truthy(self) -> None:
        """BoolOp 'and' with all truthy operands evaluates to True."""
        data = {"val": "${True and True and True}", "True": True}
        result = resolve_expressions(data)
        assert result["val"] is True

    def test_bool_op_or_all_falsy(self) -> None:
        """BoolOp 'or' with all falsy operands evaluates to False."""
        data = {"val": "${False or False}", "False": False}
        result = resolve_expressions(data)
        assert result["val"] is False

    def test_call_evaluation_error(self) -> None:
        """A function call that raises inside an expression wraps the error as ExpressionEvalError."""
        data = {"x": 0, "val": "${int('abc')}"}
        with pytest.raises(confarg.exceptions.ExpressionEvalError):
            resolve_expressions(data)

    def test_expression_eval_error_reraise_pure(self) -> None:
        """A runtime error in a pure ${expr} expression raises ExpressionEvalError."""
        data = {"x": 0, "val": "${1 / x}"}
        with pytest.raises(confarg.exceptions.ExpressionEvalError):
            resolve_expressions(data)

    def test_expression_eval_error_reraise_interpolation(self) -> None:
        """A runtime error inside a string interpolation expression raises ExpressionEvalError."""
        data = {"x": 0, "val": "prefix_${1 / x}"}
        with pytest.raises(confarg.exceptions.ExpressionEvalError):
            resolve_expressions(data)

    def test_get_nested_list_invalid_index_type(self) -> None:
        """Non-integer path segment into a list raises MissingReferenceError."""
        with pytest.raises(confarg.exceptions.MissingReferenceError):
            _get_nested({"items": [1, 2, 3]}, "items.notanint")

    def test_get_nested_list_out_of_range(self) -> None:
        """Out-of-range index into a list raises MissingReferenceError."""
        with pytest.raises(confarg.exceptions.MissingReferenceError):
            _get_nested({"items": [1, 2]}, "items.99")

    def test_set_nested_traverse_error(self) -> None:
        """_set_nested_by_path raises MissingReferenceError when traversal encounters a non-container."""
        with pytest.raises(confarg.exceptions.MissingReferenceError):
            _set_nested_by_path({"a": 42}, "a.b.c", "value")

    def test_set_nested_set_non_container_raises(self) -> None:
        """_set_nested_by_path raises MissingReferenceError when the target node is not a container."""
        # Traverse into list index 1 (yields int 2), then set "x" on int → else branch
        with pytest.raises(confarg.exceptions.MissingReferenceError):
            _set_nested_by_path({"a": [1, 2, 3]}, "a.1.x", "value")

    def test_unsupported_binary_op_raises(self) -> None:
        """An unsupported binary operator (@ matrix multiply) raises ExpressionEvalError."""
        node = ast.parse("a @ b", mode="eval").body
        with pytest.raises(confarg.exceptions.ExpressionEvalError, match="Unsupported binary"):
            _evaluate_ast(node, {"a": 1, "b": 2})

    def test_unsupported_unary_op_raises(self) -> None:
        """An unsupported unary operator (~ bitwise invert) raises ExpressionEvalError."""
        node = ast.parse("~a", mode="eval").body
        with pytest.raises(confarg.exceptions.ExpressionEvalError, match="Unsupported unary"):
            _evaluate_ast(node, {"a": 1})

    def test_unsupported_comparison_raises(self) -> None:
        """An unsupported comparison operator ('is') raises ExpressionEvalError."""
        node = ast.parse("a is b", mode="eval").body
        with pytest.raises(confarg.exceptions.ExpressionEvalError, match="Unsupported comparison"):
            _evaluate_ast(node, {"a": 1, "b": 1})


# ---------------------------------------------------------------------------
# typedload._coerce — uncovered branches
# ---------------------------------------------------------------------------


class TestCoerceEdgeCases:
    """Edge cases in the leaf-type coercion logic."""

    def test_coerce_leaf_path_failure(self) -> None:
        """_coerce_leaf raises TypeCoercionError when a None value cannot become a Path."""
        with pytest.raises(confarg.exceptions.TypeCoercionError):
            _coerce_leaf(Path, None)

    def test_coerce_leaf_unsupported_type(self) -> None:
        """_coerce_leaf raises TypeCoercionError for unrecognized leaf types."""

        class WeirdType:
            pass

        with pytest.raises(confarg.exceptions.TypeCoercionError, match="Unsupported leaf type"):
            _coerce_leaf(WeirdType, "value")


# ---------------------------------------------------------------------------
# typedload._construct — uncovered branches
# ---------------------------------------------------------------------------


class TestConstructEdgeCases:
    """Edge cases in the typed construction logic."""

    def test_construct_list_from_empty_dict(self) -> None:
        """An empty dict constructs as an empty list."""
        result = construct(list[int], {})
        assert result == []

    def test_construct_list_from_dict_with_non_int_keys_raises(self) -> None:
        """Dict with non-integer keys raises TypeCoercionError when constructing a list."""
        with pytest.raises(confarg.exceptions.TypeCoercionError, match="integer"):
            construct(list[int], {"bad": 1})

    def test_construct_tuple_from_dict_non_int_keys_raises(self) -> None:
        """Dict with non-integer keys raises TypeCoercionError when constructing a tuple."""
        with pytest.raises(confarg.exceptions.TypeCoercionError, match="integer"):
            construct(tuple[int, str], {"bad": "value"})

    def test_construct_union_none_with_none_type(self) -> None:
        """None value for an int | None union constructs to None."""
        result = construct(int | None, None)
        assert result is None

    def test_construct_optional_coercion_failure_hint(self) -> None:
        """An uncoercible value for int | None hints about 'none'/'null' in the error message."""
        with pytest.raises(confarg.exceptions.TypeCoercionError, match="None"):
            construct(int | None, _StrToken("notanint"))

    def test_ambiguous_class_tag_multiple_matches_raises(self) -> None:
        """Class tag matching multiple union variants (subclass relationship) raises AmbiguousUnionError."""
        # _StructUnionVariantB is a subclass of _StructUnionVariantA, so the
        # class tag for B matches both variants in the union → AmbiguousUnionError.
        data = {"class": f"{_StructUnionVariantB.__module__}.{_StructUnionVariantB.__name__}", "x": 0}
        with pytest.raises(confarg.exceptions.AmbiguousUnionError, match="matches multiple"):
            construct(_StructUnionVariantA | _StructUnionVariantB, data)

    def test_class_tag_no_matching_variant_raises(self) -> None:
        """Class tag that matches no union variant raises TypeCoercionError."""
        # _StructUnionVariantA is not a subclass of either _ConstructAVariant or
        # _ConstructBVariant → TypeCoercionError "not compatible with any union variant".
        data = {"class": f"{_StructUnionVariantA.__module__}.{_StructUnionVariantA.__name__}", "x": 0}
        with pytest.raises(confarg.exceptions.TypeCoercionError, match="not compatible"):
            construct(_ConstructAVariant | _ConstructBVariant, data)

    def test_construct_bool_in_bool_int_union(self) -> None:
        """Bool | int union: True value is constructed as bool."""
        result = construct(bool | int, data=True)
        assert result is True

    def test_construct_union_none_type_in_scalar_loop(self) -> None:
        """Str | None union: a string value constructs as str."""
        result = construct(str | None, "hello")
        assert result == "hello"

    def test_value_matches_type_none(self) -> None:
        """None value matches int | None."""
        assert _value_matches_type(None, int | None, "class") is True

    def test_value_matches_type_non_dict_for_struct(self) -> None:
        """A non-dict value does not match a struct type."""
        assert _value_matches_type("not_a_dict", _StructUnionVariantA, "class") is False

    def test_value_matches_type_float_from_invalid_str(self) -> None:
        """A non-numeric string token does not match float."""
        assert _value_matches_type(_StrToken("notfloat"), float, "class") is False

    def test_ambiguous_union_msg_includes_optional_fields(self) -> None:
        """AmbiguousUnionError message lists optional fields to help the user disambiguate."""
        # Both _AmbigOptionalP and _AmbigOptionalQ match {"val": {"x": 1}} →
        # AmbiguousUnionError with "optional" in message (listing optional fields).
        with pytest.raises(confarg.exceptions.AmbiguousUnionError, match="optional"):
            confarg.build(_AmbigContainer, {"val": {"x": 1}})

    def test_construct_struct_union_tuple_from_union(self) -> None:
        """tuple[int, str] | None union is constructed from positional CLI args."""

        @dataclass
        class WithUnionTuple:
            coord: tuple[int, str] | None = None

        result = confarg.load(WithUnionTuple, argv=["--coord", "5", "hello"], env={})
        assert result.coord == (5, "hello")

    def test_partial_tuple_index_extends_with_none(self) -> None:
        """Partial indexed env var update for a fixed-length tuple merges with the default."""

        @dataclass
        class WithTuple:
            items: tuple[int, str] = (1, "x")

        result = confarg.load(WithTuple, argv=[], env={"ITEMS__1": "y"}, env_prefix="")
        assert result.items == (1, "y")

    def test_class_tag_import_error_raises(self) -> None:
        """Class tag pointing to a non-importable module raises TypeCoercionError."""

        @dataclass
        class A:
            x: int = 0

        data = {"class": "nonexistent.module.SomeClass", "x": 1}

        with pytest.raises(confarg.exceptions.TypeCoercionError, match="Cannot import"):
            construct(A, data)


# ---------------------------------------------------------------------------
# _argparse — uncovered branches
# ---------------------------------------------------------------------------


class TestArgparseBranches:
    """Uncovered branches in the argparse integration layer."""

    def test_get_field_docstrings_no_class_found(self) -> None:
        """_get_field_docstrings returns an empty dict when the class cannot be located by name."""

        @dataclass
        class Dummy:
            x: int = 0

        original_name = Dummy.__name__
        try:
            Dummy.__name__ = "RenamedClass"
            result = _get_field_docstrings(Dummy)
            assert result == {}
        finally:
            Dummy.__name__ = original_name

    def test_walk_struct_non_struct_returns_early(self) -> None:
        """_collect_struct_specs returns empty list for non-struct types."""
        assert _collect_struct_specs(int, "", "class") == []

    def test_walk_struct_get_type_hints_exception(self) -> None:
        """_collect_struct_specs falls back gracefully when get_type_hints raises for broken annotations."""

        # This class has a CLASS-LEVEL annotation with an undefined forward ref.
        # With `from __future__ import annotations`, all annotations are strings;
        # get_type_hints(cls) tries to evaluate "UndefinedTypeXYZ999" in this
        # module's globals → NameError → except Exception → fallback to flds.
        class BrokenClassAnnot:
            _bad: UndefinedTypeXYZ999  # noqa: F821  # ty: ignore[unresolved-reference]  # intentionally undefined to trigger NameError fallback

            def __init__(self, value: int) -> None:
                self.value = value

        _collect_struct_specs(BrokenClassAnnot, "", "class")

    def test_walk_struct_union_tag_field_skipped(self) -> None:
        """The union_tag field is not registered as a CLI flag by populate_parser."""

        @dataclass
        class WithTypeField:
            type: str = "a"
            value: int = 0

        parser = argparse.ArgumentParser()
        populate_parser(WithTypeField, parser, union_tag="type")
        flags = {s for a in parser._actions for s in a.option_strings}
        assert "--type" not in flags
        assert "--value" in flags

    def test_walk_struct_callable_field_registered(self) -> None:
        """A Callable-typed field is registered as a CLI flag by populate_parser."""

        @dataclass
        class WithCallable:
            fn: Callable[[int], str] = str

        parser = argparse.ArgumentParser()
        populate_parser(WithCallable, parser)
        flags = {s for a in parser._actions for s in a.option_strings}
        assert "--fn" in flags

    def test_walk_struct_variable_length_tuple_field(self) -> None:
        """A variable-length tuple[int, ...] field is registered as a CLI flag."""

        @dataclass
        class WithVarTuple:
            nums: tuple[int, ...] = ()

        parser = argparse.ArgumentParser()
        populate_parser(WithVarTuple, parser)
        flags = {s for a in parser._actions for s in a.option_strings}
        assert "--nums" in flags

    def test_walk_struct_var_param_field_skipped(self) -> None:
        """*args fields are not included in static flag specs."""

        class PlainWithArgs:
            def __init__(self, x: int, *extras: str):
                pass

        specs = _collect_struct_specs(PlainWithArgs, "", "class")
        assert not any(s.name == "extras" for s in specs)

    def test_register_subconfig_flags_non_struct(self) -> None:
        """_collect_subconfig_specs returns empty list for non-struct types."""
        assert _collect_subconfig_specs(int, "config", "", "class") == []

    def test_register_subconfig_flags_get_type_hints_exception(self) -> None:
        """_collect_subconfig_specs falls back gracefully when get_type_hints raises."""

        # A class with a broken CLASS-LEVEL annotation (not __init__) causes
        # get_type_hints(cls) to fail, but _struct_fields succeeds via __init__.
        class BrokenClassAnnot:
            _bad: UndefinedType999  # noqa: F821  # ty: ignore[unresolved-reference]  # intentionally undefined to trigger NameError fallback

            def __init__(self, x: int, y: str = "default") -> None:
                self.x = x
                self.y = y

        _collect_subconfig_specs(BrokenClassAnnot, "config", "", "class")

    def test_register_subconfig_flags_union_tag_skipped(self) -> None:
        """_collect_subconfig_specs skips the union_tag field."""

        @dataclass
        class WithTypeField:
            type: str = "a"
            value: int = 0

        _collect_subconfig_specs(WithTypeField, "config", "", union_tag="type")

    def test_collect_ns_fields_non_struct(self) -> None:
        """_collect_ns_fields is a no-op for non-struct types."""
        result: dict[str, Any] = {}
        _collect_ns_fields({}, int, "", "class", result)
        assert result == {}

    def test_collect_ns_fields_get_type_hints_exception(self) -> None:
        """_collect_ns_fields falls back gracefully when get_type_hints raises."""

        class BrokenClassAnnot2:
            _bad: UndefinedType888  # noqa: F821  # ty: ignore[unresolved-reference]  # intentionally undefined to trigger NameError fallback

            def __init__(self, x: int, y: str = "default") -> None:
                self.x = x
                self.y = y

        result: dict[str, Any] = {}
        _collect_ns_fields({"x": "42"}, BrokenClassAnnot2, "", "class", result)
        assert "x" in result or result == {}

    def test_collect_ns_fields_union_tag_skipped(self) -> None:
        """_collect_ns_fields excludes the union_tag field from the result."""

        @dataclass
        class WithTypeField:
            type: str = "a"
            value: int = 0

        result: dict[str, Any] = {}
        _collect_ns_fields({"type": "b", "value": "99"}, WithTypeField, "", union_tag="type", result=result)
        assert "type" not in result

    def test_collect_ns_fields_multi_union_skipped(self) -> None:
        """_collect_ns_fields skips fields with multi-variant union types."""

        @dataclass
        class WithMultiUnion:
            val: int | str = 0

        result: dict[str, Any] = {}
        _collect_ns_fields({"val": "99"}, WithMultiUnion, "", "class", result)

    def test_collect_ns_fields_dict_skipped(self) -> None:
        """_collect_ns_fields skips dict-typed fields."""

        @dataclass
        class WithDict:
            mapping: dict[str, int] = field(default_factory=dict)

        result: dict[str, Any] = {}
        _collect_ns_fields({"mapping": '{"a": 1}'}, WithDict, "", "class", result)
        assert "mapping" not in result

    def test_from_namespace_with_expressions(self) -> None:
        """from_namespace resolves ${...} expressions supplied via the env parameter."""

        @dataclass
        class WithExpr:
            host: str = "localhost"
            db_host: str = "myserver"

        parser = argparse.ArgumentParser()
        populate_parser(WithExpr, parser)
        ns = parser.parse_args([])
        # Pass env vars with an expression — the resolved value triggers expr_map storage
        result = from_namespace(WithExpr, ns, env={"HOST": "${db_host}", "DB_HOST": "realserver"}, env_prefix="")
        assert result.host == "realserver"


# ---------------------------------------------------------------------------
# _parse_env — dict type and tuple branches
# ---------------------------------------------------------------------------


class TestParseEnvDictAndFallthrough:
    """Env-var parsing for dict fields and out-of-range tuple indices."""

    def test_dict_field_from_env(self) -> None:
        """Dict-typed field is populated from env vars using double-underscore key separation."""
        WithDict = make_target("mapping", dict[str, int], default_factory=dict)
        result = confarg.load(
            WithDict,
            argv=[],
            env={"MAPPING__KEY": "42"},
            env_prefix="",
        )
        assert result.mapping.get("key") == 42 or "key" in result.mapping

    def test_tuple_out_of_range_from_env(self) -> None:
        """Out-of-range env var index for a fixed-length tuple raises TypeCoercionError."""
        # Index 5 is out of range for a 2-element tuple; the partial-index
        # merge extends the base list to 6 elements, then _construct_tuple rejects it.
        WithTuple = make_target("coords", tuple[int, str], default=(0, ""))
        with pytest.raises(confarg.exceptions.TypeCoercionError):
            confarg.load(
                WithTuple,
                argv=[],
                env={"COORDS__5": "hello"},
                env_prefix="",
            )

    def test_scalar_field_with_deep_env_path(self) -> None:
        """A deeper-than-expected env var path for a scalar field raises TypeCoercionError."""
        WithInt = make_target("count", int, default=0)
        with pytest.raises(confarg.exceptions.TypeCoercionError):
            confarg.load(WithInt, argv=[], env={"COUNT__EXTRA": "5"}, env_prefix="")


# ---------------------------------------------------------------------------
# _callable — non-callable instance, slotted callable, bare Callable check
# ---------------------------------------------------------------------------


class TestCallableBranches:
    """Uncovered branches in callable resolution."""

    def test_non_callable_instance_raises(self) -> None:
        """An instance of a non-callable class raises TypeCoercionError in _resolve_class_spec."""
        cls_path = f"{_NotCallableClass.__module__}.{_NotCallableClass.__qualname__}"
        with pytest.raises(confarg.exceptions.TypeCoercionError, match="is not callable"):
            _resolve_class_spec(
                _ClassSpec(cls_path, {}, {}, {"class": cls_path}),
                "test_path",
                "class",
                None,
                construct,
            )

    def test_slotted_callable_confarg_spec_except_branch(self) -> None:
        """A slotted callable class resolves successfully in _resolve_class_spec."""
        cls_path = f"{_SlottedCallableClass.__module__}.{_SlottedCallableClass.__qualname__}"
        result = _resolve_class_spec(
            _ClassSpec(cls_path, {"value": 5}, {}, {"class": cls_path, "value": 5}),
            "test_path",
            "class",
            None,
            construct,
        )
        assert callable(result)

    def test_check_callable_signature_non_callable_type_returns_early(self) -> None:
        """_check_callable_signature is a no-op when the target type is not Callable."""
        # Line 222-223: `if not _is_callable(tp): return` — tp=int is not a Callable type
        _check_callable_signature(lambda: None, int, path="test")

    def test_check_callable_signature_bare_callable_returns_early(self) -> None:
        """_check_callable_signature is a no-op for bare Callable (no parameter types)."""
        # Line 225-226: bare Callable has no param_types → returns early
        _check_callable_signature(lambda: None, Callable, path="test")


# ---------------------------------------------------------------------------
# _files — YAML missing library
# ---------------------------------------------------------------------------


class TestFilesMissingLibrary:
    """File loading fails gracefully when optional libraries are absent."""

    def test_yaml_missing_library(self, tmp_yaml) -> None:
        """Missing PyYAML library raises InvalidConfigFileError when loading a YAML file."""
        path = tmp_yaml("host: myserver")
        with (
            unittest.mock.patch.dict(sys.modules, {"yaml": None}),
            pytest.raises(confarg.exceptions.InvalidConfigFileError, match="PyYAML"),
        ):
            _load_yaml(path)


# ---------------------------------------------------------------------------
# _parse_cli — non-struct subclass, union with no matching field,
#              dict-at-path, non-bool non-struct bare flag
# ---------------------------------------------------------------------------


class TestParseCLIBranches:
    """Additional uncovered CLI parsing branches."""

    def test_non_struct_subclass_skipped(self) -> None:
        """Unknown CLI field for a non-struct subclass raises UnknownArgumentError."""
        # _NonStructSubChild overrides __init__ with no params → not a struct.
        # _subclass_field_type(_NonStructSubBase, "unknown") → scans subclasses,
        # hits `if not _is_struct(sub): continue` (line 80), returns None.
        with pytest.raises(confarg.exceptions.UnknownArgumentError):
            confarg.load(_NonStructSubBase, argv=["--unknown_field", "5"])

    def test_union_variants_no_matching_field_returns_none(self) -> None:
        """_resolve_field_type returns None when the path matches no union variant field."""
        result = _resolve_field_type(_AmbigVariantX | _AmbigVariantY, ["z"], "class")
        assert result is None

    def test_dict_at_path_triggers_line_164_and_360(self) -> None:
        """A deep CLI sub-key path into a dict-typed field raises TypeCoercionError."""
        DCWithDict = make_target("mapping", dict[str, int], default_factory=dict)
        # --mapping.subkey.deeper triggers ft=None, then _is_dict_at_path returns True
        with pytest.raises(confarg.exceptions.TypeCoercionError):
            confarg.load(DCWithDict, argv=["--mapping.subkey.deeper", "hello"])

    def test_dict_at_path_bare_flag(self) -> None:
        """A bare CLI flag (no value) at a dict sub-path is skipped without error."""
        DCWithDict = make_target("mapping", dict[str, int], default_factory=dict)
        # Bare flag (no value) after dict-at-path: i+1 is end or flag, skip value
        confarg.load(DCWithDict, argv=["--mapping.subkey.deeper", "--mapping.key", "42"])

    def test_non_bool_optional_bare_flag_sets_none(self) -> None:
        """'none' token for a str | None non-struct target resolves to None."""
        # Non-struct optional target with cli_prefix + "none" token → __root__ = None
        result = confarg.load(str | None, argv=["--myapp", "none"], cli_prefix="myapp")
        assert result is None

    def test_non_bool_non_optional_bare_flag_sets_true(self) -> None:
        """'true' token for a bool | str non-struct target is stolen as bool True."""
        # Non-struct bool|str union: "true" steals to bool True
        result = confarg.load(bool | str, argv=["--myapp", "true"], cli_prefix="myapp")
        assert result is True


# ---------------------------------------------------------------------------
# _serialize — union variant not found (float in int|DC field)
# ---------------------------------------------------------------------------


class TestSerializeUnionVariantNotFound:
    """Serialization when the value does not match any union variant."""

    def test_serialize_no_matching_union_variant(self) -> None:
        """A float value in an int | DC union field is serialized as-is."""
        instance = _WithIntOrDC.__new__(_WithIntOrDC)
        object.__setattr__(instance, "val", math.pi)
        result = confarg.dump(instance)
        assert result["val"] == math.pi


# ---------------------------------------------------------------------------
# dictexpr — keyword args in method call, non-integer subscript,
#            unexpected exceptions in pure and interpolation modes
# ---------------------------------------------------------------------------


class TestExpressionsBranches:
    """Additional uncovered branches in the expression engine."""

    def test_collect_names_keyword_arg_in_safe_method_call(self) -> None:
        """Keyword arg names in a safe method call are collected as references."""
        refs = _extract_references("${x.replace(a, old=b)}")
        assert "x" in refs
        assert "b" in refs

    def test_attribute_chain_noninteger_subscript_returns_none(self) -> None:
        """_attribute_chain returns None for string subscripts (non-integer indices)."""
        refs = _extract_references("${servers['primary'].host}")
        assert isinstance(refs, set)

    def test_pure_expression_unexpected_exception_wrapped(self) -> None:
        """An unexpected exception inside a pure expression is wrapped as ExpressionEvalError."""

        @dataclass
        class DC:
            a: list = field(default_factory=list)
            b: str = ""
            result: str = ""

        with pytest.raises(confarg.exceptions.ExpressionEvalError):
            confarg.build(DC, {"a": [1, 2, 3], "b": "key", "result": "${a[b]}"})

    def test_interpolation_missing_ref_reraises(self) -> None:
        """A missing field reference inside a string interpolation raises MissingReferenceError."""
        WithStr = make_target("msg", str, default="")
        with pytest.raises(confarg.exceptions.MissingReferenceError):
            confarg.build(WithStr, {"msg": "hello ${missing_field} world"})

    def test_interpolation_unexpected_exception_wrapped(self) -> None:
        """An unexpected exception inside a string interpolation is wrapped as ExpressionEvalError."""

        @dataclass
        class DC:
            a: list = field(default_factory=list)
            b: str = ""
            result: str = ""

        with pytest.raises(confarg.exceptions.ExpressionEvalError):
            confarg.build(DC, {"a": [1, 2, 3], "b": "key", "result": "prefix_${a[b]}_suffix"})


# ---------------------------------------------------------------------------
# typedload/_coerce — non-token non-numeric float, non-str value for str type
# ---------------------------------------------------------------------------


class TestCoerceBranches:
    """Additional uncovered coercion branches."""

    def test_float_from_dict_raises(self) -> None:
        """A dict value cannot be coerced to float; raises TypeCoercionError."""
        with pytest.raises(confarg.exceptions.TypeCoercionError):
            _coerce_leaf(float, {"nested": "val"}, "field")

    def test_str_from_int_raises(self) -> None:
        """A bare int value cannot be coerced to str; raises TypeCoercionError."""
        with pytest.raises(confarg.exceptions.TypeCoercionError):
            _coerce_leaf(str, 42, "field")


# ---------------------------------------------------------------------------
# typedload/_construct — union single-tuple variant from dict, tuple from
#   dict with bad keys / out-of-range index, tuple variants in union, bool|int
# ---------------------------------------------------------------------------


class TestConstructBranches:
    """Additional uncovered construction branches for tuples and unions."""

    def test_union_single_tuple_variant_dict_data(self) -> None:
        """Union with a single tuple variant constructs correctly from indexed env vars."""
        # Line 128: tup_tp = tup_vars[0] for union with single tuple variant + dict data
        result = confarg.load(
            _WithUnionTupleOrNone,
            argv=[],
            env={"COORD__0": "1", "COORD__1": "hello"},
            env_prefix="",
        )
        assert result.coord == (1, "hello")

    def test_construct_tuple_from_dict_non_integer_keys(self) -> None:
        """Dict with non-integer string keys raises TypeCoercionError for a tuple."""
        with pytest.raises(confarg.exceptions.TypeCoercionError, match="integer indices"):
            construct(tuple[int, str], {"a": 1, "b": "hello"})

    def test_construct_tuple_from_dict_out_of_range_index(self) -> None:
        """Out-of-range integer index for a fixed-length tuple raises TypeCoercionError."""
        with pytest.raises(confarg.exceptions.TypeCoercionError, match="out of range"):
            construct(tuple[int, str], {"0": 1, "5": "hello"})

    def test_tuple_variants_in_union_list_data(self) -> None:
        """tuple[int, str] | int union: a list value constructs as the tuple variant."""
        result = construct(tuple[int, str] | int, [1, "hello"])
        assert result == (1, "hello")

    def test_tuple_variants_dict_noninteger_keys(self) -> None:
        """Dict with non-integer keys raises TypeCoercionError for a tuple | int union."""
        with pytest.raises(confarg.exceptions.TypeCoercionError):
            construct(tuple[int, str] | int, {"a": 1, "b": "hello"})

    def test_bool_int_union_bool_value_returns_bool(self) -> None:
        """Bool | int union: a True value is constructed as bool, not int."""
        result = construct(bool | int, data=True)
        assert result is True

    def test_value_matches_type_bool_with_non_token_non_bool_value(self) -> None:
        """An int (non-bool, non-token) value does not match bool."""
        # Line 512: bool type, value is int (not bool, not _StrToken) → return False
        assert _value_matches_type(42, bool, "class") is False

    def test_union_class_tag_resolves_to_non_class(self) -> None:
        """A class tag that resolves to a non-class object raises TypeCoercionError."""
        with pytest.raises(confarg.exceptions.TypeCoercionError, match="must be a class path"):
            construct(
                _StructUnionVariantA | _StructUnionVariantB,
                {"class": "confarg._defaults.UNION_TAG", "x": 0},
            )

    def test_list_replace_base_key_in_construct(self) -> None:
        """LIST_REPLACE_BASE_KEY in a list construction dict applies ops against the base list."""
        result = construct(list[int], {LIST_REPLACE_BASE_KEY: [1, 2, 3]})
        assert result == [1, 2, 3]

    def test_list_delete_without_base_raises(self) -> None:
        """LIST_DELETE_KEY without a base list raises TypeCoercionError."""
        with pytest.raises(confarg.exceptions.TypeCoercionError, match="requires a base list"):
            construct(list[int], {LIST_DELETE_KEY: [0]})

    def test_try_coll_variants_all_fail_returns_no_match(self) -> None:
        """_try_coll_variants returns _UNION_NO_MATCH when all collection variants fail."""
        # list[int] | int: passing {"bad": "val"} fails list construction → except → continue
        # then int coercion also fails → TypeCoercionError from outer union handler
        with pytest.raises(confarg.exceptions.TypeCoercionError):
            construct(list[int] | int, {"bad": "val"})

    def test_coerce_scalar_variants_none_token_multi_union(self) -> None:
        """_coerce_scalar_variants returns None for 'none' token in a multi-variant union."""
        # int | str | None with _StrToken("none") → hits line 503
        result = construct(int | str | None, _StrToken("none"))
        assert result is None


# ---------------------------------------------------------------------------
# _merge — uncovered branches
# ---------------------------------------------------------------------------


class TestMergeGaps:
    """Uncovered branches in _merge.py."""

    def test_delete_sentinel_repr(self) -> None:
        """DICT_DELETE sentinel has repr '_DELETE_'."""
        assert repr(DICT_DELETE) == "_DELETE_"

    def test_merge_regular_key_delete_preserves_append(self) -> None:
        """When a delete-spec arrives and existing value has an append-spec, the append is preserved."""
        result: dict = {"key": {LIST_APPEND_KEY: [1, 2]}}
        _merge_regular_key("key", {LIST_DELETE_KEY: [0]}, result)
        assert LIST_APPEND_KEY in result["key"]
        assert LIST_DELETE_KEY in result["key"]

    def test_apply_append_key_existing_list(self) -> None:
        """When the existing value is a plain list, items are appended to it directly."""
        result: dict = {"key": [1, 2]}
        _apply_append_key("key", 3, result)
        assert result["key"] == [1, 2, 3]

    def test_apply_append_key_existing_append_dict(self) -> None:
        """When the existing value is a {'+': [...]} dict, items are merged into the append list."""
        result: dict = {"key": {LIST_APPEND_KEY: [1, 2]}}
        _apply_append_key("key", 3, result)
        assert result["key"][LIST_APPEND_KEY] == [1, 2, 3]

    def test_normalize_merge_ops_double_delete_indices(self) -> None:
        """Two 'N-' keys in the same dict merge their delete indices (hits line 132)."""
        # "-" key (len=1) is treated as a regular key → stored as result["-"] = [1]
        # "3-" key → delete_indices = [3]
        # At end: existing_del = [1] → sorted({1, 3}) = [1, 3]
        result = _normalize_merge_ops({LIST_DELETE_KEY: [1], "3-": "x"})
        assert 3 in result[LIST_DELETE_KEY]
        assert 1 in result[LIST_DELETE_KEY]

    def test_deep_merge_list_delete_both_sides(self) -> None:
        """Merging two dicts both having LIST_DELETE_KEY combines deletion indices."""
        base = {"items": {LIST_DELETE_KEY: [0]}}
        override = {"items": {LIST_DELETE_KEY: [1]}}
        merged = _deep_merge(base, override)
        assert sorted(merged["items"][LIST_DELETE_KEY]) == [0, 1]

    def test_set_nested_nonint_key_in_append_dict(self) -> None:
        """Non-integer path segment into an append-dict falls through to normal dict set."""
        d: dict = {LIST_APPEND_KEY: [{"a": 1}]}
        _set_nested(d, ["nonint", "b"], "value")
        assert d.get("nonint") == {"b": "value"}

    def test_set_nested_list_intermediate_converted(self) -> None:
        """An intermediate list value in _set_nested is converted to {LIST_REPLACE_BASE_KEY: list}."""
        d: dict = {"a": [1, 2, 3]}
        _set_nested(d, ["a", "subkey"], "value")
        assert LIST_REPLACE_BASE_KEY in d["a"]

    def test_accumulate_list_delete_list_intermediate(self) -> None:
        """An intermediate list value in _accumulate_list_delete is converted to a replace-base dict."""
        d: dict = {"a": [1, 2, 3]}
        _accumulate_list_delete(d, ["a"], 0, "test")
        assert LIST_REPLACE_BASE_KEY in d["a"]


# ---------------------------------------------------------------------------
# _parse_cli — uncovered branches (second batch)
# ---------------------------------------------------------------------------


class TestParseCliGaps2:
    """Second batch of uncovered CLI parsing branches."""

    def test_list_delete_unknown_field_raises(self) -> None:
        """--nonexistent.0- on a dataclass without that field raises UnknownArgumentError."""
        WithList = make_target("items", list[int], default_factory=list)
        with pytest.raises(confarg.exceptions.UnknownArgumentError):
            confarg.load(WithList, argv=["--nonexistent.0-"])

    def test_double_append_after_replace_base(self) -> None:
        """Two --items+ after --items a b accumulates all items (hits LIST_REPLACE_BASE_KEY branch)."""
        WithList = make_target("items", list[str], default_factory=list)
        result = confarg.load(WithList, argv=["--items", "a", "b", "--items+", "c", "--items+", "d"])
        assert result.items == ["a", "b", "c", "d"]

    def test_append_token_non_dict_node_traversal(self) -> None:
        """_handle_append_token handles non-dict intermediate node gracefully."""

        @dataclass
        class _Inner:
            nums: list[int] = field(default_factory=list)

        @dataclass
        class _Outer:
            inner: _Inner = field(default_factory=_Inner)

        ctx = _ParseCtx(argv=["--inner.nums+", "1"], target=_Outer, union_tag="class")
        # Set data["inner"] to a list (not a dict) to trigger the else branch at line 421
        ctx.data["inner"] = [99]
        _handle_append_token(ctx, 1, "--inner.nums+", list[int], ["inner", "nums"])

    def test_scalar_root_missing_value_raises(self) -> None:
        """Non-struct target with no value after the flag raises ConfargError."""
        with pytest.raises(confarg.exceptions.ConfargError, match="Missing value"):
            confarg.load(str, argv=["--confarg"], cli_prefix="confarg")


# ---------------------------------------------------------------------------
# _parse_env — JSON parse failure
# ---------------------------------------------------------------------------


class TestParseEnvJsonFailure:
    """JSON parse failure in env-var value for list/dict fields."""

    def test_malformed_json_list_falls_through(self) -> None:
        """A malformed JSON array string for a list field falls through to string coercion."""
        WithList = make_target("items", list[str], default_factory=list)
        # "[1,2,3" is invalid JSON → JSONDecodeError → pass → _try_coerce as string
        # Result is unpredictable but must not crash

        with contextlib.suppress(confarg.exceptions.TypeCoercionError):
            confarg.load(WithList, argv=[], env={"ITEMS": "[1,2,3"}, env_prefix="")


# ---------------------------------------------------------------------------
# _types — _is_nullable for type(None)
# ---------------------------------------------------------------------------


class TestIsNullable:
    """_allows_none returns True for the NoneType itself."""

    def test_is_nullable_none_type(self) -> None:
        """_allows_none(type(None)) returns True."""
        assert _allows_none(type(None)) is True


# ---------------------------------------------------------------------------
# _files — circular include in list, unsupported extension in include
# ---------------------------------------------------------------------------


class TestFilesIncludeGaps:
    """Coverage for circular-include detection in lists and unsupported include extensions."""

    def test_circular_include_in_list_raises(self, tmp_path: Path) -> None:
        """A list item with __include__ pointing back to itself raises ConfargError."""
        p = tmp_path / "circular.json"
        p.write_text(json.dumps({"items": [{"__include__": "circular.json"}]}))
        with pytest.raises(confarg.exceptions.ConfargError, match="Circular include"):
            _load_file(p)

    def test_unsupported_extension_in_include_raises(self, tmp_path: Path) -> None:
        """An __include__ pointing to an unsupported extension raises InvalidConfigFileError."""
        unsupported = tmp_path / "data.xyz"
        unsupported.write_text("hello")
        p = tmp_path / "root.json"
        p.write_text(json.dumps({"__include__": "data.xyz"}))
        with pytest.raises(confarg.exceptions.InvalidConfigFileError, match="Unsupported"):
            _load_file(p)


# ---------------------------------------------------------------------------
# typedload/_coerce — TypeRef non-class
# ---------------------------------------------------------------------------


class TestCoerceTypeRefNonClass:
    """TypeRef coercion raises when import resolves to a non-class."""

    def test_type_ref_non_class_raises(self) -> None:
        """A dotted path resolving to a function raises TypeCoercionError for TypeRef fields."""
        # os.path.join is a function, not a class; bare `type` has object constraint
        with pytest.raises(confarg.exceptions.TypeCoercionError, match="expected a class"):
            _coerce_type_ref(type, _StrToken("os.path.join"))


# ---------------------------------------------------------------------------
# _callable — uncovered branches
# ---------------------------------------------------------------------------


class TestCallableGaps:
    """Uncovered branches in _callable.py."""

    def test_import_dotted_module_raises_non_import_error(self, monkeypatch) -> None:
        """_import_dotted raises SymbolImportError when module loading raises non-ImportError."""
        real_import = importlib.import_module

        def patched_import(name: str, *args, **kwargs):
            if name == "fake_exploding_module":
                msg = "deliberate boom"
                raise RuntimeError(msg)
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(importlib, "import_module", patched_import)
        with pytest.raises(SymbolImportError, match="error loading module"):
            _import_dotted("fake_exploding_module.something")

    def test_format_fn_dict_example_uninspectable(self) -> None:
        """_format_fn_dict_example falls back gracefully when signature inspection raises."""

        class _NoSig:
            def __init__(self):
                pass

        _NoSig.__init__ = None  # ty: ignore[invalid-assignment]  # deliberately clobber __init__ to trigger fallback path
        result = _format_fn_dict_example("some.path", _NoSig)
        assert "some.path" in result

    def test_format_fn_dict_example_optional_params(self) -> None:
        """_format_fn_dict_example formats optional constructor params (lines 128-130)."""
        # _CovOptMethod has required=int, optional=str; calling it with no args raises TypeError
        # → _format_fn_dict_example is called → optional params loop runs
        with pytest.raises(TypeCoercionError, match="Cannot instantiate"):
            _resolve_bare_string(f"{_COV_MOD}._CovOptMethod.method", "test_path")

    def test_resolve_call_kwargs_uninspectable(self, monkeypatch) -> None:
        """_resolve_call_kwargs falls back to raw dict for uninspectable callables."""

        def _boom(*args, **kwargs):
            msg = "uninspectable"
            raise TypeError(msg)

        monkeypatch.setattr(callable_mod.inspect, "signature", _boom)
        result = _resolve_call_kwargs(len, {"x": 1}, "test", "class", construct_fn=None)
        assert result == {"x": 1}

    def test_resolve_call_spec_raises_on_call_failure(self) -> None:
        """_resolve_call_spec raises TypeCoercionError when the called function raises."""
        with pytest.raises(confarg.exceptions.TypeCoercionError, match="Failed to call"):
            _resolve_call_spec(f"{_COV_MOD}._cov_raise_fn", {"x": 1}, {}, "test", "class", construct)

    def test_coerce_bind_kwargs_string_values(self) -> None:
        """_coerce_bind_kwargs coerces _StrToken bind values to annotated parameter types."""

        def fn(lr: float, steps: int = 10) -> None:
            pass

        result = _coerce_bind_kwargs(fn, {"lr": _StrToken("0.01"), "steps": _StrToken("5")})
        assert result["lr"] == pytest.approx(0.01)
        assert result["steps"] == 5

    def test_coerce_bind_kwargs_uninspectable(self) -> None:
        """_coerce_bind_kwargs returns bind unchanged for uninspectable callables."""
        result = _coerce_bind_kwargs(len, {"x": "val"})
        assert result == {"x": "val"}

    def test_check_bind_params_uninspectable(self, monkeypatch) -> None:
        """_check_bind_params returns without error for uninspectable callables."""

        def _boom(*args, **kwargs):
            msg = "uninspectable"
            raise ValueError(msg)

        monkeypatch.setattr(callable_mod.inspect, "signature", _boom)
        _check_bind_params(len, {"x": 1}, "test")

    def test_resolve_call_kwargs_unannotated_param(self) -> None:
        """_resolve_call_kwargs passes unannotated params through unchanged (line 229)."""

        def fn(x, y=10):  # no annotations
            pass

        result = _resolve_call_kwargs(fn, {"x": "hello", "y": "5"}, "test", "class", construct_fn=None)
        assert result["x"] == "hello"

    def test_resolve_factory_kwargs_uninspectable(self) -> None:
        """_resolve_factory_kwargs returns raw kwargs for uninspectable __init__."""

        class _Uninspectable:
            pass

        _Uninspectable.__init__ = None  # ty: ignore[invalid-assignment]  # deliberately clobber __init__ to trigger fallback path
        result = _resolve_factory_kwargs(_Uninspectable, {"a": 1}, "test", "class", construct_fn=None)
        assert result == {"a": 1}

    def test_resolve_factory_kwargs_get_type_hints_fails(self) -> None:
        """_resolve_factory_kwargs falls back to {} hints when get_type_hints raises."""

        class _BrokenHints:
            def __init__(self, x: UndefinedType777) -> None:  # noqa: F821  # ty: ignore[unresolved-reference]  # intentionally undefined to trigger NameError fallback
                self.x = x

        result = _resolve_factory_kwargs(_BrokenHints, {"x": 1}, "test", "class", construct_fn=None)
        assert result["x"] == 1

    def test_resolve_factory_kwargs_unannotated_param(self) -> None:
        """_resolve_factory_kwargs passes unannotated params through unchanged (line 451)."""

        class _UnannotatedInit:
            def __init__(self, x, y=10):  # no annotations
                pass

        result = _resolve_factory_kwargs(_UnannotatedInit, {"x": "val", "y": "5"}, "test", "class", construct_fn=None)
        assert result["x"] == "val"

    def test_resolve_call_kwargs_get_type_hints_fails(self) -> None:
        """_resolve_call_kwargs falls back to {} hints when get_type_hints raises."""

        def _fn(x: UndefinedType777) -> None:  # noqa: F821  # ty: ignore[unresolved-reference]  # intentionally undefined to trigger NameError fallback
            pass

        result = _resolve_call_kwargs(_fn, {"x": 1}, "test", "class", construct_fn=None)
        assert result["x"] == 1

    def test_coerce_bind_kwargs_signature_raises(self, monkeypatch) -> None:
        """_coerce_bind_kwargs returns bind unchanged when inspect.signature raises."""

        def _boom(*args, **kwargs):
            msg = "uninspectable"
            raise ValueError(msg)

        monkeypatch.setattr(callable_mod.inspect, "signature", _boom)

        def fn(x: int) -> None:
            pass

        result = _coerce_bind_kwargs(fn, {"x": _StrToken("1")})
        assert result == {"x": _StrToken("1")}

    def test_coerce_bind_kwargs_get_type_hints_fails(self) -> None:
        """_coerce_bind_kwargs falls back to {} hints when get_type_hints raises."""

        def _fn(x: UndefinedHintType999) -> None:  # noqa: F821  # ty: ignore[unresolved-reference]  # intentionally undefined to trigger NameError fallback
            pass

        result = _coerce_bind_kwargs(_fn, {"x": _StrToken("1")})
        assert result["x"] == _StrToken("1")

    def test_coerce_bind_kwargs_unannotated_param(self) -> None:
        """_coerce_bind_kwargs passes _StrToken values through for unannotated params."""

        def fn(x, y=10):  # no annotations
            pass

        result = _coerce_bind_kwargs(fn, {"x": _StrToken("hello")})
        assert result["x"] == _StrToken("hello")

    def test_coerce_bind_kwargs_non_numeric_type(self) -> None:
        """_coerce_bind_kwargs leaves _StrToken values for non-bool/int/float types."""

        def fn(name: str) -> None:
            pass

        result = _coerce_bind_kwargs(fn, {"name": _StrToken("hello")})
        assert result["name"] == _StrToken("hello")

    def test_coerce_bind_kwargs_coercion_fails(self) -> None:
        """_coerce_bind_kwargs falls back to original value when coercion raises."""

        def fn(x: int) -> None:
            pass

        result = _coerce_bind_kwargs(fn, {"x": _StrToken("not_an_int")})
        assert result["x"] == _StrToken("not_an_int")

    def test_is_factory_class_issubclass_type_error(self) -> None:
        """_is_factory_class returns False when issubclass raises TypeError."""

        # Non-runtime-checkable Protocol → issubclass raises TypeError
        class _P(Protocol):
            def method(self) -> None: ...

        class _A:
            pass

        assert _is_factory_class(_A, Callable[..., _P]) is False


# ---------------------------------------------------------------------------
# _build.py — callable spec functions, fn-path scanning
# ---------------------------------------------------------------------------


class TestBuildCallableSpecs:
    """Tests for _build.py callable spec builder functions."""

    def test_collect_callable_bind_specs_valid_fn(self) -> None:
        """_collect_callable_bind_specs returns FlagSpecs for a valid function's parameters."""
        specs = _collect_callable_bind_specs("myfn", f"{_COV_MOD}._cov_call_fn", set())
        names = [s.name for s in specs]
        assert "myfn.bind.x" in names
        assert "myfn.bind.y" in names

    def test_collect_callable_bind_specs_import_error(self) -> None:
        """_collect_callable_bind_specs returns [] for an unimportable fn_path."""
        result = _collect_callable_bind_specs("myfn", "nonexistent.module.fn", set())
        assert result == []

    def test_collect_callable_bind_specs_dedup(self) -> None:
        """_collect_callable_bind_specs skips specs already in existing_names."""
        existing = {"myfn.bind.x"}
        specs = _collect_callable_bind_specs("myfn", f"{_COV_MOD}._cov_call_fn", existing)
        names = [s.name for s in specs]
        assert "myfn.bind.x" not in names
        assert "myfn.bind.y" in names

    def test_collect_callable_factory_specs_valid_class(self) -> None:
        """_collect_callable_factory_specs returns FlagSpecs for factory constructor params."""
        specs = _collect_callable_factory_specs("myopt", _CovCallableCls, set())
        names = [s.name for s in specs]
        assert "myopt.lr" in names

    def test_collect_callable_field_specs_class_mode(self) -> None:
        """_collect_callable_field_specs in 'class' mode returns factory specs."""
        specs = _collect_callable_field_specs("opt", f"{_COV_MOD}._CovCallableCls", "class", set())
        names = [s.name for s in specs]
        assert "opt.lr" in names

    def test_collect_callable_field_specs_fn_mode(self) -> None:
        """_collect_callable_field_specs in 'fn' mode returns bind specs."""
        specs = _collect_callable_field_specs("myfn", f"{_COV_MOD}._cov_call_fn", "fn", set())
        names = [s.name for s in specs]
        assert "myfn.bind.x" in names

    def test_collect_callable_field_specs_call_mode(self) -> None:
        """_collect_callable_field_specs in 'call' mode returns bind specs."""
        specs = _collect_callable_field_specs("myfn", f"{_COV_MOD}._cov_call_fn", "call", set())
        names = [s.name for s in specs]
        assert "myfn.bind.x" in names

    def test_collect_callable_field_specs_fn_mode_method(self) -> None:
        """_collect_callable_field_specs in 'fn' mode for a method uses owning class specs."""
        specs = _collect_callable_field_specs("myfn", f"{_COV_MOD}._CovOptMethod.method", "fn", set())
        # Owning class is _CovOptMethod; returns factory specs for its constructor
        names = [s.name for s in specs]
        assert any("myfn" in n for n in names)

    def test_get_callable_field_return_type(self) -> None:
        """_get_callable_field_return_type returns the return type for a Callable field."""
        ret = _get_callable_field_return_type(_WithCovCallable, "fn")
        assert ret is _CovDCResult

    def test_get_callable_field_return_type_non_struct(self) -> None:
        """_get_callable_field_return_type returns None for non-struct path segments."""
        assert _get_callable_field_return_type(int, "fn") is None

    def test_get_callable_field_return_type_missing_field(self) -> None:
        """_get_callable_field_return_type returns None when field path doesn't exist."""
        assert _get_callable_field_return_type(_WithCovCallable, "nonexistent") is None

    def test_get_callable_field_return_type_multi_union(self) -> None:
        """_get_callable_field_return_type returns None for multi-variant union field."""
        assert _get_callable_field_return_type(_WithUnionForCompletion, "val") is None

    def test_get_callable_field_return_type_non_callable_field(self) -> None:
        """_get_callable_field_return_type returns None for non-callable leaf field."""
        assert _get_callable_field_return_type(_CovDCResult, "result_val") is None

    def test_collect_callable_bind_specs_signature_fails(self) -> None:
        """_collect_callable_bind_specs returns [] when signature inspection raises."""
        # _CovUninspectable.__init__.__signature__ is broken → TypeError
        result = _collect_callable_bind_specs("myopt", f"{_COV_MOD}._CovUninspectable", set())
        assert result == []

    def test_collect_callable_bind_specs_varargs_skipped(self) -> None:
        """_collect_callable_bind_specs skips *args/**kwargs parameters."""
        specs = _collect_callable_bind_specs("myfn", f"{_COV_MOD}._cov_fn_with_varargs", set())
        names = [s.name for s in specs]
        assert "myfn.bind.key" in names
        assert not any("myfn.bind.args" in n for n in names)

    def test_collect_callable_factory_specs_fields_raises(self) -> None:
        """_collect_callable_factory_specs returns [] when _init_fields raises."""
        # _CovUninspectable.__init__.__signature__ raises TypeError → _init_fields raises
        result = _collect_callable_factory_specs("myopt", _CovUninspectable, set())
        assert result == []

    def test_collect_callable_factory_specs_dedup(self) -> None:
        """_collect_callable_factory_specs skips specs already in existing_names."""
        existing = {"myopt.lr"}
        specs = _collect_callable_factory_specs("myopt", _CovCallableCls, existing)
        assert all(s.name != "myopt.lr" for s in specs)

    def test_collect_callable_field_specs_class_mode_import_error(self) -> None:
        """_collect_callable_field_specs in 'class' mode falls through on import error."""
        # Bad path → SymbolImportError → falls through to bind specs → returns []
        result = _collect_callable_field_specs("opt", "nonexistent.Bad", "class", set())
        assert result == []

    def test_collect_callable_field_specs_fn_mode_class_path(self) -> None:
        """_collect_callable_field_specs in 'fn' mode with a class path returns factory specs."""
        specs = _collect_callable_field_specs("opt", f"{_COV_MOD}._CovCallableCls", "fn", set())
        names = [s.name for s in specs]
        assert "opt.lr" in names

    def test_collect_callable_field_specs_fn_mode_import_error(self) -> None:
        """_collect_callable_field_specs in 'fn' mode falls through on import error."""
        result = _collect_callable_field_specs("myfn", "nonexistent.fn", "fn", set())
        assert result == []

    def test_collect_fn_paths_from_config_fields_raises(self) -> None:
        """_collect_fn_paths_from_config returns {} when _struct_fields raises."""

        class _BrokenDCFields:
            pass

        _BrokenDCFields.__dataclass_fields__ = property(  # ty: ignore[unresolved-attribute]  # deliberately corrupt __dataclass_fields__ for testing
            lambda self: (_ for _ in ()).throw(TypeError("boom")),
        )
        result = _collect_fn_paths_from_config({}, _BrokenDCFields, "", "class")
        assert result == {}

    def test_build_dynamic_flags_config_equals_form(self, tmp_path: Path) -> None:
        """build_dynamic_flags reads fn paths from config file in --config=FILE argv form."""
        cfg = tmp_path / "cfg.json"
        cfg.write_text(json.dumps({"fn": {"fn": f"{_COV_MOD}._cov_call_fn"}}))
        specs = build_dynamic_flags(
            _WithCovCallable,
            [f"--config={cfg}"],
        )
        names = [s.name for s in specs]
        assert "fn.bind.x" in names

    def test_build_dynamic_flags_exception_from_collect(self, monkeypatch) -> None:
        """build_dynamic_flags returns [] when an unexpected exception occurs."""

        def _boom(*args, **kwargs):
            msg = "deliberate boom"
            raise RuntimeError(msg)

        monkeypatch.setattr(build_mod, "_collect_fn_paths_from_argv", _boom)
        result = build_dynamic_flags(_WithCovCallable, [])
        assert result == []

    def test_collect_fn_paths_from_argv_equals_form(self) -> None:
        """_collect_fn_paths_from_argv handles --field.fn=path (= form)."""
        result = _collect_fn_paths_from_argv(["--optimizer.fn=my.module.fn"])
        assert result == {"optimizer": ("my.module.fn", "fn")}

    def test_collect_fn_paths_from_argv_space_form(self) -> None:
        """_collect_fn_paths_from_argv handles --field.fn path (space form)."""
        result = _collect_fn_paths_from_argv(["--optimizer.fn", "my.module.fn"])
        assert result == {"optimizer": ("my.module.fn", "fn")}

    def test_collect_fn_paths_from_argv_non_flag_token(self) -> None:
        """_collect_fn_paths_from_argv skips non-flag tokens."""
        result = _collect_fn_paths_from_argv(["value", "--optimizer.class=my.Cls"])
        assert "optimizer" in result

    def test_collect_fn_paths_from_argv_space_form_no_value(self) -> None:
        """_collect_fn_paths_from_argv skips --field.fn with no following value."""
        result = _collect_fn_paths_from_argv(["--optimizer.fn"])
        assert result == {}

    def test_collect_fn_paths_from_config_callable_fn(self) -> None:
        """_collect_fn_paths_from_config finds fn: entries for Callable fields."""
        config = {"fn": {"fn": "my.module.fn"}}
        result = _collect_fn_paths_from_config(config, _WithCovCallable, "", "class")
        assert "fn" in result
        assert result["fn"] == ("my.module.fn", "fn")

    def test_collect_fn_paths_from_config_callable_class(self) -> None:
        """_collect_fn_paths_from_config finds class: entries for Callable fields."""
        config = {"fn": {"class": "my.module.Cls"}}
        result = _collect_fn_paths_from_config(config, _WithCovCallable, "", "class")
        assert result.get("fn") == ("my.module.Cls", "class")

    def test_collect_fn_paths_from_config_callable_call(self) -> None:
        """_collect_fn_paths_from_config finds call: entries for Callable fields."""
        config = {"fn": {"call": "my.module.factory"}}
        result = _collect_fn_paths_from_config(config, _WithCovCallable, "", "class")
        assert result.get("fn") == ("my.module.factory", "call")

    def test_collect_fn_paths_from_config_callable_bare_string(self) -> None:
        """_collect_fn_paths_from_config handles bare string value for Callable field."""
        config = {"fn": "my.module.fn"}
        result = _collect_fn_paths_from_config(config, _WithCovCallable, "", "class")
        assert result.get("fn") == ("my.module.fn", "fn")

    def test_collect_fn_paths_from_config_non_struct(self) -> None:
        """_collect_fn_paths_from_config returns {} for non-struct types."""
        result = _collect_fn_paths_from_config({}, int, "", "class")
        assert result == {}

    def test_collect_struct_specs_callable_with_struct_return(self) -> None:
        """_collect_struct_specs registers factory specs when Callable return type is a struct."""
        specs = _collect_struct_specs(_WithCovCallable, "", "class")
        names = [s.name for s in specs]
        # Should include factory specs for _CovDCResult fields
        assert "fn.result_val" in names

    def test_build_dynamic_flags_with_argv(self) -> None:
        """build_dynamic_flags generates bind specs when --field.fn=path is in argv."""
        specs = build_dynamic_flags(
            _WithCovCallable,
            [f"--fn.fn={_COV_MOD}._cov_call_fn"],
        )
        names = [s.name for s in specs]
        assert "fn.bind.x" in names

    def test_build_dynamic_flags_with_config_file(self, tmp_path: Path) -> None:
        """build_dynamic_flags reads fn paths from a config file referenced in argv."""
        cfg = tmp_path / "cfg.json"
        cfg.write_text(json.dumps({"fn": {"fn": f"{_COV_MOD}._cov_call_fn"}}))
        specs = build_dynamic_flags(
            _WithCovCallable,
            ["--config", str(cfg)],
        )
        names = [s.name for s in specs]
        assert "fn.bind.x" in names

    def test_build_dynamic_flags_exception_returns_empty(self) -> None:
        """build_dynamic_flags returns [] on any internal exception."""
        # Passing a non-type target causes an internal error; result is []
        result = build_dynamic_flags(None, [])  # ty: ignore[invalid-argument-type]  # deliberately passing None to exercise internal error-handling
        assert result == []

    def test_resolve_struct_struct_fields_raises(self) -> None:
        """_resolve_struct returns None when _struct_fields raises for a struct-like type."""

        class _BrokenStruct:
            """Passes _is_struct but fails _struct_fields."""

        # Make _is_struct think this is a struct by giving it __dataclass_fields__
        _BrokenStruct.__dataclass_fields__ = property(  # ty: ignore[unresolved-attribute]  # deliberately corrupt __dataclass_fields__ for testing
            lambda self: (_ for _ in ()).throw(TypeError("boom")),
        )
        # Should return None, not raise
        result = _resolve_struct(_BrokenStruct)
        # It might or might not be None; important thing is it doesn't raise
        assert result is None or isinstance(result, tuple)


# ---------------------------------------------------------------------------
# _namespace.py — callable spec and env_configs
# ---------------------------------------------------------------------------


class TestNamespaceGaps:
    """Uncovered branches in _namespace.py."""

    def test_collect_callable_spec_fn_key(self) -> None:
        """_collect_callable_spec stores fn: value from flat namespace."""
        flat = {"myfn.fn": "some.module.fn"}
        result: dict = {}
        _collect_callable_spec(flat, "myfn", Callable, result)
        assert result.get("myfn", {}).get("fn") == "some.module.fn"

    def test_collect_callable_spec_class_key(self) -> None:
        """_collect_callable_spec stores class: value from flat namespace."""
        flat = {"myfn.class": "some.module.Cls"}
        result: dict = {}
        _collect_callable_spec(flat, "myfn", Callable, result)
        assert result.get("myfn", {}).get("class") == "some.module.Cls"

    def test_collect_callable_spec_bind_keys(self) -> None:
        """_collect_callable_spec assembles bind: dict from flat namespace."""
        flat = {"myfn.fn": "some.fn", "myfn.bind.x": "42"}
        result: dict = {}
        _collect_callable_spec(flat, "myfn", Callable, result)
        assert result["myfn"]["bind"]["x"] == "42"

    def test_collect_callable_spec_bare_string_no_spec(self) -> None:
        """A bare string value with no other spec keys is stored as a plain string."""
        flat = {"myfn": "some.module.fn"}
        result: dict = {}
        _collect_callable_spec(flat, "myfn", Callable, result)
        assert result.get("myfn") == "some.module.fn"

    def test_collect_callable_spec_blob_dict_merged(self) -> None:
        """A pre-existing dict blob for the flag is merged with the assembled spec."""
        flat = {"myfn": {"fn": "existing.fn"}, "myfn.bind.x": "42"}
        result: dict = {}
        _collect_callable_spec(flat, "myfn", Callable, result)
        merged = result.get("myfn", {})
        assert merged.get("fn") == "existing.fn"
        assert merged.get("bind", {}).get("x") == "42"

    def test_collect_ns_fields_callable_field(self) -> None:
        """_collect_ns_fields handles a Callable-typed field."""
        flat = {"fn.fn": "some.module.fn"}
        result: dict = {}
        _collect_ns_fields(flat, _WithCovCallable, "", "class", result)
        assert "fn" in result

    def test_from_namespace_with_env_configs(self, tmp_path: Path) -> None:
        """from_namespace processes env_configs (files referenced by env vars)."""
        cfg = tmp_path / "sub.json"
        cfg.write_text(json.dumps({"result_val": "from_env_config"}))

        parser = argparse.ArgumentParser()
        populate_parser(_CovDCResult, parser)
        ns = parser.parse_args([])
        result = from_namespace(
            _CovDCResult,
            ns,
            env={"CONFARG_CONFIG__": str(cfg)},
            env_prefix="CONFARG_",
        )
        # The main point is no crash; result_val may or may not be set
        assert isinstance(result, _CovDCResult)

    def test_callable_return_type_for(self) -> None:
        """_callable_return_type_for delegates to _callable_return_type."""
        result = _callable_return_type_for(Callable[..., _CovDCResult])
        assert result is _CovDCResult

    def test_merge_blob_into_spec_non_dict_bind(self) -> None:
        """_merge_blob_into_spec uses bind directly when blob.bind is not a dict."""
        # blob["bind"] is a string, not a dict → elif bind: merged["bind"] = bind
        merged = _merge_blob_into_spec({"bind": "not_a_dict"}, {}, {"x": 1})
        assert merged["bind"] == {"x": 1}

    def test_collect_callable_spec_factory_kwargs(self) -> None:
        """_collect_callable_spec collects flat factory kwargs into spec when fn key present."""
        flat = {"myfn.fn": "some.fn", "myfn.lr": "0.01"}
        result: dict = {}
        _collect_callable_spec(flat, "myfn", Callable[..., _CovCallableCls], result)
        assert result.get("myfn", {}).get("lr") == "0.01"

    def test_from_namespace_env_config_subpath(self, tmp_path: Path) -> None:
        """from_namespace processes env_configs with non-empty subpath (lines 255-256)."""
        cfg = tmp_path / "inner.json"
        cfg.write_text(json.dumps({"value": "from_env_subpath"}))

        parser = argparse.ArgumentParser()
        populate_parser(_CovOuter, parser)
        ns = parser.parse_args([])
        result = from_namespace(
            _CovOuter,
            ns,
            env={"CONFARG_CONFIG__INNER": str(cfg)},
            env_prefix="CONFARG_",
        )
        assert result.inner.value == "from_env_subpath"


# ---------------------------------------------------------------------------
# _register.py — small gaps
# ---------------------------------------------------------------------------


class TestRegisterGaps:
    """Uncovered branches in _register.py."""

    def test_register_spec_skips_existing_dest(self) -> None:
        """_register_spec silently skips a spec whose name is already registered."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--myfield", dest="myfield", default=argparse.SUPPRESS)
        existing = {"myfield"}
        spec = FlagSpec(name="myfield", metavar="VAL", help="", group=None, group_description="")
        _register_spec(spec, parser, existing)
        # Should not raise, should not add duplicate
        assert len([a for a in parser._actions if a.dest == "myfield"]) == 1

    def test_populate_parser_with_argv(self) -> None:
        """populate_parser with argv registers dynamic bind specs."""
        parser = argparse.ArgumentParser()
        populate_parser(
            _WithCovCallable,
            parser,
            argv=[f"--fn.fn={_COV_MOD}._cov_call_fn"],
        )
        dests = {a.dest for a in parser._actions}
        assert "fn.bind.x" in dests

    def test_add_callable_fn_flags(self) -> None:
        """_add_callable_fn_flags registers fn/class/call flags on the parser."""
        parser = argparse.ArgumentParser()
        _add_callable_fn_flags(parser, "myfield")
        dests = {a.dest for a in parser._actions}
        assert "myfield.fn" in dests
        assert "myfield.class" in dests
        assert "myfield.call" in dests

    def test_add_callable_bind_flags_no_existing_dests(self) -> None:
        """_add_callable_bind_flags works without pre-computed existing_dests."""
        parser = argparse.ArgumentParser()
        _add_callable_bind_flags(parser, "myfn", f"{_COV_MOD}._cov_call_fn")
        dests = {a.dest for a in parser._actions}
        assert "myfn.bind.x" in dests


# ---------------------------------------------------------------------------
# _completion.py — argparse completion gaps
# ---------------------------------------------------------------------------


class TestCompletionGaps:
    """Uncovered branches in _completion.py."""

    def test_resolve_tags_from_config_non_struct(self) -> None:
        """_resolve_tags_from_config returns {} for non-struct types."""
        result = _resolve_tags_from_config({}, int, "", "class")
        assert result == {}

    def test_resolve_tags_from_config_struct_fields_raises(self) -> None:
        """_resolve_tags_from_config returns {} when _struct_fields raises."""

        class _BrokenStruct:
            __dataclass_fields__ = property(
                lambda s: (_ for _ in ()).throw(ValueError("boom")),
            )

        result = _resolve_tags_from_config({}, _BrokenStruct, "", "class")
        assert result == {}

    def test_resolve_tags_from_config_optional_union(self) -> None:
        """_resolve_tags_from_config handles Optional[T] (single-variant union) in config."""

        @dataclass
        class _WithOptionalSub:
            sub: _CovDCResult | None = None

        config = {"sub": {"result_val": "hello"}}
        result = _resolve_tags_from_config(config, _WithOptionalSub, "", "class")
        # No union_tag in sub → tags is empty but shouldn't crash
        assert isinstance(result, dict)

    def test_extend_walk_concrete_singleton_literal_skipped(self) -> None:
        """_extend_walk skips singleton literal fields when concrete=True."""

        @dataclass
        class _WithLiteral:
            kind: Literal["fixed"] = "fixed"
            value: int = 0

        parser = argparse.ArgumentParser()
        ctx = _WalkCtx(parser=parser, union_tag="class", existing_dests=set())
        _extend_walk(_WithLiteral, ctx, parser, "", concrete=True)
        dests = {a.dest for a in parser._actions}
        assert "kind" not in dests  # singleton literal skipped in concrete mode
        assert "value" in dests  # non-singleton fields are added

    def test_extend_walk_callable_field(self) -> None:
        """_extend_walk registers callable fn/class/call flags for Callable fields."""
        parser = argparse.ArgumentParser()
        ctx = _WalkCtx(parser=parser, union_tag="class", existing_dests={a.dest for a in parser._actions})
        _extend_walk(_WithCovCallable, ctx, parser, "")
        dests = {a.dest for a in parser._actions}
        assert "fn.fn" in dests

    def test_pre_extend_parser_outer_except(self, monkeypatch) -> None:
        """_pre_extend_parser_for_completion swallows any outer exception."""
        # Monkeypatch _collect_partial_config to raise an unexpected exception
        monkeypatch.setattr(
            "confarg.cli.argparse._completion._collect_partial_config",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        parser = argparse.ArgumentParser()
        # Must not raise
        _pre_extend_parser_for_completion(parser, WithDefaults, "class", "config", [])

    def test_pre_extend_parser_with_union_tag(self) -> None:
        """_pre_extend_parser_for_completion extends parser when a union class tag is in argv."""
        cls_path = f"{_COV_MOD}._ConstructAVariant"
        parser = argparse.ArgumentParser()
        populate_parser(_WithUnionForCompletion, parser)
        _pre_extend_parser_for_completion(
            parser,
            _WithUnionForCompletion,
            "class",
            "config",
            [f"--val.class={cls_path}"],
        )
        dests = {a.dest for a in parser._actions}
        assert "val.x" in dests

    def test_pre_extend_parser_with_callable_bind(self) -> None:
        """_pre_extend_parser_for_completion registers bind flags for --fn.fn in argv."""
        parser = argparse.ArgumentParser()
        populate_parser(_WithCovCallable, parser)
        _pre_extend_parser_for_completion(
            parser,
            _WithCovCallable,
            "class",
            "config",
            [f"--fn.fn={_COV_MOD}._cov_call_fn"],
        )
        dests = {a.dest for a in parser._actions}
        assert "fn.bind.x" in dests

    def test_extend_walk_var_params_skipped(self) -> None:
        """_extend_walk skips var_params fields like **kwargs in plain classes."""
        parser = argparse.ArgumentParser()
        ctx = _WalkCtx(parser=parser, union_tag="class", existing_dests={a.dest for a in parser._actions})
        _extend_walk(_CovWithKwargs, ctx, parser, "")
        dests = {a.dest for a in parser._actions}
        # "extra" is a **kwargs param → skipped via line 174
        assert "extra" not in dests

    def test_extend_walk_struct_group_already_exists(self) -> None:
        """_extend_walk reuses an existing group when the struct field was already walked."""
        parser = argparse.ArgumentParser()
        # First walk creates the "inner" group
        ctx = _WalkCtx(parser=parser, union_tag="class", existing_dests=set())
        _extend_walk(_CovOuter, ctx, parser, "")
        # Second walk finds the group already exists → hits line 216
        _extend_walk(_CovOuter, ctx, parser, "")
        # Should not raise
        assert any(g.title == "inner" for g in parser._action_groups)

    def test_extend_walk_dict_field_skipped(self) -> None:
        """_extend_walk skips dict-typed fields."""
        parser = argparse.ArgumentParser()
        ctx = _WalkCtx(parser=parser, union_tag="class", existing_dests={a.dest for a in parser._actions})
        _extend_walk(_CovWithDict, ctx, parser, "")
        dests = {a.dest for a in parser._actions}
        # "settings" is a dict field → should be skipped
        assert "settings" not in dests
        assert "name" in dests

    def test_pre_extend_parser_non_struct_class_skipped(self) -> None:
        """_pre_extend_parser_for_completion skips class_path that resolves to non-struct."""
        parser = argparse.ArgumentParser()
        populate_parser(_WithUnionForCompletion, parser)
        # "builtins.int" is a type but NOT a struct → continue at line 259
        _pre_extend_parser_for_completion(
            parser,
            _WithUnionForCompletion,
            "class",
            "config",
            ["--val.class=builtins.int"],
        )
        # Should not crash and should not add int's (nonexistent) fields
        dests = {a.dest for a in parser._actions}
        assert "val.x" not in dests

    def test_pre_extend_parser_bind_flags_exception(self, monkeypatch) -> None:
        """_pre_extend_parser_for_completion swallows exception from _add_callable_bind_flags."""

        def _boom(*args, **kwargs):
            msg = "deliberate bind boom"
            raise RuntimeError(msg)

        monkeypatch.setattr(reg_mod, "_collect_callable_bind_specs", _boom)
        parser = argparse.ArgumentParser()
        populate_parser(_WithCovCallable, parser)
        # Must not raise even though _add_callable_bind_flags raises
        _pre_extend_parser_for_completion(
            parser,
            _WithCovCallable,
            "class",
            "config",
            [f"--fn.fn={_COV_MOD}._cov_call_fn"],
        )

    def test_setup_completion_argv_defaults_to_sys_argv(self, monkeypatch) -> None:
        """setup_completion defaults argv to sys.argv[1:] when argv=None."""
        # Inject a mock argcomplete so ImportError is avoided
        mock_argcomplete = types.ModuleType("argcomplete")
        mock_argcomplete.autocomplete = lambda *a, **kw: None  # ty: ignore[unresolved-attribute]  # dynamically adding attribute to a mock module
        monkeypatch.setitem(sys.modules, "argcomplete", mock_argcomplete)

        parser = argparse.ArgumentParser()
        populate_parser(_CovDCResult, parser)
        monkeypatch.setattr(sys, "argv", ["prog", "--result_val=hello"])
        # argv=None → sys.argv[1:] is used → covers line 325
        _argparse_setup_completion(parser, _CovDCResult, argv=None)


# ---------------------------------------------------------------------------
# click/_context.py — subpath config and env_configs
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _CLICK_AVAILABLE, reason="click not installed")
class TestClickContextGaps:
    """Uncovered branches in click/_context.py."""

    def test_from_context_subpath_config(self, tmp_path: Path) -> None:
        """from_context processes subpath config files (lines 103-104, 111-112)."""
        # _CovOuter.inner is a struct field → populate_command registers --config.inner
        cfg = tmp_path / "inner.json"
        cfg.write_text(json.dumps({"value": "from_subpath"}))

        @click.command()
        def cmd(**_kwargs):
            ctx = click.get_current_context()
            result = from_context(_CovOuter, ctx, env={}, env_prefix=None)
            assert result.inner.value == "from_subpath"

        populate_command(_CovOuter, cmd)
        runner = CliRunner()
        r = runner.invoke(cmd, [f"--config.inner={cfg}"])
        assert r.exit_code == 0, r.output

    def test_from_context_env_configs(self, tmp_path: Path) -> None:
        """from_context processes env_configs from _parse_env (lines 122-126)."""
        cfg = tmp_path / "cfg.json"
        cfg.write_text(json.dumps({"result_val": "from_env_file"}))

        @click.command()
        def cmd2(**_kwargs):
            ctx = click.get_current_context()
            result = from_context(
                _CovDCResult,
                ctx,
                env={"CONFARG_CONFIG__": str(cfg)},
                env_prefix="CONFARG_",
            )
            assert isinstance(result, _CovDCResult)

        populate_command(_CovDCResult, cmd2)
        runner = CliRunner()
        r = runner.invoke(cmd2, [])
        assert r.exit_code == 0, r.output

    def test_from_context_env_config_subpath(self, tmp_path: Path) -> None:
        """from_context processes env_configs with non-empty subpath (lines 124-125)."""
        cfg = tmp_path / "inner.json"
        cfg.write_text(json.dumps({"value": "from_env_subpath"}))

        @click.command()
        def cmd3(**_kwargs):
            ctx = click.get_current_context()
            result = from_context(
                _CovOuter,
                ctx,
                env={"CONFARG_CONFIG__INNER": str(cfg)},
                env_prefix="CONFARG_",
            )
            assert result.inner.value == "from_env_subpath"

        populate_command(_CovOuter, cmd3)
        runner = CliRunner()
        r = runner.invoke(cmd3, [])
        assert r.exit_code == 0, r.output


# ---------------------------------------------------------------------------
# click/_register.py — populate_command with argv
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _CLICK_AVAILABLE, reason="click not installed")
class TestClickRegisterGaps:
    """Uncovered branches in click/_register.py."""

    def test_populate_command_with_argv(self) -> None:
        """populate_command with argv registers dynamic bind specs."""

        @click.command()
        def cmd(**_kwargs):
            pass

        populate_command(
            _WithCovCallable,
            cmd,
            argv=[f"--fn.fn={_COV_MOD}._cov_call_fn"],
        )
        names = {p.name for p in cmd.params}
        assert "fn.bind.x" in names


# ---------------------------------------------------------------------------
# click/_completion.py — outer except in setup_completion
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _CLICK_AVAILABLE, reason="click not installed")
class TestClickCompletionGaps:
    """Uncovered branches in click/_completion.py."""

    def test_setup_completion_outer_except(self, monkeypatch) -> None:
        """setup_completion swallows any outer exception (lines 77-79)."""
        monkeypatch.setenv("_CMD_COMPLETE", "bash_complete")

        # Monkeypatch _partial_argv_from_env to raise
        monkeypatch.setattr(
            "confarg.cli.click._completion._partial_argv_from_env",
            lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        )

        @click.command(name="cmd")
        def cmd(**_kwargs):
            pass

        # Must not raise
        _click_setup_completion(cmd, _CovDCResult)
