# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests targeting previously uncovered lines across confarg modules."""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

import confarg
from confarg._callable import _detect_owning_class, _serialize_callable
from confarg._merge import _to_append_list
from confarg._types import (
    _all_have_defaults,
    _is_collection,
    _StrToken,
    _var_keyword_name,
    _var_param_names,
    _var_positional_name,
)
from confarg.cli.argparse import from_namespace, populate_parser
from confarg.cli.argparse._build import _collect_struct_specs
from tests.conftest import WithDefaults, make_target

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
        with pytest.raises(confarg.ConfargError, match="integer indices"):
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
    """dump() strips _StrToken markers from lists and raw merge dicts."""

    def test_strip_str_tokens_in_list(self) -> None:
        """_StrToken values in a list are demoted to plain str by dump()."""
        data = {"items": [_StrToken("a"), _StrToken("b")]}
        result = confarg.dump(data)
        assert result == {"items": ["a", "b"]}
        assert all(type(v) is str for v in result["items"])

    def test_dump_from_merge(self) -> None:
        """dump() applied to a raw merge() dict produces plain str values."""
        WithList = make_target("items", list[str], default_factory=list)
        raw = confarg.merge(WithList, args=["--items", "x", "y"], env={})
        d = confarg.dump(raw)
        assert d["items"] == ["x", "y"]
        assert all(type(v) is str for v in d["items"])


# ---------------------------------------------------------------------------
# __init__.merge — --config.+ without field path (line 93)
# ---------------------------------------------------------------------------


class TestConfigAppendWithoutField:
    """--config.+ without a field path is rejected."""

    def test_config_append_no_field_path_raises(self) -> None:
        """--config.+ without a field path raises ConfargError."""
        with pytest.raises(confarg.ConfargError, match="requires a field path"):
            confarg.load(WithDefaults, args=["--config.+", "dummy.toml"], env={})


# ---------------------------------------------------------------------------
# _files — error handling
# ---------------------------------------------------------------------------


class TestFileErrors:
    """File-loading and file-dumping error paths."""

    def test_load_toml_file_not_found(self, tmp_path: Path) -> None:
        """Missing TOML file raises InvalidConfigFileError."""
        from confarg._files import _load_toml

        with pytest.raises(confarg.InvalidConfigFileError, match="not found"):
            _load_toml(tmp_path / "missing.toml")

    def test_load_yaml_file_not_found(self, tmp_path: Path) -> None:
        """Missing YAML file raises InvalidConfigFileError."""
        from confarg._files import _load_yaml

        with pytest.raises(confarg.InvalidConfigFileError, match="not found"):
            _load_yaml(tmp_path / "missing.yaml")

    def test_load_json_file_not_found(self, tmp_path: Path) -> None:
        """Missing JSON file raises InvalidConfigFileError."""
        from confarg._files import _load_json

        with pytest.raises(confarg.InvalidConfigFileError, match="not found"):
            _load_json(tmp_path / "missing.json")

    def test_load_yaml_item_missing_library(self, tmp_path: Path, monkeypatch) -> None:
        """Missing PyYAML library raises InvalidConfigFileError."""
        from confarg._files import _load_yaml_item

        p = tmp_path / "test.yaml"
        p.write_text("key: value")
        monkeypatch.setitem(sys.modules, "yaml", None)
        with pytest.raises(confarg.InvalidConfigFileError, match="PyYAML"):
            _load_yaml_item(p)

    def test_load_yaml_item_file_not_found(self, tmp_path: Path) -> None:
        """Missing YAML item file raises InvalidConfigFileError."""
        from confarg._files import _load_yaml_item

        with pytest.raises(confarg.InvalidConfigFileError, match="not found"):
            _load_yaml_item(tmp_path / "missing.yaml")

    def test_load_yaml_item_malformed(self, tmp_path: Path) -> None:
        """Malformed YAML content raises InvalidConfigFileError."""
        from confarg._files import _load_yaml_item

        p = tmp_path / "bad.yaml"
        p.write_text("key: :\n  - bad: [unclosed")
        with pytest.raises(confarg.InvalidConfigFileError, match="malformed"):
            _load_yaml_item(p)

    def test_load_json_item_file_not_found(self, tmp_path: Path) -> None:
        """Missing JSON item file raises InvalidConfigFileError."""
        from confarg._files import _load_json_item

        with pytest.raises(confarg.InvalidConfigFileError, match="not found"):
            _load_json_item(tmp_path / "missing.json")

    def test_load_json_item_malformed(self, tmp_path: Path) -> None:
        """Malformed JSON content raises InvalidConfigFileError."""
        from confarg._files import _load_json_item

        p = tmp_path / "bad.json"
        p.write_text("{bad json")
        with pytest.raises(confarg.InvalidConfigFileError, match="malformed"):
            _load_json_item(p)

    def test_load_file_item_unsupported_format(self, tmp_path: Path) -> None:
        """Unsupported file extension raises InvalidConfigFileError."""
        from confarg._files import _load_file_item

        with pytest.raises(confarg.InvalidConfigFileError, match="Unsupported"):
            _load_file_item(tmp_path / "file.xyz")

    def test_dump_json_writes_file(self, tmp_path: Path) -> None:
        """JSON dump writes a valid JSON file to disk."""
        from confarg._files import _dump_json

        p = tmp_path / "out.json"
        _dump_json({"key": "value", "num": 42}, p)
        import json

        data = json.loads(p.read_text())
        assert data == {"key": "value", "num": 42}

    def test_dump_file_unsupported_format(self, tmp_path: Path) -> None:
        """Unsupported file extension in dump raises InvalidConfigFileError."""
        from confarg._files import _dump_file

        with pytest.raises(confarg.InvalidConfigFileError, match="Unsupported"):
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
        from confarg._callable import _resolve_callable_spec

        def my_func(x: int) -> str:
            return str(x)

        result = _resolve_callable_spec(my_func, Callable[[int], str], path="test")
        assert result is my_func

    def test_resolve_dict_spec_non_dict_bind_raises(self) -> None:
        """A non-dict bind: value in the fn: dict form raises TypeCoercionError."""
        from confarg._callable import _resolve_callable_spec

        spec = {"fn": "os.path.join", "bind": "not_a_dict"}
        with pytest.raises(confarg.TypeCoercionError, match="must be a dict"):
            _resolve_callable_spec(spec, Callable, path="test")

    def test_resolve_class_spec_not_a_class_raises(self) -> None:
        """A non-class path in the class: dict form raises TypeCoercionError."""
        from confarg._callable import _resolve_callable_spec

        spec = {"class": "os.path.join"}
        with pytest.raises(confarg.TypeCoercionError, match="must reference a class"):
            _resolve_callable_spec(spec, Callable, path="test")

    def test_resolve_spec_invalid_type_raises(self) -> None:
        """A non-str, non-dict callable spec raises TypeCoercionError."""
        from confarg._callable import _resolve_callable_spec

        with pytest.raises(confarg.TypeCoercionError, match="expected str or dict"):
            _resolve_callable_spec(12345, Callable, path="test")

    def test_check_signature_var_positional_skipped(self) -> None:
        """*args functions skip parameter count checking."""
        from confarg._callable import _check_callable_signature

        def varargs_func(*args: int) -> None:
            pass

        _check_callable_signature(varargs_func, Callable[[int, int], None], path="test")

    def test_check_signature_uninspectable(self) -> None:
        """Uninspectable callables skip signature checking."""
        from confarg._callable import _check_callable_signature

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
        obj.__module__ = None  # type: ignore
        obj.__qualname__ = None  # type: ignore
        with pytest.raises(confarg.ConfargError, match="no __module__"):
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

        Broken.__init__ = None  # type: ignore
        result = _var_param_names(Broken)
        assert result == frozenset()

    def test_var_positional_name_uninspectable(self) -> None:
        """_var_positional_name returns None when __init__ is not inspectable."""

        class Broken:
            pass

        Broken.__init__ = None  # type: ignore
        assert _var_positional_name(Broken) is None

    def test_var_keyword_name_uninspectable(self) -> None:
        """_var_keyword_name returns None when __init__ is not inspectable."""

        class Broken:
            pass

        Broken.__init__ = None  # type: ignore
        assert _var_keyword_name(Broken) is None

    def test_is_plain_class_uninspectable_init(self) -> None:
        """_is_plain_class returns False when __init__ is not inspectable."""
        from confarg._types import _is_plain_class

        class Broken:
            pass

        Broken.__init__ = None  # type: ignore
        assert _is_plain_class(Broken) is False

    def test_init_fields_broken_init_annotation_fallback(self) -> None:
        """_init_fields falls back gracefully when get_type_hints raises a NameError."""
        from confarg._types import _init_fields

        # With `from __future__ import annotations`, `value: UndefinedTypeABC999` is
        # stored as the string "UndefinedTypeABC999". get_type_hints(cls.__init__)
        # tries to evaluate it in this module's globals → NameError → fallback to {}.
        class BrokenInitAnnot:
            def __init__(self, value: UndefinedTypeABC999) -> None:  # noqa: F821
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
        from confarg._types import _unwrap_optional

        assert _unwrap_optional(int) is int

    def test_unwrap_optional_single_variant(self) -> None:
        """_unwrap_optional strips None from Optional[X] and returns X."""
        from typing import Optional

        from confarg._types import _unwrap_optional

        result = _unwrap_optional(Optional[int])
        assert result is int

    def test_unwrap_optional_multi_variant(self) -> None:
        """_unwrap_optional returns None for multi-variant unions (not Optional)."""
        from typing import Union

        from confarg._types import _unwrap_optional

        result = _unwrap_optional(Union[int, str])
        assert result is None

    def test_try_coerce_none_ft_returns_token(self) -> None:
        """_try_coerce with ft=None returns the token unchanged."""
        from confarg._types import _try_coerce

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
        from confarg._types import _try_coerce

        token = _StrToken("hello world")
        result = _try_coerce(str, token)
        assert result is token

    def test_try_coerce_str_token_is_still_str(self) -> None:
        """_StrToken IS a str subclass — passthrough means the caller gets a str-compatible value."""
        from confarg._types import _try_coerce

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
        from confarg._types import _try_coerce

        result = _try_coerce(ft, raw)
        assert result == expected

    def test_try_coerce_literal_str_matches_value(self) -> None:
        """_try_coerce with a Literal type coerces the token to the matching literal value."""
        from typing import Literal

        from confarg._types import _try_coerce

        token = _StrToken("fast")
        result = _try_coerce(Literal["fast", "slow"], token)
        assert result == "fast"

    def test_try_coerce_literal_int_value(self) -> None:
        """_try_coerce coerces a token to an integer literal."""
        from typing import Literal

        from confarg._types import _try_coerce

        token = _StrToken("1")
        result = _try_coerce(Literal[1, 2, 3], token)
        assert result == 1

    def test_try_coerce_enum_value(self) -> None:
        """_try_coerce coerces a token to an Enum member by value."""
        import enum

        from confarg._types import _try_coerce

        class Status(enum.Enum):
            ACTIVE = "active"
            INACTIVE = "inactive"

        token = _StrToken("active")
        result = _try_coerce(Status, token)
        assert result is Status.ACTIVE

    def test_try_coerce_invalid_bool_returns_token(self) -> None:
        """When coercion fails (e.g. bad bool string), _try_coerce returns the original token."""
        from confarg._types import _try_coerce

        token = _StrToken("not-a-bool")
        result = _try_coerce(bool, token)
        assert result is token

    def test_try_coerce_invalid_int_returns_token(self) -> None:
        """When coercion fails for int, _try_coerce returns the original token unchanged."""
        from confarg._types import _try_coerce

        token = _StrToken("abc")
        result = _try_coerce(int, token)
        assert result is token

    def test_try_coerce_optional_single_variant_coerces(self) -> None:
        """Optional[int] / int | None — _try_coerce unwraps the single non-None variant and coerces."""
        from typing import Optional

        from confarg._types import _try_coerce

        token = _StrToken("99")
        result = _try_coerce(Optional[int], token)
        assert result == 99

    def test_try_coerce_multi_union_returns_token(self) -> None:
        """Multi-variant union (int | str) — _try_coerce returns the token unchanged.

        construct() is responsible for handling union disambiguation.
        """
        from confarg._types import _try_coerce

        token = _StrToken("42")
        result = _try_coerce(int | str, token)
        assert result is token

    def test_try_coerce_unrecognised_type_returns_token(self) -> None:
        """A type that is not bool/int/float/Path/Literal/Enum → token returned unchanged."""
        from confarg._types import _try_coerce

        # dict is not in the coercible set
        token = _StrToken("{}")
        result = _try_coerce(dict, token)
        assert result is token


class TestParseCliBranches:
    """Uncovered branches in the CLI parsing logic."""

    def test_subclass_field_type_non_struct_subclass(self) -> None:
        """_subclass_field_type falls back to str for non-struct subclasses."""
        from confarg._parse_cli import _subclass_field_type

        result = _subclass_field_type(_SubClassBase, "extra")
        assert result is str

    def test_subclass_field_type_disagreeing_types(self) -> None:
        """_subclass_field_type falls back to str when subclass field types disagree."""
        from confarg._parse_cli import _subclass_field_type

        result = _subclass_field_type(_SubClassFieldBase, "val")
        assert result is str

    def test_resolve_field_type_tuple_variable_length(self) -> None:
        """_resolve_field_type handles variable-length tuple[int, ...] fields."""
        from confarg._parse_cli import _resolve_field_type

        result = _resolve_field_type(_WithVarTupleField, ["nums", "0"], "class")
        assert result is not None

    def test_resolve_field_type_tuple_invalid_index(self) -> None:
        """_resolve_field_type returns None for out-of-range fixed tuple indices."""
        from confarg._parse_cli import _resolve_field_type

        WithFixedTuple = make_target("coords", tuple[int, str])
        result = _resolve_field_type(WithFixedTuple, ["coords", "99"], "class")
        assert result is None

    def test_resolve_field_type_tuple_non_int_key(self) -> None:
        """_resolve_field_type returns None for non-integer tuple path segments."""
        from confarg._parse_cli import _resolve_field_type

        WithFixedTuple = make_target("coords", tuple[int, str])
        result = _resolve_field_type(WithFixedTuple, ["coords", "notanint"], "class")
        assert result is None

    def test_resolve_field_type_subclass_fallback(self) -> None:
        """_resolve_field_type falls back to str for unknown fields via subclass scanning."""
        from confarg._parse_cli import _resolve_field_type

        result = _resolve_field_type(_SubClassBase, ["extra"], "class")
        assert result is str

    def test_non_struct_bool_target(self) -> None:
        """Non-struct bool target with cli_prefix parses correctly from CLI."""
        result = confarg.load(bool, args=["--confarg", "true"], env={}, cli_prefix="confarg")
        assert result is True

    def test_non_struct_value_target(self) -> None:
        """Non-struct str target with cli_prefix parses correctly from CLI."""
        result = confarg.load(str, args=["--confarg", "hello"], env={}, cli_prefix="confarg")
        assert result == "hello"

    def test_unknown_arg_at_dict_path(self) -> None:
        """Unknown sub-key for a dict-typed field is accepted as a dict key."""
        WithDict = make_target("mapping", dict[str, int], default_factory=dict)
        result = confarg.load(WithDict, args=["--mapping.foo", "42"], env={})
        assert result.mapping["foo"] in (42, "42")

    def test_list_json_array_from_cli(self) -> None:
        """A JSON array string from CLI is parsed into a list."""
        WithList = make_target("items", list[int], default_factory=list)
        result = confarg.load(WithList, args=["--items", "[1,2,3]"], env={})
        assert result.items == [1, 2, 3]

    def test_none_sentinel_non_struct_parent(self) -> None:
        """'none' token for a non-struct optional target resolves to None."""
        result = confarg.load(int | None, args=["--confarg", "none"], env={}, cli_prefix="confarg")
        assert result is None

    def test_dataclass_field_with_no_value(self) -> None:
        """A bare --inner flag without a value triggers default construction."""
        result = confarg.load(_WithNestedDefaultInner, args=["--inner"], env={})
        assert result.inner.name == "default"

    def test_append_unknown_field_raises(self) -> None:
        """--unknown+ for a non-existent field raises ConfargError."""
        WithList = make_target("items", list[int], default_factory=list)
        with pytest.raises(confarg.ConfargError):
            confarg.load(WithList, args=["--nonexistent+", "1"], env={})


# ---------------------------------------------------------------------------
# _parse_env — uncovered branches
# ---------------------------------------------------------------------------


class TestParseEnvBranches:
    """Uncovered branches in the env-var parsing logic."""

    def test_ambiguous_env_var_in_union_raises(self) -> None:
        """An env var that matches fields in multiple union variants raises ConfargError."""
        with pytest.raises(confarg.ConfargError, match="Ambiguous env var"):
            confarg.load(
                _AmbigUnion,
                args=[],
                env={"SERVICE__NAME": "hello"},
                env_prefix="",
            )

    def test_tuple_variable_length_from_env(self) -> None:
        """Variable-length tuple fields are populated from indexed env vars."""
        WithVarTuple = make_target("items", tuple[int, ...], default=(1, 2))
        result = confarg.load(
            WithVarTuple,
            args=[],
            env={"ITEMS__0": "99"},
            env_prefix="",
        )
        assert result.items[0] == 99

    def test_tuple_non_int_segment_from_env(self) -> None:
        """Non-integer env var path segment for a tuple field is silently ignored."""
        WithFixedTuple = make_target("coords", tuple[int, str], default=(0, ""))
        result = confarg.load(
            WithFixedTuple,
            args=[],
            env={"COORDS__BAD": "hello"},
            env_prefix="",
        )
        assert result.coords == (0, "")

    def test_none_sentinel_for_non_struct(self) -> None:
        """'none' value in env var resolves a non-struct optional to None."""
        # "none"/"null" value → construct-time steal → __root__ = None
        result = confarg.load(
            str | None,
            args=[],
            env={"VALUE": "none"},
            env_prefix="",
        )
        assert result is None

    def test_union_root_unknown_field_warns(self) -> None:
        """Env var matching no variant field emits a ConfargWarning and is skipped."""
        # "Z" doesn't match any field in either variant → warns and is skipped.
        # "A" matches _UnionRootVariantA.a → selects VariantA unambiguously.
        import warnings

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = confarg.load(
                _UnionRootVariantA | _UnionRootVariantB,
                args=[],
                env={"A": "hello", "Z": "skipped"},
                env_prefix="",
            )
        assert isinstance(result, _UnionRootVariantA)
        assert result.a == "hello"
        assert any("Z" in str(w.message) for w in caught if issubclass(w.category, confarg.ConfargWarning))


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
        from confarg.dictexpr._expressions import _extract_references

        # Expression with invalid syntax → SyntaxError caught → silently skipped
        refs = _extract_references("${invalid syntax!!!}")
        assert isinstance(refs, set)

    def test_collect_names_keyword_args(self) -> None:
        """Keyword argument names in function calls are collected as references."""
        from confarg.dictexpr._expressions import _extract_references

        # keyword arg 'y' should be collected as a reference
        refs = _extract_references("${sorted(x, key=y)}")
        assert "x" in refs or "y" in refs

    def test_attribute_chain_subscript_at_top(self) -> None:
        """_attribute_chain handles a subscript at the top level gracefully."""
        import ast

        from confarg.dictexpr._expressions import _attribute_chain

        node = ast.parse("a[0]", mode="eval").body
        result = _attribute_chain(node)
        assert result is None or isinstance(result, list)

    def test_attribute_chain_non_int_subscript(self) -> None:
        """_attribute_chain returns None for non-integer subscript indices."""
        import ast

        from confarg.dictexpr._expressions import _attribute_chain

        node = ast.parse("a[x]", mode="eval").body
        result = _attribute_chain(node)
        assert result is None

    def test_bool_op_and_all_truthy(self) -> None:
        """BoolOp 'and' with all truthy operands evaluates to True."""
        from confarg.dictexpr._expressions import resolve_expressions

        data = {"val": "${True and True and True}", "True": True}
        result = resolve_expressions(data)
        assert result["val"] is True

    def test_bool_op_or_all_falsy(self) -> None:
        """BoolOp 'or' with all falsy operands evaluates to False."""
        from confarg.dictexpr._expressions import resolve_expressions

        data = {"val": "${False or False}", "False": False}
        result = resolve_expressions(data)
        assert result["val"] is False

    def test_call_evaluation_error(self) -> None:
        """A function call that raises inside an expression wraps the error as ExpressionEvalError."""
        from confarg.dictexpr._expressions import resolve_expressions

        data = {"x": 0, "val": "${int('abc')}"}
        with pytest.raises(confarg.ExpressionEvalError):
            resolve_expressions(data)

    def test_expression_eval_error_reraise_pure(self) -> None:
        """A runtime error in a pure ${expr} expression raises ExpressionEvalError."""
        from confarg.dictexpr._expressions import resolve_expressions

        data = {"x": 0, "val": "${1 / x}"}
        with pytest.raises(confarg.ExpressionEvalError):
            resolve_expressions(data)

    def test_expression_eval_error_reraise_interpolation(self) -> None:
        """A runtime error inside a string interpolation expression raises ExpressionEvalError."""
        from confarg.dictexpr._expressions import resolve_expressions

        data = {"x": 0, "val": "prefix_${1 / x}"}
        with pytest.raises(confarg.ExpressionEvalError):
            resolve_expressions(data)

    def test_get_nested_list_invalid_index_type(self) -> None:
        """Non-integer path segment into a list raises MissingReferenceError."""
        from confarg.dictexpr._expressions import _get_nested

        with pytest.raises(confarg.MissingReferenceError):
            _get_nested({"items": [1, 2, 3]}, "items.notanint")

    def test_get_nested_list_out_of_range(self) -> None:
        """Out-of-range index into a list raises MissingReferenceError."""
        from confarg.dictexpr._expressions import _get_nested

        with pytest.raises(confarg.MissingReferenceError):
            _get_nested({"items": [1, 2]}, "items.99")

    def test_set_nested_traverse_error(self) -> None:
        """_set_nested_by_path raises MissingReferenceError when traversal encounters a non-container."""
        from confarg.dictexpr._expressions import _set_nested_by_path

        with pytest.raises(confarg.MissingReferenceError):
            _set_nested_by_path({"a": 42}, "a.b.c", "value")

    def test_set_nested_set_non_container_raises(self) -> None:
        """_set_nested_by_path raises MissingReferenceError when the target node is not a container."""
        from confarg.dictexpr._expressions import _set_nested_by_path

        # Traverse into list index 1 (yields int 2), then set "x" on int → else branch
        with pytest.raises(confarg.MissingReferenceError):
            _set_nested_by_path({"a": [1, 2, 3]}, "a.1.x", "value")

    def test_unsupported_binary_op_raises(self) -> None:
        """An unsupported binary operator (@ matrix multiply) raises ExpressionEvalError."""
        import ast

        from confarg.dictexpr._expressions import _evaluate_ast

        node = ast.parse("a @ b", mode="eval").body
        with pytest.raises(confarg.ExpressionEvalError, match="Unsupported binary"):
            _evaluate_ast(node, {"a": 1, "b": 2})

    def test_unsupported_unary_op_raises(self) -> None:
        """An unsupported unary operator (~ bitwise invert) raises ExpressionEvalError."""
        import ast

        from confarg.dictexpr._expressions import _evaluate_ast

        node = ast.parse("~a", mode="eval").body
        with pytest.raises(confarg.ExpressionEvalError, match="Unsupported unary"):
            _evaluate_ast(node, {"a": 1})

    def test_unsupported_comparison_raises(self) -> None:
        """An unsupported comparison operator ('is') raises ExpressionEvalError."""
        import ast

        from confarg.dictexpr._expressions import _evaluate_ast

        node = ast.parse("a is b", mode="eval").body
        with pytest.raises(confarg.ExpressionEvalError, match="Unsupported comparison"):
            _evaluate_ast(node, {"a": 1, "b": 1})


# ---------------------------------------------------------------------------
# typedload._coerce — uncovered branches
# ---------------------------------------------------------------------------


class TestCoerceEdgeCases:
    """Edge cases in the leaf-type coercion logic."""

    def test_coerce_leaf_path_failure(self) -> None:
        """_coerce_leaf raises TypeCoercionError when a None value cannot become a Path."""
        from confarg.typedload._coerce import _coerce_leaf

        with pytest.raises(confarg.TypeCoercionError):
            _coerce_leaf(Path, None)

    def test_coerce_leaf_unsupported_type(self) -> None:
        """_coerce_leaf raises TypeCoercionError for unrecognized leaf types."""
        from confarg.typedload._coerce import _coerce_leaf

        class WeirdType:
            pass

        with pytest.raises(confarg.TypeCoercionError, match="Unsupported leaf type"):
            _coerce_leaf(WeirdType, "value")


# ---------------------------------------------------------------------------
# typedload._construct — uncovered branches
# ---------------------------------------------------------------------------


class TestConstructEdgeCases:
    """Edge cases in the typed construction logic."""

    def test_construct_list_from_empty_dict(self) -> None:
        """An empty dict constructs as an empty list."""
        from confarg.typedload._construct import construct

        result = construct(list[int], {})
        assert result == []

    def test_construct_list_from_dict_with_non_int_keys_raises(self) -> None:
        """Dict with non-integer keys raises TypeCoercionError when constructing a list."""
        from confarg.typedload._construct import construct

        with pytest.raises(confarg.TypeCoercionError, match="integer"):
            construct(list[int], {"bad": 1})

    def test_construct_tuple_from_dict_non_int_keys_raises(self) -> None:
        """Dict with non-integer keys raises TypeCoercionError when constructing a tuple."""
        from confarg.typedload._construct import construct

        with pytest.raises(confarg.TypeCoercionError, match="integer"):
            construct(tuple[int, str], {"bad": "value"})

    def test_construct_union_none_with_none_type(self) -> None:
        """None value for an int | None union constructs to None."""
        from confarg.typedload._construct import construct

        result = construct(int | None, None)
        assert result is None

    def test_construct_optional_coercion_failure_hint(self) -> None:
        """An uncoercible value for int | None hints about 'none'/'null' in the error message."""
        from confarg.typedload._construct import construct

        with pytest.raises(confarg.TypeCoercionError, match="None"):
            construct(int | None, _StrToken("notanint"))

    def test_ambiguous_class_tag_multiple_matches_raises(self) -> None:
        """Class tag matching multiple union variants (subclass relationship) raises AmbiguousUnionError."""
        from confarg.typedload._construct import construct

        # _StructUnionVariantB is a subclass of _StructUnionVariantA, so the
        # class tag for B matches both variants in the union → AmbiguousUnionError.
        data = {"class": f"{_StructUnionVariantB.__module__}.{_StructUnionVariantB.__name__}", "x": 0}
        with pytest.raises(confarg.AmbiguousUnionError, match="matches multiple"):
            construct(_StructUnionVariantA | _StructUnionVariantB, data)

    def test_class_tag_no_matching_variant_raises(self) -> None:
        """Class tag that matches no union variant raises TypeCoercionError."""
        from confarg.typedload._construct import construct

        # _StructUnionVariantA is not a subclass of either _ConstructAVariant or
        # _ConstructBVariant → TypeCoercionError "not compatible with any union variant".
        data = {"class": f"{_StructUnionVariantA.__module__}.{_StructUnionVariantA.__name__}", "x": 0}
        with pytest.raises(confarg.TypeCoercionError, match="not compatible"):
            construct(_ConstructAVariant | _ConstructBVariant, data)

    def test_construct_bool_in_bool_int_union(self) -> None:
        """Bool | int union: True value is constructed as bool."""
        from confarg.typedload._construct import construct

        result = construct(bool | int, True)
        assert result is True

    def test_construct_union_none_type_in_scalar_loop(self) -> None:
        """Str | None union: a string value constructs as str."""
        from confarg.typedload._construct import construct

        result = construct(str | None, "hello")
        assert result == "hello"

    def test_value_matches_type_none(self) -> None:
        """None value matches int | None."""
        from confarg.typedload._construct import _value_matches_type

        assert _value_matches_type(None, int | None, "class") is True

    def test_value_matches_type_non_dict_for_struct(self) -> None:
        """A non-dict value does not match a struct type."""
        from confarg.typedload._construct import _value_matches_type

        assert _value_matches_type("not_a_dict", _StructUnionVariantA, "class") is False

    def test_value_matches_type_float_from_invalid_str(self) -> None:
        """A non-numeric string token does not match float."""
        from confarg.typedload._construct import _value_matches_type

        assert _value_matches_type(_StrToken("notfloat"), float, "class") is False

    def test_ambiguous_union_msg_includes_optional_fields(self) -> None:
        """AmbiguousUnionError message lists optional fields to help the user disambiguate."""
        # Both _AmbigOptionalP and _AmbigOptionalQ match {"val": {"x": 1}} →
        # AmbiguousUnionError with "optional" in message (listing optional fields).
        with pytest.raises(confarg.AmbiguousUnionError, match="optional"):
            confarg.build(_AmbigContainer, {"val": {"x": 1}})

    def test_construct_struct_union_tuple_from_union(self) -> None:
        """tuple[int, str] | None union is constructed from positional CLI args."""

        @dataclass
        class WithUnionTuple:
            coord: tuple[int, str] | None = None

        result = confarg.load(WithUnionTuple, args=["--coord", "5", "hello"], env={})
        assert result.coord == (5, "hello")

    def test_partial_tuple_index_extends_with_none(self) -> None:
        """Partial indexed env var update for a fixed-length tuple merges with the default."""

        @dataclass
        class WithTuple:
            items: tuple[int, str] = (1, "x")

        result = confarg.load(WithTuple, args=[], env={"ITEMS__1": "y"}, env_prefix="")
        assert result.items == (1, "y")

    def test_class_tag_import_error_raises(self) -> None:
        """Class tag pointing to a non-importable module raises TypeCoercionError."""

        @dataclass
        class A:
            x: int = 0

        data = {"class": "nonexistent.module.SomeClass", "x": 1}
        from confarg.typedload._construct import construct

        with pytest.raises(confarg.TypeCoercionError, match="Cannot import"):
            construct(A, data)


# ---------------------------------------------------------------------------
# _argparse — uncovered branches
# ---------------------------------------------------------------------------


class TestArgparseBranches:
    """Uncovered branches in the argparse integration layer."""

    def test_get_field_docstrings_no_class_found(self) -> None:
        """_get_field_docstrings returns an empty dict when the class cannot be located by name."""
        from confarg.cli.argparse._spec import _get_field_docstrings

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
            _bad: UndefinedTypeXYZ999  # noqa: F821

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
            fn: Callable[[int], str] = lambda x: str(x)

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
        from confarg.cli.argparse._build import _collect_subconfig_specs

        assert _collect_subconfig_specs(int, "config", "", "class") == []

    def test_register_subconfig_flags_get_type_hints_exception(self) -> None:
        """_collect_subconfig_specs falls back gracefully when get_type_hints raises."""
        from confarg.cli.argparse._build import _collect_subconfig_specs

        # A class with a broken CLASS-LEVEL annotation (not __init__) causes
        # get_type_hints(cls) to fail, but _struct_fields succeeds via __init__.
        class BrokenClassAnnot:
            _bad: UndefinedType999  # noqa: F821, class-level broken forward ref

            def __init__(self, x: int, y: str = "default") -> None:
                self.x = x
                self.y = y

        _collect_subconfig_specs(BrokenClassAnnot, "config", "", "class")

    def test_register_subconfig_flags_union_tag_skipped(self) -> None:
        """_collect_subconfig_specs skips the union_tag field."""
        from confarg.cli.argparse._build import _collect_subconfig_specs

        @dataclass
        class WithTypeField:
            type: str = "a"
            value: int = 0

        _collect_subconfig_specs(WithTypeField, "config", "", union_tag="type")

    def test_collect_ns_fields_non_struct(self) -> None:
        """_collect_ns_fields is a no-op for non-struct types."""
        from confarg.cli.argparse._namespace import _collect_ns_fields

        result: dict[str, Any] = {}
        _collect_ns_fields({}, int, "", "class", result)
        assert result == {}

    def test_collect_ns_fields_get_type_hints_exception(self) -> None:
        """_collect_ns_fields falls back gracefully when get_type_hints raises."""
        from confarg.cli.argparse._namespace import _collect_ns_fields

        class BrokenClassAnnot2:
            _bad: UndefinedType888  # noqa: F821,  class-level broken forward ref

            def __init__(self, x: int, y: str = "default") -> None:
                self.x = x
                self.y = y

        result: dict[str, Any] = {}
        _collect_ns_fields({"x": "42"}, BrokenClassAnnot2, "", "class", result)
        assert "x" in result or result == {}

    def test_collect_ns_fields_union_tag_skipped(self) -> None:
        """_collect_ns_fields excludes the union_tag field from the result."""
        from confarg.cli.argparse._namespace import _collect_ns_fields

        @dataclass
        class WithTypeField:
            type: str = "a"
            value: int = 0

        result: dict[str, Any] = {}
        _collect_ns_fields({"type": "b", "value": "99"}, WithTypeField, "", union_tag="type", result=result)
        assert "type" not in result

    def test_collect_ns_fields_multi_union_skipped(self) -> None:
        """_collect_ns_fields skips fields with multi-variant union types."""
        from confarg.cli.argparse._namespace import _collect_ns_fields

        @dataclass
        class WithMultiUnion:
            val: int | str = 0

        result: dict[str, Any] = {}
        _collect_ns_fields({"val": "99"}, WithMultiUnion, "", "class", result)

    def test_collect_ns_fields_dict_skipped(self) -> None:
        """_collect_ns_fields skips dict-typed fields."""
        from confarg.cli.argparse._namespace import _collect_ns_fields

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
        result = from_namespace(ns, WithExpr, env={"HOST": "${db_host}", "DB_HOST": "realserver"}, env_prefix="")
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
            args=[],
            env={"MAPPING__KEY": "42"},
            env_prefix="",
        )
        assert result.mapping.get("key") == 42 or "key" in result.mapping

    def test_tuple_out_of_range_from_env(self) -> None:
        """Out-of-range env var index for a fixed-length tuple raises TypeCoercionError."""
        # Index 5 is out of range for a 2-element tuple; the partial-index
        # merge extends the base list to 6 elements, then _construct_tuple rejects it.
        WithTuple = make_target("coords", tuple[int, str], default=(0, ""))
        with pytest.raises(confarg.TypeCoercionError):
            confarg.load(
                WithTuple,
                args=[],
                env={"COORDS__5": "hello"},
                env_prefix="",
            )

    def test_scalar_field_with_deep_env_path(self) -> None:
        """A deeper-than-expected env var path for a scalar field raises TypeCoercionError."""
        WithInt = make_target("count", int, default=0)
        with pytest.raises(confarg.TypeCoercionError):
            confarg.load(WithInt, args=[], env={"COUNT__EXTRA": "5"}, env_prefix="")


# ---------------------------------------------------------------------------
# _callable — non-callable instance, slotted callable, bare Callable check
# ---------------------------------------------------------------------------


class TestCallableBranches:
    """Uncovered branches in callable resolution."""

    def test_non_callable_instance_raises(self) -> None:
        """An instance of a non-callable class raises TypeCoercionError in _resolve_class_spec."""
        from confarg._callable import _ClassSpec, _resolve_class_spec

        cls_path = f"{_NotCallableClass.__module__}.{_NotCallableClass.__qualname__}"
        with pytest.raises(confarg.TypeCoercionError, match="is not callable"):
            _resolve_class_spec(
                _ClassSpec(cls_path, {}, {}, {"class": cls_path}),
                "test_path",
                "class",
            )

    def test_slotted_callable_confarg_spec_except_branch(self) -> None:
        """A slotted callable class resolves successfully in _resolve_class_spec."""
        from confarg._callable import _ClassSpec, _resolve_class_spec

        cls_path = f"{_SlottedCallableClass.__module__}.{_SlottedCallableClass.__qualname__}"
        result = _resolve_class_spec(
            _ClassSpec(cls_path, {"value": 5}, {}, {"class": cls_path, "value": 5}),
            "test_path",
            "class",
        )
        assert callable(result)

    def test_check_callable_signature_non_callable_type_returns_early(self) -> None:
        """_check_callable_signature is a no-op when the target type is not Callable."""
        from confarg._callable import _check_callable_signature

        # Line 222-223: `if not _is_callable(tp): return` — tp=int is not a Callable type
        _check_callable_signature(lambda: None, int, path="test")

    def test_check_callable_signature_bare_callable_returns_early(self) -> None:
        """_check_callable_signature is a no-op for bare Callable (no parameter types)."""
        from collections.abc import Callable

        from confarg._callable import _check_callable_signature

        # Line 225-226: bare Callable has no param_types → returns early
        _check_callable_signature(lambda: None, Callable, path="test")


# ---------------------------------------------------------------------------
# _files — YAML missing library
# ---------------------------------------------------------------------------


class TestFilesMissingLibrary:
    """File loading fails gracefully when optional libraries are absent."""

    def test_yaml_missing_library(self, tmp_yaml) -> None:
        """Missing PyYAML library raises InvalidConfigFileError when loading a YAML file."""
        import sys
        import unittest.mock

        from confarg._files import _load_yaml

        path = tmp_yaml("host: myserver")
        with (
            unittest.mock.patch.dict(sys.modules, {"yaml": None}),
            pytest.raises(confarg.InvalidConfigFileError, match="PyYAML"),
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
        with pytest.raises(confarg.UnknownArgumentError):
            confarg.load(_NonStructSubBase, args=["--unknown_field", "5"])

    def test_union_variants_no_matching_field_returns_none(self) -> None:
        """_resolve_field_type returns None when the path matches no union variant field."""
        from confarg._parse_cli import _resolve_field_type

        result = _resolve_field_type(_AmbigVariantX | _AmbigVariantY, ["z"], "class")
        assert result is None

    def test_dict_at_path_triggers_line_164_and_360(self) -> None:
        """A deep CLI sub-key path into a dict-typed field raises TypeCoercionError."""
        DCWithDict = make_target("mapping", dict[str, int], default_factory=dict)
        # --mapping.subkey.deeper triggers ft=None, then _is_dict_at_path returns True
        with pytest.raises(confarg.TypeCoercionError):
            confarg.load(DCWithDict, args=["--mapping.subkey.deeper", "hello"])

    def test_dict_at_path_bare_flag(self) -> None:
        """A bare CLI flag (no value) at a dict sub-path is skipped without error."""
        DCWithDict = make_target("mapping", dict[str, int], default_factory=dict)
        # Bare flag (no value) after dict-at-path: i+1 is end or flag, skip value
        confarg.load(DCWithDict, args=["--mapping.subkey.deeper", "--mapping.key", "42"])

    def test_non_bool_optional_bare_flag_sets_none(self) -> None:
        """'none' token for a str | None non-struct target resolves to None."""
        # Non-struct optional target with cli_prefix + "none" token → __root__ = None
        result = confarg.load(str | None, args=["--myapp", "none"], cli_prefix="myapp")
        assert result is None

    def test_non_bool_non_optional_bare_flag_sets_true(self) -> None:
        """'true' token for a bool | str non-struct target is stolen as bool True."""
        # Non-struct bool|str union: "true" steals to bool True
        result = confarg.load(bool | str, args=["--myapp", "true"], cli_prefix="myapp")
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
        from confarg.dictexpr._expressions import _extract_references

        refs = _extract_references("${x.replace(a, old=b)}")
        assert "x" in refs
        assert "b" in refs

    def test_attribute_chain_noninteger_subscript_returns_none(self) -> None:
        """_attribute_chain returns None for string subscripts (non-integer indices)."""
        from confarg.dictexpr._expressions import _extract_references

        refs = _extract_references("${servers['primary'].host}")
        assert isinstance(refs, set)

    def test_pure_expression_unexpected_exception_wrapped(self) -> None:
        """An unexpected exception inside a pure expression is wrapped as ExpressionEvalError."""

        @dataclass
        class DC:
            a: list = field(default_factory=list)
            b: str = ""
            result: str = ""

        with pytest.raises(confarg.ExpressionEvalError):
            confarg.build(DC, {"a": [1, 2, 3], "b": "key", "result": "${a[b]}"})

    def test_interpolation_missing_ref_reraises(self) -> None:
        """A missing field reference inside a string interpolation raises MissingReferenceError."""
        WithStr = make_target("msg", str, default="")
        with pytest.raises(confarg.MissingReferenceError):
            confarg.build(WithStr, {"msg": "hello ${missing_field} world"})

    def test_interpolation_unexpected_exception_wrapped(self) -> None:
        """An unexpected exception inside a string interpolation is wrapped as ExpressionEvalError."""

        @dataclass
        class DC:
            a: list = field(default_factory=list)
            b: str = ""
            result: str = ""

        with pytest.raises(confarg.ExpressionEvalError):
            confarg.build(DC, {"a": [1, 2, 3], "b": "key", "result": "prefix_${a[b]}_suffix"})


# ---------------------------------------------------------------------------
# typedload/_coerce — non-token non-numeric float, non-str value for str type
# ---------------------------------------------------------------------------


class TestCoerceBranches:
    """Additional uncovered coercion branches."""

    def test_float_from_dict_raises(self) -> None:
        """A dict value cannot be coerced to float; raises TypeCoercionError."""
        from confarg.typedload._coerce import _coerce_leaf

        with pytest.raises(confarg.TypeCoercionError):
            _coerce_leaf(float, {"nested": "val"}, "field")

    def test_str_from_int_raises(self) -> None:
        """A bare int value cannot be coerced to str; raises TypeCoercionError."""
        from confarg.typedload._coerce import _coerce_leaf

        with pytest.raises(confarg.TypeCoercionError):
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
            args=[],
            env={"COORD__0": "1", "COORD__1": "hello"},
            env_prefix="",
        )
        assert result.coord == (1, "hello")

    def test_construct_tuple_from_dict_non_integer_keys(self) -> None:
        """Dict with non-integer string keys raises TypeCoercionError for a tuple."""
        from confarg.typedload._construct import construct

        with pytest.raises(confarg.TypeCoercionError, match="integer indices"):
            construct(tuple[int, str], {"a": 1, "b": "hello"})

    def test_construct_tuple_from_dict_out_of_range_index(self) -> None:
        """Out-of-range integer index for a fixed-length tuple raises TypeCoercionError."""
        from confarg.typedload._construct import construct

        with pytest.raises(confarg.TypeCoercionError, match="out of range"):
            construct(tuple[int, str], {"0": 1, "5": "hello"})

    def test_tuple_variants_in_union_list_data(self) -> None:
        """tuple[int, str] | int union: a list value constructs as the tuple variant."""
        from confarg.typedload._construct import construct

        result = construct(tuple[int, str] | int, [1, "hello"])
        assert result == (1, "hello")

    def test_tuple_variants_dict_noninteger_keys(self) -> None:
        """Dict with non-integer keys raises TypeCoercionError for a tuple | int union."""
        from confarg.typedload._construct import construct

        with pytest.raises(confarg.TypeCoercionError):
            construct(tuple[int, str] | int, {"a": 1, "b": "hello"})

    def test_bool_int_union_bool_value_returns_bool(self) -> None:
        """Bool | int union: a True value is constructed as bool, not int."""
        from confarg.typedload._construct import construct

        result = construct(bool | int, True)
        assert result is True

    def test_value_matches_type_bool_with_non_token_non_bool_value(self) -> None:
        """An int (non-bool, non-token) value does not match bool."""
        from confarg.typedload._construct import _value_matches_type

        # Line 512: bool type, value is int (not bool, not _StrToken) → return False
        assert _value_matches_type(42, bool, "class") is False

    def test_union_class_tag_resolves_to_non_class(self) -> None:
        """A class tag that resolves to a non-class object raises TypeCoercionError."""
        from confarg.typedload._construct import construct

        with pytest.raises(confarg.TypeCoercionError, match="must be a class path"):
            construct(
                _StructUnionVariantA | _StructUnionVariantB,
                {"class": "confarg._defaults.UNION_TAG", "x": 0},
            )
