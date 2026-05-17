# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for Final[X] field support: coercion, CLI flag building, and completion filtering."""

from __future__ import annotations

import argparse
import enum
from dataclasses import dataclass
from typing import Final, Literal

import pytest

import confarg
from confarg.cli.argparse._build import _collect_struct_specs
from confarg.cli.argparse._completion import _extend_walk, _WalkCtx
from tests.conftest import make_target

# ---------------------------------------------------------------------------
# Coercion: Final[Literal[str]]
# ---------------------------------------------------------------------------


class TestFinalStrLiteral:
    """Final[Literal[str]] coercion and validation."""

    def test_valid(self) -> None:
        """Valid literal value is accepted."""
        Target = make_target("kind", Final[Literal["a"]], default="a")
        result = confarg.load(Target, args=["--kind", "a"], env={})
        assert result.kind == "a"

    def test_invalid_raises(self) -> None:
        """Invalid literal value raises ConfargError."""
        Target = make_target("kind", Final[Literal["a"]], default="a")
        with pytest.raises(confarg.ConfargError):
            confarg.load(Target, args=["--kind", "b"], env={})

    def test_default_used_when_not_provided(self) -> None:
        """Default is used when the field is not set via CLI."""
        Target = make_target("kind", Final[Literal["a"]], default="a")
        result = confarg.load(Target, args=[], env={})
        assert result.kind == "a"


# ---------------------------------------------------------------------------
# Coercion: Final[Literal[int]]
# ---------------------------------------------------------------------------


class TestFinalIntLiteral:
    """Final[Literal[int]] coercion and validation."""

    def test_valid(self) -> None:
        """CLI token '42' coerces to int 42 via str(v)==s."""
        Target = make_target("code", Final[Literal[42]], default=42)
        result = confarg.load(Target, args=["--code", "42"], env={})
        assert result.code == 42

    def test_invalid_raises(self) -> None:
        """Non-matching int token raises ConfargError."""
        Target = make_target("code", Final[Literal[42]], default=42)
        with pytest.raises(confarg.ConfargError):
            confarg.load(Target, args=["--code", "43"], env={})


# ---------------------------------------------------------------------------
# Coercion: Final[Literal[bool]]
# ---------------------------------------------------------------------------


class TestFinalBoolLiteral:
    """Final[Literal[bool]] coercion — case-sensitive (str(True)=='True')."""

    def test_valid(self) -> None:
        """CLI token 'True' (capital T) is accepted for Literal[True]."""
        Target = make_target("flag", Final[Literal[True]], default=True)
        result = confarg.load(Target, args=["--flag", "True"], env={})
        assert result.flag is True

    def test_invalid_case_raises(self) -> None:
        """CLI token 'true' (lowercase) is rejected — same behaviour as bare Literal[True]."""
        Target = make_target("flag", Final[Literal[True]], default=True)
        with pytest.raises(confarg.ConfargError):
            confarg.load(Target, args=["--flag", "true"], env={})


# ---------------------------------------------------------------------------
# Coercion: Final[Literal[None]]
# ---------------------------------------------------------------------------


class TestFinalNoneLiteral:
    """Final[Literal[None]] coercion."""

    def test_valid(self) -> None:
        """CLI token 'None' is accepted for Literal[None]."""
        Target = make_target("sentinel", Final[Literal[None]], default=None)
        result = confarg.load(Target, args=["--sentinel", "None"], env={})
        assert result.sentinel is None


# ---------------------------------------------------------------------------
# Coercion: Final[Literal[EnumMember]]
# ---------------------------------------------------------------------------


class _Color(enum.Enum):
    RED = "red"


class TestFinalEnumLiteral:
    """Final[Literal[EnumMember]] coercion."""

    def test_valid(self) -> None:
        """CLI token matching str(EnumMember) is accepted."""
        Target = make_target("color", Final[Literal[_Color.RED]], default=_Color.RED)
        token = str(_Color.RED)
        result = confarg.load(Target, args=["--color", token], env={})
        assert result.color is _Color.RED


# ---------------------------------------------------------------------------
# Coercion: Final[int] (non-Literal inner type)
# ---------------------------------------------------------------------------


class TestFinalInt:
    """Final[int] coercion — any int is valid (no literal constraint)."""

    def test_any_int_accepted(self) -> None:
        """Any integer string is coerced correctly."""
        Target = make_target("count", Final[int], default=0)
        result = confarg.load(Target, args=["--count", "99"], env={})
        assert result.count == 99

    def test_wrong_type_raises(self) -> None:
        """Non-integer string raises ConfargError."""
        Target = make_target("count", Final[int], default=0)
        with pytest.raises(confarg.ConfargError):
            confarg.load(Target, args=["--count", "not_an_int"], env={})


# ---------------------------------------------------------------------------
# CLI flag building: choices for Final[Literal[...]]
# ---------------------------------------------------------------------------


class TestFinalFlagChoices:
    """_collect_struct_specs produces correct FlagSpec.choices for Final[Literal[...]] fields."""

    def test_str_literal_choices(self) -> None:
        """Final[Literal['a']] produces choices=['a']."""
        Target = make_target("kind", Final[Literal["a"]], default="a")
        specs = _collect_struct_specs(Target, "", "class")
        spec = next(s for s in specs if s.name == "kind")
        assert spec.choices == ["a"]

    def test_int_literal_choices(self) -> None:
        """Final[Literal[42]] produces choices=['42']."""
        Target = make_target("code", Final[Literal[42]], default=42)
        specs = _collect_struct_specs(Target, "", "class")
        spec = next(s for s in specs if s.name == "code")
        assert spec.choices == ["42"]

    def test_final_int_no_choices(self) -> None:
        """Final[int] produces no choices (unconstrained scalar)."""
        Target = make_target("count", Final[int], default=0)
        specs = _collect_struct_specs(Target, "", "class")
        spec = next(s for s in specs if s.name == "count")
        assert spec.choices is None


# ---------------------------------------------------------------------------
# Completion: Final field skipped when concrete=True, registered when False
# ---------------------------------------------------------------------------


@dataclass
class _WithFinalAndValue:
    kind: Final[Literal["a"]] = "a"
    value: int = 0


class TestFinalCompletion:
    """_extend_walk skips Final fields when concrete=True (class already selected)."""

    def test_final_registered_when_not_concrete(self) -> None:
        """Final fields ARE registered for completion before the class is selected."""
        parser = argparse.ArgumentParser()
        ctx = _WalkCtx(parser=parser, union_tag="class")
        _extend_walk(_WithFinalAndValue, ctx, parser, "", concrete=False)
        assert "kind" in ctx.existing_dests
        assert "value" in ctx.existing_dests

    def test_final_skipped_when_concrete(self) -> None:
        """Final fields are NOT registered once the class is concretely selected."""
        parser = argparse.ArgumentParser()
        ctx = _WalkCtx(parser=parser, union_tag="class")
        _extend_walk(_WithFinalAndValue, ctx, parser, "", concrete=True)
        assert "kind" not in ctx.existing_dests
        assert "value" in ctx.existing_dests
