# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for Callable type support."""

from __future__ import annotations

import functools
import inspect
import json
import math
import pathlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pytest

import confarg
from confarg._callable import (
    _check_callable_signature,
    _detect_owning_class,
    _import_dotted,
    _resolve_bind_kwargs,
    _serialize_callable,
)
from confarg._types import _callable_param_types, _callable_return_type, _is_callable
from confarg.exceptions import SymbolImportError, TypeCoercionError
from confarg.typedload._construct import construct

# ---------------------------------------------------------------------------
# Helpers defined at module level so they are importable by dotted path
# ---------------------------------------------------------------------------


def _double(x: int) -> int:
    return x * 2


def _add(x: int, y: int) -> int:
    return x + y


def _greet(name: str) -> str:
    return f"hello {name}"


class _Multiplier:
    """Callable class: instance multiplies its input."""

    def __init__(self, factor: int) -> None:
        self.factor = factor

    def __call__(self, x: int) -> int:
        return x * self.factor


class _NoArgCallable:
    """Callable class that takes no constructor args."""

    def __call__(self, x: int) -> int:
        return x + 1


class _Processor:
    """Class with an instance method used as a callable."""

    def __init__(self, offset: int) -> None:
        self.offset = offset

    def process(self, x: int) -> int:
        return x + self.offset


class _NoArgProcessor:
    """Class with a no-arg constructor and an instance method.

    Used to test fn: auto-instantiation when no sibling constructor kwargs are provided.
    """

    def transform(self, x: int) -> int:
        return x * 3


class _Base:
    """Base type used as a Callable's concrete return type (factory target)."""


class _Sub(_Base):
    """Subclass of the return type: valid as a bare factory."""

    def __init__(self, tag: str = "s") -> None:
        self.tag = tag


class _NoneReturningCallable:
    """Callable-object whose __call__ returns None (not a factory for None)."""

    def __call__(self, x: int) -> None:
        pass


def _make_adder(offset: int) -> Callable[[int], int]:
    """Factory function: returns a function that adds offset to its argument."""
    return lambda x: x + offset


def _make_multiplier(factor: int) -> Callable[[int], int]:
    """Factory function: returns a function that multiplies its argument."""

    def _mul(x: int) -> int:
        return x * factor

    return _mul


def _bad_factory(x: int) -> int:
    """Factory that returns a non-callable (used to test error path)."""
    return x * 2


class _InitBind:
    """Callable class whose __init__ takes a parameter named 'bind'.

    Exercises the escaped directive mode: the __init__ 'bind' argument must be
    settable *while* the '_bind' directive partial-applies to __call__.
    """

    def __init__(self, bind: int) -> None:
        self.bind = bind

    def __call__(self, lr: int) -> int:
        return self.bind + lr


class _OwnerWithFn:
    """Class whose __init__ takes a parameter named 'fn', with an instance method.

    Exercises the opener residual: passing a constructor kwarg named 'fn' while
    the method is referenced via the escaped '_fn' opener.
    """

    def __init__(self, fn: int) -> None:
        self.fn = fn

    def method(self, x: int) -> int:
        return x + self.fn


# Module path prefix used throughout tests
_MOD = "tests.test_callables"


# ---------------------------------------------------------------------------
# Target dataclasses
# ---------------------------------------------------------------------------


@dataclass
class WithCallable:
    """Target dataclass with a typed Callable field."""

    fn: Callable[[int], int]


@dataclass
class WithBareCallable:
    """Target dataclass with a bare (unparameterized) Callable field."""

    fn: Callable


@dataclass
class WithBaseFactory:
    """Target dataclass whose Callable declares a concrete class return type."""

    fn: Callable[..., _Base]


@dataclass
class WithNoneCallable:
    """Target dataclass whose Callable returns None."""

    fn: Callable[[int], None]


@dataclass
class WithOptionalCallable:
    """Target dataclass with an optional Callable field."""

    fn: Callable[[int], int] | None = None


@dataclass
class WithCallableDefault:
    """Target dataclass with a Callable field that has a default."""

    fn: Callable[[int], int] = field(default=_double)


# ---------------------------------------------------------------------------
# _is_callable / param/return helpers
# ---------------------------------------------------------------------------


class TestIsCallable:
    """Tests for the _is_callable type-inspection helper."""

    def test_parameterized(self) -> None:
        """Parameterized Callable types are recognized."""
        assert _is_callable(Callable[[int], float])

    def test_bare(self) -> None:
        """Bare Callable is recognized."""
        assert _is_callable(Callable)

    def test_ellipsis(self) -> None:
        """Callable[..., T] is recognized."""
        assert _is_callable(Callable[..., int])

    def test_non_callable(self) -> None:
        """Non-callable types are not recognized as callable."""
        assert not _is_callable(int)
        assert not _is_callable(str)
        assert not _is_callable(list[int])


class TestCallableParamReturn:
    """Tests for callable parameter and return type inspection helpers."""

    def test_param_types(self) -> None:
        """Test extraction of parameter types from a parameterized Callable."""
        assert _callable_param_types(Callable[[int, str], float]) == [int, str]

    def test_param_types_empty(self) -> None:
        """Callable[[], T] returns an empty parameter list."""
        assert _callable_param_types(Callable[[], int]) == []

    def test_param_types_bare(self) -> None:
        """Bare Callable returns None for parameter types."""
        assert _callable_param_types(Callable) is None

    def test_param_types_ellipsis(self) -> None:
        """Callable[..., T] returns None for parameter types."""
        assert _callable_param_types(Callable[..., int]) is None

    def test_return_type(self) -> None:
        """Test extraction of the return type from a parameterized Callable."""
        assert _callable_return_type(Callable[[int], float]) is float

    def test_return_type_bare(self) -> None:
        """Bare Callable returns None for return type."""
        assert _callable_return_type(Callable) is None


# ---------------------------------------------------------------------------
# _import_dotted
# ---------------------------------------------------------------------------


class TestImportDotted:
    """Tests for the _import_dotted helper."""

    def test_module_level_function(self) -> None:
        """Test importing a module-level function by dotted path."""
        fn = _import_dotted(f"{_MOD}._double")
        assert fn is _double

    def test_class(self) -> None:
        """Test importing a class by dotted path."""
        cls = _import_dotted(f"{_MOD}._Multiplier")
        assert cls is _Multiplier

    def test_stdlib_function(self) -> None:
        """Test importing a stdlib function by dotted path."""
        fn = _import_dotted("math.sqrt")
        assert fn is math.sqrt

    def test_unknown_raises(self) -> None:
        """Importing an unknown path raises SymbolImportError."""
        with pytest.raises(SymbolImportError, match="Cannot import"):
            _import_dotted("does.not.exist.at.all")

    def test_bad_attr_raises(self) -> None:
        """Importing a nonexistent attribute raises SymbolImportError."""
        with pytest.raises(SymbolImportError, match="Cannot import"):
            _import_dotted("math.no_such_fn")


# ---------------------------------------------------------------------------
# _detect_owning_class
# ---------------------------------------------------------------------------


class TestDetectOwningClass:
    """Tests for the _detect_owning_class helper."""

    def test_instance_method(self) -> None:
        """An instance method's owning class is detected."""
        cls = _detect_owning_class(_Processor.process)
        assert cls is _Processor

    def test_module_level_fn(self) -> None:
        """A module-level function returns None."""
        assert _detect_owning_class(_double) is None

    def test_lambda(self) -> None:
        """A lambda returns None."""
        lam = lambda x: x  # noqa: E731
        assert _detect_owning_class(lam) is None


# ---------------------------------------------------------------------------
# Bare string resolution
# ---------------------------------------------------------------------------


class TestBareString:
    """Tests for bare string (dotted path) callable resolution."""

    def test_function_from_cli(self) -> None:
        """A dotted function path from CLI resolves to the function."""
        result = confarg.load(
            WithCallable,
            argv=["--fn", f"{_MOD}._double"],
            env={},
        )
        assert result.fn(3) == 6

    def test_bare_class_becomes_factory_from_cli(self) -> None:
        """A bare class on an untyped Callable is used factory-like (not instantiated)."""
        result = confarg.load(
            WithBareCallable,
            argv=["--fn", f"{_MOD}._NoArgCallable"],
            env={},
        )
        assert isinstance(result.fn, functools.partial)
        assert result.fn.func is _NoArgCallable
        # calling the factory constructs an instance, which is itself callable
        assert result.fn()(4) == 5

    def test_bare_class_instance_via_class_key_from_cli(self) -> None:
        """The 'class:' dict form instantiates the class and uses the instance as the callable."""
        result = confarg.load(
            WithBareCallable,
            argv=[f"--fn.class={_MOD}._NoArgCallable"],
            env={},
        )
        assert isinstance(result.fn, _NoArgCallable)
        assert result.fn(4) == 5

    def test_bare_class_requiring_args_is_deferred(self) -> None:
        """A bare class whose ctor needs args no longer raises; construction is deferred."""
        result = confarg.load(
            WithBareCallable,
            argv=["--fn", f"{_MOD}._Multiplier"],
            env={},
        )
        assert isinstance(result.fn, functools.partial)
        assert result.fn.func is _Multiplier
        assert result.fn(factor=3)(4) == 12

    def test_method_requiring_args_error_shows_dict_form(self) -> None:
        """The error for a method needing constructor args shows the fn: dict form hint."""
        # _Processor.process is an instance method whose __init__ requires `offset`.
        # The error should show the complete fn: dict form with the required kwarg.
        with pytest.raises(TypeCoercionError) as exc_info:
            confarg.load(
                WithCallable,
                argv=["--fn", f"{_MOD}._Processor.process"],
                env={},
            )
        msg = str(exc_info.value)
        assert "Cannot instantiate" in msg
        assert f"fn: {_MOD}._Processor.process" in msg
        assert "offset" in msg  # required constructor kwarg listed
        assert "<value>" in msg  # placeholder shown

    def test_from_toml(self, tmp_toml: Any) -> None:
        """A dotted function path from TOML resolves correctly."""
        cfg = tmp_toml(f'fn = "{_MOD}._double"\n')
        result = confarg.load(WithCallable, argv=[], env={}, files=[cfg])
        assert result.fn(5) == 10

    def test_from_env(self) -> None:
        """A dotted function path from env vars resolves correctly."""
        result = confarg.load(
            WithCallable,
            argv=[],
            env={"CONFARG_FN": f"{_MOD}._double"},
            env_prefix="CONFARG_",
        )
        assert result.fn(7) == 14

    def test_default_preserved(self) -> None:
        """Default callable fields are preserved when not overridden."""
        result = confarg.load(WithCallableDefault, argv=[], env={})
        assert result.fn(3) == 6

    def test_optional_none(self) -> None:
        """Optional callable fields default to None."""
        result = confarg.load(WithOptionalCallable, argv=[], env={})
        assert result.fn is None


# ---------------------------------------------------------------------------
# fn: dict form  (via JSON config files for nested dicts)
# ---------------------------------------------------------------------------


class TestFnDictForm:
    """Tests for the fn: dict form callable specification."""

    def test_fn_no_bind(self, tmp_json: Any) -> None:
        """Test fn: dict with no bind key resolves to the function."""
        cfg = tmp_json(json.dumps({"fn": {"fn": f"{_MOD}._double"}}))
        result = confarg.load(WithCallable, argv=[], env={}, files=[cfg])
        assert result.fn(4) == 8

    def test_fn_with_bind(self, tmp_json: Any) -> None:
        """Test fn: dict with bind: key pre-applies the arguments."""
        cfg = tmp_json(json.dumps({"fn": {"fn": f"{_MOD}._add", "bind": {"y": 10}}}))
        result = confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])
        assert result.fn(5) == 15

    def test_fn_with_bind_via_cli(self) -> None:
        """--fn.fn + --fn.bind.key via CLI pre-applies the argument."""
        result = confarg.load(
            WithBareCallable,
            argv=[f"--fn.fn={_MOD}._add", "--fn.bind.y=10"],
            env={},
        )
        assert result.fn(5) == 15

    def test_fn_class_as_factory(self, tmp_json: Any) -> None:
        """Test fn: dict with a class path returns the class itself."""
        cfg = tmp_json(json.dumps({"fn": {"fn": f"{_MOD}._Multiplier"}}))
        result = confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])
        assert result.fn is _Multiplier

    def test_fn_class_as_factory_with_bind(self, tmp_json: Any) -> None:
        """Test fn: dict with a class and bind returns a partial constructor."""
        cfg = tmp_json(json.dumps({"fn": {"fn": f"{_MOD}._Multiplier", "bind": {"factor": 3}}}))
        result = confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])
        assert isinstance(result.fn, functools.partial)
        instance = result.fn()
        assert instance(4) == 12

    def test_fn_instance_method_with_init(self, tmp_json: Any) -> None:
        """Test fn: dict with an instance method and constructor kwargs."""
        cfg = tmp_json(json.dumps({"fn": {"fn": f"{_MOD}._Processor.process", "offset": 7}}))
        result = confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])
        assert result.fn(3) == 10

    def test_fn_fully_bound_via_bind(self, tmp_json: Any) -> None:
        """Test fn: dict with all parameters bound via bind key."""

        @dataclass
        class Target:
            fn: Callable[[], int]

        cfg = tmp_json(json.dumps({"fn": {"fn": f"{_MOD}._add", "bind": {"x": 1, "y": 2}}}))
        result = confarg.load(Target, argv=[], env={}, files=[cfg])
        assert result.fn() == 3

    def test_fn_both_fn_and_class_raises(self, tmp_json: Any) -> None:
        """Specifying both fn: and class: raises TypeCoercionError."""
        cfg = tmp_json(json.dumps({"fn": {"fn": f"{_MOD}._double", "class": f"{_MOD}._Multiplier"}}))
        with pytest.raises(TypeCoercionError, match="more than one of"):
            confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])

    def test_fn_no_key_raises(self, tmp_json: Any) -> None:
        """A dict without fn: or class: raises TypeCoercionError."""
        cfg = tmp_json(json.dumps({"fn": {"bind": {"x": 1}}}))
        with pytest.raises(TypeCoercionError, match=r"fn.*class"):
            confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])

    def test_fn_init_kwargs_for_non_method_raises(self, tmp_json: Any) -> None:
        """Sibling init kwargs for a plain function raises TypeCoercionError."""
        cfg = tmp_json(json.dumps({"fn": {"fn": f"{_MOD}._double", "offset": 5}}))
        with pytest.raises(TypeCoercionError, match="instance method"):
            confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])

    def test_fn_env_json(self) -> None:
        """Test fn: dict form specified as JSON in an env var."""
        spec = json.dumps({"fn": f"{_MOD}._add", "bind": {"y": 3}})
        result = confarg.load(WithBareCallable, argv=[], env={"CONFARG_FN": spec}, env_prefix="CONFARG_")
        assert result.fn(2) == 5


# ---------------------------------------------------------------------------
# fn: auto-instantiation behaviour
# ---------------------------------------------------------------------------


class TestFnDictAutoInstantiation:
    """Behavioral tests for the two auto-instantiation paths in _resolve_fn_spec.

    Without sibling kwargs: _maybe_bind_method is called, which auto-instantiates
    the owning class using its no-arg constructor and returns the bound method.

    With sibling kwargs: the owning class is detected via __qualname__, constructed
    with those kwargs via _construct_struct, and the method is retrieved from the
    resulting instance.
    """

    def test_fn_instance_method_no_sibling_kwargs_auto_instantiates(self, tmp_json: Any) -> None:
        """fn: dict with no sibling kwargs auto-instantiates the owning class (no-arg ctor)."""
        cfg = tmp_json(json.dumps({"fn": {"fn": f"{_MOD}._NoArgProcessor.transform"}}))
        result = confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])
        # _NoArgProcessor() is created automatically; transform(x) returns x * 3
        assert result.fn(4) == 12

    def test_fn_instance_method_no_sibling_kwargs_returns_bound_method(self, tmp_json: Any) -> None:
        """fn: auto-instantiation without kwargs produces a bound method (not a partial)."""
        cfg = tmp_json(json.dumps({"fn": {"fn": f"{_MOD}._NoArgProcessor.transform"}}))
        result = confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])
        assert not isinstance(result.fn, functools.partial)
        assert callable(result.fn)

    def test_fn_instance_method_with_sibling_kwargs_constructs_owning_class(self, tmp_json: Any) -> None:
        """Fn: dict with sibling kwargs detects and constructs the owning class.

        Detects the owning class via __qualname__ and constructs it using those kwargs,
        then retrieves the bound method.
        """
        cfg = tmp_json(json.dumps({"fn": {"fn": f"{_MOD}._Processor.process", "offset": 5}}))
        result = confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])
        # _Processor(offset=5) is constructed; process(x) returns x + 5
        assert result.fn(10) == 15

    def test_fn_instance_method_no_arg_ctor_required_but_has_args_raises(self, tmp_json: Any) -> None:
        """fn: without sibling kwargs raises when the owning class needs constructor args."""
        cfg = tmp_json(json.dumps({"fn": {"fn": f"{_MOD}._Processor.process"}}))
        with pytest.raises(TypeCoercionError, match="Cannot instantiate"):
            confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])

    def test_fn_instance_method_no_arg_ctor_error_suggests_dict_form(self, tmp_json: Any) -> None:
        """Error message when auto-instantiation fails references the fn: dict form."""
        cfg = tmp_json(json.dumps({"fn": {"fn": f"{_MOD}._Processor.process"}}))
        with pytest.raises(TypeCoercionError) as exc_info:
            confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])
        msg = str(exc_info.value)
        assert f"fn: {_MOD}._Processor.process" in msg
        assert "offset" in msg  # required ctor kwarg listed in the hint


# ---------------------------------------------------------------------------
# class: dict form
# ---------------------------------------------------------------------------


class TestClassDictForm:
    """Tests for the class: dict form callable specification."""

    def test_class_no_args(self, tmp_json: Any) -> None:
        """Test class: dict with a no-arg class instantiates correctly."""
        cfg = tmp_json(json.dumps({"fn": {"class": f"{_MOD}._NoArgCallable"}}))
        result = confarg.load(WithCallable, argv=[], env={}, files=[cfg])
        assert isinstance(result.fn, _NoArgCallable)
        assert result.fn(9) == 10

    def test_class_with_init_args(self, tmp_json: Any) -> None:
        """Test class: dict with constructor args instantiates correctly."""
        cfg = tmp_json(json.dumps({"fn": {"class": f"{_MOD}._Multiplier", "factor": 5}}))
        result = confarg.load(WithCallable, argv=[], env={}, files=[cfg])
        assert isinstance(result.fn, _Multiplier)
        assert result.fn(3) == 15

    def test_class_with_bind(self, tmp_json: Any) -> None:
        """Test class: dict with bind: produces a partial from the instance."""

        @dataclass
        class Target:
            fn: Callable[[], int]

        cfg = tmp_json(json.dumps({"fn": {"class": f"{_MOD}._Multiplier", "factor": 4, "bind": {"x": 2}}}))
        result = confarg.load(Target, argv=[], env={}, files=[cfg])
        assert isinstance(result.fn, functools.partial)
        assert result.fn() == 8

    def test_class_non_class_raises(self, tmp_json: Any) -> None:
        """Class: dict with a function path raises TypeCoercionError."""
        cfg = tmp_json(json.dumps({"fn": {"class": f"{_MOD}._double"}}))
        with pytest.raises(TypeCoercionError, match="must reference a class"):
            confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])

    def test_class_init_coercion(self, tmp_json: Any) -> None:
        """Constructor args from config are type-coerced by _construct_struct."""
        cfg = tmp_json(json.dumps({"fn": {"class": f"{_MOD}._Multiplier", "factor": 6}}))
        result = confarg.load(WithCallable, argv=[], env={}, files=[cfg])
        assert result.fn(2) == 12


# ---------------------------------------------------------------------------
# Bind parameter checking
# ---------------------------------------------------------------------------


def _kwargs_fn(**kwargs: int) -> int:
    return sum(kwargs.values())


class TestBindParamChecking:
    """Tests for _resolve_bind_kwargs parameter validation."""

    def test_valid_bind_passes(self) -> None:
        """Valid bind parameters pass without error."""
        assert _resolve_bind_kwargs(_add, {"x": 1, "y": 2}, "f", "class", construct) == {"x": 1, "y": 2}

    def test_unknown_key_raises(self) -> None:
        """An unknown bind key raises TypeCoercionError."""
        with pytest.raises(TypeCoercionError, match="Unknown bind parameter"):
            _resolve_bind_kwargs(_add, {"x": 1, "z": 99}, "f", "class", construct)

    def test_error_names_invalid_and_valid(self) -> None:
        """The error message names both invalid and valid keys."""
        with pytest.raises(TypeCoercionError, match="'z'") as exc_info:
            _resolve_bind_kwargs(_add, {"z": 1}, "myfield", "class", construct)
        assert "x" in str(exc_info.value)
        assert "y" in str(exc_info.value)

    def test_var_keyword_fn_skips_validation(self) -> None:
        """Test that **kwargs functions skip bind key validation."""
        _resolve_bind_kwargs(_kwargs_fn, {"anything": 1, "goes": 2}, "f", "class", construct)

    def test_uninspectable_skips_validation(self) -> None:
        """Uninspectable builtins skip bind key validation."""
        # len is a builtin with no inspectable signature on all platforms
        try:
            inspect.signature(len)
            pytest.skip("len is inspectable on this platform")
        except (ValueError, TypeError):
            pass
        assert _resolve_bind_kwargs(len, {"unknown": 1}, "f", "class", construct) == {"unknown": 1}

    def test_fn_bind_unknown_key_raises_via_load(self, tmp_json: Any) -> None:
        """Unknown bind key in fn: dict raises via confarg.load."""
        cfg = tmp_json(json.dumps({"fn": {"fn": f"{_MOD}._add", "bind": {"z": 1}}}))
        with pytest.raises(TypeCoercionError, match="Unknown bind parameter"):
            confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])

    def test_class_bind_unknown_key_raises_via_load(self, tmp_json: Any) -> None:
        """Unknown bind key in class: dict raises via confarg.load."""
        cfg = tmp_json(json.dumps({"fn": {"class": f"{_MOD}._Multiplier", "factor": 2, "bind": {"bad": 1}}}))
        with pytest.raises(TypeCoercionError, match="Unknown bind parameter"):
            confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])

    def test_method_bind_unknown_key_raises_via_load(self, tmp_json: Any) -> None:
        """Unknown bind key for a method raises via confarg.load."""
        cfg = tmp_json(json.dumps({"fn": {"fn": f"{_MOD}._Processor.process", "offset": 1, "bind": {"bad": 9}}}))
        with pytest.raises(TypeCoercionError, match="Unknown bind parameter"):
            confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])


# ---------------------------------------------------------------------------
# Signature checking
# ---------------------------------------------------------------------------


class TestSignatureChecking:
    """Tests for callable signature compatibility checking."""

    def test_compatible_function(self) -> None:
        """A compatible function passes signature checking."""
        _check_callable_signature(_double, Callable[[int], int], "field")

    def test_incompatible_param_count_raises(self) -> None:
        """A function with wrong param count raises TypeCoercionError."""
        with pytest.raises(TypeCoercionError, match="2 parameter"):
            _check_callable_signature(_double, Callable[[int, int], int], "field")

    def test_bare_callable_no_check(self) -> None:
        """Bare Callable skips signature checking."""
        _check_callable_signature(_double, Callable, "field")

    def test_ellipsis_no_check(self) -> None:
        """Callable[..., T] skips signature checking."""
        _check_callable_signature(_double, Callable[..., int], "field")

    def test_varargs_skipped(self) -> None:
        """Test that *args functions skip param count checking."""

        # *args functions accept any number of positional args — skip count check
        def _varargs(*args: int) -> int:
            return sum(args)

        _check_callable_signature(_varargs, Callable[[str, str], int], "field")

    def test_partial_accounts_for_bound_args(self) -> None:
        """Partial accounts for already-bound args in signature check."""
        p = functools.partial(_add, y=1)
        _check_callable_signature(p, Callable[[int], int], "field")

    def test_partial_wrong_count_raises(self) -> None:
        """Partial with wrong remaining param count raises TypeCoercionError."""
        p = functools.partial(_add, y=1)
        with pytest.raises(TypeCoercionError, match="expects 2 parameter"):
            _check_callable_signature(p, Callable[[int, int], int], "field")

    def test_signature_check_via_load(self) -> None:
        """Signature mismatch raises TypeCoercionError via confarg.load."""
        with pytest.raises(TypeCoercionError, match="parameter"):
            confarg.load(
                WithCallable,
                argv=["--fn", f"{_MOD}._add"],
                env={},
            )


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------


class TestSerialization:
    """Tests for callable serialization round-trips."""

    def test_plain_function(self) -> None:
        """A plain function serializes to its dotted path."""
        assert _serialize_callable(_double) == f"{_MOD}._double"

    def test_partial(self) -> None:
        """A partial serializes to fn: dict with bind: key."""
        p = functools.partial(_add, y=5)
        out = _serialize_callable(p)
        assert out == {"fn": f"{_MOD}._add", "bind": {"y": 5}}

    def test_partial_no_bind(self) -> None:
        """A partial with no bound args serializes to the bare dotted path (round-trips to the callable)."""
        p = functools.partial(_double)
        out = _serialize_callable(p)
        assert out == f"{_MOD}._double"

    def test_class_instance_with_spec(self, tmp_json: Any) -> None:
        """A class instance loaded via class: dict round-trips correctly."""
        cfg = tmp_json(json.dumps({"fn": {"class": f"{_MOD}._Multiplier", "factor": 3}}))
        result = confarg.load(WithCallable, argv=[], env={}, files=[cfg])
        dumped = confarg.dump(result)
        assert dumped["fn"] == {"class": f"{_MOD}._Multiplier", "factor": 3}

    def test_round_trip_plain_function(self) -> None:
        """A plain function round-trips through load and dump."""
        result = confarg.load(
            WithBareCallable,
            argv=["--fn", f"{_MOD}._double"],
            env={},
        )
        dumped = confarg.dump(result)
        assert dumped["fn"] == f"{_MOD}._double"

    def test_round_trip_partial(self, tmp_json: Any) -> None:
        """A partial round-trips through load and dump."""
        cfg = tmp_json(json.dumps({"fn": {"fn": f"{_MOD}._add", "bind": {"y": 7}}}))
        result = confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])
        dumped = confarg.dump(result)
        assert dumped["fn"] == {"fn": f"{_MOD}._add", "bind": {"y": 7}}


# ---------------------------------------------------------------------------
# Regression: callable-object mode via CLI (non-subclass return type)
# ---------------------------------------------------------------------------


@dataclass
class _WithNoneReturn:
    fn: Callable[[int], None]


class TestCallableObjectModeCLI:
    """CLI flags for callable-object mode when class is not a subclass of the return type.

    Previously broken: _extend_callable_flags fell through to bind mode because
    issubclass(cls, NoneType) is always False, so --<flag>.<param> was never
    registered and _collect_ns_fields skipped factory kwargs collection.
    """

    def test_class_mode_none_return_type(self) -> None:
        """--<flag>.class + --<flag>.<kwarg> works for Callable[[X], None]."""
        result = confarg.load(
            _WithNoneReturn,
            argv=[f"--fn.class={_MOD}._Multiplier", "--fn.factor=3"],
            env={},
        )
        assert isinstance(result.fn, _Multiplier)
        assert result.fn(5) == 15

    def test_class_mode_non_subclass_return_type(self) -> None:
        """--<flag>.class + --<flag>.<kwarg> works when class is not a subclass of return type."""
        result = confarg.load(
            WithCallable,
            argv=[f"--fn.class={_MOD}._Multiplier", "--fn.factor=4"],
            env={},
        )
        assert isinstance(result.fn, _Multiplier)
        assert result.fn(3) == 12

    def test_fn_mode_method_path_with_constructor_kwarg(self) -> None:
        """--<flag>.fn with a method path + --<flag>.<kwarg> for owning class constructor."""
        result = confarg.load(
            _WithNoneReturn,
            argv=[f"--fn.fn={_MOD}._Processor.process", "--fn.offset=10"],
            env={},
        )
        assert result.fn(5) == 15


class TestFnInitMethod:
    """__init__ passed as the fn: value is treated as a plain function.

    No auto-instantiation occurs, sibling init kwargs are rejected, and
    bind: applies partial application as for any other plain function.
    """

    def test_bare_string_init_is_plain_function(self) -> None:
        """Test that __init__ as bare string resolves to the plain __init__ function."""
        result = confarg.load(
            WithBareCallable,
            argv=["--fn", f"{_MOD}._Processor.__init__"],
            env={},
        )
        assert result.fn is _Processor.__init__

    def test_dict_form_init_no_bind(self, tmp_json: Any) -> None:
        """Test that __init__ in fn: dict form resolves to the plain __init__ function."""
        cfg = tmp_json(json.dumps({"fn": {"fn": f"{_MOD}._Processor.__init__"}}))
        result = confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])
        assert result.fn is _Processor.__init__

    def test_dict_form_init_with_bind(self, tmp_json: Any) -> None:
        """Test that __init__ in fn: dict form with bind: produces a partial."""
        cfg = tmp_json(json.dumps({"fn": {"fn": f"{_MOD}._Processor.__init__", "bind": {"offset": 5}}}))
        result = confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])
        assert isinstance(result.fn, functools.partial)
        assert result.fn.keywords == {"offset": 5}

    def test_dict_form_init_with_sibling_kwargs_raises(self, tmp_json: Any) -> None:
        """Sibling kwargs for __init__ in fn: dict raises TypeCoercionError."""
        cfg = tmp_json(json.dumps({"fn": {"fn": f"{_MOD}._Processor.__init__", "offset": 5}}))
        with pytest.raises(TypeCoercionError, match="bind"):
            confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])


class TestBareStringNonCallable:
    """A bare class is used factory-like; nothing is instantiated at resolution time."""

    def test_bare_class_is_factory_not_instance(self) -> None:
        """A bare class (e.g. pathlib.Path) on an untyped Callable is a factory, not an instance."""
        result = confarg.load(WithBareCallable, argv=["--fn", "pathlib.Path"], env={})
        assert isinstance(result.fn, functools.partial)
        assert result.fn.func is pathlib.Path


class TestBareStringFactoryGuardRail:
    """A bare class is factory-like; a concrete return type it cannot produce is rejected."""

    def test_guard_raises_for_non_subclass_return_type(self) -> None:
        """Callable[[int], int] + a bare class that is not an int subclass raises, pointing at 'class:'."""
        with pytest.raises(TypeCoercionError, match=r"used as a factory.*class: "):
            confarg.load(WithCallable, argv=["--fn", f"{_MOD}._NoArgCallable"], env={})

    def test_guard_raises_for_none_return_type(self) -> None:
        """Callable[[int], None] + a bare callable-object class raises (no class produces None)."""
        with pytest.raises(TypeCoercionError, match="used as a factory"):
            confarg.load(WithNoneCallable, argv=["--fn", f"{_MOD}._NoneReturningCallable"], env={})

    def test_guard_raises_from_file(self, tmp_json: Any) -> None:
        """The guard also fires for a bare class provided via a config file."""
        cfg = tmp_json(json.dumps({"fn": f"{_MOD}._NoArgCallable"}))
        with pytest.raises(TypeCoercionError, match="used as a factory"):
            confarg.load(WithCallable, argv=[], env={}, files=[cfg])

    def test_subclass_return_type_bare_is_factory(self) -> None:
        """Callable[..., _Base] + a bare _Base subclass is a valid factory."""
        result = confarg.load(WithBaseFactory, argv=["--fn", f"{_MOD}._Sub"], env={})
        assert isinstance(result.fn, functools.partial)
        assert result.fn.func is _Sub
        assert isinstance(result.fn(), _Base)

    def test_subclass_return_type_bare_is_factory_from_file(self, tmp_json: Any) -> None:
        """The subclass factory also resolves from a config file."""
        cfg = tmp_json(json.dumps({"fn": f"{_MOD}._Sub"}))
        result = confarg.load(WithBaseFactory, argv=[], env={}, files=[cfg])
        assert isinstance(result.fn, functools.partial)
        assert result.fn.func is _Sub


class TestCallDictForm:
    """Tests for the 'call:' dict key: call a factory function and use its return value."""

    def test_call_with_bind_from_file(self, tmp_json: Any) -> None:
        """call: + bind: in a config file calls the factory and uses the result."""
        cfg = tmp_json(json.dumps({"fn": {"call": f"{_MOD}._make_adder", "bind": {"offset": 5}}}))
        result = confarg.load(WithCallable, argv=[], env={}, files=[cfg])
        assert result.fn(10) == 15

    def test_call_with_sibling_kwargs_from_file(self, tmp_json: Any) -> None:
        """call: with sibling kwargs (no bind:) calls the factory correctly."""
        cfg = tmp_json(json.dumps({"fn": {"call": f"{_MOD}._make_adder", "offset": 3}}))
        result = confarg.load(WithCallable, argv=[], env={}, files=[cfg])
        assert result.fn(7) == 10

    def test_call_from_cli(self) -> None:
        """--fn.call + --fn.bind.<kwarg> via CLI calls the factory."""
        result = confarg.load(
            WithCallable,
            argv=[f"--fn.call={_MOD}._make_multiplier", "--fn.bind.factor=4"],
            env={},
        )
        assert result.fn(3) == 12

    def test_call_coerces_kwargs_from_cli(self) -> None:
        """call: via CLI coerces string tokens to parameter types."""
        result = confarg.load(
            WithCallable,
            argv=[f"--fn.call={_MOD}._make_adder", "--fn.bind.offset=7"],
            env={},
        )
        assert result.fn(0) == 7

    def test_call_non_callable_result_raises(self, tmp_json: Any) -> None:
        """call: raises TypeCoercionError when the factory returns a non-callable."""
        cfg = tmp_json(json.dumps({"fn": {"call": f"{_MOD}._bad_factory", "bind": {"x": 1}}}))
        with pytest.raises(TypeCoercionError, match="not callable"):
            confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])

    def test_call_and_fn_together_raises(self, tmp_json: Any) -> None:
        """Specifying both call: and fn: raises TypeCoercionError."""
        cfg = tmp_json(
            json.dumps({"fn": {"call": f"{_MOD}._make_adder", "fn": f"{_MOD}._double", "bind": {"offset": 1}}}),
        )
        with pytest.raises(TypeCoercionError, match="more than one of"):
            confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])

    def test_call_and_class_together_raises(self, tmp_json: Any) -> None:
        """Specifying both call: and class: raises TypeCoercionError."""
        cfg = tmp_json(
            json.dumps({"fn": {"call": f"{_MOD}._make_adder", "class": f"{_MOD}._Multiplier", "bind": {"offset": 1}}}),
        )
        with pytest.raises(TypeCoercionError, match="more than one of"):
            confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])

    def test_call_unknown_kwarg_raises(self, tmp_json: Any) -> None:
        """call: raises TypeCoercionError for unknown kwargs."""
        cfg = tmp_json(json.dumps({"fn": {"call": f"{_MOD}._make_adder", "bind": {"bad_param": 1}}}))
        with pytest.raises(TypeCoercionError, match="Unknown kwargs"):
            confarg.load(WithCallable, argv=[], env={}, files=[cfg])


class TestEscapedDirectiveMode:
    """Scheme C: an escaped opener (_fn/_class/_call) frees every plain word.

    In escaped mode the underscore forms are the directives, so plain words like
    ``bind``/``fn`` become ordinary constructor kwargs, resolving collisions with a
    callable's own parameter names.
    """

    def test_escaped_mode_sets_init_bind_and_binds_call(self, tmp_json: Any) -> None:
        """_class opener: plain 'bind' sets __init__, '_bind' partial-applies __call__."""
        cfg = tmp_json(json.dumps({"fn": {"_class": f"{_MOD}._InitBind", "bind": 5, "_bind": {"lr": 10}}}))
        result = confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])
        assert result.fn() == 15  # _InitBind(bind=5), partial(lr=10) -> 5 + 10

    def test_plain_mode_cannot_set_init_bind(self, tmp_json: Any) -> None:
        """In plain mode 'bind' is the directive, so an __init__ 'bind' param is unreachable."""
        cfg = tmp_json(json.dumps({"fn": {"class": f"{_MOD}._InitBind", "bind": 5}}))
        with pytest.raises(TypeCoercionError, match="must be a dict"):
            confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])

    def test_escaped_mode_frees_fn_as_init_kwarg(self, tmp_json: Any) -> None:
        """_fn opener: a plain 'fn' key is a constructor kwarg of the method's owning class."""
        cfg = tmp_json(json.dumps({"fn": {"_fn": f"{_MOD}._OwnerWithFn.method", "fn": 100}}))
        result = confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])
        assert result.fn(1) == 101  # _OwnerWithFn(fn=100).method(1) -> 1 + 100

    def test_lenient_stray_escaped_key_is_data(self, tmp_json: Any) -> None:
        """No guard rail: a stray '_bind' under a plain opener is passed as data (errors if rejected)."""
        cfg = tmp_json(json.dumps({"fn": {"class": f"{_MOD}._Multiplier", "factor": 3, "_bind": 1}}))
        with pytest.raises(TypeCoercionError, match="Unknown field"):
            confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])
