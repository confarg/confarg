# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for the structural conformance rules of ``confarg._conformance``."""

from __future__ import annotations

import functools
import inspect
from typing import Any

import pytest

from confarg._conformance import call_conforms


def _expected(stub: Any) -> inspect.Signature:
    """Return the expected signature *stub* spells, string annotations resolved."""
    return inspect.signature(stub, eval_str=True)


# The expected signatures: each stub spells the call it stands for.


def _one_positional(a, /): ...


def _none(): ...


def _one_named(x): ...


def _optional_positional(a=0, /): ...


def _keyword_only(*, k): ...


def _optional_keyword(*, k=0): ...


def _var_positional(*args: int): ...


def _var_keyword(**kwargs: int): ...


def _gradual_tail(a, /, *args, **kwargs): ...


def _gradual_any(*args: Any, **kwargs: Any): ...


def _typed_pair(*args: int, **kwargs: int): ...


# The implementations.


def _takes_x(x: int) -> int:
    return x


def _optional_x(x: int = 0) -> int:
    return x


def _kw_only(*, x: int) -> int:
    return x


def _positional_only(x: int, /) -> int:
    return x


def _two(x: int, y: str) -> int:
    return x


def _star_args(*args: int) -> int:
    return 0


def _star_kwargs(**kwargs: int) -> int:
    return 0


def _both_stars(*args: int, **kwargs: int) -> int:
    return 0


def _nothing() -> int:
    return 0


def _with_required_keyword(x: int, *, k: str) -> int:
    return x


def _named_y(y: int) -> int:
    return y


class TestCallConformsImplementation:
    """The implementation side: what ``call_conforms`` reads off the callable it is given."""

    def test_positional_or_keyword_takes_a_position(self) -> None:
        """A positional-or-keyword parameter takes a positional argument."""
        assert call_conforms(_takes_x, _expected(_one_positional)) is None

    def test_positional_only_takes_a_position(self) -> None:
        """A positional-only parameter takes a positional argument."""
        assert call_conforms(_positional_only, _expected(_one_positional)) is None

    def test_positional_only_refuses_a_name(self) -> None:
        """A positional-only parameter cannot take an argument passed by name."""
        reason = call_conforms(_positional_only, _expected(_one_named))
        assert reason == "argument 'x' may be passed by name, but parameter 'x' is positional-only"

    def test_keyword_only_refuses_a_position(self) -> None:
        """A keyword-only parameter cannot take a positional argument (BUG-291)."""
        reason = call_conforms(_kw_only, _expected(_one_positional))
        assert reason == "argument 1 is passed by position, and no parameter takes it ('x' is keyword-only)"

    def test_optional_parameter_takes_a_position(self) -> None:
        """An optional parameter takes a positional argument as well as a required one does (BUG-291)."""
        assert call_conforms(_optional_x, _expected(_one_positional)) is None

    def test_var_positional_takes_every_position(self) -> None:
        """``*args`` takes any positional argument."""
        assert call_conforms(_star_args, _expected(_one_positional)) is None

    def test_var_positional_refuses_a_name(self) -> None:
        """``*args`` takes no argument passed by name."""
        reason = call_conforms(_star_args, _expected(_one_named))
        assert reason == "argument 'x' may be passed by name, and no parameter takes it"

    def test_var_keyword_takes_a_keyword(self) -> None:
        """``**kwargs`` takes a keyword argument no parameter is named for."""
        assert call_conforms(_star_kwargs, _expected(_keyword_only)) is None

    def test_both_stars_take_a_named_argument(self) -> None:
        """``*args`` and ``**kwargs`` together take an argument passed by position or by name."""
        assert call_conforms(_both_stars, _expected(_one_named)) is None

    def test_required_parameter_left_unfilled_is_refused(self) -> None:
        """A required parameter the call never fills is refused."""
        reason = call_conforms(_two, _expected(_one_positional))
        assert reason == "parameter 'y' is required, and the call never passes it"

    def test_partial_bound_argument_is_not_required(self) -> None:
        """A partial's bound argument is no longer one the call must pass."""
        assert call_conforms(functools.partial(_two, y="s"), _expected(_one_positional)) is None

    def test_partial_bound_by_name_turns_the_rest_keyword_only(self) -> None:
        """A partial binding its first parameter by name leaves the next one keyword-only."""
        reason = call_conforms(functools.partial(_two, x=1), _expected(_one_positional))
        assert reason == "argument 1 is passed by position, and no parameter takes it ('y' is keyword-only)"

    def test_uninspectable_builtin_is_accepted(self) -> None:
        """A callable whose signature ``inspect`` cannot read is accepted unchecked."""

        class Uninspectable:
            def __call__(self) -> None: ...

            @property
            def __signature__(self) -> inspect.Signature:
                msg = "no signature found"
                raise ValueError(msg)

        assert call_conforms(Uninspectable(), _expected(_typed_pair)) is None

    def test_non_callable_is_refused(self) -> None:
        """Something that cannot be called at all is refused."""
        assert call_conforms(3, _expected(_none)) == "3 is not callable"

    def test_class_is_read_by_its_constructor(self) -> None:
        """A class is called through its constructor, whose receiver is no parameter."""

        class Point:
            def __init__(self, x: int) -> None:
                self.x = x

        assert call_conforms(Point, _expected(_one_positional)) is None
        assert call_conforms(Point, _expected(_none)) == "parameter 'x' is required, and the call never passes it"


class TestCallConformsExpected:
    """The expected side: every way the expected signature can be called must work (BUG-291)."""

    def test_no_argument_refuses_a_required_parameter(self) -> None:
        """A call with no argument refuses a callable that requires one."""
        assert call_conforms(_takes_x, _expected(_none)) == "parameter 'x' is required, and the call never passes it"

    def test_no_argument_takes_an_optional_parameter(self) -> None:
        """A call with no argument takes a callable whose parameters all have defaults."""
        assert call_conforms(_optional_x, _expected(_none)) is None

    def test_extra_positional_is_refused(self) -> None:
        """A call passing more positional arguments than the callable takes is refused."""
        reason = call_conforms(_nothing, _expected(_one_positional))
        assert reason == "argument 1 is passed by position, and no parameter takes it"

    def test_named_argument_must_reach_the_same_name(self) -> None:
        """An argument passed by position or by name needs a parameter of that name at that position."""
        reason = call_conforms(_named_y, _expected(_one_named))
        assert reason == "argument 'x' may be passed by name, but the parameter at its position is 'y'"

    def test_named_argument_reaches_a_parameter_of_that_name(self) -> None:
        """An argument passed by position or by name is taken by a parameter of that name at that position."""
        assert call_conforms(_takes_x, _expected(_one_named)) is None

    def test_keyword_only_needs_a_parameter_of_that_name(self) -> None:
        """An expected keyword-only argument needs a parameter of its name, or ``**kwargs``."""
        assert call_conforms(_nothing, _expected(_keyword_only)) == "keyword 'k' is passed, and no parameter takes it"

    def test_keyword_only_is_taken_by_a_positional_or_keyword_parameter(self) -> None:
        """An expected keyword-only argument is taken by a positional-or-keyword parameter of its name."""

        def takes_k(k: int) -> int:
            return k

        assert call_conforms(takes_k, _expected(_keyword_only)) is None

    def test_expected_default_needs_an_optional_parameter(self) -> None:
        """An argument the call may leave out needs a parameter with a default."""
        reason = call_conforms(_takes_x, _expected(_optional_positional))
        assert reason == "argument 1 may be left out, but parameter 'x' is required"

    def test_expected_default_keyword_needs_an_optional_parameter(self) -> None:
        """A keyword argument the call may leave out needs a parameter with a default."""

        def needs_k(*, k: int) -> int:
            return k

        def lax(*, k: int = 1, other: int = 1) -> int:
            return k

        reason = call_conforms(needs_k, _expected(_optional_keyword))
        assert reason == "keyword 'k' may be left out, but parameter 'k' is required"
        assert call_conforms(lax, _expected(_optional_keyword)) is None

    def test_expected_var_positional_needs_var_positional(self) -> None:
        """An expected ``*args`` needs the callable's own ``*args``."""
        assert call_conforms(_star_args, _expected(_var_positional)) is None
        reason = call_conforms(_optional_x, _expected(_var_positional))
        assert reason == "extra positional arguments are passed, and no '*args' takes them"

    def test_expected_var_keyword_needs_var_keyword(self) -> None:
        """An expected ``**kwargs`` needs the callable's own ``**kwargs``."""
        assert call_conforms(_star_kwargs, _expected(_var_keyword)) is None
        reason = call_conforms(_optional_x, _expected(_var_keyword))
        assert reason == "extra keyword arguments are passed, and no '**kwargs' takes them"

    def test_typed_pair_is_no_gradual_tail(self) -> None:
        """A ``*args, **kwargs`` pair annotated other than ``Any`` needs both of the callable's own."""
        reason = call_conforms(_nothing, _expected(_typed_pair))
        assert reason == "extra positional arguments are passed, and no '*args' takes them"
        assert call_conforms(_both_stars, _expected(_typed_pair)) is None

    @pytest.mark.parametrize("stub", [_gradual_tail, _gradual_any], ids=["unannotated", "any"])
    @pytest.mark.parametrize("impl", [_two, _with_required_keyword, _positional_only, _takes_x])
    def test_gradual_tail_takes_any_further_parameter(self, stub: Any, impl: Any) -> None:
        """An unannotated or ``Any`` ``*args, **kwargs`` pair reads as ``...``: any further parameter is taken."""
        if stub is _gradual_any:
            assert call_conforms(_nothing, _expected(stub)) is None
        assert call_conforms(impl, _expected(stub)) is None

    def test_gradual_tail_keeps_its_prefix(self) -> None:
        """The parameters before a gradual pair are still checked."""
        reason = call_conforms(_nothing, _expected(_gradual_tail))
        assert reason == "argument 1 is passed by position, and no parameter takes it"


class TestCallConformsTwoRoutes:
    """An argument a call may pass two ways must reach one parameter either way."""

    def test_named_argument_split_between_star_args_and_a_keyword_only_parameter(self) -> None:
        """Passed by position, the argument goes to ``*args``, leaving a required parameter of its name unset."""

        def split(*args: int, x: int) -> int:
            return x

        def split_optional(*args: int, x: int = 0) -> int:
            return x

        reason = call_conforms(split, _expected(_one_named))
        assert reason == "argument 'x' passed by position goes to '*args', leaving 'x' unset"
        assert call_conforms(split_optional, _expected(_one_named)) is None

    def test_keyword_reaching_a_parameter_a_position_fills(self) -> None:
        """A keyword argument naming the parameter a positional argument already fills is refused."""

        def first_then_keyword(a, /, *, x): ...

        reason = call_conforms(_takes_x, _expected(first_then_keyword))
        assert reason == "keyword 'x' is passed, but 'x' already takes a positional argument"
