# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for leaf type parsing: int, float, bool, str, None, Enum, Path, Literal, Annotated, type aliases."""

from __future__ import annotations

import enum
import math
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal, Optional

if TYPE_CHECKING:
    from tests._loaders import ConfargLoader

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
        [
            ("42", 42),
            ("-7", -7),
            ("0", 0),
            ("0x1F", 31),
            ("0o37", 31),
            ("0b11111", 31),
        ],
        ids=["positive", "negative", "zero", "hex", "octal", "binary"],
    )
    def test_int_from_cli(self, loader: ConfargLoader, cli_val: str, expected: int) -> None:
        """Parse integers from CLI args, including hex, octal, and binary literals."""
        result = loader.load(
            Flat,
            argv=["--name", "x", "--count", cli_val, "--rate", "1.0", "--verbose", "true"],
            env={},
        )
        assert result.count == expected

    @pytest.mark.parametrize(
        "cli_val",
        ["042", "-042"],
        ids=["leading-zero-positive", "leading-zero-negative"],
    )
    def test_int_leading_zero_raises_cli(self, loader: ConfargLoader, cli_val: str) -> None:
        """Non-zero decimal integers with a leading zero raise an error from CLI."""
        with pytest.raises(confarg.exceptions.TypeCoercionError):
            loader.load(
                Flat,
                argv=["--name", "x", "--count", cli_val, "--rate", "1.0", "--verbose", "true"],
                env={},
            )

    @pytest.mark.parametrize(
        ("env_val", "expected"),
        [("99", 99), ("0x1F", 31), ("0o37", 31)],
        ids=["decimal", "hex", "octal"],
    )
    def test_int_from_env(self, loader: ConfargLoader, env_val: str, expected: int) -> None:
        """Parse integers from env vars, including hex and octal."""
        result = loader.load(
            Flat,
            argv=["--name", "x", "--rate", "1.0", "--verbose", "true"],
            env={"COUNT": env_val},
            env_prefix="",
        )
        assert result.count == expected


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
    def test_float_from_cli(self, loader: ConfargLoader, cli_val: str, expected) -> None:
        """Parse float values from CLI args."""
        result = loader.load(
            Flat,
            argv=["--name", "x", "--count", "1", "--rate", cli_val, "--verbose", "true"],
            env={},
        )
        assert result.rate == expected

    def test_float_from_env(self, loader: ConfargLoader) -> None:
        """Parse a float from an env var."""
        result = loader.load(
            Flat,
            argv=["--name", "x", "--count", "1", "--verbose", "true"],
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
        """Parse nan/inf variants from CLI args — vanilla only.

        Some values (e.g. ``-inf``) are misinterpreted by argparse as flags
        rather than argument values, so this test uses the vanilla loader only.
        """
        result = confarg.load(
            Flat,
            argv=["--name", "x", "--count", "1", "--rate", cli_val, "--verbose", "true"],
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
    def test_float_special_from_env(self, loader: ConfargLoader, env_val: str, check) -> None:
        """Parse nan/inf from env vars."""
        result = loader.load(
            Flat,
            argv=["--name", "x", "--count", "1", "--verbose", "true"],
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
    def test_float_special_from_toml(self, loader: ConfargLoader, tmp_toml, toml_content: str, check) -> None:
        """Parse nan/inf from TOML config files."""
        path = tmp_toml(toml_content)
        result = loader.load(WithDefaults, argv=[], env={}, files=[path])
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
    def test_float_special_from_yaml(self, loader: ConfargLoader, tmp_yaml, yaml_content: str, check) -> None:
        """Parse nan/inf from YAML config files."""
        path = tmp_yaml(yaml_content)
        result = loader.load(WithDefaults, argv=[], env={}, files=[path])
        assert check(result.rate)


# ---------------------------------------------------------------------------
# bool
# ---------------------------------------------------------------------------


class TestBool:
    """Boolean leaf type parsing."""

    def test_bool_flag_true(self, loader: ConfargLoader) -> None:
        """--verbose true sets bool to True."""
        result = loader.load(Flat, argv=["--name", "x", "--count", "0", "--rate", "0", "--verbose", "true"], env={})
        assert result.verbose is True

    def test_bool_flag_false(self, loader: ConfargLoader) -> None:
        """--verbose false sets bool to False."""
        result = loader.load(Flat, argv=["--name", "x", "--count", "0", "--rate", "0", "--verbose", "false"], env={})
        assert result.verbose is False

    @pytest.mark.parametrize(
        ("env_val", "expected"),
        [("true", True), ("false", False)],
        ids=["true", "false"],
    )
    def test_bool_from_env(self, loader: ConfargLoader, env_val: str, expected: bool) -> None:  # noqa: FBT001
        """Truthy/falsy env var strings set bool correctly."""
        result = loader.load(WithDefaults, argv=[], env={"VERBOSE": env_val}, env_prefix="")
        assert result.verbose is expected


# ---------------------------------------------------------------------------
# str
# ---------------------------------------------------------------------------


class TestStr:
    """String leaf type parsing."""

    def test_str_from_cli(self, loader: ConfargLoader) -> None:
        """Parse a string from a CLI arg."""
        result = loader.load(
            Flat,
            argv=["--name", "hello", "--count", "0", "--rate", "0", "--verbose", "true"],
            env={},
        )
        assert result.name == "hello"

    def test_str_empty_from_cli(self, loader: ConfargLoader) -> None:
        """Parse an empty string from a CLI arg."""
        result = loader.load(Flat, argv=["--name", "", "--count", "0", "--rate", "0", "--verbose", "true"], env={})
        assert result.name == ""

    def test_str_from_env(self, loader: ConfargLoader) -> None:
        """Parse a string from an env var."""
        result = loader.load(WithDefaults, argv=[], env={"NAME": "world"}, env_prefix="")
        assert result.name == "world"


# ---------------------------------------------------------------------------
# None type
# ---------------------------------------------------------------------------


WithNone = make_target("nothing", type(None), default=None)


class TestNoneType:
    """None type parsing — bare CLI flags and empty env vars produce None."""

    def test_none_field_default(self, loader: ConfargLoader) -> None:
        """A field typed as None keeps its default."""
        result = loader.load(WithNone, argv=[], env={})
        assert result.nothing is None

    def test_none_bare_flag_cli(self, loader: ConfargLoader) -> None:
        """--nothing none sets a None-typed field to None."""
        result = loader.load(WithNone, argv=["--nothing", "none"], env={})
        assert result.nothing is None

    def test_none_empty_env(self, loader: ConfargLoader) -> None:
        """An empty env var (NOTHING=) sets a None-typed field to None."""
        result = loader.load(WithNone, argv=[], env={"NOTHING": ""}, env_prefix="")
        assert result.nothing is None

    @pytest.mark.parametrize(
        "target_cls",
        [
            make_target("value", Optional[int], default=None),
            make_target("value", int | None, default=None),
        ],
        ids=["Optional[int]", "int | None"],
    )
    def test_optional_unset_via_none_sentinel_cli(self, loader: ConfargLoader, tmp_toml, target_cls) -> None:
        """--value none overrides a config-file value back to None."""
        path = tmp_toml("value = 42\n")
        result = loader.load(target_cls, argv=["--value", "none"], env={}, files=[path])
        assert result.value is None

    @pytest.mark.parametrize(
        "target_cls",
        [
            make_target("value", Optional[int], default=None),
            make_target("value", int | None, default=None),
        ],
        ids=["Optional[int]", "int | None"],
    )
    def test_optional_unset_via_empty_env(self, loader: ConfargLoader, tmp_toml, target_cls) -> None:
        """Empty env VALUE= raises for int|None — use VALUE__NONE= to set None."""
        path = tmp_toml("value = 42\n")
        with pytest.raises(confarg.exceptions.TypeCoercionError, match="To set this field to None"):
            loader.load(target_cls, argv=[], env={"VALUE": ""}, env_prefix="", files=[path])

    def test_optional_str_none_sentinel_cli(self, loader: ConfargLoader) -> None:
        """--value none sets str | None field to Python None (steal rule)."""
        WithOptionalStr = make_target("value", str | None, default=None)
        result = loader.load(WithOptionalStr, argv=["--value", "none"], env={})
        assert result.value is None

    def test_optional_str_none_string_is_literal(self) -> None:
        """--value.str none for str | None keeps the string 'none' — vanilla only.

        The ``.str`` escape flag is specific to the vanilla CLI parser and is not
        registered by the CLI integrations.
        """
        WithOptionalStr = make_target("value", str | None, default=None)
        result = confarg.load(WithOptionalStr, argv=["--value.str", "none"], env={})
        assert result.value == "none"

    def test_optional_str_empty_env_is_empty_string(self, loader: ConfargLoader) -> None:
        """VALUE= for str | None gives empty string, not None."""
        WithOptionalStr = make_target("value", str | None, default=None)
        result = loader.load(WithOptionalStr, argv=[], env={"VALUE": ""}, env_prefix="")
        assert result.value == ""

    def test_none_string_is_literal_for_non_optional(self) -> None:
        """'none' for a non-optional int field raises an error — vanilla only.

        CLI integrations treat the value as a string and raise TypeCoercionError
        the same way, but the exception path differs for some frameworks at parse
        time, so this is tested with the vanilla loader only.
        """
        with pytest.raises(confarg.exceptions.ConfargError):
            confarg.load(WithDefaults, argv=["--count", "none"], env={})


# ---------------------------------------------------------------------------
# Enum
# ---------------------------------------------------------------------------


class TestEnum:
    """Enum leaf type parsing."""

    def test_enum_from_cli_by_value(self) -> None:
        """Parse an enum from its value via CLI."""
        WithEnum = make_target("color", Color, default=Color.RED)
        result = confarg.load(WithEnum, argv=["--color", "green"], env={})
        assert result.color is Color.GREEN

    def test_enum_from_env_by_value(self) -> None:
        """Parse an enum from its value via env var."""
        WithEnum = make_target("color", Color, default=Color.RED)
        result = confarg.load(WithEnum, argv=[], env={"COLOR": "blue"}, env_prefix="")
        assert result.color is Color.BLUE

    def test_enum_default(self) -> None:
        """Enum keeps its default when not provided."""
        WithEnum = make_target("color", Color, default=Color.RED)
        result = confarg.load(WithEnum, argv=[], env={})
        assert result.color is Color.RED

    def test_int_enum_from_cli(self) -> None:
        """Parse an IntEnum from its value via CLI."""
        WithIntEnum = make_target("color", IntColor, default=IntColor.RED)
        result = confarg.load(WithIntEnum, argv=["--color", "2"], env={})
        assert result.color is IntColor.GREEN

    def test_enum_name_takes_priority_over_value(self) -> None:
        """When input matches both a member name and a different member's value, name wins."""

        class Ambiguous(enum.Enum):
            RED = "GREEN"  # name="RED", value="GREEN"
            GREEN = "green"

        WithAmbiguous = make_target("x", Ambiguous, default=Ambiguous.GREEN)
        result = confarg.load(WithAmbiguous, argv=["--x", "GREEN"], env={})
        assert result.x is Ambiguous.GREEN  # matched by name "GREEN", not by value of RED member


# ---------------------------------------------------------------------------
# Union[Enum, scalar] — stealing rule and explicit cast
# ---------------------------------------------------------------------------


class _Value(enum.Enum):
    FOO = 1
    BAR = 2


class TestEnumScalarUnion:
    """Stealing rule (enum > scalar > str) and explicit .TYPE cast for Union[Enum, scalar]."""

    def test_enum_steals_from_str_by_name(self) -> None:
        """'FOO' matches enum member by name even in Union[Enum, str]."""
        T = make_target("value", _Value | str, default="x")
        result = confarg.load(T, argv=["--value", "FOO"], env={})
        assert result.value is _Value.FOO

    def test_enum_steals_from_str_by_value(self) -> None:
        """'1' matches enum member by value even in Union[Enum, str]."""
        T = make_target("value", _Value | str, default="x")
        result = confarg.load(T, argv=["--value", "1"], env={})
        assert result.value is _Value.FOO

    def test_str_cast_escapes_enum_stealing(self) -> None:
        """--value.str FOO forces str even when FOO is an enum member name."""
        T = make_target("value", _Value | str, default="x")
        result = confarg.load(T, argv=["--value.str", "FOO"], env={})
        assert result.value == "FOO"
        assert type(result.value) is str

    def test_str_cast_non_member_string(self) -> None:
        """--value.str with a value not matching any enum member still produces str."""
        T = make_target("value", _Value | str, default="x")
        result = confarg.load(T, argv=["--value.str", "hello"], env={})
        assert result.value == "hello"

    def test_enum_steals_from_int_by_value(self) -> None:
        """'1' matches enum member by value in Union[Enum, int]."""
        T = make_target("value", _Value | int, default=0)
        result = confarg.load(T, argv=["--value", "1"], env={})
        assert result.value is _Value.FOO

    def test_int_cast_escapes_enum_stealing(self) -> None:
        """--value.int 1 forces int even when 1 is an enum member value."""
        T = make_target("value", _Value | int, default=0)
        result = confarg.load(T, argv=["--value.int", "1"], env={})
        assert result.value == 1
        assert type(result.value) is int

    def test_int_cast_hex(self) -> None:
        """--value.int 0x1 forces int parsing via int(s, 0)."""
        T = make_target("value", _Value | int, default=0)
        result = confarg.load(T, argv=["--value.int", "0x1"], env={})
        assert result.value == 1
        assert type(result.value) is int

    def test_enum_priority_over_int_regardless_of_declaration_order(self) -> None:
        """Enum wins over int even when int is declared first in the union."""
        T = make_target("value", int | _Value, default=0)
        result = confarg.load(T, argv=["--value", "1"], env={})
        assert result.value is _Value.FOO

    def test_str_fallback_when_no_enum_match(self) -> None:
        """Non-matching string falls through to str when enum doesn't match."""
        T = make_target("value", _Value | str, default="x")
        result = confarg.load(T, argv=["--value", "UNKNOWN"], env={})
        assert result.value == "UNKNOWN"
        assert type(result.value) is str


class TestCastDict:
    """Tagged ``{__cast__, __value__}`` dict for explicit typing in config files."""

    def test_cast_str_in_union_enum_str(self, tmp_toml) -> None:
        """Config file with __cast__ forces str even in Union[Enum, str]."""
        T = make_target("value", _Value | str, default="x")
        path = tmp_toml('[value]\n__cast__ = "str"\n__value__ = "FOO"\n')
        result = confarg.load(T, argv=[], env={}, files=[path])
        assert result.value == "FOO"
        assert type(result.value) is str

    def test_cast_int_in_union_enum_int(self, tmp_toml) -> None:
        """Config file with __cast__ forces int even in Union[Enum, int]."""
        T = make_target("value", _Value | int, default=0)
        path = tmp_toml('[value]\n__cast__ = "int"\n__value__ = 1\n')
        result = confarg.load(T, argv=[], env={}, files=[path])
        assert result.value == 1
        assert type(result.value) is int

    def test_cast_unknown_type_raises(self, tmp_toml) -> None:
        """Unknown __cast__ type raises ConfargError."""
        T = make_target("value", _Value | str, default="x")
        path = tmp_toml('[value]\n__cast__ = "uuid"\n__value__ = "abc"\n')
        with pytest.raises(confarg.exceptions.ConfargError):
            confarg.load(T, argv=[], env={}, files=[path])


# ---------------------------------------------------------------------------
# Path
# ---------------------------------------------------------------------------


class TestPath:
    """Path leaf type parsing."""

    def test_path_from_cli(self, loader: ConfargLoader) -> None:
        """Parse a Path from a CLI arg."""
        WithPath = make_target("location", Path, default=Path())
        result = loader.load(WithPath, argv=["--location", "/tmp/foo"], env={})
        assert result.location == Path("/tmp/foo")

    def test_path_from_env(self, loader: ConfargLoader) -> None:
        """Parse a Path from an env var."""
        WithPath = make_target("location", Path, default=Path())
        result = loader.load(WithPath, argv=[], env={"LOCATION": "/var/log"}, env_prefix="")
        assert result.location == Path("/var/log")


# ---------------------------------------------------------------------------
# Literal
# ---------------------------------------------------------------------------


class TestLiteral:
    """Literal type parsing."""

    def test_literal_valid_value(self) -> None:
        """Parse a valid Literal value from CLI."""
        WithLiteral = make_target("mode", Literal["fast", "slow"], default="fast")
        result = confarg.load(WithLiteral, argv=["--mode", "slow"], env={})
        assert result.mode == "slow"

    def test_literal_default(self) -> None:
        """Literal keeps its default when not provided."""
        WithLiteral = make_target("mode", Literal["fast", "slow"], default="fast")
        result = confarg.load(WithLiteral, argv=[], env={})
        assert result.mode == "fast"

    def test_literal_invalid_raises(self) -> None:
        """Providing an invalid Literal value raises an error."""
        WithLiteral = make_target("mode", Literal["fast", "slow"], default="fast")
        with pytest.raises(confarg.exceptions.ConfargError):
            confarg.load(WithLiteral, argv=["--mode", "turbo"], env={})

    @pytest.mark.parametrize("token", ["none", "null"])
    def test_literal_none_from_str_token(self, token: str) -> None:
        """'none'/'null' tokens coerce to None in Literal[None, str]."""
        WithLiteral = make_target("value", Literal[None, "toto"], default="toto")
        result = confarg.load(WithLiteral, argv=["--value", token], env={})
        assert result.value is None

    def test_literal_int_stealing_over_str(self) -> None:
        """Int member is preferred over str member for Literal["16", 16]."""
        WithLiteral = make_target("value", Literal["16", 16], default=16)
        result = confarg.load(WithLiteral, argv=["--value", "16"], env={})
        assert result.value == 16
        assert type(result.value) is int

    def test_literal_int_hex_notation(self) -> None:
        """Hex notation resolves to the matching int member."""
        WithLiteral = make_target("value", Literal["16", 16], default=16)
        result = confarg.load(WithLiteral, argv=["--value", "0x10"], env={})
        assert result.value == 16
        assert type(result.value) is int

    def test_literal_int_hex_no_match_raises(self) -> None:
        """Hex value that doesn't match any Literal member raises an error."""
        WithLiteral = make_target("value", Literal["16", 16], default=16)
        with pytest.raises(confarg.exceptions.ConfargError):
            confarg.load(WithLiteral, argv=["--value", "0xF"], env={})


# ---------------------------------------------------------------------------
# Annotated
# ---------------------------------------------------------------------------


class TestAnnotated:
    """Annotated type parsing (metadata ignored)."""

    def test_annotated_int(self, loader: ConfargLoader) -> None:
        """Annotated[int, ...] parses as plain int."""
        WithAnnotated = make_target("value", Annotated[int, "some metadata"], default=0)
        result = loader.load(WithAnnotated, argv=["--value", "42"], env={})
        assert result.value == 42

    def test_annotated_default(self, loader: ConfargLoader) -> None:
        """Annotated field keeps its default."""
        WithAnnotated = make_target("value", Annotated[int, "some metadata"], default=0)
        result = loader.load(WithAnnotated, argv=[], env={})
        assert result.value == 0


# ---------------------------------------------------------------------------
# Type alias (3.12+)
# ---------------------------------------------------------------------------


class TestTypeAlias:
    """Python 3.12+ type alias support (``type HostPort = tuple[str, int]``)."""

    def test_type_alias_default(self, loader: ConfargLoader) -> None:
        """Field using a type alias keeps its default."""
        result = loader.load(WithHostPort, argv=[], env={})
        assert result.endpoint == ("localhost", 80)

    def test_type_alias_from_cli(self, loader: ConfargLoader) -> None:
        """Field using a type alias is parsed from CLI args."""
        result = loader.load(WithHostPort, argv=["--endpoint", "myhost", "9090"], env={})
        assert result.endpoint == ("myhost", 9090)

    def test_type_alias_from_env(self, loader: ConfargLoader) -> None:
        """Field using a type alias is parsed from indexed env vars."""
        result = loader.load(
            WithHostPort,
            argv=[],
            env={"ENDPOINT__0": "envhost", "ENDPOINT__1": "443"},
            env_prefix="",
        )
        assert result.endpoint == ("envhost", 443)


class TestTypeAlias312:
    """Python 3.12 ``type X = ...`` alias shapes: scalar, dataclass, union, annotated."""

    # ------------------------------------------------------------------
    # type Alias = int  (scalar alias)
    # ------------------------------------------------------------------

    def test_scalar_alias_from_cli(self, loader: ConfargLoader) -> None:
        """Type Alias = int — field parsed from CLI."""
        target = make_target("value", AliasInt)
        result = loader.load(target, argv=["--value", "42"], env={})
        assert result.value == 42

    def test_scalar_alias_from_env(self, loader: ConfargLoader) -> None:
        """Type Alias = int — field parsed from env var."""
        target = make_target("value", AliasInt)
        result = loader.load(target, argv=[], env={"VALUE": "99"}, env_prefix="")
        assert result.value == 99

    def test_scalar_alias_default(self, loader: ConfargLoader) -> None:
        """Type Alias = int — default value is preserved."""
        target = make_target("value", AliasInt, default=7)
        result = loader.load(target, argv=[], env={})
        assert result.value == 7

    # ------------------------------------------------------------------
    # type Alias = MyDataClass  (dataclass alias)
    # ------------------------------------------------------------------

    def test_dc_alias_from_cli(self, loader: ConfargLoader) -> None:
        """Type Alias = DbConfig — nested fields parsed from CLI."""
        result = loader.load(
            WithAliasDc,
            argv=["--db.host", "localhost", "--db.port", "5432", "--db.name", "mydb"],
            env={},
        )
        assert result.db == DbConfig(host="localhost", port=5432, name="mydb")

    def test_dc_alias_from_env(self, loader: ConfargLoader) -> None:
        """Type Alias = DbConfig — nested fields parsed from env vars."""
        result = loader.load(
            WithAliasDc,
            argv=[],
            env={"DB__HOST": "envhost", "DB__PORT": "3306", "DB__NAME": "envdb"},
            env_prefix="",
        )
        assert result.db == DbConfig(host="envhost", port=3306, name="envdb")

    # ------------------------------------------------------------------
    # type Alias = DC1 | DC2  (union alias)
    # ------------------------------------------------------------------

    def test_union_alias_first_variant_from_cli(self) -> None:
        """Type Alias = DbConfig | CacheConfig — first variant from CLI — vanilla only.

        CLI integrations only register ``--service.class`` for union fields;
        auto-disambiguation from provided fields is a vanilla-parser feature.
        """
        result = confarg.load(
            WithAliasUnion,
            argv=["--service.host", "db.local", "--service.port", "5432", "--service.name", "prod"],
            env={},
        )
        assert result.service == DbConfig(host="db.local", port=5432, name="prod")

    def test_union_alias_second_variant_from_cli(self) -> None:
        """Type Alias = DbConfig | CacheConfig — second variant from CLI — vanilla only."""
        result = confarg.load(
            WithAliasUnion,
            argv=["--service.enabled", "true", "--service.ttl", "600"],
            env={},
        )
        assert result.service == CacheConfig(enabled=True, ttl=600)

    def test_union_alias_first_variant_from_env(self, loader: ConfargLoader) -> None:
        """Type Alias = DbConfig | CacheConfig — first variant resolved from env vars."""
        result = loader.load(
            WithAliasUnion,
            argv=[],
            env={"SERVICE__HOST": "db.local", "SERVICE__PORT": "5432", "SERVICE__NAME": "prod"},
            env_prefix="",
        )
        assert result.service == DbConfig(host="db.local", port=5432, name="prod")

    # ------------------------------------------------------------------
    # type Alias = Annotated[DC1 | DC2, metadata]  (annotated alias)
    # ------------------------------------------------------------------

    def test_annotated_alias_first_variant_from_cli(self) -> None:
        """Type Alias = Annotated[DC1 | DC2, meta] — first variant from CLI — vanilla only."""
        result = confarg.load(
            WithAliasAnnotated,
            argv=["--service.host", "db.local", "--service.port", "5432", "--service.name", "prod"],
            env={},
        )
        assert result.service == DbConfig(host="db.local", port=5432, name="prod")

    def test_annotated_alias_second_variant_from_cli(self) -> None:
        """Type Alias = Annotated[DC1 | DC2, meta] — second variant from CLI — vanilla only."""
        result = confarg.load(
            WithAliasAnnotated,
            argv=["--service.enabled", "true", "--service.ttl", "600"],
            env={},
        )
        assert result.service == CacheConfig(enabled=True, ttl=600)

    def test_annotated_alias_matches_unannotated_alias(self, loader: ConfargLoader) -> None:
        """Annotated alias produces same result as plain union alias (env-based disambiguation)."""
        union_result = loader.load(
            WithAliasUnion,
            argv=[],
            env={"SERVICE__ENABLED": "true", "SERVICE__TTL": "300"},
            env_prefix="",
        )
        annotated_result = loader.load(
            WithAliasAnnotated,
            argv=[],
            env={"SERVICE__ENABLED": "true", "SERVICE__TTL": "300"},
            env_prefix="",
        )
        assert union_result.service == annotated_result.service
