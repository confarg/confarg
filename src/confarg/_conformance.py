# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Structural conformance: whether a class is a Protocol, and whether a callable can be called as a signature is.

A leaf module, importing the standard library only, so every module asking the question can
import it. A refusal is returned as its reason, never raised: the caller raises it.

Dev Notes:
    docs-dev/architecture/callables.md#a-callable-is-checked-by-its-call-shape
"""

from __future__ import annotations

import inspect
import sys
import typing
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

_Parameter = inspect.Parameter

_POSITIONAL = (_Parameter.POSITIONAL_ONLY, _Parameter.POSITIONAL_OR_KEYWORD)
_BY_NAME = (_Parameter.POSITIONAL_OR_KEYWORD, _Parameter.KEYWORD_ONLY)
_VARIADIC = (_Parameter.VAR_POSITIONAL, _Parameter.VAR_KEYWORD)


def is_protocol(tp: Any) -> bool:
    """Return whether *tp* is a Protocol class, one declared with ``Protocol`` among its bases.

    A class implementing a Protocol is none, whether it inherits it or not, and neither is
    ``typing.Protocol`` itself. ``typing_extensions.Protocol`` declares one too.

    Dev Notes:
        ``typing.is_protocol`` exists from 3.13; on 3.12 its body is spelled here, reading the
        ``_is_protocol`` flag both ``typing`` and ``typing_extensions`` set on a Protocol class.
    """
    if sys.version_info >= (3, 13):
        return typing.is_protocol(tp)
    return isinstance(tp, type) and bool(getattr(tp, "_is_protocol", False)) and tp is not typing.Protocol


def call_conforms(impl: Any, expected: inspect.Signature) -> str | None:
    """Return why *impl* cannot be called every way *expected* can be, or None when it can.

    Annotations are not compared, but for one reading: an expected ``*args, **kwargs`` pair,
    each unannotated or ``Any``, stands for ``...``, so any further parameter of *impl* is
    taken. A string annotation is not ``Any``: read *expected* with ``eval_str=True`` where
    its annotations may be strings. A callable whose signature ``inspect`` cannot read is
    accepted; anything that is not callable is refused.

    The reason names an expected argument by its position, or by its name where the call may
    pass it by name, and a parameter of *impl* by its name.

    Dev Notes:
        docs-dev/architecture/callables.md#a-callable-is-checked-by-its-call-shape
    """
    if not callable(impl):
        return f"{impl!r} is not callable"
    try:
        actual = inspect.signature(impl)
    except (ValueError, TypeError):
        return None
    return _Callee.of(actual).refusal(expected)


def _is_open(annotation: Any) -> bool:
    """Return whether a variadic parameter annotated *annotation* takes anything."""
    return annotation is _Parameter.empty or annotation is Any


def _argument(index: int, expected: _Parameter) -> str:
    """Spell the expected positional argument *expected*, the *index*-th, by its name where a call may use it."""
    if expected.kind is _Parameter.POSITIONAL_OR_KEYWORD:
        return f"argument {expected.name!r}"
    return f"argument {index + 1}"


@dataclass(frozen=True)
class _Callee:
    """The parameters of an implementation, sorted by how a call reaches them.

    Attributes:
        parameters: Every parameter, in declaration order.
        positional: The parameters a positional argument fills, in order.
        by_name: The parameters a keyword argument fills, by name.
        var_positional: Whether a ``*args`` takes extra positional arguments.
        var_keyword: Whether a ``**kwargs`` takes extra keyword arguments.
    """

    parameters: tuple[_Parameter, ...]
    positional: tuple[_Parameter, ...]
    by_name: dict[str, _Parameter]
    var_positional: bool
    var_keyword: bool

    @classmethod
    def of(cls, signature: inspect.Signature) -> _Callee:
        """Return the callee *signature* describes."""
        parameters = tuple(signature.parameters.values())
        return cls(
            parameters=parameters,
            positional=tuple(p for p in parameters if p.kind in _POSITIONAL),
            by_name={p.name: p for p in parameters if p.kind in _BY_NAME},
            var_positional=any(p.kind is _Parameter.VAR_POSITIONAL for p in parameters),
            var_keyword=any(p.kind is _Parameter.VAR_KEYWORD for p in parameters),
        )

    def refusal(self, expected: inspect.Signature) -> str | None:
        """Return why a call shaped as *expected* does not reach this callee, or None when every such call does."""
        filled: set[str] = set()
        wanted = tuple(expected.parameters.values())
        reason = next((r for r in self._argument_refusals(wanted, filled) if r is not None), None)
        return reason if reason is not None else self._rest_refusal(wanted, filled)

    def _argument_refusals(self, wanted: tuple[_Parameter, ...], filled: set[str]) -> Iterator[str | None]:
        """Yield why each argument the *wanted* call names reaches no parameter, adding those it reaches to *filled*."""
        positional = (e for e in wanted if e.kind in _POSITIONAL)
        for index, e in enumerate(positional):
            yield self._positional_refusal(index, e, filled)
        for e in wanted:
            if e.kind is _Parameter.KEYWORD_ONLY:
                yield self._keyword_refusal(e, filled)

    def _rest_refusal(self, wanted: tuple[_Parameter, ...], filled: set[str]) -> str | None:
        """Return why the extra arguments the *wanted* call passes, or a parameter not in *filled*, do not fit."""
        variadic = {e.kind: e for e in wanted if e.kind in _VARIADIC}
        if len(variadic) == len(_VARIADIC) and all(_is_open(e.annotation) for e in variadic.values()):
            return None
        if _Parameter.VAR_POSITIONAL in variadic and not self.var_positional:
            return "extra positional arguments are passed, and no '*args' takes them"
        if _Parameter.VAR_KEYWORD in variadic and not self.var_keyword:
            return "extra keyword arguments are passed, and no '**kwargs' takes them"
        unfilled = (p for p in self.parameters if p.kind not in _VARIADIC and p.name not in filled)
        missing = next((p for p in unfilled if p.default is _Parameter.empty), None)
        return None if missing is None else f"parameter {missing.name!r} is required, and the call never passes it"

    def _positional_refusal(self, index: int, expected: _Parameter, filled: set[str]) -> str | None:
        """Return why the *index*-th positional argument *expected* reaches no parameter, filling the one it reaches."""
        argument = _argument(index, expected)
        taker = self.positional[index] if index < len(self.positional) else None
        if taker is None and not self.var_positional:
            return f"{argument} is passed by position, and no parameter takes it{self._keyword_only_hint()}"
        if expected.kind is _Parameter.POSITIONAL_OR_KEYWORD:
            reason = self._named_positional_refusal(expected, taker)
            if reason is not None:
                return reason
        if taker is None:
            return None
        filled.add(taker.name)
        if expected.default is not _Parameter.empty and taker.default is _Parameter.empty:
            return f"{argument} may be left out, but parameter {taker.name!r} is required"
        return None

    def _named_positional_refusal(self, expected: _Parameter, taker: _Parameter | None) -> str | None:
        """Return why the argument *expected*, passed by position to *taker* or by name, reaches two parameters."""
        argument = f"argument {expected.name!r}"
        if taker is not None:
            if taker.name != expected.name:
                return f"{argument} may be passed by name, but the parameter at its position is {taker.name!r}"
            if taker.kind is _Parameter.POSITIONAL_ONLY:
                return f"{argument} may be passed by name, but parameter {taker.name!r} is positional-only"
            return None
        named = self.by_name.get(expected.name)
        if named is None:
            return None if self.var_keyword else f"{argument} may be passed by name, and no parameter takes it"
        if named.default is _Parameter.empty:
            return f"{argument} passed by position goes to '*args', leaving {named.name!r} unset"
        return None

    def _keyword_refusal(self, expected: _Parameter, filled: set[str]) -> str | None:
        """Return why the keyword argument *expected* does not reach this callee, filling what it reaches."""
        keyword = f"keyword {expected.name!r}"
        taker = self.by_name.get(expected.name)
        if taker is None:
            return None if self.var_keyword else f"{keyword} is passed, and no parameter takes it"
        if taker.name in filled:
            return f"{keyword} is passed, but {taker.name!r} already takes a positional argument"
        filled.add(taker.name)
        if expected.default is not _Parameter.empty and taker.default is _Parameter.empty:
            return f"{keyword} may be left out, but parameter {taker.name!r} is required"
        return None

    def _keyword_only_hint(self) -> str:
        """Return a note naming a keyword-only parameter, a required one first, or nothing when there is none."""
        keyword_only = [p for p in self.parameters if p.kind is _Parameter.KEYWORD_ONLY]
        keyword_only.sort(key=lambda p: p.default is not _Parameter.empty)
        return f" ({keyword_only[0].name!r} is keyword-only)" if keyword_only else ""
