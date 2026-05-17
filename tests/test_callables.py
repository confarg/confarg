# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for Callable type support."""

from __future__ import annotations

import enum
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
    _import_dotted,
    _instance_method_owner,
    _resolve_bind_kwargs,
    _serialize_callable,
    _SpecContext,
)
from confarg._types import _callable_param_types, _is_callable
from confarg.exceptions import ConfargError, SymbolImportError, TypeCoercionError
from confarg.typedload._construct import construct

# ---------------------------------------------------------------------------
# Helpers defined at module level so they are importable by dotted path
# ---------------------------------------------------------------------------


def _double(x: int) -> int:
    return x * 2


def _add(x: int, y: int) -> int:  # noqa: FURB118  # a user function with its own dotted path, not operator.add
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


@dataclass(frozen=True)
class _FrozenMultiplier:
    """A callable instance that refuses attributes, so nothing can be stamped on it."""

    factor: int

    def __call__(self, x: int) -> int:
        return x * self.factor


class _HiddenMultiplier:
    """A callable instance that keeps its argument under another name, so its state cannot be read."""

    def __init__(self, factor: int) -> None:
        self._factor = factor

    def __call__(self, x: int) -> int:
        return x * self._factor


class _CallableWithClassfn:
    """A callable instance whose constructor parameter is named like the ``classfn`` opener."""

    def __init__(self, classfn: int) -> None:
        self.classfn = classfn

    def __call__(self, x: int) -> int:
        return x + self.classfn


class _Processor:
    """Class with an instance method used as a callable."""

    def __init__(self, offset: int) -> None:
        self.offset = offset

    def process(self, x: int) -> int:
        return x + self.offset


class _NoArgProcessor:
    """Class with a no-arg constructor and an instance method.

    Used to test bind: auto-instantiation of an instance method's owner.
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


def _pick(name: str) -> Callable[[int], int]:
    """Factory function: returns one of the module's functions, shared with any other configuration."""
    return {"double": _double}[name]


def _greeter(name: str) -> Callable[[], str]:
    """Factory function: returns a partial of a module function, holding its argument."""
    return functools.partial(_greet, name=name)


def _multiplier(factor: int) -> Callable[[int], int]:
    """Factory function: returns a callable instance it built itself, which no ``class:`` spec built."""
    return _Multiplier(factor)


def _impostor(x: int) -> int:
    """A function whose qualified name is another function's, so its dotted path imports that one."""
    return x


_impostor.__qualname__ = "_double"


def _bad_factory(x: int) -> int:
    """Factory that returns a non-callable (used to test error path)."""
    return x * 2


class _InitBind:
    """Callable class whose __init__ takes a parameter named 'bind'.

    Beside class:, every other key is a field, so the 'bind' argument is settable *while* an
    outer bind: partially applies __call__.
    """

    def __init__(self, bind: int) -> None:
        self.bind = bind

    def __call__(self, lr: int) -> int:
        return self.bind + lr


class _OwnerWithBind:
    """Class whose __init__ takes a parameter named 'bind', with an instance method.

    Beside classfn:, every other key builds the owner, so a constructor argument named like
    an opener is reachable.
    """

    def __init__(self, bind: int) -> None:
        self.bind = bind

    def method(self, x: int) -> int:
        return x + self.bind


def _with_fn_param(fn: int, x: int) -> int:
    """A function with a parameter named 'fn', which is no directive word."""
    return fn + x


def _with_classfn_param(classfn: int, x: int) -> int:
    """A function with a parameter named like the classfn opener."""
    return classfn + x


class _Scaler:
    """Owner and method that share the parameter name ``k``, with a static and a class method.

    The constructor needs ``k``, so building it with no arguments fails: a path that does
    not need an owner must not try to build one.
    """

    def __init__(self, k: int) -> None:
        self.k = k

    def scale(self, k: int) -> int:
        return self.k * k

    def adder(self, k: int) -> Callable[[int], int]:
        return lambda x: x + self.k + k

    @staticmethod
    def static_double(x: int) -> int:
        return x * 2

    @classmethod
    def class_triple(cls, x: int) -> int:
        return x * 3


class _ScalerSub(_Scaler):
    """Inherits ``_Scaler``'s class method, which a path through it binds to the subclass."""


class _ProcessorSub(_Processor):
    """Inherits ``process`` from a base whose constructor needs an argument; its own has a default.

    Only its own constructor builds it with no arguments, so a result shows which one ran. It
    stores its argument as it is, as an owner whose state dumps must.
    """

    def __init__(self, offset: int = 50) -> None:
        super().__init__(offset=offset)


class _Shifter:
    """A callable class with a subclass: a spec naming it must build it, not ask which subclass."""

    def __init__(self, by: int) -> None:
        self.by = by

    def __call__(self, x: int) -> int:
        return x + self.by

    def shift(self, x: int) -> int:
        return x + self.by


class _NegShifter(_Shifter):
    """Subclass of _Shifter, which a spec naming _Shifter must not need to rule out."""

    def __call__(self, x: int) -> int:
        return x - self.by


def _processor_method(offset: int) -> Callable[[int], int]:
    """Factory function: returns a method bound to an owner it built itself, with state."""
    return _Processor(offset).process


@dataclass(frozen=True)
class _FrozenProcessor:
    """An owner that refuses attributes, so nothing can be stamped on it."""

    offset: int

    def process(self, x: int) -> int:
        return x + self.offset


class _HiddenProcessor:
    """An owner that keeps its argument under another name, so its state cannot be read."""

    def __init__(self, offset: int) -> None:
        self._offset = offset

    def process(self, x: int) -> int:
        return x + self._offset


class _Tone(enum.Enum):
    """An owner whose class is no struct: no spec builds a member from fields."""

    LOW = 1

    def shift(self, x: int) -> int:
        return x + self.value


class _OwnerWithClassfn:
    """An owner whose constructor parameter is named like the opener a ``classfn:`` spec holds."""

    def __init__(self, classfn: int) -> None:
        self.classfn = classfn

    def method(self, x: int) -> int:
        return x + self.classfn


# Module path prefix used throughout tests
_MOD = "tests.test_callables"


def _no_owner(owner: Any) -> dict[str, Any]:
    """Stand in for the owner-field reader where no callable serialized is a bound method."""
    pytest.fail(f"no owner to read, got {owner!r}")


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
# _instance_method_owner
# ---------------------------------------------------------------------------


class TestInstanceMethodOwner:
    """The owner of an instance method is the class its dotted path names."""

    def test_instance_method(self) -> None:
        """An instance method's owner is the class before its last segment."""
        assert _instance_method_owner(f"{_MOD}._Processor.process") is _Processor

    def test_inherited_method_is_owned_by_the_named_class(self) -> None:
        """A method a base defines is owned by the class the path names, not by the base."""
        assert _instance_method_owner(f"{_MOD}._ProcessorSub.process") is _ProcessorSub

    def test_module_level_fn(self) -> None:
        """A module-level function has no owner."""
        assert _instance_method_owner(f"{_MOD}._double") is None

    @pytest.mark.parametrize("name", ["static_double", "class_triple", "__init__"])
    def test_methods_that_need_no_instance(self, name: str) -> None:
        """A static method, a class method and ``__init__`` have no owner to build."""
        assert _instance_method_owner(f"{_MOD}._Scaler.{name}") is None

    def test_a_class_has_no_owner(self) -> None:
        """A class named by a path is no method."""
        assert _instance_method_owner(f"{_MOD}._Scaler") is None


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

    def test_method_requiring_args_error_points_to_classfn(self) -> None:
        """The error for a method needing constructor args gives the classfn: spec to paste."""
        # _Processor.process is an instance method whose __init__ requires `offset`.
        with pytest.raises(TypeCoercionError) as exc_info:
            confarg.load(
                WithCallable,
                argv=["--fn", f"{_MOD}._Processor.process"],
                env={},
            )
        msg = str(exc_info.value)
        assert "Cannot instantiate" in msg
        assert f"  classfn: {_MOD}._Processor.process\n  offset: <value>" in msg

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
# bind: dict form  (via JSON config files for nested dicts)
# ---------------------------------------------------------------------------


class TestBindDictForm:
    """Tests for the bind: dict form: a partial of its target, the arguments under args applied (FEAT-30)."""

    def test_bind_no_siblings_is_the_bare_target(self, tmp_json: Any) -> None:
        """bind: with no argument is the bare string: the function itself, not a partial."""
        cfg = tmp_json(json.dumps({"fn": {"bind": f"{_MOD}._double"}}))
        result = confarg.load(WithCallable, argv=[], env={}, files=[cfg])
        assert result.fn is _double

    def test_bind_with_siblings(self, tmp_json: Any) -> None:
        """bind: pre-applies the arguments under args."""
        cfg = tmp_json(json.dumps({"fn": {"bind": f"{_MOD}._add", "args": {"y": 10}}}))
        result = confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])
        assert isinstance(result.fn, functools.partial)
        assert result.fn.keywords == {"y": 10}
        assert result.fn(5) == 15

    def test_bind_with_siblings_via_cli(self) -> None:
        """--fn.bind + --fn.args.<param> via CLI pre-applies the argument."""
        result = confarg.load(
            WithBareCallable,
            argv=[f"--fn.bind={_MOD}._add", "--fn.args.y=10"],
            env={},
        )
        assert result.fn(5) == 15

    def test_bind_class_no_siblings_is_the_bare_factory(self, tmp_json: Any) -> None:
        """bind: naming a class with no argument is the bare class string: a factory partial."""
        cfg = tmp_json(json.dumps({"fn": {"bind": f"{_MOD}._Multiplier"}}))
        result = confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])
        assert isinstance(result.fn, functools.partial)
        assert result.fn.func is _Multiplier
        assert result.fn.keywords == {}

    def test_bind_class_with_siblings_is_a_factory(self, tmp_json: Any) -> None:
        """bind: naming a class with arguments returns a partial constructor."""
        cfg = tmp_json(json.dumps({"fn": {"bind": f"{_MOD}._Multiplier", "args": {"factor": 3}}}))
        result = confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])
        assert isinstance(result.fn, functools.partial)
        instance = result.fn()
        assert instance(4) == 12

    def test_bind_class_factory_is_checked_against_the_return_type(self, tmp_json: Any) -> None:
        """A class the Callable's return type rules out is refused under bind: as it is bare."""
        cfg = tmp_json(json.dumps({"fn": {"bind": f"{_MOD}._Multiplier", "args": {"factor": 3}}}))
        with pytest.raises(TypeCoercionError, match=r"used as a factory.*class: "):
            confarg.load(WithCallable, argv=[], env={}, files=[cfg])

    def test_classfn_instance_method_with_init(self, tmp_json: Any) -> None:
        """classfn: with an instance method builds its owner from the sibling keys."""
        cfg = tmp_json(json.dumps({"fn": {"classfn": f"{_MOD}._Processor.process", "offset": 7}}))
        result = confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])
        assert result.fn(3) == 10

    def test_bind_fully_bound(self, tmp_json: Any) -> None:
        """bind: with every parameter given under args leaves a zero-argument callable."""

        @dataclass
        class Target:
            fn: Callable[[], int]

        cfg = tmp_json(json.dumps({"fn": {"bind": f"{_MOD}._add", "args": {"x": 1, "y": 2}}}))
        result = confarg.load(Target, argv=[], env={}, files=[cfg])
        assert result.fn() == 3

    def test_bind_and_call_together_raises(self, tmp_json: Any) -> None:
        """Specifying both bind: and call:, two computations, raises TypeCoercionError."""
        cfg = tmp_json(json.dumps({"fn": {"bind": f"{_MOD}._double", "call": f"{_MOD}._make_adder"}}))
        with pytest.raises(TypeCoercionError, match="more than one of"):
            confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])

    def test_bind_beside_class_is_a_field_of_the_class(self, tmp_json: Any) -> None:
        """Beside class:, which builds an object, a bind key is one of its fields, not a second opener."""
        cfg = tmp_json(json.dumps({"fn": {"bind": f"{_MOD}._double", "class": f"{_MOD}._Multiplier"}}))
        with pytest.raises(TypeCoercionError, match=r"Unknown field\(s\) \['bind'\] for _Multiplier"):
            confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])

    def test_a_key_beside_bind_other_than_args_is_refused(self, tmp_json: Any) -> None:
        """A computation's arguments go under args, so a key beside the opener is refused, saying so."""
        cfg = tmp_json(json.dumps({"fn": {"bind": f"{_MOD}._add", "y": 10}}))
        with pytest.raises(TypeCoercionError, match=r"holds \['y'\] beside 'bind'.*go under 'args'"):
            confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])

    def test_args_that_is_no_mapping_is_refused(self, tmp_json: Any) -> None:
        """Args holds the arguments by name, so a list is refused."""
        cfg = tmp_json(json.dumps({"fn": {"bind": f"{_MOD}._add", "args": [1, 2]}}))
        with pytest.raises(TypeCoercionError, match=r"'args' at 'fn' takes the target's arguments by name, got list"):
            confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])

    def test_no_opener_raises(self, tmp_json: Any) -> None:
        """A dict without an opener raises TypeCoercionError naming the four."""
        cfg = tmp_json(json.dumps({"fn": {"x": 1}}))
        with pytest.raises(TypeCoercionError, match=r"one of 'bind', 'class', 'call' or 'classfn'"):
            confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])

    def test_fn_is_no_opener(self, tmp_json: Any) -> None:
        """The removed fn: opener is an ordinary key, so a spec holding only it has no opener."""
        cfg = tmp_json(json.dumps({"fn": {"fn": f"{_MOD}._double"}}))
        with pytest.raises(TypeCoercionError, match=r"must specify one of 'bind', 'class', 'call' or 'classfn'"):
            confarg.load(WithCallable, argv=[], env={}, files=[cfg])

    def test_fn_is_an_ordinary_argument(self, tmp_json: Any) -> None:
        """A target parameter named fn is filled under args, with no escaping."""
        cfg = tmp_json(json.dumps({"fn": {"bind": f"{_MOD}._with_fn_param", "args": {"fn": 4}}}))
        result = confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])
        assert result.fn(x=3) == 7

    def test_kwargs_dict_under_bind_is_refused(self, tmp_json: Any) -> None:
        """The removed bind: kwargs dict reads as a target spec with no opener, refused one key below."""
        cfg = tmp_json(json.dumps({"fn": {"bind": {"y": 3}}}))
        with pytest.raises(TypeCoercionError, match=r"at 'fn\.bind' must specify one of"):
            confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])

    def test_bind_target_of_another_type_is_refused(self, tmp_json: Any) -> None:
        """A bind: target that is neither a path nor a spec is refused, naming the sibling form."""
        cfg = tmp_json(json.dumps({"fn": {"bind": 5}}))
        with pytest.raises(TypeCoercionError, match=r"takes a dotted path or a callable spec, got int"):
            confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])

    def test_sibling_for_a_function_without_that_parameter_raises(self, tmp_json: Any) -> None:
        """An argument the target does not take is refused."""
        cfg = tmp_json(json.dumps({"fn": {"bind": f"{_MOD}._double", "args": {"offset": 5}}}))
        with pytest.raises(TypeCoercionError, match=r"Unknown bind parameter\(s\) \['offset'\]"):
            confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])

    def test_bind_env_json(self) -> None:
        """bind: dict form specified as JSON in an env var."""
        spec = json.dumps({"bind": f"{_MOD}._add", "args": {"y": 3}})
        result = confarg.load(WithBareCallable, argv=[], env={"CONFARG_FN": spec}, env_prefix="CONFARG_")
        assert result.fn(2) == 5

    def test_bind_env_json_optional(self) -> None:
        """An optional callable decodes the spec its non-optional peer decodes (BUG-17)."""
        spec = json.dumps({"bind": f"{_MOD}._add", "args": {"y": 3}})
        result = confarg.load(WithOptionalCallable, argv=[], env={"CONFARG_FN": spec}, env_prefix="CONFARG_")
        assert result.fn is not None
        assert result.fn(2) == 5


class TestBindTargetSpec:
    """A bind: target may be a callable spec of its own; the outer args apply to its result."""

    def test_partial_over_a_class_instance(self, tmp_json: Any) -> None:
        """bind: over a class: spec partially applies the instance's __call__."""

        @dataclass
        class Target:
            fn: Callable[[], int]

        cfg = tmp_json(json.dumps({"fn": {"bind": {"class": f"{_MOD}._Multiplier", "factor": 4}, "args": {"x": 2}}}))
        result = confarg.load(Target, argv=[], env={}, files=[cfg])
        assert isinstance(result.fn, functools.partial)
        assert isinstance(result.fn.func, _Multiplier)
        assert result.fn() == 8

    def test_target_spec_without_siblings_is_its_result(self, tmp_json: Any) -> None:
        """A target spec with no outer argument is the inner result itself."""
        cfg = tmp_json(json.dumps({"fn": {"bind": {"call": f"{_MOD}._make_multiplier", "args": {"factor": 3}}}}))
        result = confarg.load(WithCallable, argv=[], env={}, files=[cfg])
        assert not isinstance(result.fn, functools.partial)
        assert result.fn(2) == 6

    def test_target_spec_via_cli(self) -> None:
        """--fn.bind.class + --fn.bind.<ctor arg> + --fn.args.<call arg> on the CLI."""

        @dataclass
        class Target:
            fn: Callable[[], int]

        result = confarg.load(
            Target,
            argv=[f"--fn.bind.class={_MOD}._Multiplier", "--fn.bind.factor=4", "--fn.args.x=2"],
            env={},
        )
        assert result.fn() == 8

    def test_inner_argument_error_names_the_inner_path(self, tmp_json: Any) -> None:
        """An argument the inner target refuses is named at the inner spec's path."""
        cfg = tmp_json(json.dumps({"fn": {"bind": {"call": f"{_MOD}._make_adder", "args": {"bad": 1}}}}))
        with pytest.raises(TypeCoercionError, match=r"Unknown kwargs \['bad'\] .* at 'fn\.bind\.args'"):
            confarg.load(WithCallable, argv=[], env={}, files=[cfg])


# ---------------------------------------------------------------------------
# bind: auto-instantiation of an instance method's owner
# ---------------------------------------------------------------------------


class TestBindAutoInstantiation:
    """An instance method named by bind: (or bare) is bound to an owner built with no arguments.

    With constructor arguments for the owner, the spec is classfn:, whose other keys are the
    owner's constructor arguments.
    """

    def test_bind_instance_method_auto_instantiates(self, tmp_json: Any) -> None:
        """bind: with an instance method auto-instantiates the owning class (no-arg ctor)."""
        cfg = tmp_json(json.dumps({"fn": {"bind": f"{_MOD}._NoArgProcessor.transform"}}))
        result = confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])
        # _NoArgProcessor() is created automatically; transform(x) returns x * 3
        assert result.fn(4) == 12

    def test_bind_instance_method_returns_bound_method(self, tmp_json: Any) -> None:
        """bind: auto-instantiation without siblings produces a bound method (not a partial)."""
        cfg = tmp_json(json.dumps({"fn": {"bind": f"{_MOD}._NoArgProcessor.transform"}}))
        result = confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])
        assert not isinstance(result.fn, functools.partial)
        assert callable(result.fn)

    def test_bind_instance_method_siblings_are_method_arguments(self, tmp_json: Any) -> None:
        """An argument of bind: is an argument of the method, never of its owner."""

        @dataclass
        class Target:
            fn: Callable[[], int]

        cfg = tmp_json(json.dumps({"fn": {"bind": f"{_MOD}._NoArgProcessor.transform", "args": {"x": 4}}}))
        result = confarg.load(Target, argv=[], env={}, files=[cfg])
        assert result.fn() == 12

    def test_classfn_with_sibling_kwargs_constructs_owning_class(self, tmp_json: Any) -> None:
        """classfn: with sibling kwargs builds the owning class from them, then takes the bound method."""
        cfg = tmp_json(json.dumps({"fn": {"classfn": f"{_MOD}._Processor.process", "offset": 5}}))
        result = confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])
        # _Processor(offset=5) is constructed; process(x) returns x + 5
        assert result.fn(10) == 15

    def test_bind_instance_method_owner_needing_args_raises(self, tmp_json: Any) -> None:
        """bind: raises when the owning class needs constructor args."""
        cfg = tmp_json(json.dumps({"fn": {"bind": f"{_MOD}._Processor.process"}}))
        with pytest.raises(TypeCoercionError, match="Cannot instantiate"):
            confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])

    def test_bind_instance_method_owner_error_gives_the_classfn_spec(self, tmp_json: Any) -> None:
        """The failed auto-instantiation gives the classfn: spec, the owner's constructor listed in it."""
        cfg = tmp_json(json.dumps({"fn": {"bind": f"{_MOD}._Processor.process"}}))
        with pytest.raises(TypeCoercionError) as exc_info:
            confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])
        msg = str(exc_info.value)
        assert f"  classfn: {_MOD}._Processor.process\n  offset: <value>" in msg
        assert "'bind:'" in msg  # the spec is the target, the method's own arguments under its args

    def test_inherited_method_builds_the_named_class(self) -> None:
        """A method a base defines is bound to an instance of the class the path names."""
        cfg = confarg.build(WithBareCallable, {"fn": f"{_MOD}._ProcessorSub.process"})
        assert cfg.fn(1) == 51  # _ProcessorSub(), offset 50

    def test_call_binds_an_instance_method_as_bind_does(self) -> None:
        """call: naming an instance method calls it on an owner built with no arguments."""
        cfg = confarg.build(_TypedCallHolder, {"n": {"call": f"{_MOD}._NoArgProcessor.transform", "args": {"x": 2}}})
        assert cfg.n == 6


class TestOwnerlessMethods:
    """A static or a class method needs no owner, so no form builds one for it."""

    @pytest.mark.parametrize(("name", "expected"), [("static_double", 8), ("class_triple", 12)])
    def test_bare_path(self, name: str, expected: int) -> None:
        """The bare path names the method itself; the owner, which needs an argument, is not built."""
        cfg = confarg.build(WithCallable, {"fn": f"{_MOD}._Scaler.{name}"})
        assert cfg.fn(4) == expected

    @pytest.mark.parametrize(("name", "expected"), [("static_double", 8), ("class_triple", 12)])
    def test_bind(self, name: str, expected: int) -> None:
        """bind: applies its arguments to the method itself."""

        @dataclass
        class Target:
            fn: Callable[[], int]

        cfg = confarg.build(Target, {"fn": {"bind": f"{_MOD}._Scaler.{name}", "args": {"x": 4}}})
        assert cfg.fn() == expected

    @pytest.mark.parametrize(("name", "expected"), [("static_double", 8), ("class_triple", 12)])
    def test_call(self, name: str, expected: int) -> None:
        """call: calls the method itself with its arguments."""
        cfg = confarg.build(_TypedCallHolder, {"n": {"call": f"{_MOD}._Scaler.{name}", "args": {"x": 4}}})
        assert cfg.n == expected


class TestClassfn:
    """classfn: names an instance method; its other keys are the owner's constructor arguments (FEAT-31)."""

    def test_without_siblings_builds_the_owner_with_no_arguments(self) -> None:
        """With no sibling, the owner is built with no arguments, as for the bare path."""
        cfg = confarg.build(WithBareCallable, {"fn": {"classfn": f"{_MOD}._NoArgProcessor.transform"}})
        assert inspect.ismethod(cfg.fn)
        assert cfg.fn(4) == 12

    def test_siblings_build_the_owner_not_the_method(self) -> None:
        """The owner takes k; the method, which also has a k, is left for the caller."""
        cfg = confarg.build(WithCallable, {"fn": {"classfn": f"{_MOD}._Scaler.scale", "k": 3}})
        assert cfg.fn(5) == 15

    def test_an_owner_with_subclasses_is_built_as_named(self) -> None:
        """The owner is the class the path names, whatever subclasses it has."""
        cfg = confarg.build(WithCallable, {"fn": {"classfn": f"{_MOD}._Shifter.shift", "by": 2}})
        assert inspect.ismethod(cfg.fn)
        assert type(cfg.fn.__self__) is _Shifter
        assert cfg.fn(1) == 3

    def test_inherited_method_builds_the_named_class(self) -> None:
        """The owner is the class the path names, built with that class's constructor."""
        cfg = confarg.build(WithCallable, {"fn": {"classfn": f"{_MOD}._ProcessorSub.process", "offset": 5}})
        assert inspect.ismethod(cfg.fn)
        assert type(cfg.fn.__self__) is _ProcessorSub
        assert cfg.fn(1) == 6

    def test_bind_over_classfn_applies_the_method_arguments(self) -> None:
        """bind: over a classfn: spec: the inner k builds the owner, the outer k is the method's."""

        @dataclass
        class Target:
            fn: Callable[[], int]

        spec = {"bind": {"classfn": f"{_MOD}._Scaler.scale", "k": 3}, "args": {"k": 5}}
        cfg = confarg.build(Target, {"fn": spec})
        assert cfg.fn() == 15

    def test_call_over_classfn_in_a_typed_field(self) -> None:
        """call: over a classfn: spec calls C(**init).m(**args) and takes its value as the field."""
        spec = {"call": {"classfn": f"{_MOD}._Scaler.scale", "k": 3}, "args": {"k": 5}}
        cfg = confarg.build(_TypedCallHolder, {"n": spec})
        assert cfg.n == 15

    def test_call_over_classfn_in_a_callable_field(self) -> None:
        """call: over a classfn: spec in a Callable field: the method's return value is the callable."""
        spec = {"call": {"classfn": f"{_MOD}._Scaler.adder", "k": 1}, "args": {"k": 10}}
        cfg = confarg.build(WithCallable, {"fn": spec})
        assert cfg.fn(100) == 111

    def test_call_target_may_be_any_callable_spec(self) -> None:
        """call: takes a callable spec as its target, as bind: does: here a class: instance."""
        spec = {"call": {"class": f"{_MOD}._Multiplier", "factor": 3}, "args": {"x": 4}}
        cfg = confarg.build(_TypedCallHolder, {"n": spec})
        assert cfg.n == 12

    def test_call_target_of_another_shape_is_refused(self) -> None:
        """call: takes a dotted path or a callable spec, nothing else."""
        with pytest.raises(TypeCoercionError, match=r"'call' at 'n' takes a dotted path or a callable spec"):
            confarg.build(_TypedCallHolder, {"n": {"call": 3}})

    @pytest.mark.parametrize("name", ["_double", "_Scaler.static_double", "_Scaler.class_triple", "_Multiplier"])
    def test_a_target_that_is_no_instance_method_is_refused(self, name: str) -> None:
        """A function, a static or class method, or a class needs no owner, and is pointed to bind:."""
        with pytest.raises(TypeCoercionError, match=r"instance method.*'bind: ") as exc_info:
            confarg.build(WithBareCallable, {"fn": {"classfn": f"{_MOD}.{name}"}})
        assert f"{_MOD}.{name}" in str(exc_info.value)

    def test_a_target_that_is_no_dotted_path_is_refused(self) -> None:
        """classfn: names a method by its dotted path; a nested spec is refused."""
        with pytest.raises(TypeCoercionError, match=r"'classfn' at 'fn' takes the dotted path"):
            confarg.build(WithBareCallable, {"fn": {"classfn": {"bind": f"{_MOD}._double"}}})

    def test_unknown_owner_argument_is_refused(self) -> None:
        """A sibling the owner's constructor does not take is refused."""
        with pytest.raises(TypeCoercionError, match="bad"):
            confarg.build(WithBareCallable, {"fn": {"classfn": f"{_MOD}._Scaler.scale", "k": 1, "bad": 2}})

    def test_classfn_beside_class_is_refused(self) -> None:
        """Classfn and class both build an object, so beside each other they are two openers."""
        spec = {"classfn": f"{_MOD}._Scaler.scale", "class": f"{_MOD}._Multiplier"}
        with pytest.raises(TypeCoercionError, match="more than one of"):
            confarg.build(WithBareCallable, {"fn": spec})

    def test_bind_beside_classfn_is_a_field_of_the_owner(self) -> None:
        """Beside classfn:, a bind key is one of the owner's fields, not a second opener."""
        spec = {"classfn": f"{_MOD}._Scaler.scale", "bind": f"{_MOD}._double"}
        with pytest.raises(TypeCoercionError, match=r"Unknown field\(s\) \['bind'\] for _Scaler"):
            confarg.build(WithBareCallable, {"fn": spec})

    def test_round_trip(self) -> None:
        """The bound method dumps as the classfn: spec it was built from."""
        spec = {"classfn": f"{_MOD}._Scaler.scale", "k": 3}
        assert confarg.dump(confarg.build(WithCallable, {"fn": spec}))["fn"] == spec

    def test_round_trip_of_a_bind_over_classfn(self) -> None:
        """A partial over a classfn: method dumps the classfn: spec as its target."""

        @dataclass
        class Target:
            fn: Callable[[], int]

        spec = {"bind": {"classfn": f"{_MOD}._Scaler.scale", "k": 3}, "args": {"k": 5}}
        assert confarg.dump(confarg.build(Target, {"fn": spec}))["fn"] == spec


# ---------------------------------------------------------------------------
# class: dict form
# ---------------------------------------------------------------------------


class TestClassDictForm:
    """Tests for the class: dict form callable specification."""

    def test_class_with_subclasses_builds_the_named_class(self) -> None:
        """class: names the type wanted, so a class that has subclasses is built as named."""
        cfg = confarg.build(WithCallable, {"fn": {"class": f"{_MOD}._Shifter", "by": 2}})
        assert type(cfg.fn) is _Shifter
        assert cfg.fn(1) == 3

    def test_a_tag_beside_class_selects_nothing(self) -> None:
        """With a union tag other than class, a tag key beside class: is an unknown argument."""
        spec = {"class": f"{_MOD}._Shifter", "type": f"{_MOD}._NegShifter", "by": 2}
        with pytest.raises(TypeCoercionError, match=r"Unknown field\(s\) \['type'\] for _Shifter at 'fn'"):
            confarg.build(WithCallable, {"fn": spec}, union_tag="type")

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

    def test_class_with_bind_key_takes_it_as_a_field(self, tmp_json: Any) -> None:
        """The removed class: + bind: kwargs form reads bind as a field; the partial is bind: over class:."""
        cfg = tmp_json(json.dumps({"fn": {"class": f"{_MOD}._Multiplier", "factor": 4, "bind": {"x": 2}}}))
        with pytest.raises(TypeCoercionError, match=r"Unknown field\(s\) \['bind'\] for _Multiplier"):
            confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])

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
        assert _resolve_bind_kwargs(_add, {"x": 1, "y": 2}, _SpecContext(("f",), "class", construct)) == {
            "x": 1,
            "y": 2,
        }

    def test_unknown_key_raises(self) -> None:
        """An unknown bind key raises TypeCoercionError."""
        with pytest.raises(TypeCoercionError, match="Unknown bind parameter"):
            _resolve_bind_kwargs(_add, {"x": 1, "z": 99}, _SpecContext(("f",), "class", construct))

    def test_error_names_invalid_and_valid(self) -> None:
        """The error message names both invalid and valid keys."""
        with pytest.raises(TypeCoercionError, match="'z'") as exc_info:
            _resolve_bind_kwargs(_add, {"z": 1}, _SpecContext(("myfield",), "class", construct))
        assert "x" in str(exc_info.value)
        assert "y" in str(exc_info.value)

    def test_a_declared_self_is_an_ordinary_parameter(self) -> None:
        """A function that declares ``self`` accepts it as a kwarg: only *args and **kwargs are not fillable."""

        def handler(self: int, event: int) -> int:  # noqa: FURB118  # the declared self is the point, not operator.add
            return self + event

        assert _resolve_bind_kwargs(handler, {"self": 1}, _SpecContext(("f",), "class", construct)) == {"self": 1}

    def test_var_keyword_fn_skips_validation(self) -> None:
        """Test that **kwargs functions skip bind key validation."""
        _resolve_bind_kwargs(_kwargs_fn, {"anything": 1, "goes": 2}, _SpecContext(("f",), "class", construct))

    def test_uninspectable_skips_validation(self) -> None:
        """Uninspectable builtins skip bind key validation."""
        # len is a builtin with no inspectable signature on all platforms
        try:
            inspect.signature(len)
            pytest.skip("len is inspectable on this platform")
        except (ValueError, TypeError):
            pass
        assert _resolve_bind_kwargs(len, {"unknown": 1}, _SpecContext(("f",), "class", construct)) == {"unknown": 1}

    def test_bind_unknown_key_raises_via_load(self, tmp_json: Any) -> None:
        """An unknown argument of bind: raises via confarg.load, at the path of its args."""
        cfg = tmp_json(json.dumps({"fn": {"bind": f"{_MOD}._add", "args": {"z": 1}}}))
        with pytest.raises(TypeCoercionError, match=r"Unknown bind parameter.* at 'fn\.args'"):
            confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])

    def test_bind_over_class_unknown_key_raises_via_load(self, tmp_json: Any) -> None:
        """An unknown argument of bind: over a class: spec raises via confarg.load."""
        cfg = tmp_json(json.dumps({"fn": {"bind": {"class": f"{_MOD}._Multiplier", "factor": 2}, "args": {"bad": 1}}}))
        with pytest.raises(TypeCoercionError, match="Unknown bind parameter"):
            confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])

    def test_bind_over_classfn_unknown_key_raises_via_load(self, tmp_json: Any) -> None:
        """An unknown argument of bind: over a classfn: spec raises via confarg.load."""
        cfg = tmp_json(
            json.dumps({"fn": {"bind": {"classfn": f"{_MOD}._Processor.process", "offset": 1}, "args": {"bad": 9}}}),
        )
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
        assert _serialize_callable(_double, _no_owner) == f"{_MOD}._double"

    def test_partial(self) -> None:
        """A partial serializes to a bind: dict with its keywords under args."""
        p = functools.partial(_add, y=5)
        out = _serialize_callable(p, _no_owner)
        assert out == {"bind": f"{_MOD}._add", "args": {"y": 5}}

    @pytest.mark.parametrize(
        "keywords",
        [
            pytest.param({"fn": 1}, id="no-opener"),
            pytest.param({"bind": 1, "classfn": 2}, id="openers"),
            pytest.param({"_call": 1, "args": 2}, id="former-escaped-opener-and-args"),
        ],
    )
    def test_a_keyword_spelled_like_an_opener_round_trips_under_args(self, keywords: dict[str, int]) -> None:
        """Under args a keyword is an argument whatever it spells, so every partial dumps and reads back."""
        cfg = WithBareCallable(fn=functools.partial(_kwargs_fn, **keywords))
        dumped = confarg.dump(cfg)["fn"]
        assert dumped == {"bind": f"{_MOD}._kwargs_fn", "args": keywords}
        assert confarg.build(WithBareCallable, {"fn": dumped}).fn() == sum(keywords.values())

    def test_partial_no_bind(self) -> None:
        """A partial with no bound args serializes to the bare dotted path (round-trips to the callable)."""
        p = functools.partial(_double)
        out = _serialize_callable(p, _no_owner)
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

    @pytest.mark.parametrize(
        "path",
        [
            pytest.param("math.sqrt", id="builtin"),
            pytest.param(f"{_MOD}._Scaler.static_double", id="static-method"),
            pytest.param(f"{_MOD}._Scaler.class_triple", id="class-method"),
            pytest.param(f"{_MOD}._NoArgProcessor.transform", id="instance-method"),
            pytest.param(f"{_MOD}._ScalerSub.class_triple", id="inherited-class-method"),
        ],
    )
    def test_a_path_that_reads_back_dumps_as_itself(self, path: str) -> None:
        """A callable loaded from a path dumps as that path, a method bound to an owner with no fields included."""
        assert confarg.dump(confarg.build(WithBareCallable, {"fn": path}))["fn"] == path

    def test_an_inherited_method_dumps_through_the_class_it_is_bound_to(self) -> None:
        """A method a base defines is named through its owner's class, not by its qualified name.

        The qualified name names the base, and would read back bound to it (BUG-193).
        """
        cfg = confarg.build(WithBareCallable, {"fn": f"{_MOD}._ProcessorSub.process"})
        assert confarg.dump(cfg)["fn"] == {"classfn": f"{_MOD}._ProcessorSub.process", "offset": 50}

    @pytest.mark.parametrize(
        "fn",
        [
            pytest.param(_make_multiplier(2), id="closure"),
            pytest.param(_make_adder(1), id="lambda"),
            pytest.param(_impostor, id="shadowed"),
            pytest.param(_NoArgProcessor.transform, id="unbound-method"),
        ],
    )
    def test_a_callable_whose_path_does_not_read_back_cannot_be_dumped(self, fn: Callable[[int], int]) -> None:
        """A callable its dotted path does not import back as is refused at dump(), not on read-back.

        A closure's path holds ``<locals>`` and a lambda's ``<lambda>``; a shadowed name imports
        another object; an instance method's function reads back bound to a new owner (BUG-193).
        """
        with pytest.raises(ConfargError, match=r"no configuration spells it"):
            confarg.dump(WithBareCallable(fn=fn))

    def test_round_trip_partial(self, tmp_json: Any) -> None:
        """A partial round-trips through load and dump."""
        cfg = tmp_json(json.dumps({"fn": {"bind": f"{_MOD}._add", "args": {"y": 7}}}))
        result = confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])
        dumped = confarg.dump(result)
        assert dumped["fn"] == {"bind": f"{_MOD}._add", "args": {"y": 7}}

    def test_round_trip_partial_over_a_class_spec(self, tmp_json: Any) -> None:
        """A partial over a class: instance dumps its target as the class: spec of the fields it holds."""

        @dataclass
        class Target:
            fn: Callable[[], int]

        spec = {"bind": {"class": f"{_MOD}._Multiplier", "factor": 4}, "args": {"x": 2}}
        cfg = tmp_json(json.dumps({"fn": spec}))
        result = confarg.load(Target, argv=[], env={}, files=[cfg])
        assert confarg.dump(result)["fn"] == spec

    @pytest.mark.parametrize(
        "argv",
        [
            pytest.param(["--fn.class", f"{_MOD}._Multiplier", "--fn.factor", "2"], id="class"),
            pytest.param(["--fn.bind.class", f"{_MOD}._Multiplier", "--fn.bind.factor", "2"], id="nested"),
        ],
    )
    def test_a_spec_from_the_cli_dumps_the_values_built_from_its_tokens(self, argv: list[str]) -> None:
        """A spec the CLI spelled dumps what its instance holds, never the tokens it was parsed into."""
        dumped = confarg.dump(confarg.load(WithCallable, argv=argv, env={}))["fn"]
        assert dumped == {"class": f"{_MOD}._Multiplier", "factor": 2}
        assert type(dumped["class"]) is str
        assert type(dumped["factor"]) is int


class TestDumpOfACallResult:
    """A ``call:`` on a Callable field dumps as the callable it returned, never as the call (BUG-191)."""

    def test_a_returned_function_dumps_as_its_path(self) -> None:
        """A module function a factory returned dumps as its dotted path, which reads back without the call."""
        cfg = confarg.build(WithCallable, {"fn": {"call": f"{_MOD}._pick", "args": {"name": "double"}}})
        assert confarg.dump(cfg)["fn"] == f"{_MOD}._double"

    def test_a_shared_result_leaves_other_configurations_alone(self) -> None:
        """A configuration that names the function a factory also returned dumps that name, not the call."""
        confarg.build(WithCallable, {"fn": {"call": f"{_MOD}._pick", "args": {"name": "double"}}})
        cfg = confarg.build(WithCallable, {"fn": f"{_MOD}._double"})
        assert confarg.dump(cfg)["fn"] == f"{_MOD}._double"

    def test_a_returned_partial_dumps_as_bind(self) -> None:
        """A partial a factory returned dumps as ``bind:``, its argument as the plain str the CLI spelled."""
        cfg = confarg.load(WithBareCallable, argv=["--fn.call", f"{_MOD}._greeter", "--fn.args.name", "bob"], env={})
        dumped = confarg.dump(cfg)["fn"]
        assert dumped == {"bind": f"{_MOD}._greet", "args": {"name": "bob"}}
        assert type(dumped["args"]["name"]) is str

    def test_a_returned_closure_cannot_be_dumped(self, tmp_path: pathlib.Path) -> None:
        """A closure has no configuration spelling: the object refuses it, the merged dict keeps the call."""
        raw = {"fn": {"call": f"{_MOD}._make_adder", "args": {"offset": 2}}}
        with pytest.raises(ConfargError, match=r"no configuration spells it"):
            confarg.dump(confarg.build(WithCallable, raw))
        out = tmp_path / "out.json"
        confarg.dump_file(raw, out)
        assert json.loads(out.read_text())["fn"] == raw["fn"]

    def test_a_returned_instance_dumps_the_state_it_holds(self) -> None:
        """An instance the factory built dumps as the ``class:`` spec of its fields, never as the call (BUG-192)."""
        cfg = confarg.build(WithCallable, {"fn": {"call": f"{_MOD}._multiplier", "args": {"factor": 3}}})
        assert confarg.dump(cfg)["fn"] == {"class": f"{_MOD}._Multiplier", "factor": 3}


class TestDumpOfABoundMethod:
    """A bound method dumps the state its owner holds, as a ``classfn:`` spec (BUG-229).

    Its bare path reads back bound to an owner built with no arguments, which is the owner
    again only when that owner has no fields.
    """

    def test_an_owner_built_in_python_dumps_its_fields(self) -> None:
        """An owner the program built with arguments dumps them beside the path, and reads back as itself."""
        dumped = confarg.dump(WithCallable(fn=_Processor(100).process))["fn"]
        assert dumped == {"classfn": f"{_MOD}._Processor.process", "offset": 100}
        assert confarg.build(WithCallable, {"fn": dumped}).fn(1) == 101

    def test_an_owner_a_call_built_dumps_its_fields(self) -> None:
        """A method a factory returned dumps its owner's state, never the call."""
        cfg = confarg.build(WithCallable, {"fn": {"call": f"{_MOD}._processor_method", "args": {"offset": 100}}})
        assert confarg.dump(cfg)["fn"] == {"classfn": f"{_MOD}._Processor.process", "offset": 100}

    def test_a_change_after_build_is_dumped(self) -> None:
        """The owner's fields are read when dumping, so a change made after build() is kept."""
        cfg = confarg.build(WithCallable, {"fn": {"classfn": f"{_MOD}._Processor.process", "offset": 1}})
        assert inspect.ismethod(cfg.fn)
        owner = cfg.fn.__self__
        assert isinstance(owner, _Processor)
        owner.offset = 7
        assert confarg.dump(cfg)["fn"] == {"classfn": f"{_MOD}._Processor.process", "offset": 7}

    def test_an_owner_that_refuses_attributes_dumps_its_fields(self) -> None:
        """A frozen owner holds no stamp, and dumps from its fields all the same."""
        spec = {"classfn": f"{_MOD}._FrozenProcessor.process", "offset": 3}
        assert confarg.dump(confarg.build(WithCallable, {"fn": spec}))["fn"] == spec

    def test_an_owner_with_no_fields_dumps_as_the_path(self) -> None:
        """An owner built in Python with no fields holds what auto-binding builds, so the path stands."""
        dumped = confarg.dump(WithCallable(fn=_NoArgProcessor().transform))["fn"]
        assert dumped == f"{_MOD}._NoArgProcessor.transform"

    def test_a_partial_over_a_method_dumps_its_owner_as_the_target(self) -> None:
        """A partial's target is serialized by the same rules, its owner's fields included."""

        @dataclass
        class Target:
            fn: Callable[[], int]

        dumped = confarg.dump(Target(fn=functools.partial(_Processor(4).process, x=1)))["fn"]
        assert dumped == {"bind": {"classfn": f"{_MOD}._Processor.process", "offset": 4}, "args": {"x": 1}}
        assert confarg.build(Target, {"fn": dumped}).fn() == 5

    def test_an_owner_whose_state_cannot_be_read_is_refused(self) -> None:
        """An owner that keeps an argument under another name is refused, as a plain class field is."""
        with pytest.raises(ConfargError, match=r"_HiddenProcessor at 'fn': field 'offset' is declared"):
            confarg.dump(WithCallable(fn=_HiddenProcessor(3).process))

    def test_an_owner_that_is_no_struct_is_refused(self) -> None:
        """An enum member's method names no owner a spec could build, nor one a bare path reads back as."""
        with pytest.raises(ConfargError, match=r"no configuration spells it.*no fields a 'classfn:' spec could set"):
            confarg.dump(WithCallable(fn=_Tone.LOW.shift))

    def test_an_owner_field_named_classfn_is_refused(self) -> None:
        """A field named like the opener cannot sit beside it, so no spec spells the owner."""
        with pytest.raises(ConfargError, match=r"no configuration spells it.*'classfn'"):
            confarg.dump(WithCallable(fn=_OwnerWithClassfn(1).method))


class _Gain(enum.Enum):
    """A callable instance whose class is no struct: no spec builds a member from fields."""

    UNIT = 1

    def __call__(self, x: int) -> int:
        return x * self.value


class TestDumpOfAClassInstance:
    """A callable instance dumps the state it holds, as a ``class:`` spec (BUG-192).

    It is read as a bound method's owner is, so the two object openers dump alike.
    """

    def test_a_change_after_build_is_dumped(self) -> None:
        """The instance's fields are read when dumping, so a change made after build() is kept."""
        cfg = confarg.build(WithCallable, {"fn": {"class": f"{_MOD}._Multiplier", "factor": 3}})
        assert isinstance(cfg.fn, _Multiplier)
        cfg.fn.factor = 5
        assert confarg.dump(cfg)["fn"] == {"class": f"{_MOD}._Multiplier", "factor": 5}

    def test_an_instance_that_refuses_attributes_dumps_its_fields(self) -> None:
        """A frozen instance holds no stamp, and dumps from its fields all the same."""
        spec = {"class": f"{_MOD}._FrozenMultiplier", "factor": 3}
        assert confarg.dump(confarg.build(WithCallable, {"fn": spec}))["fn"] == spec

    def test_an_instance_built_in_python_dumps_its_fields(self) -> None:
        """An instance the program built dumps its fields, and reads back as itself."""
        dumped = confarg.dump(WithCallable(fn=_Multiplier(4)))["fn"]
        assert dumped == {"class": f"{_MOD}._Multiplier", "factor": 4}
        assert confarg.build(WithCallable, {"fn": dumped}).fn(2) == 8

    def test_an_instance_with_no_fields_dumps_as_its_opener_alone(self) -> None:
        """An instance whose constructor takes no argument is a ``class:`` spec holding nothing else.

        The bare path would read back as the class, used as a factory.
        """
        dumped = confarg.dump(WithCallable(fn=_NoArgCallable()))["fn"]
        assert dumped == {"class": f"{_MOD}._NoArgCallable"}
        assert confarg.build(WithCallable, {"fn": dumped}).fn(1) == 2

    def test_a_partial_over_an_instance_dumps_its_state_as_the_target(self) -> None:
        """A partial's target is serialized by the same rules, a change made after build() included."""

        @dataclass
        class Target:
            fn: Callable[[], int]

        cfg = confarg.build(Target, {"fn": {"bind": {"class": f"{_MOD}._Multiplier", "factor": 4}, "args": {"x": 2}}})
        assert isinstance(cfg.fn, functools.partial)
        assert isinstance(cfg.fn.func, _Multiplier)
        cfg.fn.func.factor = 6
        dumped = confarg.dump(cfg)["fn"]
        assert dumped == {"bind": {"class": f"{_MOD}._Multiplier", "factor": 6}, "args": {"x": 2}}
        assert confarg.build(Target, {"fn": dumped}).fn() == 12

    def test_an_instance_whose_state_cannot_be_read_is_refused(self) -> None:
        """An instance that keeps an argument under another name is refused, as a plain class field is."""
        cfg = confarg.build(WithCallable, {"fn": {"class": f"{_MOD}._HiddenMultiplier", "factor": 3}})
        with pytest.raises(ConfargError, match=r"_HiddenMultiplier at 'fn': field 'factor' is declared"):
            confarg.dump(cfg)

    def test_an_instance_that_is_no_struct_is_refused(self) -> None:
        """An enum member names no class a ``class:`` spec could build it from."""
        with pytest.raises(ConfargError, match=r"no configuration spells it.*no fields a 'class:' spec could set"):
            confarg.dump(WithCallable(fn=_Gain.UNIT))

    def test_a_field_named_classfn_is_refused(self) -> None:
        """A field named like the other object opener would read back as a second opener."""
        with pytest.raises(ConfargError, match=r"no configuration spells it.*'classfn'"):
            confarg.dump(WithCallable(fn=_CallableWithClassfn(1)))


class _CountedMultiplier:
    """A callable instance that counts how many times its constructor ran."""

    built = 0

    def __init__(self, factor: int) -> None:
        type(self).built += 1
        self.factor = factor

    def __call__(self, x: int) -> int:
        return x * self.factor


class TestDumpOfAnOptionalCallable:
    """An optional Callable dumps as its variant does: no other variant can take the dump back."""

    @pytest.mark.parametrize(
        ("fn", "expected"),
        [
            pytest.param(functools.partial(_add, y=1), {"bind": f"{_MOD}._add", "args": {"y": 1}}, id="partial"),
            pytest.param(_Processor(3).process, {"classfn": f"{_MOD}._Processor.process", "offset": 3}, id="method"),
            pytest.param(_Multiplier(2), {"class": f"{_MOD}._Multiplier", "factor": 2}, id="instance"),
        ],
    )
    @pytest.mark.filterwarnings("error::confarg.exceptions.ConfargWarning")
    def test_it_dumps_without_warning(self, fn: Callable[[int], int], expected: dict[str, Any]) -> None:
        """A value with no equality of its own still reads back, so no warning says it will not."""
        assert confarg.dump(WithOptionalCallable(fn=fn))["fn"] == expected

    @pytest.mark.filterwarnings("ignore::confarg.exceptions.ConfargWarning")
    def test_dump_builds_nothing(self) -> None:
        """No constructor runs to check the dump, as no path check builds one."""
        cfg = WithOptionalCallable(fn=_CountedMultiplier(2))
        _CountedMultiplier.built = 0
        confarg.dump(cfg)
        assert _CountedMultiplier.built == 0


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

    def test_classfn_method_path_with_constructor_kwarg(self) -> None:
        """--<flag>.classfn with a method path + --<flag>.<kwarg> for owning class constructor."""
        result = confarg.load(
            _WithNoneReturn,
            argv=[f"--fn.classfn={_MOD}._Processor.process", "--fn.offset=10"],
            env={},
        )
        assert result.fn(5) == 15


class TestBindInitMethod:
    """__init__ passed as the bind: target is treated as a plain function.

    No auto-instantiation occurs, and the arguments under args are partially applied to it as
    to any other plain function.
    """

    def test_bare_string_init_is_plain_function(self) -> None:
        """Test that __init__ as bare string resolves to the plain __init__ function."""
        result = confarg.load(
            WithBareCallable,
            argv=["--fn", f"{_MOD}._Processor.__init__"],
            env={},
        )
        assert result.fn is _Processor.__init__

    def test_dict_form_init_no_siblings(self, tmp_json: Any) -> None:
        """Test that __init__ as a bind: target resolves to the plain __init__ function."""
        cfg = tmp_json(json.dumps({"fn": {"bind": f"{_MOD}._Processor.__init__"}}))
        result = confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])
        assert result.fn is _Processor.__init__

    def test_dict_form_init_with_siblings(self, tmp_json: Any) -> None:
        """Test that __init__ as a bind: target with an argument produces a partial."""
        cfg = tmp_json(json.dumps({"fn": {"bind": f"{_MOD}._Processor.__init__", "args": {"offset": 5}}}))
        result = confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])
        assert isinstance(result.fn, functools.partial)
        assert result.fn.keywords == {"offset": 5}


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

    def test_call_with_the_removed_bind_kwargs_raises(self, tmp_json: Any) -> None:
        """call: beside a bind: kwargs dict is two openers; the arguments go under args."""
        cfg = tmp_json(json.dumps({"fn": {"call": f"{_MOD}._make_adder", "bind": {"offset": 5}}}))
        with pytest.raises(TypeCoercionError, match="more than one of"):
            confarg.load(WithCallable, argv=[], env={}, files=[cfg])

    def test_call_with_sibling_kwargs_from_file(self, tmp_json: Any) -> None:
        """call: with its kwargs under args calls the factory correctly."""
        cfg = tmp_json(json.dumps({"fn": {"call": f"{_MOD}._make_adder", "args": {"offset": 3}}}))
        result = confarg.load(WithCallable, argv=[], env={}, files=[cfg])
        assert result.fn(7) == 10

    def test_call_from_cli(self) -> None:
        """--fn.call + --fn.args.<kwarg> via CLI calls the factory."""
        result = confarg.load(
            WithCallable,
            argv=[f"--fn.call={_MOD}._make_multiplier", "--fn.args.factor=4"],
            env={},
        )
        assert result.fn(3) == 12

    def test_call_coerces_kwargs_from_cli(self) -> None:
        """call: via CLI coerces string tokens to parameter types."""
        result = confarg.load(
            WithCallable,
            argv=[f"--fn.call={_MOD}._make_adder", "--fn.args.offset=7"],
            env={},
        )
        assert result.fn(0) == 7

    def test_call_non_callable_result_raises(self, tmp_json: Any) -> None:
        """call: raises TypeCoercionError when the factory returns a non-callable."""
        cfg = tmp_json(json.dumps({"fn": {"call": f"{_MOD}._bad_factory", "args": {"x": 1}}}))
        with pytest.raises(TypeCoercionError, match="not callable"):
            confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])

    def test_call_and_bind_together_raises(self, tmp_json: Any) -> None:
        """Specifying both call: and bind: raises TypeCoercionError."""
        cfg = tmp_json(
            json.dumps({"fn": {"call": f"{_MOD}._make_adder", "bind": f"{_MOD}._double", "offset": 1}}),
        )
        with pytest.raises(TypeCoercionError, match="more than one of"):
            confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])

    def test_call_beside_class_is_a_field_of_the_class(self, tmp_json: Any) -> None:
        """Beside class:, a call key is one of the class's fields, not a second opener."""
        cfg = tmp_json(
            json.dumps({"fn": {"call": f"{_MOD}._make_adder", "class": f"{_MOD}._Multiplier", "factor": 1}}),
        )
        with pytest.raises(TypeCoercionError, match=r"Unknown field\(s\) \['call'\] for _Multiplier"):
            confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])

    def test_call_unknown_kwarg_raises(self, tmp_json: Any) -> None:
        """call: raises TypeCoercionError for unknown kwargs."""
        cfg = tmp_json(json.dumps({"fn": {"call": f"{_MOD}._make_adder", "args": {"bad_param": 1}}}))
        with pytest.raises(TypeCoercionError, match="Unknown kwargs"):
            confarg.load(WithCallable, argv=[], env={}, files=[cfg])


class TestOpenerWordsAsArguments:
    """No opener word needs escaping: an argument sits under args, a field beside class: or classfn:."""

    def test_class_takes_a_field_named_bind_and_an_outer_bind_applies_call(self, tmp_json: Any) -> None:
        """bind: over a class: spec: the inner 'bind' sets __init__, the outer args bind __call__."""
        cfg = tmp_json(json.dumps({"fn": {"bind": {"class": f"{_MOD}._InitBind", "bind": 5}, "args": {"lr": 10}}}))
        result = confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])
        assert result.fn() == 15  # _InitBind(bind=5), partial(lr=10) -> 5 + 10

    def test_class_takes_a_field_named_bind(self, tmp_json: Any) -> None:
        """Beside class:, 'bind' is a constructor argument."""
        cfg = tmp_json(json.dumps({"fn": {"class": f"{_MOD}._InitBind", "bind": 5}}))
        result = confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])
        assert result.fn(10) == 15

    def test_classfn_takes_an_owner_field_named_bind(self, tmp_json: Any) -> None:
        """Beside classfn:, 'bind' is a constructor argument of the method's owner."""
        cfg = tmp_json(json.dumps({"fn": {"classfn": f"{_MOD}._OwnerWithBind.method", "bind": 100}}))
        result = confarg.load(WithBareCallable, argv=[], env={}, files=[cfg])
        assert result.fn(1) == 101  # _OwnerWithBind(bind=100).method(1) -> 1 + 100

    def test_a_parameter_named_like_an_opener_is_an_argument_under_args(self) -> None:
        """A parameter named classfn is filled under args, and dumps back that way."""
        spec = {"bind": f"{_MOD}._with_classfn_param", "args": {"classfn": 2}}
        cfg = confarg.build(WithBareCallable, {"fn": spec})
        assert cfg.fn(x=3) == 5
        assert confarg.dump(cfg)["fn"] == spec

    @pytest.mark.parametrize("word", ["_bind", "_class", "_call", "_classfn"])
    def test_an_underscored_word_is_no_opener(self, word: str) -> None:
        """The former escaped forms are ordinary keys, so a spec holding only one has no opener."""
        with pytest.raises(TypeCoercionError, match=r"must specify one of 'bind', 'class', 'call' or 'classfn'"):
            confarg.build(WithBareCallable, {"fn": {word: f"{_MOD}._double"}})


# ---------------------------------------------------------------------------
# call: in a field that is not a Callable (FEAT-28)
# ---------------------------------------------------------------------------


@dataclass
class _Inner:
    a: int = 1


@dataclass
class _WithCallField:
    call: int = 0


def _text() -> str:
    return "hi"


def _inner_value() -> _Inner:
    return _Inner(a=7)


def _inner_dict() -> dict:
    return {"a": 2}


@dataclass
class _TypedCallHolder:
    n: int = 0
    inner: _Inner | None = None
    w: _WithCallField | None = None
    d: dict[str, str] | None = None
    o: int | None = None
    anything: Any = None


class TestCallInTypedField:
    """A ``call:`` spec fills any typed field, and a field whose type holds that key as data keeps it."""

    def test_call_fills_an_int_field(self):
        """A call fills an int field from its keyword arguments."""
        cfg = confarg.build(_TypedCallHolder, {"n": {"call": f"{__name__}._double", "args": {"x": 4}}})
        assert cfg.n == 8

    def test_call_result_already_an_instance_is_taken_as_is(self):
        """A call result that already is the annotated class is taken as it is."""
        cfg = confarg.build(_TypedCallHolder, {"inner": {"call": f"{__name__}._inner_value"}})
        assert cfg.inner == _Inner(a=7)

    def test_call_result_of_another_shape_is_constructed_as_the_annotation(self):
        """A call result of another shape is constructed as the annotated class."""
        cfg = confarg.build(_TypedCallHolder, {"inner": {"call": f"{__name__}._inner_dict"}})
        assert cfg.inner == _Inner(a=2)

    def test_optional_field_takes_the_call(self):
        """An Optional field takes the call as its member type."""
        cfg = confarg.build(_TypedCallHolder, {"o": {"call": f"{__name__}._double", "args": {"x": 3}}})
        assert cfg.o == 6

    def test_wrong_return_type_fails_as_a_wrong_literal_does(self):
        """A value that is no int fails as a wrong literal does, at the field."""
        with pytest.raises(TypeCoercionError, match="Cannot coerce str 'hi' to int at 'n'"):
            confarg.build(_TypedCallHolder, {"n": {"call": f"{__name__}._text"}})

    def test_bind_beside_call_is_refused(self):
        """bind: beside call: is a second opener, refused as in a Callable spec."""
        with pytest.raises(TypeCoercionError, match="more than one of"):
            confarg.build(_TypedCallHolder, {"n": {"call": f"{__name__}._double", "bind": {"x": 1}}})

    def test_a_key_beside_call_other_than_args_is_refused(self):
        """A typed call's arguments go under args, so a key beside the opener is refused, saying so."""
        with pytest.raises(TypeCoercionError, match=r"holds \['x'\] beside 'call'.*go under 'args'"):
            confarg.build(_TypedCallHolder, {"n": {"call": f"{__name__}._double", "x": 4}})

    def test_unknown_callee_names_the_import(self):
        """A callee that cannot be imported names it."""
        with pytest.raises(SymbolImportError, match=r"nope.nothing"):
            confarg.build(_TypedCallHolder, {"n": {"call": "nope.nothing"}})

    def test_struct_member_named_call_stays_data(self):
        """A struct member named call keeps the field as data."""
        cfg = confarg.build(_TypedCallHolder, {"w": {"call": 7}})
        assert cfg.w == _WithCallField(call=7)

    def test_dict_field_keeps_the_call_key_as_data(self):
        """A dict field keeps a call key as data."""
        cfg = confarg.build(_TypedCallHolder, {"d": {"call": "not-a-spec"}})
        assert cfg.d == {"call": "not-a-spec"}

    def test_any_field_takes_the_call(self):
        """An Any field reads a call key as a spec, as a field of any other type does (FEAT-42)."""
        data = {"anything": {"call": f"{__name__}._double", "args": {"x": 4}}}
        cfg = confarg.build(_TypedCallHolder, data)
        assert cfg.anything == 8

    def test_load_reaches_the_same_result(self, tmp_path):
        """load() takes the same route as build() for a file."""
        path = tmp_path / "cfg.json"
        path.write_text(json.dumps({"n": {"call": f"{__name__}._double", "args": {"x": 5}}}))
        cfg = confarg.load(_TypedCallHolder, files=[path], env={}, argv=[])
        assert cfg.n == 10


@dataclass
class _AnyHolder:
    anything: Any = None
    items: list[Any] | None = None
    bare: dict | None = None
    int_or_any: int | Any = None
    tagged_or_any: _TagBase | Any = None


class TestAnyReadsSpecs:
    """An ``Any`` field reads every opener, at every depth; a bare dotted string stays a string (FEAT-42)."""

    def test_class_builds_the_named_class(self):
        """class: names any importable class, its other keys the fields."""
        cfg = confarg.build(_AnyHolder, {"anything": {"class": f"{__name__}._Inner", "a": 3}})
        assert cfg.anything == _Inner(a=3)

    def test_class_needs_no_call_method(self):
        """Unlike under a Callable, the instance need not be callable."""
        cfg = confarg.build(_AnyHolder, {"anything": {"class": f"{__name__}._TagUnrelated"}})
        assert cfg.anything == _TagUnrelated()

    def test_bind_yields_a_partial(self):
        """bind: applies its arguments, as on a Callable field."""
        cfg = confarg.build(_AnyHolder, {"anything": {"bind": f"{__name__}._add", "args": {"y": 1}}})
        assert cfg.anything(x=2) == 3

    def test_bind_without_arguments_is_the_target(self):
        """{bind: T} is T itself, so a function can be named where a bare string stays text."""
        cfg = confarg.build(_AnyHolder, {"anything": {"bind": f"{__name__}._double"}})
        assert cfg.anything is _double

    def test_classfn_yields_the_bound_method(self):
        """classfn: builds the owner from the other keys and yields its method."""
        cfg = confarg.build(_AnyHolder, {"anything": {"classfn": f"{__name__}._Processor.process", "offset": 2}})
        assert cfg.anything(1) == 3

    def test_a_bare_dotted_string_stays_a_string(self):
        """The shorthand applies only where the type asks for a callable."""
        cfg = confarg.build(_AnyHolder, {"anything": f"{__name__}._double"})
        assert cfg.anything == f"{__name__}._double"

    def test_a_dict_without_an_opener_stays_a_dict(self):
        """A dict holding no opener is data."""
        cfg = confarg.build(_AnyHolder, {"anything": {"a": 1, "b": [2]}})
        assert cfg.anything == {"a": 1, "b": [2]}

    def test_a_spec_nested_in_a_dict_and_a_list_is_read(self):
        """A dict an Any holds is dict[Any, Any] and a list list[Any], so a spec at any depth is read."""
        spec = {"class": f"{__name__}._Inner", "a": 2}
        cfg = confarg.build(_AnyHolder, {"anything": {"k": [spec, {"deeper": spec}]}})
        assert cfg.anything == {"k": [_Inner(a=2), {"deeper": _Inner(a=2)}]}

    def test_a_list_of_any_reads_each_element(self):
        """list[Any] elements are Any nodes."""
        cfg = confarg.build(_AnyHolder, {"items": [{"call": f"{__name__}._double", "args": {"x": 1}}, "t"]})
        assert cfg.items == [2, "t"]

    def test_a_bare_dict_reads_its_values(self):
        """A bare dict is dict[Any, Any], so its values read specs."""
        cfg = confarg.build(_AnyHolder, {"bare": {"k": {"class": f"{__name__}._Inner"}}})
        assert cfg.bare == {"k": _Inner()}

    def test_a_class_that_does_not_import_is_refused(self):
        """A tag naming no class is an error, not data."""
        with pytest.raises(ConfargError, match=r"nope\.Nothing"):
            confarg.build(_AnyHolder, {"anything": {"class": "nope.Nothing"}})

    def test_a_class_naming_no_class_is_refused(self):
        """class: names a class; a function is refused."""
        with pytest.raises(TypeCoercionError, match="must reference a class"):
            confarg.build(_AnyHolder, {"anything": {"class": f"{__name__}._double"}})

    def test_two_openers_are_refused(self):
        """Two computation openers are refused, as in a Callable spec."""
        with pytest.raises(TypeCoercionError, match="more than one of"):
            confarg.build(_AnyHolder, {"anything": {"bind": f"{__name__}._double", "call": f"{__name__}._double"}})

    def test_a_tag_beside_a_scalar_variant_builds_the_class(self):
        """In int | Any, a dict the int refuses is the Any variant's spec."""
        cfg = confarg.build(_AnyHolder, {"int_or_any": {"class": f"{__name__}._Inner", "a": 5}})
        assert cfg.int_or_any == _Inner(a=5)

    def test_a_tag_naming_a_variant_still_selects_it(self):
        """A tag naming a subclass of a struct variant selects that variant."""
        cfg = confarg.build(_AnyHolder, {"tagged_or_any": {"class": f"{__name__}._TagSub", "b": 4}})
        assert cfg.tagged_or_any == _TagSub(b=4)

    def test_a_tag_naming_no_variant_is_the_any_variants_spec(self):
        """In S | Any, a tag naming no variant builds the class it names."""
        cfg = confarg.build(_AnyHolder, {"tagged_or_any": {"class": f"{__name__}._TagUnrelated", "z": 4}})
        assert cfg.tagged_or_any == _TagUnrelated(z=4)

    def test_a_tag_that_does_not_import_is_refused_beside_a_variant(self):
        """In S | Any, a tag that does not import is refused."""
        with pytest.raises(TypeCoercionError, match=r"nope\.Nothing"):
            confarg.build(_AnyHolder, {"tagged_or_any": {"class": "nope.Nothing"}})

    def test_a_call_beside_a_scalar_variant_takes_the_value(self):
        """In int | Any, a call's value is taken as it is."""
        cfg = confarg.build(_AnyHolder, {"int_or_any": {"call": f"{__name__}._text"}})
        assert cfg.int_or_any == "hi"


@dataclass
class _TypedCallDumpHolder:
    base: int = 0
    n: int = 0
    inner: _Inner | None = None


class TestDumpOfATypedCall:
    """The object dumps the value a typed ``call:`` produced; the merged dict keeps the call as written."""

    @pytest.mark.parametrize(("callee", "dumped"), [("_inner_value", {"a": 7}), ("_inner_dict", {"a": 2})])
    def test_a_struct_result_dumps_as_its_fields(self, callee: str, dumped: dict) -> None:
        """A struct result dumps its fields, whether the call returned it or it was built from the return."""
        cfg = confarg.build(_TypedCallDumpHolder, {"inner": {"call": f"{__name__}.{callee}"}})
        assert confarg.dump(cfg)["inner"] == dumped

    def test_a_change_after_build_is_dumped(self) -> None:
        """The dump records the value the object holds now, not the call that first produced it."""
        cfg = confarg.build(_TypedCallDumpHolder, {"inner": {"call": f"{__name__}._inner_value"}})
        assert cfg.inner is not None
        cfg.inner.a = 9
        assert confarg.dump(cfg)["inner"] == {"a": 9}

    def test_a_scalar_result_dumps_as_its_value(self) -> None:
        """A computed int dumps as the int."""
        cfg = confarg.build(_TypedCallDumpHolder, {"n": {"call": f"{__name__}._double", "args": {"x": 4}}})
        assert confarg.dump(cfg)["n"] == 8

    def test_the_merged_dict_dumps_the_call_as_written(self, tmp_path: pathlib.Path) -> None:
        """Before build the call is data: dump_file writes it as merged, its expression unresolved."""
        source = tmp_path / "in.json"
        source.write_text(json.dumps({"base": 3, "n": {"call": f"{__name__}._double", "args": {"x": "${base}"}}}))
        raw = confarg.merge(_TypedCallDumpHolder, files=[source], env={}, argv=[])
        out = tmp_path / "out.json"
        confarg.dump_file(raw, out)
        assert json.loads(out.read_text())["n"] == {"call": f"{__name__}._double", "args": {"x": "${base}"}}
        built = tmp_path / "built.json"
        confarg.dump_file(confarg.build(_TypedCallDumpHolder, raw), built)
        assert json.loads(built.read_text())["n"] == 6


# ---------------------------------------------------------------------------
# class: on a typed field names a subclass; call: builds anything else (FEAT-29)
# ---------------------------------------------------------------------------


@dataclass
class _TagBase:
    a: int = 1


@dataclass
class _TagSub(_TagBase):
    b: int = 2


@dataclass
class _TagUnrelated:
    z: int = 3


@dataclass
class _TagHolder:
    base: _TagBase | None = None


class TestClassTagNamesASubclass:
    """A ``class:`` key on a typed field names a subclass of the annotation; anything else is refused."""

    def test_subclass_named_by_class_is_built(self):
        """A subclass of the annotation is built from the sibling keys."""
        cfg = confarg.build(_TagHolder, {"base": {"class": f"{__name__}._TagSub", "b": 5}})
        assert cfg.base == _TagSub(a=1, b=5)

    def test_unrelated_class_refusal_disclaims_the_call_spec(self):
        """An unrelated class is refused, and the message disclaims call: rather than promising a build (BUG-196)."""
        with pytest.raises(
            TypeCoercionError,
            match=r"is not a subclass of .*_TagBase\. A 'call:' spec computes a value the field's type accepts",
        ) as info:
            confarg.build(_TagHolder, {"base": {"class": f"{__name__}._TagUnrelated", "z": 9}})
        assert "with a factory" not in str(info.value)
