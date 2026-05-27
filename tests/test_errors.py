# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for error handling: exception hierarchy, missing fields, coercion errors, unknown args."""

from __future__ import annotations

from typing import Literal

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
# Exception hierarchy
# ---------------------------------------------------------------------------


class TestExceptionHierarchy:
    """Exception types and their inheritance."""

    def test_confarg_error_is_base(self) -> None:
        """All confarg exceptions inherit from ConfargError."""
        assert issubclass(confarg.exceptions.MissingFieldError, confarg.exceptions.ConfargError)
        assert issubclass(confarg.exceptions.SymbolImportError, confarg.exceptions.ConfargError)
        assert issubclass(confarg.exceptions.TypeCoercionError, confarg.exceptions.ConfargError)
        assert issubclass(confarg.exceptions.InvalidConfigFileError, confarg.exceptions.ConfargError)
        assert issubclass(confarg.exceptions.UnknownArgumentError, confarg.exceptions.ConfargError)
        assert issubclass(confarg.exceptions.AmbiguousUnionError, confarg.exceptions.ConfargError)

    def test_confarg_error_is_exception(self) -> None:
        """ConfargError inherits from Exception."""
        assert issubclass(confarg.exceptions.ConfargError, Exception)


# ---------------------------------------------------------------------------
# Missing required fields
# ---------------------------------------------------------------------------


class TestMissingFields:
    """Errors when required fields are not provided."""

    def test_missing_all_required(self) -> None:
        """Flat has no defaults; omitting all fields raises MissingFieldError."""
        with pytest.raises(confarg.exceptions.MissingFieldError):
            confarg.load(Flat, argv=[], env={})

    def test_missing_one_required(self) -> None:
        """Omitting one required field raises MissingFieldError."""
        with pytest.raises(confarg.exceptions.MissingFieldError):
            confarg.load(
                Flat,
                argv=["--name", "x", "--rate", "1.0", "--verbose", "true"],
                env={},
            )

    def test_missing_nested_required(self) -> None:
        """Omitting required nested fields raises MissingFieldError."""
        with pytest.raises(confarg.exceptions.MissingFieldError):
            confarg.load(AppConfig, argv=[], env={})

    def test_error_message_contains_field_name(self) -> None:
        """MissingFieldError message mentions the missing field."""
        with pytest.raises(confarg.exceptions.MissingFieldError, match="count"):
            confarg.load(
                Flat,
                argv=["--name", "x", "--rate", "1.0", "--verbose", "true"],
                env={},
            )

    def test_scalar_target_missing_value_message(self) -> None:
        """MissingFieldError for scalar targets does not mention positional arguments."""
        with pytest.raises(confarg.exceptions.MissingFieldError) as exc_info:
            confarg.build(int, {})
        msg = str(exc_info.value)
        assert "positional" not in msg
        assert "CLI" in msg or "cli" in msg.lower()
        assert "environment" in msg or "env" in msg.lower()
        assert "config" in msg


# ---------------------------------------------------------------------------
# Type coercion errors
# ---------------------------------------------------------------------------


class TestTypeCoercionErrors:
    """Errors when a value cannot be coerced to the target type."""

    def test_int_coercion_failure(self) -> None:
        """Non-numeric string for int field raises TypeCoercionError."""
        with pytest.raises(confarg.exceptions.TypeCoercionError):
            confarg.load(
                Flat,
                argv=["--name", "x", "--count", "notanumber", "--rate", "0", "--verbose", "true"],
                env={},
            )

    def test_float_coercion_failure(self) -> None:
        """Non-numeric string for float field raises TypeCoercionError."""
        with pytest.raises(confarg.exceptions.TypeCoercionError):
            confarg.load(
                Flat,
                argv=["--name", "x", "--count", "1", "--rate", "notafloat", "--verbose", "true"],
                env={},
            )

    def test_bool_coercion_failure_from_env(self) -> None:
        """Unrecognized string for bool from env raises TypeCoercionError."""
        with pytest.raises(confarg.exceptions.TypeCoercionError):
            confarg.load(WithDefaults, argv=[], env={"VERBOSE": "maybe"}, env_prefix="")

    def test_literal_invalid_value(self) -> None:
        """Invalid Literal value raises an error."""
        WithLiteral = make_target("mode", Literal["fast", "slow"], default="fast")
        with pytest.raises(confarg.exceptions.ConfargError):
            confarg.load(WithLiteral, argv=["--mode", "invalid"], env={})

    def test_enum_invalid_value(self) -> None:
        """Invalid enum value raises TypeCoercionError listing valid members."""
        WithEnum = make_target("color", Color, default=Color.RED)
        with pytest.raises(confarg.exceptions.TypeCoercionError, match=r"Valid members:.*RED.*GREEN.*BLUE"):
            confarg.load(WithEnum, argv=["--color", "purple"], env={})

    def test_optional_int_null_string_hints_none_sentinel_cli(self) -> None:
        """TypeCoercionError for Optional[int] hints to use 'none' or 'null'."""
        WithOpt = make_target("value", int | None, default=None)
        with pytest.raises(confarg.exceptions.TypeCoercionError, match=r"'none' or 'null'"):
            confarg.load(WithOpt, argv=["--value", "blah"], env={})

    def test_optional_int_null_string_hints_none_sentinel_env(self) -> None:
        """TypeCoercionError for Optional[int] from env hints to use 'none' or 'null'."""
        WithOpt = make_target("value", int | None, default=None)
        with pytest.raises(confarg.exceptions.TypeCoercionError, match=r"'none' or 'null'"):
            confarg.load(WithOpt, argv=[], env={"VALUE": "blah"}, env_prefix="")


# ---------------------------------------------------------------------------
# Unknown arguments
# ---------------------------------------------------------------------------


class TestUnknownArguments:
    """Errors for unrecognized CLI arguments."""

    def test_unknown_cli_arg(self) -> None:
        """Unknown CLI flag raises UnknownArgumentError."""
        with pytest.raises(confarg.exceptions.UnknownArgumentError):
            confarg.load(WithDefaults, argv=["--nonexistent", "val"], env={})

    def test_unknown_nested_cli_arg(self) -> None:
        """Unknown nested CLI path raises UnknownArgumentError."""
        with pytest.raises(confarg.exceptions.UnknownArgumentError):
            confarg.load(WithDefaults, argv=["--foo.bar", "val"], env={})

    def test_unknown_arg_message_contains_name(self) -> None:
        """UnknownArgumentError message mentions the unknown argument."""
        with pytest.raises(confarg.exceptions.UnknownArgumentError, match="nonexistent"):
            confarg.load(WithDefaults, argv=["--nonexistent", "val"], env={})


# ---------------------------------------------------------------------------
# Non-dataclass without prefix
# ---------------------------------------------------------------------------


class TestNonDataclassErrors:
    """Errors for non-dataclass targets without proper setup."""

    def test_non_dataclass_no_prefix_is_handled(self) -> None:
        """Non-dataclass target without prefix raises or handles gracefully."""
        with pytest.raises(confarg.exceptions.ConfargError):
            confarg.load(int, argv=["42"], env={})
