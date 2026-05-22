# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for leaf type parsing: int, float, bool, str, None, Enum, Path, Literal, Annotated, type aliases."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Annotated, Literal, Optional

import pytest

import confarg
from tests.conftest import (
    AliasInt,
    CacheConfig,
    Color,
    DbConfig,
    Flat,
    IntColor,
    WithAliasAnnotated,
    WithAliasDc,
    WithAliasUnion,
    WithDefaults,
    WithHostPort,
    make_target,
)

# ---------------------------------------------------------------------------
# int
# ---------------------------------------------------------------------------


class TestInt:
    """Integer leaf type parsing."""

    @pytest.mark.parametrize(
        ("cli_val", "expected"),
        [("42", 42), ("-7", -7), ("0", 0)],
        ids=["positive", "negative", "zero"],
    )
    def test_int_from_cli(self, cli_val: str, expected: int) -> None:
        """Parse integers from CLI args."""
        result = confarg.load(
            Flat,
            args=["--name", "x", "--count", cli_val, "--rate", "1.0", "--verbose", "true"],
            env={},
        )
        assert result.count == expected

    def test_int_from_env(self) -> None:
        """Parse an integer from an env var."""
        result = confarg.load(
            Flat,
            args=["--name", "x", "--rate", "1.0", "--verbose", "true"],
            env={"COUNT": "99"},
            env_prefix="",
        )
        assert result.count == 99


# ---------------------------------------------------------------------------
# float
# ---------------------------------------------------------------------------


class TestFloat:
    """Float leaf type parsing."""

    @pytest.mark.parametrize(
        ("cli_val", "expected"),
        [
            ("3.14", 3.14),
            ("-0.5", -0.5),
            ("1e-3", pytest.approx(0.001)),
        ],
        ids=["positive", "negative", "scientific"],
    )
    def test_float_from_cli(self, cli_val: str, expected) -> None:
        """Parse float values from CLI args."""
        result = confarg.load(
            Flat,
            args=["--name", "x", "--count", "1", "--rate", cli_val, "--verbose", "true"],
            env={},
        )
        assert result.rate == expected

    def test_float_from_env(self) -> None:
        """Parse a float from an env var."""
        result = confarg.load(
            Flat,
            args=["--name", "x", "--count", "1", "--verbose", "true"],
            env={"RATE": "2.718"},
            env_prefix="",
        )
        assert result.rate == pytest.approx(2.718)

    # -- nan / inf from CLI ---------------------------------------------------

    @pytest.mark.parametrize(
        ("cli_val", "check"),
        [
            ("nan", math.isnan),
            ("NaN", math.isnan),
            ("NAN", math.isnan),
            ("Nan", math.isnan),
            ("inf", lambda r: math.isinf(r) and r > 0),
            ("Inf", lambda r: math.isinf(r) and r > 0),
            ("INF", lambda r: math.isinf(r) and r > 0),
            ("Infinity", lambda r: math.isinf(r) and r > 0),
            ("INFINITY", lambda r: math.isinf(r) and r > 0),
            ("-inf", lambda r: math.isinf(r) and r < 0),
        ],
        ids=["nan", "NaN", "NAN", "Nan", "inf", "Inf", "INF", "Infinity", "INFINITY", "-inf"],
    )
    def test_float_special_from_cli(self, cli_val: str, check) -> None:
        """Parse nan/inf variants from CLI args (case-insensitive)."""
        result = confarg.load(
            Flat,
            args=["--name", "x", "--count", "1", "--rate", cli_val, "--verbose", "true"],
            env={},
        )
        assert check(result.rate)

    # -- nan / inf from env ---------------------------------------------------

    @pytest.mark.parametrize(
        ("env_val", "check"),
        [
            ("nan", math.isnan),
            ("inf", lambda r: math.isinf(r) and r > 0),
            ("-inf", lambda r: math.isinf(r) and r < 0),
        ],
        ids=["nan", "inf", "-inf"],
    )
    def test_float_special_from_env(self, env_val: str, check) -> None:
        """Parse nan/inf from env vars."""
        result = confarg.load(
            Flat,
            args=["--name", "x", "--count", "1", "--verbose", "true"],
            env={"RATE": env_val},
            env_prefix="",
        )
        assert check(result.rate)

    # -- nan / inf from config files ------------------------------------------

    @pytest.mark.parametrize(
        ("toml_content", "check"),
        [
            ("rate = nan\n", math.isnan),
            ("rate = inf\n", lambda r: math.isinf(r) and r > 0),
            ("rate = -inf\n", lambda r: math.isinf(r) and r < 0),
        ],
        ids=["nan", "inf", "-inf"],
    )
    def test_float_special_from_toml(self, tmp_toml, toml_content: str, check) -> None:
        """Parse nan/inf from TOML config files."""
        path = tmp_toml(toml_content)
        result = confarg.load(WithDefaults, args=[], env={}, files=[path])
        assert check(result.rate)

    @pytest.mark.parametrize(
        ("yaml_content", "check"),
        [
            ("rate: .nan\n", math.isnan),
            ("rate: .inf\n", lambda r: math.isinf(r) and r > 0),
            ("rate: -.inf\n", lambda r: math.isinf(r) and r < 0),
        ],
        ids=["nan", "inf", "-inf"],
    )
    def test_float_special_from_yaml(self, tmp_yaml, yaml_content: str, check) -> None:
        """Parse nan/inf from YAML config files."""
        path = tmp_yaml(yaml_content)
        result = confarg.load(WithDefaults, args=[], env={}, files=[path])
        assert check(result.rate)


# ---------------------------------------------------------------------------
# bool
# ---------------------------------------------------------------------------


class TestBool:
    """Boolean leaf type parsing."""

    def test_bool_flag_true(self) -> None:
        """--verbose true sets bool to True."""
        result = confarg.load(Flat, args=["--name", "x", "--count", "0", "--rate", "0", "--verbose", "true"], env={})
        assert result.verbose is True

    def test_bool_flag_false(self) -> None:
        """--verbose false sets bool to False."""
        result = confarg.load(Flat, args=["--name", "x", "--count", "0", "--rate", "0", "--verbose", "false"], env={})
        assert result.verbose is False

    @pytest.mark.parametrize(
        ("env_val", "expected"),
        [("true", True), ("false", False)],
        ids=["true", "false"],
    )
    def test_bool_from_env(self, env_val: str, expected: bool) -> None:  # noqa: FBT001
        """Truthy/falsy env var strings set bool correctly."""
        result = confarg.load(WithDefaults, args=[], env={"VERBOSE": env_val}, env_prefix="")
        assert result.verbose is expected


# ---------------------------------------------------------------------------
# str
# ---------------------------------------------------------------------------


class TestStr:
    """String leaf type parsing."""

    def test_str_from_cli(self) -> None:
        """Parse a string from a CLI arg."""
        result = confarg.load(
            Flat,
            args=["--name", "hello", "--count", "0", "--rate", "0", "--verbose", "true"],
            env={},
        )
        assert result.name == "hello"

    def test_str_empty_from_cli(self) -> None:
        """Parse an empty string from a CLI arg."""
        result = confarg.load(Flat, args=["--name", "", "--count", "0", "--rate", "0", "--verbose", "true"], env={})
        assert result.name == ""

    def test_str_from_env(self) -> None:
        """Parse a string from an env var."""
        result = confarg.load(WithDefaults, args=[], env={"NAME": "world"}, env_prefix="")
        assert result.name == "world"


# ---------------------------------------------------------------------------
# None type
# ---------------------------------------------------------------------------


WithNone = make_target("nothing", type(None), default=None)


class TestNoneType:
    """None type parsing — bare CLI flags and empty env vars produce None."""

    def test_none_field_default(self) -> None:
        """A field typed as None keeps its default."""
        result = confarg.load(WithNone, args=[], env={})
        assert result.nothing is None

    def test_none_bare_flag_cli(self) -> None:
        """--nothing none sets a None-typed field to None."""
        result = confarg.load(WithNone, args=["--nothing", "none"], env={})
        assert result.nothing is None

    def test_none_empty_env(self) -> None:
        """An empty env var (NOTHING=) sets a None-typed field to None."""
        result = confarg.load(WithNone, args=[], env={"NOTHING": ""}, env_prefix="")
        assert result.nothing is None

    @pytest.mark.parametrize(
        "target_cls",
        [
            make_target("value", Optional[int], default=None),
            make_target("value", int | None, default=None),
        ],
        ids=["Optional[int]", "int | None"],
    )
    def test_optional_unset_via_none_sentinel_cli(self, tmp_toml, target_cls) -> None:
        """--value none overrides a config-file value back to None."""
        path = tmp_toml("value = 42\n")
        result = confarg.load(target_cls, args=["--value", "none"], env={}, files=[path])
        assert result.value is None

    @pytest.mark.parametrize(
        "target_cls",
        [
            make_target("value", Optional[int], default=None),
            make_target("value", int | None, default=None),
        ],
        ids=["Optional[int]", "int | None"],
    )
    def test_optional_unset_via_empty_env(self, tmp_toml, target_cls) -> None:
        """Empty env VALUE= raises for int|None — use VALUE__NONE= to set None."""
        path = tmp_toml("value = 42\n")
        with pytest.raises(confarg.exceptions.TypeCoercionError, match="To set this field to None"):
            confarg.load(target_cls, args=[], env={"VALUE": ""}, env_prefix="", files=[path])

    def test_optional_str_none_sentinel_cli(self) -> None:
        """--value none sets str | None field to Python None (steal rule)."""
        WithOptionalStr = make_target("value", str | None, default=None)
        result = confarg.load(WithOptionalStr, args=["--value", "none"], env={})
        assert result.value is None

    def test_optional_str_none_string_is_literal(self) -> None:
        """--value.str none for str | None keeps the string 'none' via the .str escape."""
        WithOptionalStr = make_target("value", str | None, default=None)
        result = confarg.load(WithOptionalStr, args=["--value.str", "none"], env={})
        assert result.value == "none"

    def test_optional_str_empty_env_is_empty_string(self) -> None:
        """VALUE= for str | None gives empty string, not None."""
        WithOptionalStr = make_target("value", str | None, default=None)
        result = confarg.load(WithOptionalStr, args=[], env={"VALUE": ""}, env_prefix="")
        assert result.value == ""

    def test_none_string_is_literal_for_non_optional(self) -> None:
        """'none' for a non-optional int field is just a bad int, raises TypeCoercionError."""
        with pytest.raises(confarg.exceptions.ConfargError):
            confarg.load(WithDefaults, args=["--count", "none"], env={})


# ---------------------------------------------------------------------------
# Enum
# ---------------------------------------------------------------------------


class TestEnum:
    """Enum leaf type parsing."""

    def test_enum_from_cli_by_value(self) -> None:
        """Parse an enum from its value via CLI."""
        WithEnum = make_target("color", Color, default=Color.RED)
        result = confarg.load(WithEnum, args=["--color", "green"], env={})
        assert result.color is Color.GREEN

    def test_enum_from_env_by_value(self) -> None:
        """Parse an enum from its value via env var."""
        WithEnum = make_target("color", Color, default=Color.RED)
        result = confarg.load(WithEnum, args=[], env={"COLOR": "blue"}, env_prefix="")
        assert result.color is Color.BLUE

    def test_enum_default(self) -> None:
        """Enum keeps its default when not provided."""
        WithEnum = make_target("color", Color, default=Color.RED)
        result = confarg.load(WithEnum, args=[], env={})
        assert result.color is Color.RED

    def test_int_enum_from_cli(self) -> None:
        """Parse an IntEnum from its value via CLI."""
        WithIntEnum = make_target("color", IntColor, default=IntColor.RED)
        result = confarg.load(WithIntEnum, args=["--color", "2"], env={})
        assert result.color is IntColor.GREEN


# ---------------------------------------------------------------------------
# Path
# ---------------------------------------------------------------------------


class TestPath:
    """Path leaf type parsing."""

    def test_path_from_cli(self) -> None:
        """Parse a Path from a CLI arg."""
        WithPath = make_target("location", Path, default=Path())
        result = confarg.load(WithPath, args=["--location", "/tmp/foo"], env={})
        assert result.location == Path("/tmp/foo")

    def test_path_from_env(self) -> None:
        """Parse a Path from an env var."""
        WithPath = make_target("location", Path, default=Path())
        result = confarg.load(WithPath, args=[], env={"LOCATION": "/var/log"}, env_prefix="")
        assert result.location == Path("/var/log")


# ---------------------------------------------------------------------------
# Literal
# ---------------------------------------------------------------------------


class TestLiteral:
    """Literal type parsing."""

    def test_literal_valid_value(self) -> None:
        """Parse a valid Literal value from CLI."""
        WithLiteral = make_target("mode", Literal["fast", "slow"], default="fast")
        result = confarg.load(WithLiteral, args=["--mode", "slow"], env={})
        assert result.mode == "slow"

    def test_literal_default(self) -> None:
        """Literal keeps its default when not provided."""
        WithLiteral = make_target("mode", Literal["fast", "slow"], default="fast")
        result = confarg.load(WithLiteral, args=[], env={})
        assert result.mode == "fast"

    def test_literal_invalid_raises(self) -> None:
        """Providing an invalid Literal value raises an error."""
        WithLiteral = make_target("mode", Literal["fast", "slow"], default="fast")
        with pytest.raises(confarg.exceptions.ConfargError):
            confarg.load(WithLiteral, args=["--mode", "turbo"], env={})


# ---------------------------------------------------------------------------
# Annotated
# ---------------------------------------------------------------------------


class TestAnnotated:
    """Annotated type parsing (metadata ignored)."""

    def test_annotated_int(self) -> None:
        """Annotated[int, ...] parses as plain int."""
        WithAnnotated = make_target("value", Annotated[int, "some metadata"], default=0)
        result = confarg.load(WithAnnotated, args=["--value", "42"], env={})
        assert result.value == 42

    def test_annotated_default(self) -> None:
        """Annotated field keeps its default."""
        WithAnnotated = make_target("value", Annotated[int, "some metadata"], default=0)
        result = confarg.load(WithAnnotated, args=[], env={})
        assert result.value == 0


# ---------------------------------------------------------------------------
# Type alias (3.12+)
# ---------------------------------------------------------------------------


class TestTypeAlias:
    """Python 3.12+ type alias support (``type HostPort = tuple[str, int]``)."""

    def test_type_alias_default(self) -> None:
        """Field using a type alias keeps its default."""
        result = confarg.load(WithHostPort, args=[], env={})
        assert result.endpoint == ("localhost", 80)

    def test_type_alias_from_cli(self) -> None:
        """Field using a type alias is parsed from CLI args."""
        result = confarg.load(WithHostPort, args=["--endpoint", "myhost", "9090"], env={})
        assert result.endpoint == ("myhost", 9090)

    def test_type_alias_from_env(self) -> None:
        """Field using a type alias is parsed from indexed env vars."""
        result = confarg.load(
            WithHostPort,
            args=[],
            env={"ENDPOINT__0": "envhost", "ENDPOINT__1": "443"},
            env_prefix="",
        )
        assert result.endpoint == ("envhost", 443)


class TestTypeAlias312:
    """Python 3.12 ``type X = ...`` alias shapes: scalar, dataclass, union, annotated."""

    # ------------------------------------------------------------------
    # type Alias = int  (scalar alias)
    # ------------------------------------------------------------------

    def test_scalar_alias_from_cli(self) -> None:
        """Type Alias = int — field parsed from CLI."""
        target = make_target("value", AliasInt)
        result = confarg.load(target, args=["--value", "42"], env={})
        assert result.value == 42

    def test_scalar_alias_from_env(self) -> None:
        """Type Alias = int — field parsed from env var."""
        target = make_target("value", AliasInt)
        result = confarg.load(target, args=[], env={"VALUE": "99"}, env_prefix="")
        assert result.value == 99

    def test_scalar_alias_default(self) -> None:
        """Type Alias = int — default value is preserved."""
        target = make_target("value", AliasInt, default=7)
        result = confarg.load(target, args=[], env={})
        assert result.value == 7

    # ------------------------------------------------------------------
    # type Alias = MyDataClass  (dataclass alias)
    # ------------------------------------------------------------------

    def test_dc_alias_from_cli(self) -> None:
        """Type Alias = DbConfig — nested fields parsed from CLI."""
        result = confarg.load(
            WithAliasDc,
            args=["--db.host", "localhost", "--db.port", "5432", "--db.name", "mydb"],
            env={},
        )
        assert result.db == DbConfig(host="localhost", port=5432, name="mydb")

    def test_dc_alias_from_env(self) -> None:
        """Type Alias = DbConfig — nested fields parsed from env vars."""
        result = confarg.load(
            WithAliasDc,
            args=[],
            env={"DB__HOST": "envhost", "DB__PORT": "3306", "DB__NAME": "envdb"},
            env_prefix="",
        )
        assert result.db == DbConfig(host="envhost", port=3306, name="envdb")

    # ------------------------------------------------------------------
    # type Alias = DC1 | DC2  (union alias)
    # ------------------------------------------------------------------

    def test_union_alias_first_variant_from_cli(self) -> None:
        """Type Alias = DbConfig | CacheConfig — first variant resolved from CLI."""
        result = confarg.load(
            WithAliasUnion,
            args=["--service.host", "db.local", "--service.port", "5432", "--service.name", "prod"],
            env={},
        )
        assert result.service == DbConfig(host="db.local", port=5432, name="prod")

    def test_union_alias_second_variant_from_cli(self) -> None:
        """Type Alias = DbConfig | CacheConfig — second variant resolved from CLI."""
        result = confarg.load(
            WithAliasUnion,
            args=["--service.enabled", "true", "--service.ttl", "600"],
            env={},
        )
        assert result.service == CacheConfig(enabled=True, ttl=600)

    def test_union_alias_first_variant_from_env(self) -> None:
        """Type Alias = DbConfig | CacheConfig — first variant resolved from env vars."""
        result = confarg.load(
            WithAliasUnion,
            args=[],
            env={"SERVICE__HOST": "db.local", "SERVICE__PORT": "5432", "SERVICE__NAME": "prod"},
            env_prefix="",
        )
        assert result.service == DbConfig(host="db.local", port=5432, name="prod")

    # ------------------------------------------------------------------
    # type Alias = Annotated[DC1 | DC2, metadata]  (annotated alias)
    # ------------------------------------------------------------------

    def test_annotated_alias_first_variant_from_cli(self) -> None:
        """Type Alias = Annotated[DC1 | DC2, meta] — Annotated wrapper stripped, first variant resolved."""
        result = confarg.load(
            WithAliasAnnotated,
            args=["--service.host", "db.local", "--service.port", "5432", "--service.name", "prod"],
            env={},
        )
        assert result.service == DbConfig(host="db.local", port=5432, name="prod")

    def test_annotated_alias_second_variant_from_cli(self) -> None:
        """Type Alias = Annotated[DC1 | DC2, meta] — second variant resolved."""
        result = confarg.load(
            WithAliasAnnotated,
            args=["--service.enabled", "true", "--service.ttl", "600"],
            env={},
        )
        assert result.service == CacheConfig(enabled=True, ttl=600)

    def test_annotated_alias_matches_unannotated_alias(self) -> None:
        """Annotated alias produces same result as plain union alias."""
        union_result = confarg.load(
            WithAliasUnion,
            args=["--service.enabled", "true", "--service.ttl", "300"],
            env={},
        )
        annotated_result = confarg.load(
            WithAliasAnnotated,
            args=["--service.enabled", "true", "--service.ttl", "300"],
            env={},
        )
        assert union_result.service == annotated_result.service
