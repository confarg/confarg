# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for namedtuple support (typing.NamedTuple and collections.namedtuple)."""

from __future__ import annotations

import argparse
from collections import namedtuple
from dataclasses import dataclass, field
from typing import Any, NamedTuple

import pytest

import confarg
from confarg._merge import DICT_DELETE, ListOp
from confarg.cli.argparse import from_namespace, populate_parser
from confarg.exceptions import ConfargError, MissingFieldError, TypeCoercionError
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


class MaybePoint(NamedTuple):
    """Typed 2D point whose y is optional but has no default."""

    x: int
    y: int | None


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

    def test_short_list_missing_required_field_raises(self) -> None:
        """A list that stops before a required field is the MissingFieldError a dict gets (BUG-167)."""
        with pytest.raises(MissingFieldError, match=r"'p\.y' .*\(--p\.y\)"):
            construct(Point, [1], path=("p",))
        with pytest.raises(MissingFieldError, match=r"'p\.y' .*\(--p\.y\)"):
            construct(Point, {"x": 1}, path=("p",))

    def test_short_list_does_not_fill_an_optional_field_with_none(self) -> None:
        """An optional field with no default is still required, positionally as by name (BUG-167)."""
        with pytest.raises(MissingFieldError, match=r"'p\.y'"):
            construct(MaybePoint, [1], path=("p",))
        with pytest.raises(MissingFieldError, match=r"'p\.y'"):
            construct(MaybePoint, {"x": 1}, path=("p",))

    def test_index_out_of_range_raises(self) -> None:
        """Index key out of bounds raises TypeCoercionError."""
        with pytest.raises(TypeCoercionError, match="index 5 out of range"):
            construct(Point, {"5": 1})

    def test_negative_index_counts_from_the_end(self) -> None:
        """A negative index key resolves against the arity, as a fixed tuple's does (BUG-80)."""
        assert construct(Point, {"0": 5, "-1": 6}) == Point(x=5, y=6)
        assert construct(Color, {"0": 0, "1": 0, "2": 0, "-1": 42}) == Color(r=0, g=0, b=0, a=42)

    def test_negative_index_out_of_range_raises(self) -> None:
        """A negative index past the length raises, as a positive one past it does."""
        with pytest.raises(TypeCoercionError, match="index -3 out of range"):
            construct(Point, {"-3": 1})

    def test_negative_index_beside_a_field_name_builds(self) -> None:
        """A negative key beside a field-name key names the other position (Q-1)."""
        assert construct(Point, {"x": 1, "-1": 2}) == Point(x=1, y=2)

    def test_index_beside_a_field_name_builds(self) -> None:
        """An index and a name each fill the position they spell (Q-1)."""
        assert construct(Point, {"0": 7, "y": 9}) == Point(x=7, y=9)

    def test_two_spellings_of_one_position_resolve_in_order(self) -> None:
        """Two spellings of one position: the later in the dict wins, as a later write does (Q-1)."""
        assert construct(Point, {"x": 13, "y": 2, "0": 9}) == Point(x=9, y=2)
        assert construct(Point, {"0": 9, "y": 2, "x": 13}) == Point(x=13, y=2)
        assert construct(Point, {"x": 1, "y": 2, "-1": 3}) == Point(x=1, y=3)

    @pytest.mark.parametrize("key", ["01", "-0", "+1", "1_0", " 1", "\u0661", "\u00b2"])
    def test_an_odd_index_spelling_names_no_position(self, key: str) -> None:
        """Only ``str(i)`` and ``str(i - n)`` name a position, as on the CLI (BUG-142)."""
        with pytest.raises(TypeCoercionError, match="Unknown field"):
            construct(Point, {"x": 1, key: 2})
        with pytest.raises(TypeCoercionError, match="Unknown field"):
            construct(Point, {key: 2})

    @pytest.mark.parametrize("key", ["01", "-0", "+1", "1_0", " 1", "\u0661"])
    def test_an_odd_index_spelling_names_no_tuple_position(self, key: str) -> None:
        """A fixed tuple reads its positions by the same rule (BUG-142)."""
        with pytest.raises(TypeCoercionError, match="dict keys must be integer indices"):
            construct(tuple[int, int], {"0": 1, key: 2})

    def test_from_dict_integer_keys(self) -> None:
        """Integer keys (a YAML file's own int parsing) index like their string spellings."""
        assert construct(Point, {0: 5, 1: 6}) == Point(x=5, y=6)
        assert construct(Color, {0: 0, 1: 0, 2: 0, -1: 42}) == Color(r=0, g=0, b=0, a=42)

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
        cfg = confarg.load(WithStrOrPoint, argv=[], env={"MYAPP_V": "[13, 42]"}, env_prefix="MYAPP_")
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
        argv = ["--pair", "13", "42"]
        ns = parser.parse_args(argv)
        result = from_namespace(WithPoint, ns, argv=argv)
        assert result.pair == Point(x=13, y=42)

    def test_field_name_form(self) -> None:
        """--pair.x 13 --pair.y 42 sets x=13, y=42."""
        parser = argparse.ArgumentParser()
        populate_parser(WithPoint, parser)
        argv = ["--pair.x", "13", "--pair.y", "42"]
        ns = parser.parse_args(argv)
        result = from_namespace(WithPoint, ns, argv=argv)
        assert result.pair == Point(x=13, y=42)

    def test_index_form(self) -> None:
        """--pair.0 13 --pair.1 42 sets x=13, y=42."""
        parser = argparse.ArgumentParser()
        populate_parser(WithPoint, parser)
        argv = ["--pair.0", "13", "--pair.1", "42"]
        ns = parser.parse_args(argv)
        result = from_namespace(WithPoint, ns, argv=argv)
        assert result.pair == Point(x=13, y=42)

    def test_field_name_overrides_nargs(self) -> None:
        """Sub-flag overrides that field's position; nargs fills the rest."""
        parser = argparse.ArgumentParser()
        populate_parser(WithPoint, parser)
        argv = ["--pair", "1", "2", "--pair.x", "99"]
        ns = parser.parse_args(argv)
        result = from_namespace(WithPoint, ns, argv=argv)
        # x=99 from sub-flag; y=2 from nargs position 1
        assert result.pair == Point(x=99, y=2)

    def test_index_beside_name_sub_flag_builds_as_vanilla(self) -> None:
        """A --pair.0 beside --pair.x keeps both keys, and the later one wins at build (Q-1).

        The collector used to re-key the index flag under its field name — name
        winning over index, a collection-time priority vanilla never makes (BUG-65).
        Vanilla stores both keys as spelled, in argv order, and construction reads them
        as one position, the later write winning.
        """
        parser = argparse.ArgumentParser()
        populate_parser(WithPoint, parser)
        argv = ["--pair.0", "1", "--pair.x", "99", "--pair.y", "2"]
        ns = parser.parse_args(argv)
        assert from_namespace(WithPoint, ns, argv=argv).pair == Point(x=99, y=2)

    def test_all_sub_flags_no_nargs(self) -> None:
        """All fields set via sub-flags without the combined nargs flag."""
        parser = argparse.ArgumentParser()
        populate_parser(WithPoint, parser)
        argv = ["--pair.x", "5", "--pair.y", "6"]
        ns = parser.parse_args(argv)
        result = from_namespace(WithPoint, ns, argv=argv)
        assert result.pair == Point(x=5, y=6)

    def test_with_defaults(self) -> None:
        """Fields with defaults don't need to be set on CLI."""
        parser = argparse.ArgumentParser()
        populate_parser(WithColor, parser)
        argv = ["--color.r", "200", "--color.g", "100", "--color.b", "50"]
        ns = parser.parse_args(argv)
        result = from_namespace(WithColor, ns, argv=argv)
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
            env={"MYAPP_PAIR": blob},
            env_prefix="MYAPP_",
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
        """--pair with no token is rejected, exactly as a same-arity tuple field is.

        The parser names the flag rather than leaving ``build()`` to report an arity it
        cannot attribute to a token (BUG-43).
        """
        with pytest.raises(ConfargError, match="Missing value for '--pair'"):
            confarg.load(WithIntPair, argv=["--pair"], env={})
        with pytest.raises(ConfargError, match="Missing value for '--pair'"):
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
        result = confarg.load(WithPoint, argv=[], env={"MYAPP_PAIR": "[13, 42]"}, env_prefix="MYAPP_")
        assert result.pair == Point(x=13, y=42)

    def test_json_object(self) -> None:
        """JSON object env var → field-name construction."""
        result = confarg.load(WithPoint, argv=[], env={"MYAPP_PAIR": '{"x": 13, "y": 42}'}, env_prefix="MYAPP_")
        assert result.pair == Point(x=13, y=42)

    def test_field_name_segments(self) -> None:
        """Individual field-name segments in env vars."""
        result = confarg.load(
            WithPoint,
            argv=[],
            env={"MYAPP_PAIR__X": "13", "MYAPP_PAIR__Y": "42"},
            env_prefix="MYAPP_",
        )
        assert result.pair == Point(x=13, y=42)

    def test_index_segments(self) -> None:
        """Numeric index segments in env vars."""
        result = confarg.load(
            WithPoint,
            argv=[],
            env={"MYAPP_PAIR__0": "13", "MYAPP_PAIR__1": "42"},
            env_prefix="MYAPP_",
        )
        assert result.pair == Point(x=13, y=42)

    def test_negative_index_segments(self) -> None:
        """A negative index segment in an env var counts from the end (BUG-80)."""
        result = confarg.load(
            WithPoint,
            argv=[],
            env={"MYAPP_PAIR__0": "13", "MYAPP_PAIR__-1": "42"},
            env_prefix="MYAPP_",
        )
        assert result.pair == Point(x=13, y=42)

    def test_with_prefix(self) -> None:
        """Env var prefix is respected."""
        result = confarg.load(WithPoint, argv=[], env={"APP__PAIR": "[7, 8]"}, env_prefix="APP")
        assert result.pair == Point(x=7, y=8)

    def test_case_insensitive_field_names(self) -> None:
        """Env var field matching is case-insensitive."""
        result = confarg.load(WithPoint, argv=[], env={"MYAPP_PAIR__X": "5", "MYAPP_PAIR__Y": "6"}, env_prefix="MYAPP_")
        assert result.pair == Point(x=5, y=6)

    def test_with_defaults_partial(self) -> None:
        """Partial env vars use field defaults for missing fields."""
        result = confarg.load(
            WithColor,
            argv=[],
            env={"MYAPP_COLOR__R": "255", "MYAPP_COLOR__G": "0", "MYAPP_COLOR__B": "0"},
            env_prefix="MYAPP_",
        )
        assert result.color == Color(r=255, g=0, b=0, a=255)

    def test_unknown_env_field_raises(self) -> None:
        """Unknown namedtuple field in env var is refused at parse, as the flag is (BUG-170)."""
        with pytest.raises(ConfargError, match="segment 'z' names no element of 'pair'"):
            confarg.load(WithPoint, argv=[], env={"MYAPP_PAIR__Z": "99"}, env_prefix="MYAPP_")


# ---------------------------------------------------------------------------
# Config file tests
# ---------------------------------------------------------------------------


class TestConfigFiles:
    """Tests for namedtuple in config files (list and dict forms)."""

    @pytest.mark.parametrize("key", ["01", "-0", "+1"])
    def test_an_odd_index_over_a_file_list_names_no_position(self, tmp_path, key: str) -> None:
        """Over an earlier file's list, a later file's odd index is refused as without it (BUG-142).

        The merge applies a fixed-length patch over a base list itself only where every key
        names a position as construction reads it; any other key defers to construction.
        """
        (tmp_path / "a.yaml").write_text("pair: [1, 2]\n")
        (tmp_path / "b.json").write_text(f'{{"pair": {{"{key}": 5}}}}')
        files = [str(tmp_path / "a.yaml"), str(tmp_path / "b.json")]
        with pytest.raises(TypeCoercionError, match="Unknown field"):
            confarg.load(WithPoint, argv=[], files=files, env={})
        with pytest.raises(TypeCoercionError, match="dict keys must be integer indices"):
            confarg.load(WithIntPair, argv=[], files=files, env={})

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


@dataclass
class _Segment:
    """Dataclass whose namedtuple holds another namedtuple."""

    seg: Line


class Line(NamedTuple):
    """A namedtuple one of whose fields is a namedtuple."""

    start: Point
    width: int


class TestPatchOverAPositionalBase:
    """A patch over a positional list builds whichever channel spelled the list (BUG-160).

    The merge cannot tell a namedtuple's list from a plain one, so it carries the list as
    the ``__base__`` base beside the patch; ``build()`` lays the patch over the positions, by
    field name or by index, as ``Point(*base)._replace(...)`` would.
    """

    def test_construct_lays_a_name_patch_over_the_base(self) -> None:
        """The ``__base__`` base fills the positions the name keys do not take."""
        assert construct(Point, {ListOp.BASE: [1, 2], "x": 9}) == Point(x=9, y=2)

    def test_construct_lays_an_index_patch_over_the_base(self) -> None:
        """An index patch, negative included, takes its position as a fixed tuple's does."""
        assert construct(Point, {ListOp.BASE: [1, 2], "0": 9}) == Point(x=9, y=2)
        assert construct(Point, {ListOp.BASE: [1, 2], "-1": 9}) == Point(x=1, y=9)

    def test_construct_fills_past_a_short_base_from_the_defaults(self) -> None:
        """A base shorter than the arity leaves the rest to the patch, then to the defaults."""
        assert construct(Color, {ListOp.BASE: [1, 2], "b": 3}) == Color(r=1, g=2, b=3, a=255)
        assert construct(Color, {ListOp.BASE: [1, 2, 3], "3": 4}) == Color(r=1, g=2, b=3, a=4)

    def test_construct_patches_into_a_nested_position(self) -> None:
        """A patch below a position refines what the base holds there, as a list patch does."""
        assert construct(Line, {ListOp.BASE: [[1, 2], 5], "start": {"y": 9}}) == Line(
            start=Point(1, 9),
            width=5,
        )

    def test_construct_refuses_a_base_longer_than_the_arity(self) -> None:
        """A base with more positions than fields is refused, as the plain list is."""
        with pytest.raises(TypeCoercionError, match="expected 2 elements, got 3"):
            construct(Point, {ListOp.BASE: [1, 2, 3], "x": 9})

    def test_construct_lays_a_mixed_patch(self) -> None:
        """A patch mixing names and indices lays each over the position it spells (Q-1)."""
        assert construct(Point, {ListOp.BASE: [1, 2], "x": 9, "1": 8}) == Point(x=9, y=8)
        assert construct(Point, {ListOp.BASE: [1, 2], "x": 9, "0": 8}) == Point(x=8, y=2)

    def test_name_patch_on_the_cli_over_a_file_list(self, tmp_path) -> None:
        """``--pair.x`` over a file's ``pair: [1, 2]`` builds as over ``--pair 1 2``."""
        p = tmp_path / "base.yaml"
        p.write_text("pair: [1, 2]\n")
        assert confarg.load(WithPoint, argv=["--config", str(p), "--pair.x", "9"], env={}).pair == Point(9, 2)

    def test_name_patch_in_the_env_over_a_file_list(self, tmp_path) -> None:
        """``APP_PAIR__X`` over a file's list builds the same."""
        p = tmp_path / "base.yaml"
        p.write_text("pair: [1, 2]\n")
        cfg = confarg.load(WithPoint, argv=[], files=[str(p)], env={"APP_PAIR__X": "9"}, env_prefix="APP_")
        assert cfg.pair == Point(9, 2)

    def test_name_patch_in_a_later_file_over_an_earlier_list(self, tmp_path) -> None:
        """A later file's ``pair: {x: 9}`` over an earlier file's list builds the same."""
        a = tmp_path / "a.yaml"
        a.write_text("pair: [1, 2]\n")
        b = tmp_path / "b.yaml"
        b.write_text("pair: {x: 9}\n")
        assert confarg.load(WithPoint, argv=[], files=[str(a), str(b)], env={}).pair == Point(9, 2)

    def test_name_patch_beside_a_whole_list_in_the_env(self) -> None:
        """Within the env channel, ``APP_PAIR__X`` refines ``APP_PAIR``'s list."""
        env = {"APP_PAIR": "[1, 2]", "APP_PAIR__X": "9"}
        assert confarg.load(WithPoint, argv=[], env=env, env_prefix="APP_").pair == Point(9, 2)

    def test_index_patch_past_a_short_file_list(self, tmp_path) -> None:
        """An index past a file's short list fills that position (the merge's deferred patch)."""
        p = tmp_path / "base.yaml"
        p.write_text("color: [1, 2, 3]\n")
        cfg = confarg.load(WithColor, argv=["--config", str(p), "--color.3", "4"], env={})
        assert cfg.color == Color(r=1, g=2, b=3, a=4)

    def test_whole_list_with_a_patch_replaces_a_name_dict_below(self, tmp_path) -> None:
        """A later channel's list-plus-patch replaces an earlier name dict, it does not join it."""
        p = tmp_path / "base.yaml"
        p.write_text("pair: {x: 5}\n")
        env = {"APP_PAIR": "[1, 2]", "APP_PAIR__Y": "9"}
        cfg = confarg.load(WithPoint, argv=[], files=[str(p)], env=env, env_prefix="APP_")
        assert cfg.pair == Point(1, 9)

    def test_name_patch_below_a_nested_position(self, tmp_path) -> None:
        """``--seg.start.y`` over a file's nested list refines the inner namedtuple."""
        p = tmp_path / "base.yaml"
        p.write_text("seg: [[1, 2], 5]\n")
        cfg = confarg.load(_Segment, argv=["--config", str(p), "--seg.start.y", "9"], env={})
        assert cfg.seg == Line(start=Point(1, 9), width=5)


class TestNamedtupleFieldsCache:
    """``_namedtuple_fields`` is cached per class, but never an answer it had to guess (REF-48)."""

    def test_fields_are_read_only(self) -> None:
        """The cached mapping is shared, so it refuses a write."""
        from confarg._types import _namedtuple_fields  # noqa: PLC0415 — private helper under test

        with pytest.raises(TypeError):
            _namedtuple_fields(Point)["z"] = int  # ty: ignore[invalid-assignment]  # the write must fail

    def test_unresolved_annotation_is_retried(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A forward reference reads as Any until its name exists, then as the type it names."""
        from confarg._types import _namedtuple_fields  # noqa: PLC0415 — private helper under test

        class Pending(NamedTuple):
            x: _NotYetDefined  # noqa: F821  # ty: ignore[unresolved-reference]  # monkeypatched in below

        assert dict(_namedtuple_fields(Pending)) == {"x": Any}
        monkeypatch.setitem(globals(), "_NotYetDefined", int)
        assert dict(_namedtuple_fields(Pending)) == {"x": int}


# ---------------------------------------------------------------------------
# A delete on a fixed-length position unsets it (BUG-243)
# ---------------------------------------------------------------------------


class _DefPt(NamedTuple):
    """A namedtuple whose fields default, so an unset position falls back to its class default."""

    x: int = 1
    y: int = 2


@dataclass
class _Positions:
    """Fixed-length fields of each kind, their defaults laid by the default layer."""

    pt: _DefPt = _DefPt()  # noqa: RUF009  # a tuple default, laid as the bottom layer
    pf: _DefPt = _DefPt(5, 6)  # noqa: RUF009  # a field default that disagrees with the class's
    rq: Point = Point(5, 6)  # noqa: RUF009  # a namedtuple whose fields have no default
    t: tuple[int, int] = (1, 2)
    to: tuple[int | None, int] = (1, 2)
    opt: _DefPt | None = None
    m: int | None = None


def _base(
    tmp_path, body: str = "pt: [7, 8]\npf: [7, 8]\nrq: [7, 8]\nt: [7, 8]\nto: [7, 8]\nopt: [7, 8]\n"
) -> list[str]:
    path = tmp_path / "base.yaml"
    path.write_text(body)
    return [str(path)]


class TestAPositionDeleteUnsetsIt:
    """A delete at a namedtuple's or a fixed tuple's position unsets it; nothing slides (BUG-243)."""

    @pytest.mark.parametrize("flag", ["--pt.0-", "--pt.x-", "--pt.-2-"])
    def test_every_spelling_unsets_the_namedtuple_position(self, tmp_path, flag: str) -> None:
        """``y`` stays where it is, and ``x`` falls back to its class default."""
        assert confarg.load(_Positions, files=_base(tmp_path), argv=[flag], env={}).pt == _DefPt(1, 8)

    @pytest.mark.parametrize("name", ["APP_PT__0-", "APP_PT__X-"])
    def test_the_environment_unsets_it_too(self, tmp_path, name: str) -> None:
        """A variable's delete is read as the flag's is."""
        cfg = confarg.load(_Positions, files=_base(tmp_path), argv=[], env={name: ""}, env_prefix="APP_")
        assert cfg.pt == _DefPt(1, 8)

    def test_a_position_with_no_default_is_missing(self, tmp_path) -> None:
        """A namedtuple field with no default is a missing field once unset."""
        with pytest.raises(MissingFieldError, match=r"rq\.x"):
            confarg.load(_Positions, files=_base(tmp_path), argv=["--rq.x-"], env={})

    def test_a_later_set_fills_the_unset_position(self, tmp_path) -> None:
        """``--rq.x- --rq.x 1`` sets what the delete cleared, and nothing else moves."""
        assert confarg.load(_Positions, files=_base(tmp_path), argv=["--rq.x-", "--rq.x", "1"], env={}).rq == Point(
            1, 8
        )

    def test_a_fixed_tuple_position_is_missing(self, tmp_path) -> None:
        """A fixed tuple's position has no default of its own: unset, it is missing."""
        with pytest.raises(MissingFieldError, match=r"t\[0\]"):
            confarg.load(_Positions, files=_base(tmp_path), argv=["--t.0-"], env={})
        with pytest.raises(MissingFieldError, match=r"t\[0\]"):
            confarg.load(_Positions, argv=["--t.0-"], env={})

    def test_a_fixed_tuple_position_that_takes_none_is_none(self, tmp_path) -> None:
        """A position whose type takes ``None`` is ``None`` once unset, with a file or without."""
        assert confarg.load(_Positions, files=_base(tmp_path), argv=["--to.0-"], env={}).to == (None, 8)
        assert confarg.load(_Positions, argv=["--to.0-"], env={}).to == (None, 2)

    def test_a_fixed_tuple_delete_then_set(self, tmp_path) -> None:
        """``--t.0- --t.0 9`` sets position 0 and keeps position 1."""
        assert confarg.load(_Positions, files=_base(tmp_path), argv=["--t.0-", "--t.0", "9"], env={}).t == (9, 8)

    def test_the_field_default_is_unset_too(self, tmp_path) -> None:
        """The delete removes the position from the field default: the class's own default shows."""
        assert confarg.load(_Positions, argv=["--pf.x-"], env={}).pf == _DefPt(1, 6)
        assert confarg.load(_Positions, files=_base(tmp_path), argv=["--pf.x-"], env={}).pf == _DefPt(1, 8)

    def test_an_optional_namedtuple_takes_its_variant(self, tmp_path) -> None:
        """A union whose one variant is fixed-length unsets as the variant does."""
        assert confarg.load(_Positions, files=_base(tmp_path), argv=["--opt.0-"], env={}).opt == _DefPt(1, 8)

    def test_spellings_combine_within_one_source(self) -> None:
        """A name and an index name one position within argv, the later write winning."""
        assert confarg.load(_Positions, argv=["--pt.0-", "--pt.y", "5"], env={}).pt == _DefPt(1, 5)
        assert confarg.load(_Positions, argv=["--pt.0", "9", "--pt.x-"], env={}).pt == _DefPt(1, 2)
        assert confarg.load(_Positions, argv=["--pf.0", "9", "--pf.x-"], env={}).pf == _DefPt(1, 6)

    def test_the_delete_survives_a_higher_layer(self, tmp_path) -> None:
        """The environment's delete is still a delete under a flag that patches the other position."""
        cfg = confarg.load(
            _Positions, files=_base(tmp_path), argv=["--pt.y", "5"], env={"APP_PT__X-": ""}, env_prefix="APP_"
        )
        assert cfg.pt == _DefPt(1, 5)
        cfg = confarg.load(
            _Positions, files=_base(tmp_path), argv=["--pt.x", "3"], env={"APP_PT__X-": ""}, env_prefix="APP_"
        )
        assert cfg.pt == _DefPt(3, 8)

    def test_the_merge_keeps_the_delete_in_the_keyed_form(self, tmp_path) -> None:
        """Over a base list the position delete keys the base and stays in it, for the default below."""
        merged = confarg.merge(
            _Positions, files=_base(tmp_path, "pt: [7, 8]\nt: [7, 8]\n"), argv=["--pt.0-", "--t.0-"], env={}
        )
        assert merged == {"pt": {"x": DICT_DELETE, "y": 8}, "t": {"0": DICT_DELETE, "1": 8}}

    def test_a_dumped_merge_reads_back(self, tmp_path) -> None:
        """``dump_file(merge(...))`` writes the delete as ``{__unset__: true}``, which reads back the same."""
        merged = confarg.merge(_Positions, files=_base(tmp_path), argv=["--pf.x-"], env={})
        saved = tmp_path / "saved.yaml"
        confarg.dump_file(merged, saved)
        assert confarg.merge(_Positions, files=[str(saved)], argv=[], env={}) == merged
        assert confarg.load(_Positions, files=[str(saved)], argv=[], env={}).pf == _DefPt(1, 8)

    @pytest.mark.parametrize("key", ['"0"', "x"])
    def test_a_file_unsets_a_position(self, tmp_path, key: str) -> None:
        """A file writes the same delete as ``{__unset__: true}`` at the position, by index or by name."""
        (tmp_path / "del.yaml").write_text(f"pt: {{{key}: {{__unset__: true}}}}\n")
        files = [*_base(tmp_path), str(tmp_path / "del.yaml")]
        assert confarg.load(_Positions, files=files, argv=[], env={}).pt == _DefPt(1, 8)

    @pytest.mark.parametrize("field", ["pt", "t"])
    @pytest.mark.parametrize("op", ["__delete__", "__delete_after__"])
    def test_a_file_list_delete_is_refused(self, tmp_path, field: str, op: str) -> None:
        """A fixed-length position is unset in place, so a file's list delete there is refused, naming ``__unset__``."""
        (tmp_path / "del.yaml").write_text(f"{field}: {{{op}: [0]}}\n")
        for files in ([*_base(tmp_path), str(tmp_path / "del.yaml")], [str(tmp_path / "del.yaml")]):
            with pytest.raises(ConfargError, match="__unset__"):
                confarg.load(_Positions, files=files, argv=[], env={})

    def test_a_reference_reads_the_built_value(self, tmp_path) -> None:
        """``${pt.x}`` reads what ``pt.x`` builds to once unset: its class default."""
        (tmp_path / "ref.yaml").write_text("m: '${pf.x}'\n")
        files = [*_base(tmp_path), str(tmp_path / "ref.yaml")]
        cfg = confarg.load(_Positions, files=files, argv=["--pf.x-"], env={})
        assert cfg.m == cfg.pf.x == 1

    def test_a_reference_reads_none_at_an_unset_optional_position(self, tmp_path) -> None:
        """``${to[0]}`` reads the ``None`` construction fills an unset optional position with."""
        (tmp_path / "ref.yaml").write_text("m: '${to[0]}'\n")
        files = [*_base(tmp_path), str(tmp_path / "ref.yaml")]
        cfg = confarg.load(_Positions, files=files, argv=["--to.0-"], env={})
        assert cfg.m is None
        assert cfg.to == (None, 8)
