# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Hypothesis-based property tests: round-trip coercion, name construction, merge priority invariants."""

from __future__ import annotations

import keyword

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

import confarg
from confarg._parse_cli import _looks_like_flag
from tests.conftest import (
    Color,
    WithDefaults,
    env_prefixes,
    leaf_bools,
    leaf_floats,
    leaf_ints,
    leaf_strs,
    make_target,
    valid_identifiers,
)

# ---------------------------------------------------------------------------
# Round-trip coercion: value -> str -> parse -> value
# ---------------------------------------------------------------------------


class TestRoundTripCoercion:
    """Property: value -> string -> parse produces the original value."""

    @given(value=leaf_ints)
    def test_int_round_trip(self, value: int) -> None:
        """Int survives string round-trip via CLI."""
        result = confarg.load(WithDefaults, argv=["--count", str(value)], env={})
        assert result.count == value

    @given(value=leaf_floats)
    def test_float_round_trip(self, value: float) -> None:
        """Float survives string round-trip via CLI."""
        result = confarg.load(WithDefaults, argv=["--rate", str(value)], env={})
        # Use approximate comparison for floats
        assert abs(result.rate - value) < 1e-6 or result.rate == value

    @given(value=leaf_bools)
    def test_bool_round_trip(self, value: bool) -> None:  # noqa: FBT001
        """Bool survives string round-trip via env."""
        result = confarg.load(WithDefaults, argv=[], env={"VERBOSE": str(value).lower()}, env_prefix="")
        assert result.verbose is value

    @given(value=leaf_strs)
    def test_str_round_trip(self, value: str) -> None:
        """Str survives round-trip via CLI."""
        result = confarg.load(WithDefaults, argv=["--name", value], env={})
        assert result.name == value

    @given(value=leaf_ints)
    def test_int_round_trip_env(self, value: int) -> None:
        """Int survives string round-trip via env."""
        result = confarg.load(WithDefaults, argv=[], env={"COUNT": str(value)}, env_prefix="")
        assert result.count == value

    @given(value=leaf_floats)
    def test_float_round_trip_env(self, value: float) -> None:
        """Float survives string round-trip via env."""
        result = confarg.load(WithDefaults, argv=[], env={"RATE": str(value)}, env_prefix="")
        assert abs(result.rate - value) < 1e-6 or result.rate == value


# ---------------------------------------------------------------------------
# Env var name construction (real property tests)
# ---------------------------------------------------------------------------

_no_dunder = valid_identifiers.filter(lambda s: "__" not in s and not keyword.iskeyword(s))


class TestEnvNameConstruction:
    """Property: the library reads env vars using the uppercased field name."""

    @given(field_name=_no_dunder, value=leaf_strs)
    def test_flat_field_read_from_uppercase_env(self, field_name: str, value: str) -> None:
        """FIELD_NAME.upper() in env maps to field_name on the dataclass."""
        assume("${" not in value)  # avoid accidental expression syntax
        target = make_target(field_name, str, default="")
        result = confarg.load(target, argv=[], env={field_name.upper(): value}, env_prefix="")
        assert getattr(result, field_name) == value

    @given(
        prefix=env_prefixes.filter(lambda s: "__" not in s),
        value=leaf_strs,
    )
    def test_prefixed_env_reads_field(self, prefix: str, value: str) -> None:
        """PREFIX__NAME env var maps to field 'name' with env_prefix=PREFIX."""
        assume("${" not in value)
        target = make_target("name", str, default="")
        result = confarg.load(target, argv=[], env={f"{prefix}__NAME": value}, env_prefix=prefix)
        assert result.name == value


# ---------------------------------------------------------------------------
# Merge priority invariant
# ---------------------------------------------------------------------------


class TestMergePriorityInvariant:
    """Property: CLI always overrides env, env always overrides config."""

    @given(cli_val=leaf_strs, env_val=leaf_strs)
    def test_cli_beats_env(self, cli_val: str, env_val: str) -> None:
        """CLI value always wins over env value for the same field."""
        result = confarg.load(
            WithDefaults,
            argv=["--name", cli_val],
            env={"NAME": env_val},
            env_prefix="",
        )
        assert result.name == cli_val

    @given(cli_val=leaf_ints, env_val=leaf_ints)
    def test_cli_beats_env_int(self, cli_val: int, env_val: int) -> None:
        """CLI int always wins over env int."""
        result = confarg.load(
            WithDefaults,
            argv=["--count", str(cli_val)],
            env={"COUNT": str(env_val)},
            env_prefix="",
        )
        assert result.count == cli_val

    @given(env_val=leaf_strs)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_env_beats_config(self, env_val: str, tmp_path) -> None:
        """Env value always wins over config file value."""
        config_file = tmp_path / "config.toml"
        config_file.write_text('name = "from_config"\n')
        result = confarg.load(
            WithDefaults,
            argv=[],
            env={"NAME": env_val},
            env_prefix="",
            files=[config_file],
        )
        assert result.name == env_val

    @given(cli_val=leaf_strs, env_val=leaf_strs)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_cli_beats_config(self, cli_val: str, env_val: str, tmp_path) -> None:
        """CLI value always wins over config file value."""
        config_file = tmp_path / "config.toml"
        config_file.write_text('name = "from_config"\n')
        result = confarg.load(
            WithDefaults,
            argv=["--name", cli_val],
            env={"NAME": env_val},
            env_prefix="",
            files=[config_file],
        )
        assert result.name == cli_val


# ---------------------------------------------------------------------------
# Bool coercion strings
# ---------------------------------------------------------------------------

_VALID_BOOL_STRINGS = frozenset(["true", "True", "TRUE", "1", "yes", "on", "false", "False", "FALSE", "0", "no", "off"])


class TestBoolCoercionProperty:
    """Property: standard truthy/falsy strings coerce correctly; others raise."""

    @given(val=st.sampled_from(sorted(["true", "True", "TRUE", "1", "yes", "on"])))
    def test_truthy_strings(self, val: str) -> None:
        """All truthy strings coerce to True."""
        result = confarg.load(WithDefaults, argv=[], env={"VERBOSE": val}, env_prefix="")
        assert result.verbose is True

    @given(val=st.sampled_from(sorted(["false", "False", "FALSE", "0", "no", "off"])))
    def test_falsy_strings(self, val: str) -> None:
        """All falsy strings coerce to False."""
        result = confarg.load(WithDefaults, argv=[], env={"VERBOSE": val}, env_prefix="")
        assert result.verbose is False

    @given(
        val=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N")),
            min_size=1,
            max_size=20,
        ).filter(lambda s: s not in _VALID_BOOL_STRINGS),
    )
    @settings(max_examples=50)
    def test_invalid_bool_string_raises(self, val: str) -> None:
        """Strings outside the recognised bool set raise TypeCoercionError."""
        with pytest.raises(confarg.exceptions.TypeCoercionError):
            confarg.load(WithDefaults, argv=[], env={"VERBOSE": val}, env_prefix="")


# ---------------------------------------------------------------------------
# Collection round-trip
# ---------------------------------------------------------------------------


class TestCollectionRoundTrip:
    """Property: collection values survive round-trip through CLI."""

    @given(values=st.lists(leaf_ints, min_size=0, max_size=10))
    def test_list_round_trip(self, values: list[int]) -> None:
        """List of ints survives CLI round-trip."""
        WithList = make_target("items", list[int], default_factory=list)
        args = ["--items"] + [str(v) for v in values] if values else []
        result = confarg.load(WithList, argv=args, env={})
        assert result.items == values

    @given(values=st.lists(leaf_ints, min_size=1, max_size=10))
    def test_list_indexed_round_trip(self, values: list[int]) -> None:
        """List of ints via indexed args survives round-trip."""
        WithList = make_target("items", list[int], default_factory=list)
        args: list[str] = []
        for i, v in enumerate(values):
            args.extend([f"--items.{i}", str(v)])
        result = confarg.load(WithList, argv=args, env={})
        assert result.items == values

    @given(
        values=st.frozensets(
            leaf_strs.filter(lambda s: len(s) > 0 and not _looks_like_flag(s)),
            min_size=0,
            max_size=10,
        ),
    )
    def test_set_round_trip(self, values: frozenset[str]) -> None:
        """Set of strings survives CLI round-trip."""
        WithSet = make_target("tags", set[str], default_factory=set)
        args = ["--tags", *list(values)] if values else []
        result = confarg.load(WithSet, argv=args, env={})
        assert result.tags == set(values)

    @given(
        keys=st.lists(
            st.from_regex(r"[a-z][a-z0-9]{0,9}", fullmatch=True),
            min_size=0,
            max_size=5,
            unique=True,
        ),
        vals=st.lists(leaf_ints, min_size=0, max_size=5),
    )
    def test_dict_round_trip_env(self, keys: list[str], vals: list[int]) -> None:
        """Dict[str, int] survives round-trip through indexed env vars."""
        d = dict(zip(keys, vals, strict=False))
        WithDict = make_target("mapping", dict[str, int], default_factory=dict)
        env = {f"MAPPING__{k}": str(v) for k, v in d.items()}
        result = confarg.load(WithDict, argv=[], env=env, env_prefix="")
        assert result.mapping == d


# ---------------------------------------------------------------------------
# Enum round-trip
# ---------------------------------------------------------------------------


class TestEnumRoundTrip:
    """Property: every enum member round-trips through CLI and env."""

    @given(color=st.sampled_from(list(Color)))
    def test_enum_from_cli_value(self, color: Color) -> None:
        """Enum member round-trips via its .value string through CLI."""
        WithEnum = make_target("color", Color, default=Color.RED)
        result = confarg.load(WithEnum, argv=["--color", color.value], env={})
        assert result.color is color

    @given(color=st.sampled_from(list(Color)))
    def test_enum_from_env_value(self, color: Color) -> None:
        """Enum member round-trips via its .value string through env."""
        WithEnum = make_target("color", Color, default=Color.RED)
        result = confarg.load(WithEnum, argv=[], env={"COLOR": color.value}, env_prefix="")
        assert result.color is color

    @given(color=st.sampled_from(list(Color)))
    def test_enum_dump_load_identity(self, color: Color) -> None:
        """Dump then load gives the same enum member."""
        WithEnum = make_target("color", Color, default=Color.RED)
        obj = WithEnum(color=color)
        dumped = confarg.dump(obj)
        loaded = confarg.load(WithEnum, argv=[], env={"COLOR": dumped["color"]}, env_prefix="")
        assert loaded.color is color
