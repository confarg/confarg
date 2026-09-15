# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for namedtuple support (typing.NamedTuple and collections.namedtuple)."""

from __future__ import annotations

import argparse
from collections import namedtuple
from dataclasses import dataclass, field
from typing import NamedTuple

import pytest

import confarg
from confarg.cli.argparse import from_namespace, populate_parser
from confarg.exceptions import MissingFieldError, TypeCoercionError
from confarg.typedload import construct

# ---------------------------------------------------------------------------
# Type fixtures
# ---------------------------------------------------------------------------


class Point(NamedTuple):
    """Typed 2D point."""

    x: int
    y: int


class Color(NamedTuple):
    """RGB color with a default alpha."""

    r: int
    g: int
    b: int
    a: int = 255


# Untyped namedtuple (all fields are Any)
Coord = namedtuple("Coord", ["lat", "lon"])


@dataclass
class WithPoint:
    """Dataclass with a typed namedtuple field."""

    pair: Point


@dataclass
class WithColor:
    """Dataclass with a namedtuple that has defaults."""

    color: Color = field(default_factory=lambda: Color(0, 0, 0))


@dataclass
class WithIntPair:
    """Dataclass with a plain fixed-length tuple field, the namedtuple's reference shape."""

    pair: tuple[int, int] = (0, 0)


@dataclass
class WithOptionalPoint:
    """Dataclass with an optional namedtuple field."""

    pair: Point | None = None


@dataclass
class WithCoord:
    """Dataclass with an untyped namedtuple field."""

    location: Coord


@dataclass
class WithStrOrPoint:
    """Dataclass whose field is a union with a namedtuple variant."""

    v: str | Point = "unset"


@dataclass
class WithStrOrIntPair:
    """The same union spelled with a plain tuple, the namedtuple's reference shape."""

    v: str | tuple[int, int] = "unset"


# ---------------------------------------------------------------------------
# Construction tests
# ---------------------------------------------------------------------------


class TestConstruct:
    """Unit tests for _construct_namedtuple."""

    def test_from_list(self) -> None:
        """List input constructs namedtuple by position."""
        result = construct(Point, [1, 2])
        assert result == Point(x=1, y=2)

    def test_from_tuple(self) -> None:
        """Tuple input constructs namedtuple by position."""
        result = construct(Point, (3, 4))
        assert result == Point(x=3, y=4)

    def test_from_dict_field_names(self) -> None:
        """Dict with field-name keys constructs namedtuple."""
        result = construct(Point, {"x": 10, "y": 20})
        assert result == Point(x=10, y=20)

    def test_from_dict_index_keys(self) -> None:
        """Dict with integer-string keys constructs namedtuple by index."""
        result = construct(Point, {"0": 5, "1": 6})
        assert result == Point(x=5, y=6)

    def test_from_dict_with_default_omitted(self) -> None:
        """Dict that omits a defaulted field uses the default."""
        result = construct(Color, {"r": 255, "g": 0, "b": 0})
        assert result == Color(r=255, g=0, b=0, a=255)

    def test_from_list_with_defaults(self) -> None:
        """Shorter list uses defaults for trailing fields."""
        result = construct(Color, [100, 150, 200])
        assert result == Color(r=100, g=150, b=200, a=255)

    def test_type_coercion_from_strings(self) -> None:
        """String tokens are coerced to the declared field types."""
        from confarg._types import _StrToken  # noqa: PLC0415 — private test helper

        result = construct(Point, [_StrToken("7"), _StrToken("8")])
        assert result == Point(x=7, y=8)

    def test_wrong_length_raises(self) -> None:
        """List longer than namedtuple arity raises TypeCoercionError."""
        with pytest.raises(TypeCoercionError, match="expected 2 elements, got 3"):
            construct(Point, [1, 2, 3])

    def test_unknown_field_raises(self) -> None:
        """Dict with unknown field name raises TypeCoercionError."""
        with pytest.raises(TypeCoercionError, match="Unknown field"):
            construct(Point, {"x": 1, "z": 99})

    def test_missing_required_field_raises(self) -> None:
        """Dict that omits a required field raises MissingFieldError."""
        with pytest.raises(MissingFieldError, match="Missing required field"):
            construct(Point, {"x": 1})

    def test_index_out_of_range_raises(self) -> None:
        """Index key out of bounds raises TypeCoercionError."""
        with pytest.raises(TypeCoercionError, match="index 5 out of range"):
            construct(Point, {"5": 1})

    def test_untyped_namedtuple(self) -> None:
        """Untyped namedtuple constructed from dict passes values through as-is."""
        result = construct(Coord, {"lat": "51.5", "lon": "-0.1"})
        assert result == Coord(lat="51.5", lon="-0.1")

    def test_untyped_from_list(self) -> None:
        """Untyped namedtuple constructed from list passes values through as-is."""
        result = construct(Coord, ["51.5", "-0.1"])
        assert result == Coord(lat="51.5", lon="-0.1")


class TestUnionVariant:
    """A namedtuple variant of a union takes the sequence its reference tuple takes.

    ``str | Point`` and ``str | tuple[int, int]`` are the same shape, so every channel
    must build the namedtuple from ``[13, 42]`` exactly as it builds the tuple (BUG-21).
    """

    def test_union_from_list(self) -> None:
        """A list builds the namedtuple variant rather than failing against str."""
        assert confarg.build(WithStrOrPoint, {"v": [13, 42]}).v == Point(x=13, y=42)

    def test_union_matches_plain_tuple(self) -> None:
        """The namedtuple variant accepts exactly what the same-arity tuple variant accepts."""
        assert (
            tuple(confarg.build(WithStrOrPoint, {"v": [13, 42]}).v)
            == confarg.build(
                WithStrOrIntPair,
                {"v": [13, 42]},
            ).v
        )

    def test_union_from_dict(self) -> None:
        """A dict of field names still builds the namedtuple variant."""
        assert confarg.build(WithStrOrPoint, {"v": {"x": 13, "y": 42}}).v == Point(x=13, y=42)

    def test_union_scalar_variant_still_wins(self) -> None:
        """A plain string still goes to the str variant, not to the namedtuple."""
        assert confarg.build(WithStrOrPoint, {"v": "hello"}).v == "hello"

    def test_union_wrong_arity_is_refused(self) -> None:
        """A list of the wrong arity matches no variant, as it does for the plain tuple."""
        for target in (WithStrOrIntPair, WithStrOrPoint):
            with pytest.raises(TypeCoercionError):
                confarg.build(target, {"v": [13, 42, 7]})

    def test_union_from_cli(self) -> None:
        """The CLI spelling reaches the namedtuple variant too."""
        assert confarg.load(WithStrOrPoint, argv=["--v", "13", "42"], env={}).v == Point(x=13, y=42)

    def test_union_from_env(self) -> None:
        """The env spelling reaches the namedtuple variant too."""
        cfg = confarg.load(WithStrOrPoint, argv=[], env={"V": "[13, 42]"}, env_prefix="")
        assert cfg.v == Point(x=13, y=42)


# ---------------------------------------------------------------------------
# Serialization tests
# ---------------------------------------------------------------------------


class TestSerialize:
    """Tests for namedtuple → dict serialization."""

    def test_serialize_to_dict(self) -> None:
        """Namedtuple serializes to a dict keyed by field name."""
        p = Point(x=3, y=4)
        result = confarg.dump(WithPoint(pair=p))
        assert result == {"pair": {"x": 3, "y": 4}}

    def test_serialize_with_defaults(self) -> None:
        """Defaulted fields appear in the serialized dict."""
        c = Color(r=255, g=0, b=0)
        result = confarg.dump(WithColor(color=c))
        assert result == {"color": {"r": 255, "g": 0, "b": 0, "a": 255}}

    def test_round_trip_via_dict(self) -> None:
        """dump() then from_dict() reconstructs an equal namedtuple."""
        p = Point(x=7, y=8)
        dumped = confarg.dump(WithPoint(pair=p))
        loaded = confarg.from_dict(WithPoint, dumped)
        assert loaded.pair == p


# ---------------------------------------------------------------------------
# CLI: argparse integration
# ---------------------------------------------------------------------------


class TestCLIArgparse:
    """Tests for all three CLI input forms for namedtuple fields."""

    def test_flags_registered(self) -> None:
        """All three flag forms are registered in the parser."""
        parser = argparse.ArgumentParser()
        populate_parser(WithPoint, parser)
        actions = {a.option_strings[0] for a in parser._actions if a.option_strings}
        assert "--pair" in actions
        assert "--pair.x" in actions
        assert "--pair.y" in actions
        assert "--pair.0" in actions
        assert "--pair.1" in actions

    def test_nargs_form(self) -> None:
        """--pair 13 42 sets x=13, y=42."""
        parser = argparse.ArgumentParser()
        populate_parser(WithPoint, parser)
        ns = parser.parse_args(["--pair", "13", "42"])
        result = from_namespace(WithPoint, ns)
        assert result.pair == Point(x=13, y=42)

    def test_field_name_form(self) -> None:
        """--pair.x 13 --pair.y 42 sets x=13, y=42."""
        parser = argparse.ArgumentParser()
        populate_parser(WithPoint, parser)
        ns = parser.parse_args(["--pair.x", "13", "--pair.y", "42"])
        result = from_namespace(WithPoint, ns)
        assert result.pair == Point(x=13, y=42)

    def test_index_form(self) -> None:
        """--pair.0 13 --pair.1 42 sets x=13, y=42."""
        parser = argparse.ArgumentParser()
        populate_parser(WithPoint, parser)
        ns = parser.parse_args(["--pair.0", "13", "--pair.1", "42"])
        result = from_namespace(WithPoint, ns)
        assert result.pair == Point(x=13, y=42)

    def test_field_name_overrides_nargs(self) -> None:
        """Sub-flag overrides that field's position; nargs fills the rest."""
        parser = argparse.ArgumentParser()
        populate_parser(WithPoint, parser)
        ns = parser.parse_args(["--pair", "1", "2", "--pair.x", "99"])
        result = from_namespace(WithPoint, ns)
        # x=99 from sub-flag; y=2 from nargs position 1
        assert result.pair == Point(x=99, y=2)

    def test_field_name_overrides_index(self) -> None:
        """Field-name sub-flag takes precedence over index sub-flag for same position."""
        parser = argparse.ArgumentParser()
        populate_parser(WithPoint, parser)
        ns = parser.parse_args(["--pair.0", "1", "--pair.x", "99", "--pair.y", "2"])
        result = from_namespace(WithPoint, ns)
        assert result.pair == Point(x=99, y=2)

    def test_all_sub_flags_no_nargs(self) -> None:
        """All fields set via sub-flags without the combined nargs flag."""
        parser = argparse.ArgumentParser()
        populate_parser(WithPoint, parser)
        ns = parser.parse_args(["--pair.x", "5", "--pair.y", "6"])
        result = from_namespace(WithPoint, ns)
        assert result.pair == Point(x=5, y=6)

    def test_with_defaults(self) -> None:
        """Fields with defaults don't need to be set on CLI."""
        parser = argparse.ArgumentParser()
        populate_parser(WithColor, parser)
        ns = parser.parse_args(["--color.r", "200", "--color.g", "100", "--color.b", "50"])
        result = from_namespace(WithColor, ns)
        assert result.color == Color(r=200, g=100, b=50, a=255)


class TestCLIVanilla:
    """Vanilla argv parsing treats a namedtuple as the fixed-length sequence it is.

    A namedtuple field takes the CLI spellings ``tuple[int, int]`` takes -- exactly its
    arity in positional tokens, or a whole ``[...]`` JSON array -- plus the whole
    ``{...}`` JSON object its field names make meaningful, which the env channel already
    accepts.
    """

    def test_positional_form(self) -> None:
        """--pair 13 42 consumes exactly the namedtuple's arity, as a fixed tuple does."""
        assert confarg.load(WithPoint, argv=["--pair", "13", "42"], env={}).pair == Point(x=13, y=42)

    def test_json_array_form(self) -> None:
        """--pair '[13, 42]' takes a whole JSON array, as a fixed tuple does."""
        assert confarg.load(WithPoint, argv=["--pair", "[13, 42]"], env={}).pair == Point(x=13, y=42)

    def test_json_object_form(self) -> None:
        """--pair '{"x": 13, "y": 42}' takes a whole JSON object, as the env channel does."""
        cfg = confarg.load(WithPoint, argv=["--pair", '{"x": 13, "y": 42}'], env={})
        assert cfg.pair == Point(x=13, y=42)

    def test_json_object_form_partial(self) -> None:
        """A whole JSON object may omit a field that has a default."""
        cfg = confarg.load(WithColor, argv=["--color", '{"r": 1, "g": 2, "b": 3}'], env={})
        assert cfg.color == Color(r=1, g=2, b=3, a=255)

    def test_json_object_matches_env(self) -> None:
        """The CLI and the env channel decode the same whole JSON object (BUG-16)."""
        blob = '{"x": 13, "y": 42}'
        assert confarg.load(WithPoint, argv=["--pair", blob], env={}) == confarg.load(
            WithPoint,
            argv=[],
            env={"PAIR": blob},
            env_prefix="",
        )

    def test_optional_positional_form(self) -> None:
        """Optionality does not change the spelling: Point | None consumes its arity too."""
        cfg = confarg.load(WithOptionalPoint, argv=["--pair", "13", "42"], env={})
        assert cfg.pair == Point(x=13, y=42)

    def test_optional_json_object_form(self) -> None:
        """Optionality does not change the spelling: Point | None takes the whole object."""
        cfg = confarg.load(WithOptionalPoint, argv=["--pair", '{"x": 13, "y": 42}'], env={})
        assert cfg.pair == Point(x=13, y=42)

    def test_field_name_form(self) -> None:
        """--pair.x 13 --pair.y 42 still addresses the fields individually."""
        cfg = confarg.load(WithPoint, argv=["--pair.x", "13", "--pair.y", "42"], env={})
        assert cfg.pair == Point(x=13, y=42)

    def test_bare_flag_is_rejected(self) -> None:
        """--pair with no token is rejected, exactly as a same-arity tuple field is."""
        with pytest.raises(TypeCoercionError):
            confarg.load(WithIntPair, argv=["--pair"], env={})
        with pytest.raises(TypeCoercionError):
            confarg.load(WithPoint, argv=["--pair"], env={})

    def test_spellings_match_a_same_arity_tuple(self) -> None:
        """Every positional spelling a tuple[int, int] accepts, the namedtuple accepts."""
        for argv in (["--pair", "13", "42"], ["--pair", "[13, 42]"]):
            assert (
                tuple(confarg.load(WithPoint, argv=argv, env={}).pair)
                == confarg.load(
                    WithIntPair,
                    argv=argv,
                    env={},
                ).pair
            )


# ---------------------------------------------------------------------------
# Env var tests
# ---------------------------------------------------------------------------


class TestEnvVars:
    """Tests for env var parsing of namedtuple fields."""

    def test_json_array(self) -> None:
        """JSON array env var → positional construction."""
        result = confarg.load(WithPoint, argv=[], env={"PAIR": "[13, 42]"}, env_prefix="")
        assert result.pair == Point(x=13, y=42)

    def test_json_object(self) -> None:
        """JSON object env var → field-name construction."""
        result = confarg.load(WithPoint, argv=[], env={"PAIR": '{"x": 13, "y": 42}'}, env_prefix="")
        assert result.pair == Point(x=13, y=42)

    def test_field_name_segments(self) -> None:
        """Individual field-name segments in env vars."""
        result = confarg.load(WithPoint, argv=[], env={"PAIR__X": "13", "PAIR__Y": "42"}, env_prefix="")
        assert result.pair == Point(x=13, y=42)

    def test_index_segments(self) -> None:
        """Numeric index segments in env vars."""
        result = confarg.load(WithPoint, argv=[], env={"PAIR__0": "13", "PAIR__1": "42"}, env_prefix="")
        assert result.pair == Point(x=13, y=42)

    def test_with_prefix(self) -> None:
        """Env var prefix is respected."""
        result = confarg.load(WithPoint, argv=[], env={"APP__PAIR": "[7, 8]"}, env_prefix="APP")
        assert result.pair == Point(x=7, y=8)

    def test_case_insensitive_field_names(self) -> None:
        """Env var field matching is case-insensitive."""
        result = confarg.load(WithPoint, argv=[], env={"PAIR__X": "5", "PAIR__Y": "6"}, env_prefix="")
        assert result.pair == Point(x=5, y=6)

    def test_with_defaults_partial(self) -> None:
        """Partial env vars use field defaults for missing fields."""
        result = confarg.load(
            WithColor,
            argv=[],
            env={"COLOR__R": "255", "COLOR__G": "0", "COLOR__B": "0"},
            env_prefix="",
        )
        assert result.color == Color(r=255, g=0, b=0, a=255)

    def test_unknown_env_field_raises(self) -> None:
        """Unknown namedtuple field in env var raises TypeCoercionError at construction."""
        with pytest.raises(TypeCoercionError, match="Unknown field"):
            confarg.load(WithPoint, argv=[], env={"PAIR__Z": "99"}, env_prefix="")


# ---------------------------------------------------------------------------
# Config file tests
# ---------------------------------------------------------------------------


class TestConfigFiles:
    """Tests for namedtuple in config files (list and dict forms)."""

    def test_list_form_toml(self, tmp_path) -> None:
        """TOML: pair = [13, 42] constructs a namedtuple."""
        p = tmp_path / "config.toml"
        p.write_text("pair = [13, 42]\n")
        result = confarg.load(WithPoint, argv=[], files=[str(p)])
        assert result.pair == Point(x=13, y=42)

    def test_dict_form_toml(self, tmp_path) -> None:
        """TOML: [pair] section with x/y keys constructs a namedtuple."""
        p = tmp_path / "config.toml"
        p.write_text("[pair]\nx = 13\ny = 42\n")
        result = confarg.load(WithPoint, argv=[], files=[str(p)])
        assert result.pair == Point(x=13, y=42)

    def test_list_form_yaml(self, tmp_path) -> None:
        """YAML: pair as list constructs a namedtuple."""
        p = tmp_path / "config.yaml"
        p.write_text("pair:\n  - 13\n  - 42\n")
        result = confarg.load(WithPoint, argv=[], files=[str(p)])
        assert result.pair == Point(x=13, y=42)

    def test_dict_form_yaml(self, tmp_path) -> None:
        """YAML: pair as mapping with field-name keys constructs a namedtuple."""
        p = tmp_path / "config.yaml"
        p.write_text("pair:\n  x: 13\n  y: 42\n")
        result = confarg.load(WithPoint, argv=[], files=[str(p)])
        assert result.pair == Point(x=13, y=42)

    def test_json_list_form(self, tmp_path) -> None:
        """JSON: pair as list constructs a namedtuple."""
        p = tmp_path / "config.json"
        p.write_text('{"pair": [13, 42]}')
        result = confarg.load(WithPoint, argv=[], files=[str(p)])
        assert result.pair == Point(x=13, y=42)

    def test_json_dict_form(self, tmp_path) -> None:
        """JSON: pair as object with field names constructs a namedtuple."""
        p = tmp_path / "config.json"
        p.write_text('{"pair": {"x": 13, "y": 42}}')
        result = confarg.load(WithPoint, argv=[], files=[str(p)])
        assert result.pair == Point(x=13, y=42)

    def test_dump_round_trip_toml(self, tmp_path) -> None:
        """dump() then load() from TOML reconstructs an equal namedtuple."""
        try:
            import tomli_w  # noqa: PLC0415 — optional dep, checked at test time
        except ImportError:
            pytest.skip("tomli_w not available")
        original = WithPoint(pair=Point(x=3, y=4))
        dumped = confarg.dump(original)
        p = tmp_path / "config.toml"
        with open(p, "wb") as f:
            tomli_w.dump(dumped, f)
        loaded = confarg.load(WithPoint, argv=[], files=[str(p)])
        assert loaded.pair == original.pair
