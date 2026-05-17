# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Round-trip tests: merge() → dump_file() → merge(files=[saved]) must be identity."""

from __future__ import annotations

import math
from dataclasses import dataclass

from hypothesis import HealthCheck, given, settings

import confarg
from tests.conftest import WithDefaults, cli_safe_strs, leaf_bools, leaf_floats, leaf_ints, leaf_strs

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_finite(f: float) -> bool:
    return math.isfinite(f)


# ---------------------------------------------------------------------------
# CLI round-trips
# ---------------------------------------------------------------------------


class TestCliRoundTrip:
    """Round-trip tests for CLI-sourced values."""

    @given(
        name=cli_safe_strs,
        count=leaf_ints,
        rate=leaf_floats.filter(_is_finite),
        verbose=leaf_bools,
    )
    @settings(max_examples=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_cli_flat_roundtrip(self, tmp_path, name, count, rate, verbose):
        """Test that CLI values round-trip through merge → dump_file → merge."""
        args = ["--name", name, "--count", str(count), "--rate", str(rate)]
        if verbose:
            args.extend(["--verbose", "true"])

        raw = confarg.merge(WithDefaults, args=args, env={})
        out = tmp_path / "snap.yaml"
        confarg.dump_file(raw, out)
        reloaded = confarg.merge(WithDefaults, args=[], env={}, files=[out])

        assert raw == reloaded

    @given(count=leaf_ints, rate=leaf_floats.filter(_is_finite))
    @settings(max_examples=100)
    def test_cli_numeric_types_are_native(self, count, rate):
        """Pre-coerced CLI values must be native Python types, not strings."""
        raw = confarg.merge(
            WithDefaults,
            args=["--count", str(count), "--rate", str(rate)],
            env={},
        )
        assert type(raw["count"]) is int
        assert type(raw["rate"]) is float


# ---------------------------------------------------------------------------
# Env var round-trips
# ---------------------------------------------------------------------------


class TestEnvRoundTrip:
    """Round-trip tests for env var-sourced values."""

    @given(
        name=leaf_strs,
        count=leaf_ints,
        rate=leaf_floats.filter(_is_finite),
        verbose=leaf_bools,
    )
    @settings(max_examples=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_env_flat_roundtrip(self, tmp_path, name, count, rate, verbose):
        """Test that env var values round-trip through merge → dump_file → merge."""
        env = {
            "NAME": name,
            "COUNT": str(count),
            "RATE": str(rate),
            "VERBOSE": "true" if verbose else "false",
        }

        raw = confarg.merge(WithDefaults, args=[], env=env)
        out = tmp_path / "snap.yaml"
        confarg.dump_file(raw, out)
        reloaded = confarg.merge(WithDefaults, args=[], env={}, files=[out])

        assert raw == reloaded

    @given(count=leaf_ints)
    @settings(max_examples=100)
    def test_env_numeric_type_is_native(self, count):
        """Pre-coerced env var values must be native Python types, not strings."""
        raw = confarg.merge(WithDefaults, args=[], env={"COUNT": str(count)}, env_prefix="")
        assert type(raw["count"]) is int


# ---------------------------------------------------------------------------
# Mixed sources round-trip
# ---------------------------------------------------------------------------


class TestMixedRoundTrip:
    """Round-trip tests for mixed CLI/env/file sources."""

    @given(
        name=cli_safe_strs,
        count=leaf_ints,
        rate=leaf_floats.filter(_is_finite),
        verbose=leaf_bools,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_cli_over_env_over_file_roundtrip(self, tmp_path, name, count, rate, verbose):
        """CLI > env > file priority. After saving the merged dict, reloading gives same result."""
        # File provides all fields
        file_path = tmp_path / "base.yaml"
        base = confarg.merge(
            WithDefaults,
            args=["--name", name, "--count", str(count), "--rate", str(rate)],
            env={"VERBOSE": "true" if verbose else "false"},
        )
        confarg.dump_file(base, file_path)

        # Reload from the saved file only
        reloaded = confarg.merge(WithDefaults, args=[], env={}, files=[file_path])
        assert base == reloaded


# ---------------------------------------------------------------------------
# Nested dataclass round-trip
# ---------------------------------------------------------------------------


@dataclass
class Inner:
    """Inner dataclass for nested round-trip tests."""

    x: int
    y: float


@dataclass
class Outer:
    """Outer dataclass wrapping an Inner for nested round-trip tests."""

    inner: Inner
    label: str = "default"


class TestNestedRoundTrip:
    """Round-trip tests for nested dataclasses."""

    @given(x=leaf_ints, y=leaf_floats.filter(_is_finite), label=cli_safe_strs)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_nested_cli_roundtrip(self, tmp_path, x, y, label):
        """Test that nested CLI values round-trip through merge → dump_file → merge."""
        args = ["--inner.x", str(x), "--inner.y", str(y), "--label", label]
        raw = confarg.merge(Outer, args=args, env={})
        out = tmp_path / "snap.yaml"
        confarg.dump_file(raw, out)
        reloaded = confarg.merge(Outer, args=[], env={}, files=[out])
        assert raw == reloaded
