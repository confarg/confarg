# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Module-level helper types importable by dotted path from gap-coverage tests.

The callable-spec machinery resolves functions and classes via their
fully-qualified name, so these helpers must live at module level in an
importable module; ``_COV_MOD`` is that path.  Shared by
``tests/test_coverage_gaps.py`` and the relocated per-backend gap suites.
"""

from __future__ import annotations

from collections.abc import (
    Callable,  # noqa: TC003  # must be a runtime import: confarg resolves these annotations via get_type_hints
)
from dataclasses import dataclass, field
from typing import Any

_COV_MOD = "tests._cov_helpers"


@dataclass
class _ConstructAVariant:
    x: int = 0


@dataclass
class _ConstructBVariant:
    y: int = 0


def _cov_call_fn(x: int, y: str = "default") -> str:
    return f"{x}-{y}"


class _CovOptMethod:
    """Class with required+optional __init__ params and an instance method."""

    def __init__(self, required: int, optional: str = "default") -> None:
        self.required = required
        self.optional = optional

    def method(self) -> None:
        pass


class _CovUninspectable:
    """Class whose __init__ raises TypeError on signature inspection."""

    def __init__(self, value: int = 0) -> None:
        self.value = value


_CovUninspectable.__init__.__signature__ = property(  # ty: ignore[unresolved-attribute]  # deliberately corrupt __signature__ for testing
    lambda self: (_ for _ in ()).throw(TypeError("uninspectable")),
)


@dataclass
class _CovDCResult:
    result_val: str = ""


@dataclass
class _WithCovCallable:
    fn: Callable[..., _CovDCResult]


class _CovCallableCls:
    def __init__(self, lr: float = 0.01) -> None:
        self.lr = lr

    def __call__(self) -> None:
        pass


def _cov_raise_fn(x: int) -> str:
    msg = "deliberate error"
    raise RuntimeError(msg)


def _cov_fn_with_varargs(*args: int, key: str = "default") -> str:
    return str(args)


@dataclass
class _CovInner:
    value: str = ""


@dataclass
class _CovOuter:
    inner: _CovInner = field(default_factory=_CovInner)


@dataclass
class _WithUnionForCompletion:
    val: _ConstructAVariant | _ConstructBVariant = field(default_factory=_ConstructAVariant)


@dataclass
class _CovWithDict:
    settings: dict[str, Any] = field(default_factory=dict)
    name: str = ""


class _CovWithKwargs:
    """Plain class with **kwargs — used to test var_params skip in _extend_walk."""

    def __init__(self, x: int = 0, **extra: Any) -> None:
        self.x = x
