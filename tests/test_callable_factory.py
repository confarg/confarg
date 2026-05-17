# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for factory-style Callable[..., T] construction.

Factories are a bare class FQN (no args) or 'fn: <class>' + 'bind:' (with args); calling
them constructs a T. 'class:' always instantiates the class (the instance is the callable).
"""

from __future__ import annotations

import enum
import functools
from collections.abc import Callable  # noqa: TC003
from dataclasses import dataclass

import pytest

import confarg
from confarg._callable import _serialize_callable
from confarg.exceptions import TypeCoercionError

# ---------------------------------------------------------------------------
# Module-level helpers — importable by dotted path
# ---------------------------------------------------------------------------

_MOD = "tests.test_callable_factory"


class _Optimizer:
    """Abstract-ish base for optimizer-like classes."""

    def step(self) -> None: ...


class _SGD(_Optimizer):
    def __init__(self, lr: float = 0.01, momentum: float = 0.0) -> None:
        self.lr = lr
        self.momentum = momentum

    def step(self) -> None:
        pass


class _Adam(_Optimizer):
    def __init__(self, lr: float = 0.001, beta1: float = 0.9) -> None:
        self.lr = lr
        self.beta1 = beta1

    def step(self) -> None:
        pass


class _SGDVariant(_SGD):
    """Subclass of _SGD — valid override for Callable[..., _SGD]."""

    def __init__(self, lr: float = 0.01, momentum: float = 0.0, dampening: float = 0.0) -> None:
        super().__init__(lr=lr, momentum=momentum)
        self.dampening = dampening


class _ProduceOpt:
    """Callable object that produces _Optimizer instances — NOT a subclass."""

    def __init__(self, strategy: str = "sgd") -> None:
        self.strategy = strategy

    def __call__(self) -> _Optimizer:
        return _SGD()


class _Mode(enum.Enum):
    FAST = "fast"
    SLOW = "slow"


@dataclass
class _Schedule:
    warmup: int = 0


class _ModedOpt(_Optimizer):
    """Optimizer whose constructor takes non-scalar (enum/dataclass/list) params."""

    def __init__(self, mode: _Mode, schedule: _Schedule, tags: list[int], lr: float = 0.01) -> None:
        self.mode = mode
        self.schedule = schedule
        self.tags = tags
        self.lr = lr

    def step(self) -> None:
        pass


class _BindConsumer:
    """Callable object (NOT an _Optimizer) whose __call__ takes an enum param."""

    def __call__(self, mode: _Mode) -> _Optimizer:
        return _SGD()


# ---------------------------------------------------------------------------
# Target dataclasses
# ---------------------------------------------------------------------------


@dataclass
class _WithConcreteOpt:
    optimizer: Callable[..., _SGD]


@dataclass
class _WithAbstractOpt:
    optimizer: Callable[..., _Optimizer]


@dataclass
class _WithDefault:
    optimizer: Callable[..., _SGD] | None = None


# ---------------------------------------------------------------------------
# Construction from config dict (config-file path)
# ---------------------------------------------------------------------------


class TestFactoryFromDict:
    """Tests for factory-style callable construction from config dicts."""

    def test_fn_class_with_bind_returns_partial(self):
        """'fn: <class>' + bind returns a partial constructor (factory with pre-applied args)."""
        result = confarg.build(
            _WithConcreteOpt,
            {"optimizer": {"fn": f"{_MOD}._SGD", "bind": {"lr": 0.05}}},
        )
        assert isinstance(result.optimizer, functools.partial)
        assert result.optimizer.func is _SGD
        assert result.optimizer.keywords == {"lr": 0.05}

    def test_calling_partial_produces_instance(self):
        """Calling the returned partial produces a correctly configured instance."""
        result = confarg.build(
            _WithConcreteOpt,
            {"optimizer": {"fn": f"{_MOD}._SGD", "bind": {"lr": 0.05, "momentum": 0.9}}},
        )
        opt = result.optimizer()
        assert isinstance(opt, _SGD)
        assert opt.lr == pytest.approx(0.05)
        assert opt.momentum == pytest.approx(0.9)

    def test_no_key_dict_raises(self):
        """A callable dict with no fn/class/call key is rejected (the implicit form is gone)."""
        with pytest.raises(TypeCoercionError, match="must specify one of 'fn', 'class', or 'call'"):
            confarg.build(
                _WithConcreteOpt,
                {"optimizer": {"lr": 0.02, "momentum": 0.8}},
            )

    def test_fn_subclass_override(self):
        """'fn:' can name a subclass of the Callable return type."""
        result = confarg.build(
            _WithConcreteOpt,
            {"optimizer": {"fn": f"{_MOD}._SGDVariant", "bind": {"lr": 0.01, "dampening": 0.1}}},
        )
        assert isinstance(result.optimizer, functools.partial)
        assert result.optimizer.func is _SGDVariant
        assert result.optimizer.keywords["dampening"] == pytest.approx(0.1)

    def test_fn_abstract_base(self):
        """'fn: <class>' + bind on a Callable[..., Base] field builds a partial of the class."""
        result = confarg.build(
            _WithAbstractOpt,
            {"optimizer": {"fn": f"{_MOD}._Adam", "bind": {"lr": 0.003}}},
        )
        assert isinstance(result.optimizer, functools.partial)
        assert result.optimizer.func is _Adam
        assert result.optimizer.keywords == {"lr": 0.003}

    def test_class_key_instantiates_callable_object(self):
        """'class:' instantiates a callable-object class with its init kwargs."""
        result = confarg.build(
            _WithAbstractOpt,
            {"optimizer": {"class": f"{_MOD}._ProduceOpt", "strategy": "sgd"}},
        )
        assert isinstance(result.optimizer, _ProduceOpt)
        assert result.optimizer.strategy == "sgd"

    def test_class_on_factory_target_raises(self):
        """'class:' on a non-callable-object class raises, pointing at the factory forms."""
        with pytest.raises(TypeCoercionError, match=r"not callable.*factory"):
            confarg.build(
                _WithAbstractOpt,
                {"optimizer": {"class": f"{_MOD}._Adam", "lr": 0.01}},
            )

    def test_unknown_bind_kwarg_raises(self):
        """An unknown bind kwarg for an 'fn:' factory raises TypeCoercionError."""
        with pytest.raises(TypeCoercionError, match="Unknown bind parameter"):
            confarg.build(
                _WithConcreteOpt,
                {"optimizer": {"fn": f"{_MOD}._SGD", "bind": {"bad_kwarg": 99}}},
            )

    def test_bare_string_factory(self):
        """A bare class path is a factory when the class is a subclass of the return type."""
        result = confarg.build(
            _WithConcreteOpt,
            {"optimizer": f"{_MOD}._SGD"},
        )
        assert isinstance(result.optimizer, functools.partial)
        assert result.optimizer.func is _SGD
        assert result.optimizer.keywords == {}

    def test_bare_string_non_subclass_raises_guard(self):
        """A bare class that can't produce the return type is rejected, pointing at 'class:'."""
        with pytest.raises(TypeCoercionError, match=r"used as a factory.*class: "):
            confarg.build(
                _WithAbstractOpt,
                {"optimizer": f"{_MOD}._ProduceOpt"},
            )

    def test_class_key_callable_object_mode(self):
        """The 'class:' dict form instantiates a callable-object and uses the instance."""
        result = confarg.build(
            _WithAbstractOpt,
            {"optimizer": {"class": f"{_MOD}._ProduceOpt"}},
        )
        assert isinstance(result.optimizer, _ProduceOpt)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestFactoryFromCLI:
    """Tests for factory-style callable construction from CLI arguments (vanilla load)."""

    def test_fn_and_bind_flags(self):
        """--optimizer.fn + --optimizer.bind.<kwarg> flags construct a factory partial."""
        result = confarg.load(
            _WithConcreteOpt,
            argv=[f"--optimizer.fn={_MOD}._SGD", "--optimizer.bind.lr=0.05"],
            env={},
        )
        assert isinstance(result.optimizer, functools.partial)
        assert result.optimizer.func is _SGD
        assert result.optimizer.keywords["lr"] == pytest.approx(0.05)

    def test_kwarg_without_fn_or_class_raises(self):
        """A bare --optimizer.<kwarg> (no fn/class) is a keyless dict → rejected."""
        with pytest.raises(TypeCoercionError, match="must specify one of 'fn', 'class', or 'call'"):
            confarg.load(
                _WithConcreteOpt,
                argv=["--optimizer.lr=0.02"],
                env={},
            )

    def test_abstract_base_cli(self):
        """--optimizer.fn + bind on a Callable[..., Base] field constructs a partial via CLI."""
        result = confarg.load(
            _WithAbstractOpt,
            argv=[f"--optimizer.fn={_MOD}._Adam", "--optimizer.bind.lr=0.003"],
            env={},
        )
        assert isinstance(result.optimizer, functools.partial)
        assert result.optimizer.func is _Adam
        assert result.optimizer.keywords["lr"] == pytest.approx(0.003)


# ---------------------------------------------------------------------------
# Env vars
# ---------------------------------------------------------------------------


class TestFactoryFromEnv:
    """Tests for factory-mode callable construction from environment variables."""

    def test_env_fn_and_bind(self):
        """Env vars with fn and bind construct a factory partial via env."""
        result = confarg.load(
            _WithConcreteOpt,
            argv=[],
            env={
                "CONFARG_OPTIMIZER__FN": f"{_MOD}._SGD",
                "CONFARG_OPTIMIZER__BIND__LR": "0.07",
            },
            env_prefix="CONFARG_",
        )
        assert isinstance(result.optimizer, functools.partial)
        assert result.optimizer.func is _SGD
        assert result.optimizer.keywords["lr"] == pytest.approx(0.07)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestFactorySerialization:
    """Tests for factory-mode callable serialization."""

    def test_factory_partial_serializes_as_fn_bind_dict(self):
        """A factory partial with kwargs serializes as an fn: dict with bind: (not class:)."""
        p = functools.partial(_SGD, lr=0.05, momentum=0.9)
        out = _serialize_callable(p)
        assert out == {"fn": f"{_MOD}._SGD", "bind": {"lr": 0.05, "momentum": 0.9}}

    def test_factory_partial_no_kwargs_serializes_as_bare_string(self):
        """A factory partial with no kwargs serializes as a bare class FQN string."""
        p = functools.partial(_SGD)
        out = _serialize_callable(p)
        assert out == f"{_MOD}._SGD"

    def test_function_partial_serializes_as_fn_dict(self):
        """Test that a function partial serializes as a fn: dict with bind:."""

        def _fn(x: int) -> int:
            return x

        p = functools.partial(_fn, x=1)
        out = _serialize_callable(p)
        assert isinstance(out, dict)
        assert "fn" in out
        assert out.get("bind") == {"x": 1}

    def test_round_trip_factory(self):
        """Load → dump → reload preserves the factory (as fn:+bind:)."""

        @dataclass
        class Cfg:
            optimizer: Callable[..., _SGD]

        cfg = confarg.build(
            Cfg,
            {"optimizer": {"fn": f"{_MOD}._SGD", "bind": {"lr": 0.05}}},
        )
        dumped = confarg.dump(cfg)
        assert dumped["optimizer"] == {"fn": f"{_MOD}._SGD", "bind": {"lr": 0.05}}

        cfg2 = confarg.build(Cfg, dumped)
        assert isinstance(cfg2.optimizer, functools.partial)
        assert cfg2.optimizer.func is _SGD
        assert cfg2.optimizer.keywords["lr"] == pytest.approx(0.05)


class TestBindTypedConstruction:
    """bind: values go through the same typed-construction route as any other config element."""

    def test_fn_class_bind_constructs_complex_types_from_dict(self):
        """fn: ClassName + bind builds enum/dataclass/list params (config-file / native path)."""
        result = confarg.build(
            _WithAbstractOpt,
            {
                "optimizer": {
                    "fn": f"{_MOD}._ModedOpt",
                    "bind": {"mode": "fast", "schedule": {"warmup": 10}, "tags": [1, 2]},
                },
            },
        )
        assert isinstance(result.optimizer, functools.partial)
        kw = result.optimizer.keywords
        assert kw["mode"] is _Mode.FAST  # enum coerced from string
        assert kw["schedule"] == _Schedule(warmup=10)  # dataclass built from mapping
        assert kw["tags"] == [1, 2]

    def test_fn_class_bind_constructs_enum_from_cli(self):
        """An enum bind value arriving as a CLI string is coerced (all-input-types parity)."""
        result = confarg.load(
            _WithAbstractOpt,
            argv=["--optimizer.fn", f"{_MOD}._ModedOpt", "--optimizer.bind.mode", "slow"],
            env={},
        )
        # Previously this stayed the raw string "slow"; now it is the enum member.
        assert isinstance(result.optimizer, functools.partial)
        assert result.optimizer.keywords["mode"] is _Mode.SLOW

    def test_callable_object_bind_constructs_complex_types(self):
        """class: callable-object mode also coerces bind values via the canonical route."""
        result = confarg.build(
            _WithAbstractOpt,
            {
                "optimizer": {
                    "class": f"{_MOD}._BindConsumer",
                    "bind": {"mode": "fast"},
                },
            },
        )
        assert isinstance(result.optimizer, functools.partial)
        assert result.optimizer.keywords["mode"] is _Mode.FAST

    def test_bad_bind_value_raises(self):
        """An uncoercible bind value fails fast, like any other config value."""
        with pytest.raises(TypeCoercionError):
            confarg.build(
                _WithConcreteOpt,
                {"optimizer": {"fn": f"{_MOD}._SGD", "bind": {"lr": "not_a_float"}}},
            )

    def test_scalar_bind_from_cli_still_coerces(self):
        """Regression: scalar bind from the CLI still coerces (--field.bind.lr 0.1 → 0.1)."""
        result = confarg.load(
            _WithConcreteOpt,
            argv=["--optimizer.fn", f"{_MOD}._SGD", "--optimizer.bind.lr", "0.1"],
            env={},
        )
        assert isinstance(result.optimizer, functools.partial)
        assert result.optimizer.keywords["lr"] == pytest.approx(0.1)
