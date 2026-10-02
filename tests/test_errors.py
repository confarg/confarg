# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for error handling: exception hierarchy, missing fields, coercion errors, unknown args."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, NamedTuple

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


class Point(NamedTuple):
    """Two-field namedtuple, for the container-rejects-a-token messages."""

    x: int
    y: int


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

    def test_missing_all_required(self, loader: ConfargLoader) -> None:
        """Flat has no defaults; omitting all fields raises MissingFieldError."""
        with pytest.raises(confarg.exceptions.MissingFieldError):
            loader.load(Flat, argv=[], env={})

    def test_missing_one_required(self, loader: ConfargLoader) -> None:
        """Omitting one required field raises MissingFieldError."""
        with pytest.raises(confarg.exceptions.MissingFieldError):
            loader.load(
                Flat,
                argv=["--name", "x", "--rate", "1.0", "--verbose", "true"],
                env={},
            )

    def test_missing_nested_required(self, loader: ConfargLoader) -> None:
        """Omitting required nested fields raises MissingFieldError."""
        with pytest.raises(confarg.exceptions.MissingFieldError):
            loader.load(AppConfig, argv=[], env={})

    def test_error_message_contains_field_name(self, loader: ConfargLoader) -> None:
        """MissingFieldError message mentions the missing field."""
        with pytest.raises(confarg.exceptions.MissingFieldError, match="count"):
            loader.load(
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

    def test_int_coercion_failure(self, loader: ConfargLoader) -> None:
        """Non-numeric string for int field raises TypeCoercionError."""
        with pytest.raises(confarg.exceptions.TypeCoercionError):
            loader.load(
                Flat,
                argv=["--name", "x", "--count", "notanumber", "--rate", "0", "--verbose", "true"],
                env={},
            )

    def test_float_coercion_failure(self, loader: ConfargLoader) -> None:
        """Non-numeric string for float field raises TypeCoercionError."""
        with pytest.raises(confarg.exceptions.TypeCoercionError):
            loader.load(
                Flat,
                argv=["--name", "x", "--count", "1", "--rate", "notafloat", "--verbose", "true"],
                env={},
            )

    def test_bool_coercion_failure_from_env(self, loader: ConfargLoader) -> None:
        """Unrecognized string for bool from env raises TypeCoercionError."""
        with pytest.raises(confarg.exceptions.TypeCoercionError):
            loader.load(WithDefaults, argv=[], env={"MYAPP_VERBOSE": "maybe"}, env_prefix="MYAPP_")

    def test_literal_invalid_value(self) -> None:
        """Invalid Literal value raises an error — vanilla only.

        CLI integrations validate choices at parse time (raising framework-level
        errors); vanilla validates at coercion time (raising ConfargError).
        """
        WithLiteral = make_target("mode", Literal["fast", "slow"], default="fast")
        with pytest.raises(confarg.exceptions.ConfargError):
            confarg.load(WithLiteral, argv=["--mode", "invalid"], env={})

    def test_enum_invalid_value(self) -> None:
        """Invalid enum value raises TypeCoercionError — vanilla only.

        CLI integrations validate choices at parse time (raising framework-level
        errors); vanilla validates at coercion time (raising TypeCoercionError).
        """
        WithEnum = make_target("color", Color, default=Color.RED)
        with pytest.raises(confarg.exceptions.TypeCoercionError, match=r"Valid members:.*RED.*GREEN.*BLUE"):
            confarg.load(WithEnum, argv=["--color", "purple"], env={})

    def test_optional_int_null_string_hints_none_sentinel_cli(self, loader: ConfargLoader) -> None:
        """TypeCoercionError for Optional[int] hints to use 'none' or 'null'."""
        WithOpt = make_target("value", int | None, default=None)
        with pytest.raises(confarg.exceptions.TypeCoercionError, match=r"'none' or 'null'"):
            loader.load(WithOpt, argv=["--value", "blah"], env={})

    def test_optional_int_null_string_hints_none_sentinel_env(self, loader: ConfargLoader) -> None:
        """TypeCoercionError for Optional[int] from env hints to use 'none' or 'null'."""
        WithOpt = make_target("value", int | None, default=None)
        with pytest.raises(confarg.exceptions.TypeCoercionError, match=r"'none' or 'null'"):
            loader.load(WithOpt, argv=[], env={"MYAPP_VALUE": "blah"}, env_prefix="MYAPP_")


class TestTokensStayOutOfMessages:
    """A channel token is named as the ``str`` it is, never as the private wrapper.

    Dev Notes:
        docs-dev/architecture/05-types-and-construction.md#token-model
    """

    @pytest.mark.parametrize(
        ("annotation", "default_factory", "expected"),
        [
            (Point, None, "Cannot construct Point at 'value': expected list, tuple, or dict, got str 'abc'"),
            (
                list[int],
                list,
                "Cannot construct list at 'value': expected list or dict with integer keys, got str 'abc'",
            ),
            (
                set[int],
                set,
                "Cannot construct collection at 'value': expected sequence or dict with integer keys, got str 'abc'",
            ),
            (
                tuple[int, str],
                None,
                "Cannot construct tuple at 'value': expected list, tuple, or dict with integer keys, got str 'abc'",
            ),
        ],
        ids=["namedtuple", "list", "set", "tuple"],
    )
    def test_container_rejecting_a_token_names_it_str(
        self,
        annotation: object,
        default_factory: object,
        expected: str,
    ) -> None:
        """A scalar token handed to a container prints as ``str``, not ``_StrToken``."""
        kwargs = {"default_factory": default_factory} if default_factory else {"default": None}
        Target = make_target("value", annotation, **kwargs)
        with pytest.raises(confarg.exceptions.TypeCoercionError) as excinfo:
            confarg.load(Target, argv=[], env={"MYAPP_VALUE": "abc"}, env_prefix="MYAPP_")
        assert str(excinfo.value) == expected


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


class TestRemoteSourceErrors:
    """Messages for the failures only a remote config source can have."""

    def test_unknown_scheme_lists_what_is_registered(self) -> None:
        """The message names the registered schemes and how to add one."""
        error = confarg.exceptions.InvalidConfigFileError.unknown_scheme("gs", ["file", "http", "s3"])
        text = str(error)
        assert "gs://" in text
        assert "file, http, s3" in text
        assert "confarg.register_scheme('gs', ...)" in text

    def test_unknown_scheme_hints_the_local_file_escape(self) -> None:
        """A filename with a colon in it has a documented spelling, and the error gives it."""
        error = confarg.exceptions.InvalidConfigFileError.unknown_scheme("weird", ["file"])
        assert "./weird:" in str(error)

    def test_unreachable_names_the_location_and_the_cause(self) -> None:
        """A read failure reports both what could not be read and why."""
        error = confarg.exceptions.InvalidConfigFileError.unreachable(
            "https://h/app.yaml",
            OSError("connection reset"),
        )
        text = str(error)
        assert "https://h/app.yaml" in text
        assert "connection reset" in text

    def test_no_format_explains_the_extension_rule(self) -> None:
        """An extensionless location is told why it cannot be loaded."""
        text = str(confarg.exceptions.InvalidConfigFileError.no_format("https://h/api/config"))
        assert "https://h/api/config" in text
        assert "no file extension" in text
        assert "Content-Type" in text

    def test_cross_origin_include_names_both_locations(self) -> None:
        """The refusal says which document tried to reach what."""
        text = str(
            confarg.exceptions.InvalidConfigFileError.cross_origin_include(
                "https://h/app.yaml",
                "file:///etc/shadow",
            ),
        )
        assert "https://h/app.yaml" in text
        assert "file:///etc/shadow" in text
        assert "own scheme and host" in text

    def test_every_new_error_is_an_invalid_config_file_error(self) -> None:
        """The new failures join the existing config-file error class, not a new one."""
        for error in (
            confarg.exceptions.InvalidConfigFileError.unreachable("x", OSError("e")),
            confarg.exceptions.InvalidConfigFileError.unknown_scheme("gs", ["file"]),
            confarg.exceptions.InvalidConfigFileError.no_format("x"),
            confarg.exceptions.InvalidConfigFileError.cross_origin_include("a", "b"),
        ):
            assert isinstance(error, confarg.exceptions.ConfargError)
