# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for factory mode: Callable[..., T] where class: is a subclass of T."""

from __future__ import annotations

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
    """Tests for factory-mode callable construction from config dicts."""

    def test_class_subclass_returns_partial(self):
        """Test that class: subclass of return type returns a partial constructor."""
        result = confarg.build(
            _WithConcreteOpt,
            {"optimizer": {"class": f"{_MOD}._SGD", "lr": 0.05}},
        )
        assert isinstance(result.optimizer, functools.partial)
        assert result.optimizer.func is _SGD
        assert result.optimizer.keywords == {"lr": 0.05}

    def test_calling_partial_produces_instance(self):
        """Test that calling the returned partial produces a correctly configured instance."""
        result = confarg.build(
            _WithConcreteOpt,
            {"optimizer": {"class": f"{_MOD}._SGD", "lr": 0.05, "momentum": 0.9}},
        )
        opt = result.optimizer()
        assert isinstance(opt, _SGD)
        assert opt.lr == pytest.approx(0.05)
        assert opt.momentum == pytest.approx(0.9)

    def test_no_class_key_concrete_return_type(self):
        """No 'class:' key: use return type as implicit class."""
        result = confarg.build(
            _WithConcreteOpt,
            {"optimizer": {"lr": 0.02, "momentum": 0.8}},
        )
        assert isinstance(result.optimizer, functools.partial)
        assert result.optimizer.func is _SGD
        assert result.optimizer.keywords == {"lr": 0.02, "momentum": 0.8}

    def test_subclass_override(self):
        """class: can be a subclass of the Callable return type."""
        result = confarg.build(
            _WithConcreteOpt,
            {"optimizer": {"class": f"{_MOD}._SGDVariant", "lr": 0.01, "dampening": 0.1}},
        )
        assert isinstance(result.optimizer, functools.partial)
        assert result.optimizer.func is _SGDVariant
        assert result.optimizer.keywords["dampening"] == pytest.approx(0.1)

    def test_abstract_base_with_class(self):
        """Test that class: with abstract base type creates a partial of the given class."""
        result = confarg.build(
            _WithAbstractOpt,
            {"optimizer": {"class": f"{_MOD}._Adam", "lr": 0.003}},
        )
        assert isinstance(result.optimizer, functools.partial)
        assert result.optimizer.func is _Adam
        assert result.optimizer.keywords == {"lr": 0.003}

    def test_non_subclass_uses_callable_object_mode(self):
        """class: not a subclass of return type → instantiate (callable-object mode)."""
        result = confarg.build(
            _WithAbstractOpt,
            {"optimizer": {"class": f"{_MOD}._ProduceOpt", "strategy": "sgd"}},
        )
        assert isinstance(result.optimizer, _ProduceOpt)
        assert result.optimizer.strategy == "sgd"

    def test_bind_in_factory_mode_raises(self):
        """Test that using bind: in factory mode raises TypeCoercionError."""
        with pytest.raises(TypeCoercionError, match=r"bind.*not valid in factory mode"):
            confarg.build(
                _WithConcreteOpt,
                {"optimizer": {"class": f"{_MOD}._SGD", "lr": 0.01, "bind": {"x": 1}}},
            )

    def test_unknown_kwarg_raises(self):
        """Test that an unknown constructor kwarg raises TypeCoercionError."""
        with pytest.raises(TypeCoercionError, match="Unknown constructor kwargs"):
            confarg.build(
                _WithConcreteOpt,
                {"optimizer": {"class": f"{_MOD}._SGD", "bad_kwarg": 99}},
            )

    def test_bare_string_factory(self):
        """A bare string class path is factory mode when class is a subclass of return type."""
        result = confarg.build(
            _WithConcreteOpt,
            {"optimizer": f"{_MOD}._SGD"},
        )
        assert isinstance(result.optimizer, functools.partial)
        assert result.optimizer.func is _SGD
        assert result.optimizer.keywords == {}

    def test_bare_string_callable_object_mode(self):
        """A bare string class path stays callable-object mode when not a subclass."""
        result = confarg.build(
            _WithAbstractOpt,
            {"optimizer": f"{_MOD}._ProduceOpt"},
        )
        assert isinstance(result.optimizer, _ProduceOpt)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestFactoryFromCLI:
    """Tests for factory-mode callable construction from CLI arguments."""

    def test_class_and_kwarg_flags(self):
        """Test that --optimizer.class + --optimizer.kwarg flags construct a partial."""
        result = confarg.load(
            _WithConcreteOpt,
            args=[f"--optimizer.class={_MOD}._SGD", "--optimizer.lr=0.05"],
            env={},
        )
        assert isinstance(result.optimizer, functools.partial)
        assert result.optimizer.func is _SGD
        assert result.optimizer.keywords["lr"] == pytest.approx(0.05)

    def test_only_kwarg_flags_concrete_return_type(self):
        """No --class flag: implicit _SGD from return type annotation."""
        result = confarg.load(
            _WithConcreteOpt,
            args=["--optimizer.lr=0.02"],
            env={},
        )
        assert isinstance(result.optimizer, functools.partial)
        assert result.optimizer.func is _SGD
        assert result.optimizer.keywords["lr"] == pytest.approx(0.02)

    def test_abstract_base_cli(self):
        """Test that abstract base class: + kwarg flags construct a partial via CLI."""
        result = confarg.load(
            _WithAbstractOpt,
            args=[f"--optimizer.class={_MOD}._Adam", "--optimizer.lr=0.003"],
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

    def test_env_class_and_kwarg(self):
        """Test that env vars with class and kwarg construct a partial via env."""
        result = confarg.load(
            _WithConcreteOpt,
            args=[],
            env={
                "CONFARG_OPTIMIZER__CLASS": f"{_MOD}._SGD",
                "CONFARG_OPTIMIZER__LR": "0.07",
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

    def test_factory_partial_serializes_as_class_dict(self):
        """Test that a factory partial serializes as a class: dict with constructor kwargs."""
        p = functools.partial(_SGD, lr=0.05, momentum=0.9)
        out = _serialize_callable(p)
        assert out == {"class": f"{_MOD}._SGD", "lr": 0.05, "momentum": 0.9}

    def test_factory_partial_no_kwargs(self):
        """Test that a factory partial with no kwargs serializes without extra keys."""
        p = functools.partial(_SGD)
        out = _serialize_callable(p)
        assert out == {"class": f"{_MOD}._SGD"}

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
        """Load → dump → reload preserves the factory."""

        @dataclass
        class Cfg:
            optimizer: Callable[..., _SGD]

        cfg = confarg.build(
            Cfg,
            {"optimizer": {"class": f"{_MOD}._SGD", "lr": 0.05}},
        )
        dumped = confarg.dump(cfg)
        assert dumped["optimizer"] == {"class": f"{_MOD}._SGD", "lr": 0.05}

        cfg2 = confarg.build(Cfg, dumped)
        assert isinstance(cfg2.optimizer, functools.partial)
        assert cfg2.optimizer.func is _SGD
        assert cfg2.optimizer.keywords["lr"] == pytest.approx(0.05)
