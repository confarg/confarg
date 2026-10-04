# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for environment variable parsing: naming, prefix, separator, coercion, indexed collections."""

from __future__ import annotations

import warnings
from dataclasses import dataclass as _dc
from dataclasses import field, make_dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple, Optional, Union
from uuid import UUID

if TYPE_CHECKING:
    from tests._loaders import ConfargLoader

import pytest

import confarg
from tests.conftest import (
    AppConfig,
    Color,
    Flat,
    WithDefaults,
    make_target,
)

# ---------------------------------------------------------------------------
# Basic env var naming
# ---------------------------------------------------------------------------


class TestEnvNaming:
    """Env var name construction."""

    def test_flat_field_no_prefix(self, loader: ConfargLoader) -> None:
        """Flat field is uppercased with env_prefix="" (no prefix)."""
        result = loader.load(WithDefaults, argv=[], env={"NAME": "hello"}, env_prefix="")
        assert result.name == "hello"

    def test_flat_field_explicit_prefix(self, loader: ConfargLoader) -> None:
        """Env vars are read when an explicit env_prefix is set."""
        result = loader.load(WithDefaults, argv=[], env={"CONFARG_NAME": "hello"}, env_prefix="CONFARG_")
        assert result.name == "hello"

    def test_env_disabled_by_default(self, loader: ConfargLoader) -> None:
        """Env vars are ignored when env_prefix is None (the default)."""
        result = loader.load(WithDefaults, argv=[], env={"NAME": "ignored"})
        assert result.name == "default"

    def test_flat_field_with_prefix(self, loader: ConfargLoader) -> None:
        """Flat field with prefix: PREFIX__FIELD."""
        result = loader.load(WithDefaults, argv=[], env={"MYAPP__NAME": "world"}, env_prefix="MYAPP")
        assert result.name == "world"

    def test_nested_field_double_underscore(self, loader: ConfargLoader) -> None:
        """Nested field uses __ as level separator."""
        result = loader.load(
            AppConfig,
            argv=[],
            env={"MYAPP_DB__HOST": "h", "MYAPP_DB__PORT": "1", "MYAPP_DB__NAME": "n"},
            env_prefix="MYAPP_",
        )
        assert result.db.host == "h"

    def test_nested_with_prefix(self, loader: ConfargLoader) -> None:
        """Nested field with prefix: PREFIX__LEVEL__FIELD."""
        result = loader.load(
            AppConfig,
            argv=[],
            env={"APP__DB__HOST": "h", "APP__DB__PORT": "1", "APP__DB__NAME": "n"},
            env_prefix="APP",
        )
        assert result.db.host == "h"


# ---------------------------------------------------------------------------
# Custom separator
# ---------------------------------------------------------------------------


class TestEnvCustomSeparator:
    """Custom env var level separator."""

    def test_single_underscore_separator(self, loader: ConfargLoader) -> None:
        """Use single underscore as separator (less safe but user's choice)."""
        result = loader.load(
            AppConfig,
            argv=[],
            env={"MYAPP_DB_HOST": "h", "MYAPP_DB_PORT": "1", "MYAPP_DB_NAME": "n"},
            env_prefix="MYAPP_",
            env_separator="_",
        )
        assert result.db.host == "h"

    def test_dot_separator(self, loader: ConfargLoader) -> None:
        """Use dot as separator."""
        result = loader.load(
            AppConfig,
            argv=[],
            env={"MYAPP_DB.HOST": "h", "MYAPP_DB.PORT": "1", "MYAPP_DB.NAME": "n"},
            env_prefix="MYAPP_",
            env_separator=".",
        )
        assert result.db.host == "h"

    def test_custom_separator_with_prefix(self, loader: ConfargLoader) -> None:
        """Custom separator combined with prefix."""
        result = loader.load(
            AppConfig,
            argv=[],
            env={"X_DB_HOST": "h", "X_DB_PORT": "1", "X_DB_NAME": "n"},
            env_prefix="X",
            env_separator="_",
        )
        assert result.db.host == "h"


# ---------------------------------------------------------------------------
# Type coercion from env
# ---------------------------------------------------------------------------


class TestEnvCoercion:
    """Env var string-to-type coercion."""

    @pytest.mark.parametrize(
        ("env_key", "env_val", "field", "expected", "target_cls"),
        [
            ("MYAPP_COUNT", "42", "count", 42, None),
            ("MYAPP_RATE", "3.14", "rate", pytest.approx(3.14), None),
            ("MYAPP_LOCATION", "/tmp", "location", Path("/tmp"), make_target("location", Path, default=Path())),
            ("MYAPP_COLOR", "green", "color", Color.GREEN, make_target("color", Color, default=Color.RED)),
        ],
        ids=["int", "float", "path", "enum"],
    )
    def test_type_coercion(self, loader: ConfargLoader, env_key, env_val, field, expected, target_cls) -> None:  # noqa: PLR0913 — pytest parametrize + loader fixture
        """Env var string coerced to the target type."""
        cls = target_cls or WithDefaults
        result = loader.load(cls, argv=[], env={env_key: env_val}, env_prefix="MYAPP_")
        actual = getattr(result, field)
        assert actual == expected

    def test_expression_survives_coercion_to_a_registered_leaf(self, loader: ConfargLoader) -> None:
        """An env expression stays a str through coercion so the resolver can still see it.

        ``Path("${base}/logs")`` coerces *successfully*, so without the explicit
        expression check in ``_try_coerce`` env coercion turned the token into a
        ``Path`` that ``resolve_expressions`` never revisited — leaving a literal
        ``${base}/logs``, while the same value from a config file resolved.
        """
        cls = make_dataclass("WithLeafExpr", [("base", str, "/app"), ("log", Path, Path())])
        merged = loader.merge(
            cls,
            argv=[],
            env={"MYAPP_BASE": "/app", "MYAPP_LOG": "${base}/logs"},
            env_prefix="MYAPP_",
        )
        assert merged["log"] == "${base}/logs"
        assert isinstance(merged["log"], str)
        assert loader.load(
            cls,
            argv=[],
            env={"MYAPP_BASE": "/app", "MYAPP_LOG": "${base}/logs"},
            env_prefix="MYAPP_",
        ).log == Path(
            "/app/logs",
        )

    @pytest.mark.parametrize(
        "env_val",
        ["true", "True", "TRUE", "1", "yes", "on"],
        ids=["true", "True", "TRUE", "1", "yes", "on"],
    )
    def test_bool_true_values(self, loader: ConfargLoader, env_val: str) -> None:
        """Various truthy strings for bool."""
        result = loader.load(WithDefaults, argv=[], env={"MYAPP_VERBOSE": env_val}, env_prefix="MYAPP_")
        assert result.verbose is True, f"Expected True for {env_val!r}"

    @pytest.mark.parametrize(
        "env_val",
        ["false", "False", "FALSE", "0", "no", "off"],
        ids=["false", "False", "FALSE", "0", "no", "off"],
    )
    def test_bool_false_values(self, loader: ConfargLoader, env_val: str) -> None:
        """Various falsy strings for bool."""
        result = loader.load(WithDefaults, argv=[], env={"MYAPP_VERBOSE": env_val}, env_prefix="MYAPP_")
        assert result.verbose is False, f"Expected False for {env_val!r}"

    @pytest.mark.parametrize(
        ("target_cls", "env_val", "expected"),
        [
            (make_target("value", Optional[int], default=None), "99", 99),
            (make_target("value", int | None, default=None), "99", 99),
        ],
        ids=[
            "Optional[int]-value",
            "int|None-value",
        ],
    )
    def test_optional_coercion(self, loader: ConfargLoader, target_cls, env_val: str, expected) -> None:
        """Optional / pipe-none coercion from env var string."""
        result = loader.load(target_cls, argv=[], env={"MYAPP_VALUE": env_val}, env_prefix="MYAPP_")
        assert result.value == expected

    @pytest.mark.parametrize(
        "target_cls",
        [
            make_target("value", Optional[int], default=None),
            make_target("value", int | None, default=None),
        ],
        ids=["Optional[int]", "int|None"],
    )
    def test_optional_int_empty_env_raises(self, loader: ConfargLoader, target_cls) -> None:
        """Empty env VALUE= for int|None raises — use VALUE__NONE= to set None."""
        with pytest.raises(confarg.exceptions.TypeCoercionError, match="To set this field to None"):
            loader.load(target_cls, argv=[], env={"MYAPP_VALUE": ""}, env_prefix="MYAPP_")

    def test_optional_str_empty_env_is_empty_string(self, loader: ConfargLoader) -> None:
        """Empty env VALUE= gives empty string for str | None, not None."""
        WithOptionalStr = make_target("value", str | None, default=None)
        result = loader.load(WithOptionalStr, argv=[], env={"MYAPP_VALUE": ""}, env_prefix="MYAPP_")
        assert result.value == ""


# ---------------------------------------------------------------------------
# NONE sentinel
# ---------------------------------------------------------------------------


class TestEnvNoneSentinel:
    """Passing 'none' or 'null' as env var value sets Optional fields to None."""

    @pytest.mark.parametrize(
        "target_cls",
        [
            make_target("value", Optional[int], default=99),
            make_target("value", int | None, default=99),
            make_target("value", str | None, default="hello"),
        ],
        ids=["Optional[int]", "int|None", "str|None"],
    )
    def test_none_sentinel_sets_optional_to_none(self, loader: ConfargLoader, target_cls) -> None:
        """Test that 'none' env var value sets an Optional field to None."""
        result = loader.load(target_cls, argv=[], env={"MYAPP_VALUE": "none"}, env_prefix="MYAPP_")
        assert result.value is None

    def test_none_sentinel_case_insensitive(self, loader: ConfargLoader) -> None:
        """Test that 'none'/'None'/'NONE'/'null'/'Null'/'NULL' all set Optional to None."""
        WithOpt = make_target("value", Optional[int], default=99)
        for val in ["none", "None", "NONE", "null", "Null", "NULL"]:
            result = loader.load(WithOpt, argv=[], env={"MYAPP_VALUE": val}, env_prefix="MYAPP_")
            assert result.value is None

    def test_none_sentinel_value_is_ignored(self, loader: ConfargLoader) -> None:
        """'null' is a case-insensitive alias for None alongside 'none'."""
        WithOpt = make_target("value", Optional[int], default=99)
        result = loader.load(WithOpt, argv=[], env={"MYAPP_VALUE": "null"}, env_prefix="MYAPP_")
        assert result.value is None

    def test_none_sentinel_with_prefix(self, loader: ConfargLoader) -> None:
        """Test that none sentinel works when an env_prefix is set."""
        WithOpt = make_target("value", Optional[int], default=99)
        result = loader.load(WithOpt, argv=[], env={"APP__VALUE": "none"}, env_prefix="APP")
        assert result.value is None

    def test_none_sentinel_nested(self, loader: ConfargLoader) -> None:
        """Test that none sentinel works for a nested optional dataclass field."""
        Inner = make_dataclass("Inner", [("x", int, field(default=1))])
        Outer = make_dataclass("Outer", [("inner", Inner | None, field(default=None))])
        result: Any = loader.load(Outer, argv=[], env={"MYAPP_INNER": "none"}, env_prefix="MYAPP_")
        assert result.inner is None


# ---------------------------------------------------------------------------
# Indexed collections from env
# ---------------------------------------------------------------------------


class TestEnvIndexedCollections:
    """Indexed collection items from env vars."""

    @pytest.mark.parametrize(
        ("target_cls", "env", "field", "expected"),
        [
            (
                make_target("items", list[int], default_factory=list),
                {"MYAPP_ITEMS__0": "10", "MYAPP_ITEMS__1": "20"},
                "items",
                [10, 20],
            ),
            (
                make_target("tags", set[str], default_factory=set),
                {"MYAPP_TAGS__0": "a", "MYAPP_TAGS__1": "b"},
                "tags",
                {"a", "b"},
            ),
            (
                make_target("metadata", dict[str, int], default_factory=dict),
                {"MYAPP_METADATA__x": "1", "MYAPP_METADATA__y": "2"},
                "metadata",
                {"x": 1, "y": 2},
            ),
        ],
        ids=["list", "set", "dict"],
    )
    def test_indexed_collection(self, loader: ConfargLoader, target_cls, env, field, expected) -> None:
        """Collection items via indexed/keyed env vars."""
        result = loader.load(target_cls, argv=[], env=env, env_prefix="MYAPP_")
        assert getattr(result, field) == expected

    def test_list_indexed_with_prefix(self, loader: ConfargLoader) -> None:
        """List items with prefix and index."""
        WithList = make_target("items", list[int], default_factory=list)
        result = loader.load(
            WithList,
            argv=[],
            env={"P__ITEMS__0": "1", "P__ITEMS__1": "2"},
            env_prefix="P",
        )
        assert result.items == [1, 2]


# ---------------------------------------------------------------------------
# Env vars ignored when env={}
# ---------------------------------------------------------------------------


class TestEnvDisabled:
    """Env parsing disabled via empty dict."""

    def test_empty_env_ignores_vars(self, loader: ConfargLoader) -> None:
        """Passing env={} means no env vars are read."""
        result = loader.load(WithDefaults, argv=[], env={})
        assert result.name == "default"
        assert result.count == 0


# ---------------------------------------------------------------------------
# Unrecognized env vars
# ---------------------------------------------------------------------------


class TestEnvUnrecognized:
    """Unrecognized env vars emit ConfargWarning and are ignored."""

    def test_extra_env_vars_warn(self, loader: ConfargLoader) -> None:
        """Env vars not matching any field emit ConfargWarning and are ignored."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = loader.load(
                WithDefaults,
                argv=[],
                env={"MYAPP_UNKNOWN": "val", "MYAPP_NAME": "ok"},
                env_prefix="MYAPP_",
            )
        assert result.name == "ok"
        assert len(caught) == 1
        assert issubclass(caught[0].category, confarg.exceptions.ConfargWarning)
        assert "UNKNOWN" in str(caught[0].message)
        assert "unknown" in str(caught[0].message)

    def test_extra_env_vars_with_prefix_warn(self, loader: ConfargLoader) -> None:
        """Only prefixed vars are considered; unrecognised prefixed vars warn."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = loader.load(WithDefaults, argv=[], env={"X__NAME": "ok", "X__BOGUS": "no"}, env_prefix="X")
        assert result.name == "ok"
        assert any(
            "BOGUS" in str(w.message) for w in caught if issubclass(w.category, confarg.exceptions.ConfargWarning)
        )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEnvEdgeCases:
    """Edge cases for env var handling."""

    def test_empty_string_value(self, loader: ConfargLoader) -> None:
        """Empty string env var is treated as the value."""
        result = loader.load(WithDefaults, argv=[], env={"MYAPP_NAME": ""}, env_prefix="MYAPP_")
        assert result.name == ""

    def test_all_fields_from_env(self, loader: ConfargLoader) -> None:
        """All fields of a flat dataclass from env vars."""
        result = loader.load(
            Flat,
            argv=[],
            env={"MYAPP_NAME": "n", "MYAPP_COUNT": "1", "MYAPP_RATE": "2.0", "MYAPP_VERBOSE": "true"},
            env_prefix="MYAPP_",
        )
        assert result.name == "n"
        assert result.count == 1
        assert result.rate == pytest.approx(2.0)
        assert result.verbose is True

    def test_nested_all_from_env(self, loader: ConfargLoader) -> None:
        """All nested fields from env vars."""
        result = loader.load(
            AppConfig,
            argv=[],
            env={
                "MYAPP_DB__HOST": "h",
                "MYAPP_DB__PORT": "3306",
                "MYAPP_DB__NAME": "db",
                "MYAPP_CACHE__ENABLED": "false",
                "MYAPP_CACHE__TTL": "60",
                "MYAPP_DEBUG": "true",
            },
            env_prefix="MYAPP_",
        )
        assert result.db.host == "h"
        assert result.db.port == 3306
        assert result.cache.enabled is False
        assert result.cache.ttl == 60
        assert result.debug is True


# ---------------------------------------------------------------------------
# JSON values in env vars
# ---------------------------------------------------------------------------


class TestEnvJsonValues:
    """JSON arrays and objects passed as env var values."""

    def test_json_array_for_list(self, loader: ConfargLoader) -> None:
        """A JSON array string is decoded into a list field."""
        WithList = make_target("items", list[int])
        result = loader.load(WithList, argv=[], env={"MYAPP_ITEMS": "[1, 2, 3]"}, env_prefix="MYAPP_")
        assert result.items == [1, 2, 3]

    def test_json_array_for_tuple(self, loader: ConfargLoader) -> None:
        """A JSON array string is decoded into a fixed-length tuple field."""
        WithTuple = make_target("point", tuple[float, float])
        result = loader.load(WithTuple, argv=[], env={"MYAPP_POINT": "[1.5, 2.5]"}, env_prefix="MYAPP_")
        assert result.point == (1.5, 2.5)

    def test_json_array_with_prefix(self, loader: ConfargLoader) -> None:
        """JSON array env var respects env_prefix."""
        WithList = make_target("tags", list[str])
        result = loader.load(WithList, argv=[], env={"APP__TAGS": '["x", "y"]'}, env_prefix="APP")
        assert result.tags == ["x", "y"]

    def test_json_array_wrong_length_raises(self, loader: ConfargLoader) -> None:
        """A JSON array with wrong length raises a TypeCoercionError."""
        WithTuple = make_target("point", tuple[int, int, int])
        with pytest.raises(confarg.exceptions.TypeCoercionError, match="expected 3 elements, got 2"):
            loader.load(WithTuple, argv=[], env={"MYAPP_POINT": "[1, 2]"}, env_prefix="MYAPP_")

    def test_json_array_invalid_json_falls_back_to_string(self, loader: ConfargLoader) -> None:
        """Malformed JSON starting with '[' is treated as a plain string."""
        WithStr = make_target("val", str, default="")
        result = loader.load(WithStr, argv=[], env={"MYAPP_VAL": "[not json"}, env_prefix="MYAPP_")
        assert result.val == "[not json"

    def test_json_object_for_dataclass(self, loader: ConfargLoader) -> None:
        """A JSON object string is decoded into a nested dataclass field."""
        result = loader.load(
            AppConfig,
            argv=[],
            env={
                "MYAPP_DB": '{"host": "localhost", "port": 5432, "name": "mydb"}',
                "MYAPP_CACHE__ENABLED": "true",
                "MYAPP_CACHE__TTL": "60",
            },
            env_prefix="MYAPP_",
        )
        assert result.db.host == "localhost"
        assert result.db.port == 5432
        assert result.db.name == "mydb"

    def test_json_object_with_prefix(self, loader: ConfargLoader) -> None:
        """JSON object env var respects env_prefix."""
        result = loader.load(
            AppConfig,
            argv=[],
            env={
                "APP__DB": '{"host": "h", "port": 1, "name": "n"}',
                "APP__CACHE__ENABLED": "false",
                "APP__CACHE__TTL": "10",
            },
            env_prefix="APP",
        )
        assert result.db.host == "h"
        assert result.db.port == 1

    def test_json_object_for_dict(self, loader: ConfargLoader) -> None:
        """A JSON object string is decoded into a dict field."""
        WithDict = make_target("env", dict[str, str], default_factory=dict)
        result = loader.load(WithDict, argv=[], env={"MYAPP_ENV": '{"a": "b"}'}, env_prefix="MYAPP_")
        assert result.env == {"a": "b"}

    def test_json_object_for_optional_dict(self, loader: ConfargLoader) -> None:
        """An optional dict decodes the whole mapping its non-optional peer decodes."""
        WithOptDict = make_target("env", dict[str, str] | None, default=None)
        result = loader.load(WithOptDict, argv=[], env={"MYAPP_ENV": '{"a": "b"}'}, env_prefix="MYAPP_")
        assert result.env == {"a": "b"}

    def test_json_object_invalid_json_falls_back_to_string(self, loader: ConfargLoader) -> None:
        """Malformed JSON starting with '{' is treated as a plain string."""
        WithStr = make_target("val", str, default="")
        result = loader.load(WithStr, argv=[], env={"MYAPP_VAL": "{not json"}, env_prefix="MYAPP_")
        assert result.val == "{not json"

    def test_json_object_not_parsed_for_str_field(self, loader: ConfargLoader) -> None:
        """A valid JSON object string is stored verbatim in a str field."""
        WithStr = make_target("val", str, default="")
        result = loader.load(WithStr, argv=[], env={"MYAPP_VAL": '{"key":"val"}'}, env_prefix="MYAPP_")
        assert result.val == '{"key":"val"}'

    def test_json_array_not_parsed_for_str_field(self, loader: ConfargLoader) -> None:
        """A valid JSON array string is stored verbatim in a str field."""
        WithStr = make_target("val", str, default="")
        result = loader.load(WithStr, argv=[], env={"MYAPP_VAL": "[1,2,3]"}, env_prefix="MYAPP_")
        assert result.val == "[1,2,3]"


# ---------------------------------------------------------------------------
# env_prefix=None
# ---------------------------------------------------------------------------


class TestEnvPrefixNone:
    """env_prefix=None skips all env var parsing."""

    def test_none_prefix_ignores_env(self, loader: ConfargLoader) -> None:
        """When env_prefix=None no env vars are processed."""
        result = loader.load(
            WithDefaults,
            argv=[],
            env={"NAME": "from_env"},
            env_prefix=None,
        )
        assert result.name == "default"

    def test_none_prefix_no_warnings(self, loader: ConfargLoader) -> None:
        """env_prefix=None emits no ConfargWarning even with unrecognised vars."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            loader.load(
                WithDefaults,
                argv=[],
                env={"TOTALLY_UNKNOWN": "x"},
                env_prefix=None,
            )
        assert not any(issubclass(w.category, confarg.exceptions.ConfargWarning) for w in caught)


# ---------------------------------------------------------------------------
# ConfargWarning for unrecognised env vars
# ---------------------------------------------------------------------------


class TestConfargWarning:
    """ConfargWarning is emitted for env vars that match the prefix but have no field."""

    def test_typo_in_field_name_warns(self, loader: ConfargLoader) -> None:
        """A prefixed var with an unknown field name emits ConfargWarning."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = loader.load(
                WithDefaults,
                argv=[],
                env={"APP_NAEM": "oops"},
                env_prefix="APP_",
            )
        assert result.name == "default"
        warns = [w for w in caught if issubclass(w.category, confarg.exceptions.ConfargWarning)]
        assert len(warns) == 1
        msg = str(warns[0].message)
        assert "APP_NAEM" in msg
        assert "naem" in msg
        assert "name" in msg  # known fields listed

    def test_correct_field_no_warning(self, loader: ConfargLoader) -> None:
        """A correctly spelled prefixed var produces no warning."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = loader.load(
                WithDefaults,
                argv=[],
                env={"APP_NAME": "hello"},
                env_prefix="APP_",
            )
        assert result.name == "hello"
        assert not any(issubclass(w.category, confarg.exceptions.ConfargWarning) for w in caught)

    def test_warning_is_a_user_warning_subclass(self) -> None:
        """ConfargWarning is a UserWarning so standard warning filters apply."""
        assert issubclass(confarg.exceptions.ConfargWarning, UserWarning)


# ---------------------------------------------------------------------------
# ConfargWarning for plain-class (non-dataclass) and union targets
# ---------------------------------------------------------------------------


class PlainTarget:
    """Plain class (non-dataclass) struct target for env var tests."""

    def __init__(self, host: str = "localhost", port: int = 5432) -> None:
        """Initialize PlainTarget with host and port."""
        self.host = host
        self.port = port


class TestConfargWarningPlainClass:
    """ConfargWarning is emitted for plain-class (non-DC) targets with unknown env vars.

    Plain-class targets trigger recursion in the CLI integration namespace collectors
    (they attempt to recurse into leaf-type fields like ``str``), so these tests use
    the vanilla loader only.
    """

    def test_unknown_field_warns_on_plain_class_target(self) -> None:
        """Unknown env var on a plain-class target emits ConfargWarning.

        Previously the guard used _is_dc which returned False for plain classes,
        so unknown fields were silently accepted instead of triggering a warning.
        """
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            confarg.load(
                PlainTarget,
                argv=[],
                env={"APP_HOTS": "oops"},  # typo: HOTS instead of HOST
                env_prefix="APP_",
            )
        warns = [w for w in caught if issubclass(w.category, confarg.exceptions.ConfargWarning)]
        assert len(warns) == 1
        msg = str(warns[0].message)
        assert "APP_HOTS" in msg
        assert "hots" in msg
        assert "host" in msg  # known fields listed

    def test_valid_field_no_warning_on_plain_class_target(self) -> None:
        """Correctly named env var on a plain-class target produces no warning."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = confarg.load(
                PlainTarget,
                argv=[],
                env={"APP_HOST": "db.local"},
                env_prefix="APP_",
            )
        assert result.host == "db.local"
        assert not any(issubclass(w.category, confarg.exceptions.ConfargWarning) for w in caught)


@_dc
class _DCVariant:
    x: str = ""


class _PlainVariant:
    def __init__(self, y: str = "") -> None:
        self.y = y


class TestConfargWarningUnionWithPlainVariant:
    """Union targets: plain-class variant fields must suppress the warning."""

    def test_field_only_in_plain_variant_no_warning(self) -> None:
        """A field that exists only in the plain-class union variant must not warn.

        Previously only DC variants were checked, so a field exclusive to a plain
        class in the union was falsely treated as unknown and silently dropped.
        """
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            confarg.merge(
                Union[_DCVariant, _PlainVariant],
                argv=[],
                env={"APP_Y": "hello"},  # 'y' only exists on _PlainVariant
                env_prefix="APP_",
            )
        assert not any(issubclass(w.category, confarg.exceptions.ConfargWarning) for w in caught)

    def test_unknown_field_in_union_warns(self) -> None:
        """An env var matching no variant in the union still warns."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            confarg.merge(
                Union[_DCVariant, _PlainVariant],
                argv=[],
                env={"APP_Z": "oops"},  # 'z' exists in neither variant
                env_prefix="APP_",
            )
        warns = [w for w in caught if issubclass(w.category, confarg.exceptions.ConfargWarning)]
        assert len(warns) == 1
        msg = str(warns[0].message)
        assert "APP_Z" in msg


# ---------------------------------------------------------------------------
# A root-level tag segment is a real member, whatever the root shape
# ---------------------------------------------------------------------------


@_dc
class _EnvTagBase:
    host: str = "localhost"


@_dc
class _EnvTagSub(_EnvTagBase):
    extra: str = "e"


@_dc
class _EnvKindOnlyBase:
    pass


@_dc
class _EnvKindOnlySub(_EnvKindOnlyBase):
    Kind: str


class TestEnvRootTagSegment:
    """A root-level tag segment names a real member, as the CLI and file channels accept it (BUG-90).

    The env channel's first-segment check asked only ``parts[0] in _struct_fields(root)``,
    so the tag — not a field — was warned away and dropped on every struct-walked root,
    while the same configuration built from argv or a file.
    """

    def test_tag_on_registered_leaf_root(
        self,
        loader: ConfargLoader,
        leaf_registry: None,
    ) -> None:
        """CLASS and HEX build a registered leaf as the root target, with no warning."""
        confarg.register_leaf_type(UUID, UUID)
        hex_text = "12345678123456781234567812345678"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            cfg = loader.load(
                UUID,
                argv=[],
                env={"APP_CLASS": "uuid.UUID", "APP_HEX": hex_text},
                env_prefix="APP_",
            )
        assert cfg == UUID(hex_text)
        assert not any(issubclass(w.category, confarg.exceptions.ConfargWarning) for w in caught)

    def test_tag_on_registered_leaf_root_merges_like_the_repro(
        self,
        loader: ConfargLoader,
        leaf_registry: None,
    ) -> None:
        """The ticket's repro: env merges to the same dict the CLI channel gives (BUG-90)."""
        confarg.register_leaf_type(UUID, UUID)
        hex_text = "12345678123456781234567812345678"
        merged = loader.merge(
            UUID,
            argv=[],
            env={"APP_CLASS": "uuid.UUID", "APP_HEX": hex_text},
            env_prefix="APP_",
        )
        assert merged == {"class": "uuid.UUID", "hex": hex_text}

    def test_tag_on_union_root(self, loader: ConfargLoader) -> None:
        """CLASS reaches the merged dict on a union root, with a variant field beside it."""
        merged = loader.merge(
            Union[_DCVariant, _PlainVariant],
            argv=[],
            env={"APP_CLASS": f"{__name__}._PlainVariant", "APP_Y": "hello"},
            env_prefix="APP_",
        )
        assert merged == {"class": f"{__name__}._PlainVariant", "y": "hello"}

    def test_tag_on_inheritance_dispatch_root(self, loader: ConfargLoader) -> None:
        """CLASS naming a subclass builds the subclass on an inheritance-dispatch root."""
        cfg = loader.load(
            _EnvTagBase,
            argv=[],
            env={"APP_CLASS": f"{__name__}._EnvTagSub", "APP_EXTRA": "x"},
            env_prefix="APP_",
        )
        assert cfg == _EnvTagSub(host="localhost", extra="x")

    def test_subclass_field_on_inheritance_dispatch_root(self, loader: ConfargLoader) -> None:
        """A subclass-only field merges without the unknown-field warning, as the CLI accepts it."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            merged = loader.merge(
                _EnvTagBase,
                argv=[],
                env={"APP_EXTRA": "x"},
                env_prefix="APP_",
            )
        assert merged == {"extra": "x"}
        assert not any(issubclass(w.category, confarg.exceptions.ConfargWarning) for w in caught)


# ---------------------------------------------------------------------------
# A custom mixed-case tag keeps its casing through the resolution walk
# ---------------------------------------------------------------------------


@_dc
class _EnvTagHost:
    db: _EnvTagBase


@_dc
class _EnvKindField:
    kind: str = "k"


class TestEnvCustomTagCasing:
    """A custom mixed-case union tag survives the env walk, as the CLI channel accepts it (BUG-101).

    The env channel resolves segments case-insensitively by lowercasing what does not match a
    field, so a ``union_tag`` spelled with uppercase letters never survived to be recognized:
    the segment was warned away as an unknown field and dropped, while the CLI channel's
    exact-case ``--Kind`` merged. The resolution walk is tag-aware instead: a segment that
    names no member but names the tag keeps the tag's exact spelling, and a real field still
    wins over the tag — the rule the default lowercase ``class`` tag already follows.
    """

    def test_custom_tag_merges_like_cli(self, loader: ConfargLoader) -> None:
        """The ticket's repro: KIND merges to the same dict the CLI channel's --Kind gives."""
        tag_val = f"{__name__}._EnvTagSub"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            merged = loader.merge(
                _EnvTagBase,
                argv=[],
                env={"APP_KIND": tag_val},
                env_prefix="APP_",
                union_tag="Kind",
            )
        assert merged == {"Kind": tag_val}
        assert not any(issubclass(w.category, confarg.exceptions.ConfargWarning) for w in caught)

    def test_custom_tag_builds_subclass(self, loader: ConfargLoader) -> None:
        """KIND plus a subclass field builds the named subclass, as the CLI channel does."""
        cfg = loader.load(
            _EnvTagBase,
            argv=[],
            env={"APP_KIND": f"{__name__}._EnvTagSub", "APP_EXTRA": "x"},
            env_prefix="APP_",
            union_tag="Kind",
        )
        assert cfg == _EnvTagSub(host="localhost", extra="x")

    def test_custom_tag_on_nested_field(self, loader: ConfargLoader) -> None:
        """DB__KIND keeps the tag's casing below the root, as the CLI channel's --db.Kind."""
        tag_val = f"{__name__}._EnvTagSub"
        merged = loader.merge(
            _EnvTagHost,
            argv=[],
            env={"APP_DB__KIND": tag_val, "APP_DB__EXTRA": "x"},
            env_prefix="APP_",
            union_tag="Kind",
        )
        assert merged == {"db": {"Kind": tag_val, "extra": "x"}}

    def test_field_named_like_the_tag_wins(self, loader: ConfargLoader) -> None:
        """A field whose lowercase spelling equals the tag is the field, as under the default tag."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            merged = loader.merge(
                _EnvKindField,
                argv=[],
                env={"APP_KIND": "v"},
                env_prefix="APP_",
                union_tag="Kind",
            )
        assert merged == {"kind": "v"}
        assert not any(issubclass(w.category, confarg.exceptions.ConfargWarning) for w in caught)


class TestEnvSubclassOnlyTagCollision:
    """A subclass-only field spelled exactly like the tag is the field on the env channel too.

    The env walk already resolved the segment to the tag's spelling, and the merged key
    is the same either way — the defect lived in construction, which read the key as a
    class path and stripped the value (BUG-103). The field wins instead, so the env
    variable's value builds the subclass that owns the field.
    """

    def test_tag_shaped_env_var_builds_owning_subclass(self, loader: ConfargLoader) -> None:
        """KIND=v builds the subclass owning the field, as the CLI channel's --Kind does."""
        cfg = loader.load(
            _EnvKindOnlyBase,
            argv=[],
            env={"APP_KIND": "v"},
            env_prefix="APP_",
            union_tag="Kind",
        )
        assert cfg == _EnvKindOnlySub(Kind="v")


# ---------------------------------------------------------------------------
# Deletion syntax: FIELD- and list index FIELD__N-
# ---------------------------------------------------------------------------


class TestEnvDelete:
    """Tests for the env var deletion suffix: FIELD- (dict key) and FIELD__N- (list index)."""

    def test_delete_field_resets_to_default(self, loader: ConfargLoader, tmp_toml) -> None:
        """NAME-=anything removes the name field, letting the default take over."""
        path = tmp_toml("name = 'from_config'\n")
        result = loader.load(
            WithDefaults,
            argv=[],
            env={"MYAPP_NAME-": "anything"},
            env_prefix="MYAPP_",
            files=[path],
        )
        assert result.name == "default"

    def test_delete_required_field_raises(self, loader: ConfargLoader, tmp_toml) -> None:
        """Deleting a required (no-default) field via env var causes MissingFieldError."""
        path = tmp_toml("name = 'from_config'\ncount = 5\nrate = 1.0\nverbose = false\n")
        with pytest.raises(confarg.exceptions.MissingFieldError):
            loader.load(
                Flat,
                argv=[],
                env={"MYAPP_NAME-": "anything"},
                env_prefix="MYAPP_",
                files=[path],
            )

    def test_delete_nested_field(self, loader: ConfargLoader, tmp_toml) -> None:
        """DB__HOST-=anything removes a nested field; raises MissingFieldError if required."""
        path = tmp_toml("[db]\nhost = 'myhost'\nport = 5432\nname = 'mydb'\n")
        with pytest.raises(confarg.exceptions.MissingFieldError):
            loader.load(
                AppConfig,
                argv=[],
                env={"MYAPP_DB__HOST-": "anything"},
                env_prefix="MYAPP_",
                files=[path],
            )

    def test_delete_list_index(self, loader: ConfargLoader, tmp_toml) -> None:
        """ITEMS__1-=anything removes element at original index 1."""
        WithList = make_target("items", list[str], default_factory=list)
        path = tmp_toml('items = ["a", "b", "c"]\n')
        result = loader.load(
            WithList,
            argv=[],
            env={"MYAPP_ITEMS__1-": "anything"},
            env_prefix="MYAPP_",
            files=[path],
        )
        assert result.items == ["a", "c"]

    def test_delete_indices_use_original_positions(self, loader: ConfargLoader, tmp_toml) -> None:
        """ITEMS__1- and ITEMS__2- use original indices (both removed before re-indexing)."""
        WithList = make_target("items", list[str], default_factory=list)
        path = tmp_toml('items = ["a", "b", "c", "d"]\n')
        result = loader.load(
            WithList,
            argv=[],
            env={"MYAPP_ITEMS__1-": "x", "MYAPP_ITEMS__2-": "x"},
            env_prefix="MYAPP_",
            files=[path],
        )
        assert result.items == ["a", "d"]

    def test_delete_duplicate_index_raises(self, loader: ConfargLoader, tmp_toml) -> None:
        """Two env vars deleting the same list index raises ConfargError."""
        WithList = make_target("items", list[str], default_factory=list)
        path = tmp_toml('items = ["a", "b", "c"]\n')
        with pytest.raises(confarg.exceptions.ConfargError, match=r"[Dd]uplicate"):
            loader.load(
                WithList,
                argv=[],
                env={"MYAPP_ITEMS__1-": "x", "MYAPP_items__1-": "x"},
                env_prefix="MYAPP_",
                files=[path],
            )

    def test_delete_list_index_after_whole_field_delete(self, loader: ConfargLoader, tmp_toml) -> None:
        """An index delete met after a whole-field delete replaces it, as on the CLI (BUG-77).

        Its descent read the delete sentinel as a dict.  Which of the two variables the
        mapping yields first is the open question of BUG-116.
        """
        WithList = make_target("items", list[str], default_factory=list)
        path = tmp_toml('items = ["a", "b", "c"]\n')
        result = loader.load(
            WithList,
            argv=[],
            env={"MYAPP_ITEMS-": "x", "MYAPP_ITEMS__0-": "x"},
            env_prefix="MYAPP_",
            files=[path],
        )
        assert result.items == ["b", "c"]

    def test_delete_out_of_range_raises(self, loader: ConfargLoader, tmp_toml) -> None:
        """Deleting an out-of-range list index raises ConfargError."""
        WithList = make_target("items", list[str], default_factory=list)
        path = tmp_toml('items = ["a", "b", "c"]\n')
        with pytest.raises(confarg.exceptions.ConfargError):
            loader.load(
                WithList,
                argv=[],
                env={"MYAPP_ITEMS__5-": "x"},
                env_prefix="MYAPP_",
                files=[path],
            )

    def test_negative_index_update(self, loader: ConfargLoader, tmp_toml) -> None:
        """ITEMS__-1=value updates the last element."""
        WithList = make_target("items", list[int], default_factory=list)
        path = tmp_toml("items = [1, 2, 3]\n")
        result = loader.load(
            WithList,
            argv=[],
            env={"MYAPP_ITEMS__-1": "99"},
            env_prefix="MYAPP_",
            files=[path],
        )
        assert result.items == [1, 2, 99]

    def test_negative_index_delete(self, loader: ConfargLoader, tmp_toml) -> None:
        """ITEMS__-1-=anything deletes the last element."""
        WithList = make_target("items", list[str], default_factory=list)
        path = tmp_toml('items = ["a", "b", "c"]\n')
        result = loader.load(
            WithList,
            argv=[],
            env={"MYAPP_ITEMS__-1-": "x"},
            env_prefix="MYAPP_",
            files=[path],
        )
        assert result.items == ["a", "b"]

    def test_env_delete_overrides_config(self, loader: ConfargLoader, tmp_toml) -> None:
        """Env deletion (higher priority) wins over a config-file value."""
        path = tmp_toml("name = 'from_config'\n")
        result = loader.load(
            WithDefaults,
            argv=[],
            env={"MYAPP_NAME-": "1"},
            env_prefix="MYAPP_",
            files=[path],
        )
        assert result.name == "default"


class TestEnvUnionSequenceStrict:
    """A bare env scalar does not auto-wrap into a sequence variant.

    Env (unlike the CLI) expresses lists explicitly via indexed segments or JSON,
    so a lone scalar that no scalar variant accepts is an error, not ``[scalar]``.
    This is the deliberate counterpart to the CLI single-token fallback.
    """

    def test_bare_scalar_no_list_fallback_raises(self, loader: ConfargLoader) -> None:
        """INPUT=hello for bool | list[str]: bool rejects it and env does not wrap to ['hello']."""
        WithUnion = make_target("input", bool | list[str], default=True)
        with pytest.raises(confarg.exceptions.TypeCoercionError):
            loader.load(WithUnion, argv=[], env={"MYAPP_INPUT": "hello"}, env_prefix="MYAPP_")

    def test_indexed_builds_singleton_list(self, loader: ConfargLoader) -> None:
        """INPUT__0=hello is the explicit way to get ['hello'] from env."""
        WithUnion = make_target("input", bool | list[str], default=True)
        result = loader.load(WithUnion, argv=[], env={"MYAPP_INPUT__0": "hello"}, env_prefix="MYAPP_")
        assert result.input == ["hello"]

    def test_json_builds_list(self, loader: ConfargLoader) -> None:
        """A JSON-array env value builds ['hello'] from env."""
        WithUnion = make_target("input", bool | list[str], default=True)
        result = loader.load(WithUnion, argv=[], env={"MYAPP_INPUT": '["hello"]'}, env_prefix="MYAPP_")
        assert result.input == ["hello"]

    def test_bare_scalar_still_matches_scalar_variant(self, loader: ConfargLoader) -> None:
        """INPUT=true still coerces to the bool variant."""
        WithUnion = make_target("input", bool | list[str], default=False)
        result = loader.load(WithUnion, argv=[], env={"MYAPP_INPUT": "true"}, env_prefix="MYAPP_")
        assert result.input is True


class TestEnvScalarThenSubkey:
    """A scalar env var followed by a deeper one for the same field resolves, never crashes.

    The two orders disagree by design — the later variable wins — but neither escapes a
    bare ``TypeError`` out of the merge core.
    """

    def test_struct_field_scalar_then_subkey(self, loader: ConfargLoader) -> None:
        """A dataclass field has no scalar shorthand: the subkey opens the scalar away."""
        result = loader.merge(
            AppConfig,
            argv=[],
            env={"APP_DB": "oops", "APP_DB__HOST": "db1"},
            env_prefix="APP_",
        )
        assert result == {"db": {"host": "db1"}}

    def test_struct_field_subkey_then_scalar(self, loader: ConfargLoader) -> None:
        """The reverse order is unchanged: the whole value wins, as it always has."""
        result = loader.merge(
            AppConfig,
            argv=[],
            env={"APP_DB__HOST": "db1", "APP_DB": "oops"},
            env_prefix="APP_",
        )
        assert result == {"db": "oops"}


# ---------------------------------------------------------------------------
# A field named exactly like the union tag is a field, on env too (BUG-102)
# ---------------------------------------------------------------------------


@_dc
class _EnvExactKindField:
    Kind: str = "field"


class TestEnvExactTagFieldCollision:
    """A field whose exact spelling equals union_tag builds from the environment.

    The env resolution walk already settles the collision on the field (BUG-101),
    but construction read the merged key back as the tag and tried to import the
    value as a class path. The field wins there too now, so the channel that
    resolves the collision must also be the channel whose value survives.
    """

    def test_exact_collision_field_builds(self, loader: ConfargLoader) -> None:
        """KIND sets the field, with no class-path import attempted."""
        cfg = loader.load(
            _EnvExactKindField,
            argv=[],
            env={"APP_KIND": "v"},
            env_prefix="APP_",
            union_tag="Kind",
        )
        assert cfg == _EnvExactKindField(Kind="v")


# ---------------------------------------------------------------------------
# The env channel spells a segment, the canonical walk types the path (REF-73)
# ---------------------------------------------------------------------------


@_dc
class _EnvLowerKindBase:
    pass


@_dc
class _EnvLowerKindSub(_EnvLowerKindBase):
    kind: str = "f"


class _EnvPt(NamedTuple):
    x: int
    y: int


@_dc
class _EnvHostA:
    Host: int = 0


@_dc
class _EnvDbA:
    Host: int = 0


@_dc
class _EnvDbB:
    Host: str = ""


@_dc
class _EnvVariantA:
    db: _EnvDbA = field(default_factory=_EnvDbA)


@_dc
class _EnvVariantB:
    db: _EnvDbB = field(default_factory=_EnvDbB)


@_dc
class _EnvWalked:
    pt: _EnvPt = field(default_factory=lambda: _EnvPt(0, 0))
    pair: tuple[int, int] = (0, 0)
    u: _EnvHostA | dict[str, int] = field(default_factory=_EnvHostA)
    v: _EnvVariantA | _EnvVariantB = field(default_factory=_EnvVariantA)
    sub: _EnvLowerKindBase = field(default_factory=_EnvLowerKindBase)


@_dc
class _EnvLowerHost:
    host: str = ""


@_dc
class _EnvUpperHost:
    Host: str = ""


@_dc
class _EnvCaseHolder:
    db: _EnvLowerHost | _EnvUpperHost = field(default_factory=_EnvLowerHost)


@_dc
class _EnvHostBase:
    host: str = ""


@_dc
class _EnvHostSub(_EnvHostBase):
    Host: str = ""


_HOST_AMBIGUOUS = r"Ambiguous env var segment 'HOST'.*\['Host', 'host'\]"


class TestEnvSpellsWhatTheWalkReaches:
    """An env variable merges what the CLI flag of the same path merges.

    The env channel's own rule is case-insensitivity: a segment takes the exact spelling of
    the member it names, and the path is then typed by the CLI channel's walk. A second walk
    kept beside it lagged every rule the canonical one gained: it dropped a namedtuple's
    negative index, skipped the non-struct variants of a union, lowercased a field below
    variants that disagree, and could not see a subclass-only field (REF-73, BUG-104).
    """

    @pytest.mark.parametrize(
        ("flag", "var"),
        [
            pytest.param("pt.y", "PT__Y", id="namedtuple-field"),
            pytest.param("pt.1", "PT__1", id="namedtuple-index"),
            pytest.param("pt.-1", "PT__-1", id="namedtuple-negative-index"),
            pytest.param("pair.1", "PAIR__1", id="tuple-index"),
            pytest.param("u.Host", "U__HOST", id="union-struct-variant"),
            pytest.param("u.foo", "U__FOO", id="union-dict-variant"),
            pytest.param("v.db.Host", "V__DB__HOST", id="below-disagreeing-variants"),
            pytest.param("sub.kind", "SUB__KIND", id="subclass-only-field"),
        ],
    )
    def test_env_merges_what_the_flag_merges(self, loader: ConfargLoader, flag: str, var: str) -> None:
        """The variable and the flag spelling the same path merge the same dict."""
        from_cli = loader.merge(_EnvWalked, argv=[f"--{flag}", "5"], env={})
        from_env = loader.merge(_EnvWalked, argv=[], env={f"APP_{var}": "5"}, env_prefix="APP_")
        assert from_env == from_cli

    def test_odd_namedtuple_index_is_not_respelled(self, loader: ConfargLoader) -> None:
        """PT__01 keeps its spelling, which the walk refuses, rather than becoming index 1."""
        merged = loader.merge(_EnvWalked, argv=[], env={"APP_PT__01": "5"}, env_prefix="APP_")
        assert merged == {"pt": {"01": "5"}}

    def test_subclass_only_field_wins_over_case_differing_tag(self, loader: ConfargLoader) -> None:
        """BUG-104's repro: KIND is the subclass-only field `kind`, not the tag `Kind`."""
        from_cli = loader.merge(_EnvLowerKindBase, argv=["--kind", "v"], env={}, union_tag="Kind")
        from_env = loader.merge(_EnvLowerKindBase, argv=[], env={"APP_KIND": "v"}, env_prefix="APP_", union_tag="Kind")
        assert from_cli == {"kind": "v"}
        assert from_env == from_cli

    def test_spellings_differing_by_case_across_variants_are_ambiguous(self) -> None:
        """A segment two variants spell differently cannot pick one of them."""
        with pytest.raises(
            confarg.exceptions.ConfargError,
            match=_HOST_AMBIGUOUS,
        ):
            confarg.merge(_EnvCaseHolder, argv=[], env={"APP_DB__HOST": "x"}, env_prefix="APP_")

    def test_declared_and_subclass_only_spellings_differing_by_case_are_ambiguous(self) -> None:
        """A subclass-only field is a member, so it collides with a declared one as a variant's would."""
        with pytest.raises(
            confarg.exceptions.ConfargError,
            match=_HOST_AMBIGUOUS,
        ):
            confarg.merge(_EnvHostBase, argv=[], env={"APP_HOST": "x"}, env_prefix="APP_")
