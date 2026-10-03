# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for the load() function signature: arg defaults, non-dataclass targets, return types."""

from __future__ import annotations

import dataclasses
import inspect
from typing import Any

import pytest

import confarg
import confarg.cli.argparse as confargargparse
import confarg.cli.click as confargclick
import confarg.cli.cyclopts as confargcyclopts
import confarg.cli.typer as confargtyper
from confarg import _defaults
from tests.conftest import (
    AppConfig,
    CacheConfig,
    DbConfig,
    Empty,
    Flat,
    WithDefaults,
)

# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------


class TestReturnType:
    """load() returns an instance of the target type."""

    def test_returns_correct_type(self) -> None:
        """load() returns an instance of the target dataclass."""
        result = confarg.load(WithDefaults, argv=[], env={})
        assert isinstance(result, WithDefaults)

    def test_returns_nested_types(self) -> None:
        """Nested dataclasses are correctly instantiated."""
        result = confarg.load(
            AppConfig,
            argv=["--db.host", "h", "--db.port", "1", "--db.name", "n"],
            env={},
        )
        assert isinstance(result, AppConfig)
        assert isinstance(result.db, DbConfig)
        assert isinstance(result.cache, CacheConfig)


# ---------------------------------------------------------------------------
# args parameter
# ---------------------------------------------------------------------------


class TestArgsParameter:
    """Behaviour of the args parameter."""

    def test_args_none_uses_sys_argv(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """argv=None reads from sys.argv[1:]."""
        monkeypatch.setattr(
            "sys.argv",
            ["prog", "--name", "argv_val", "--count", "1", "--rate", "0", "--verbose", "true"],
        )
        result = confarg.load(Flat, env={})
        assert result.name == "argv_val"

    def test_args_empty_list_no_cli(self) -> None:
        """argv=[] means no CLI parsing happens."""
        result = confarg.load(WithDefaults, argv=[], env={})
        assert result.name == "default"

    def test_args_explicit_list(self) -> None:
        """Explicit args list is used for parsing."""
        result = confarg.load(WithDefaults, argv=["--name", "explicit"], env={})
        assert result.name == "explicit"


# ---------------------------------------------------------------------------
# env parameter
# ---------------------------------------------------------------------------


class TestEnvParameter:
    """Behaviour of the env parameter."""

    def test_env_none_uses_os_environ(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """env=None reads from os.environ when an explicit env_prefix is set."""
        monkeypatch.setenv("MYAPP_NAME", "env_val")
        result = confarg.load(WithDefaults, argv=[], env_prefix="MYAPP_")
        assert result.name == "env_val"

    def test_env_none_disabled_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """env=None with default env_prefix=None means os.environ is not read."""
        monkeypatch.setenv("MYAPP_NAME", "should_be_ignored")
        result = confarg.load(WithDefaults, argv=[])
        assert result.name == "default"

    def test_env_empty_dict_no_env(self) -> None:
        """env={} means no env vars are read."""
        result = confarg.load(WithDefaults, argv=[], env={})
        assert result.name == "default"

    def test_env_explicit_dict(self) -> None:
        """Explicit env dict is used for parsing."""
        result = confarg.load(WithDefaults, argv=[], env={"MYAPP_NAME": "from_dict"}, env_prefix="MYAPP_")
        assert result.name == "from_dict"


# ---------------------------------------------------------------------------
# Non-dataclass targets
# ---------------------------------------------------------------------------


class TestNonDataclassTargets:
    """Using non-dataclass types as targets (with cli_prefix)."""

    def test_int_target(self) -> None:
        """Load a plain int via CLI with prefix."""
        result = confarg.load(int, argv=["--confarg", "42"], env={}, cli_prefix="confarg")
        assert result == 42

    def test_str_target(self) -> None:
        """Load a plain str via CLI with prefix."""
        result = confarg.load(str, argv=["--confarg", "hello"], env={}, cli_prefix="confarg")
        assert result == "hello"

    def test_bool_target(self) -> None:
        """Load a plain bool via CLI with prefix."""
        result = confarg.load(bool, argv=["--confarg", "true"], env={}, cli_prefix="confarg")
        assert result is True

    def test_float_target(self) -> None:
        """Load a plain float via env."""
        result = confarg.load(float, argv=[], env={"MYAPP_VALUE": "3.14"}, env_prefix="MYAPP_", cli_prefix="confarg")
        assert result == pytest.approx(3.14)


# ---------------------------------------------------------------------------
# Empty dataclass
# ---------------------------------------------------------------------------


class TestEmptyDataclass:
    """Edge case: dataclass with no fields."""

    def test_empty_dataclass(self) -> None:
        """Loading an empty dataclass succeeds."""
        result = confarg.load(Empty, argv=[], env={})
        assert isinstance(result, Empty)


# ---------------------------------------------------------------------------
# Keyword-only signature enforcement
# ---------------------------------------------------------------------------


class TestSignatureEnforcement:
    """load() keyword arguments are keyword-only (except target)."""

    def test_target_is_positional(self) -> None:
        """Target type can be passed positionally."""
        result = confarg.load(WithDefaults, argv=[], env={})
        assert isinstance(result, WithDefaults)

    def test_keyword_args_only(self) -> None:
        """Parameters after target are keyword-only (cannot be positional)."""
        # This test verifies the signature; it should raise TypeError
        # if someone tries to pass args positionally after target.
        with pytest.raises(TypeError):
            confarg.load(WithDefaults, [])  # ty: ignore[no-matching-overload]  # passing a positional list to verify keyword-only enforcement


# ---------------------------------------------------------------------------
# The one option set (REF-40)
# ---------------------------------------------------------------------------


#: Every public function that takes the merge options, vanilla and adapters alike.
_ENTRY_POINTS: list[Any] = [
    confarg.merge,
    confarg.load,
    confargargparse.merge_namespace,
    confargargparse.from_namespace,
    confargclick.merge_context,
    confargclick.from_context,
    confargtyper.merge_context,
    confargtyper.from_context,
    confargcyclopts.merge_app,
    confargcyclopts.from_app,
]


class TestMergeOptions:
    """Every front-end takes the one ``MergeOptions`` set, and refuses a key outside it."""

    @pytest.mark.parametrize("fn", _ENTRY_POINTS, ids=lambda fn: f"{fn.__module__}.{fn.__name__}")
    def test_takes_merge_options_as_its_only_keywords(self, fn: Any) -> None:
        """No entry point spells an option of its own beside ``**opts``."""
        params = inspect.signature(fn).parameters.values()
        keywords = [p for p in params if p.kind is not inspect.Parameter.POSITIONAL_OR_KEYWORD]
        assert [(p.name, p.kind) for p in keywords] == [("opts", inspect.Parameter.VAR_KEYWORD)]

    @pytest.mark.parametrize("fn", _ENTRY_POINTS, ids=lambda fn: f"{fn.__module__}.{fn.__name__}")
    def test_unknown_keyword_is_refused(self, fn: Any) -> None:
        """A misspelled option raises the TypeError Python raises for an unexpected keyword."""
        # The framework object is never reached: the options are checked first.
        args = (WithDefaults,) if fn in (confarg.merge, confarg.load) else (WithDefaults, object())
        with pytest.raises(TypeError, match=rf"^{fn.__name__}\(\) got an unexpected keyword argument 'env_prefx'$"):
            fn(*args, argv=[], env_prefx="APP_")

    def test_resolved_options_declare_the_same_keys(self) -> None:
        """The private resolved form names exactly the keys the public TypedDict declares."""
        fields = {f.name for f in dataclasses.fields(_defaults._Options)}
        assert fields == confarg.MergeOptions.__optional_keys__
        assert not confarg.MergeOptions.__required_keys__
