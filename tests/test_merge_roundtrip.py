# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Round-trip tests: merge() → dump_file() → merge(files=[saved]) must be identity."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, NamedTuple

import pytest
import yaml
from hypothesis import HealthCheck, given, settings

import confarg
from confarg._merge import DICT_DELETE
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

        raw = confarg.merge(WithDefaults, argv=args, env={})
        out = tmp_path / "snap.yaml"
        confarg.dump_file(raw, out)
        reloaded = confarg.merge(WithDefaults, argv=[], env={}, files=[out])

        assert raw == reloaded

    @given(count=leaf_ints, rate=leaf_floats.filter(_is_finite))
    @settings(max_examples=100)
    def test_cli_numeric_types_are_native(self, count, rate):
        """Pre-coerced CLI values must be native Python types, not strings."""
        raw = confarg.merge(
            WithDefaults,
            argv=["--count", str(count), "--rate", str(rate)],
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

        raw = confarg.merge(WithDefaults, argv=[], env=env)
        out = tmp_path / "snap.yaml"
        confarg.dump_file(raw, out)
        reloaded = confarg.merge(WithDefaults, argv=[], env={}, files=[out])

        assert raw == reloaded

    @given(count=leaf_ints)
    @settings(max_examples=100)
    def test_env_numeric_type_is_native(self, count):
        """Pre-coerced env var values must be native Python types, not strings."""
        raw = confarg.merge(WithDefaults, argv=[], env={"MYAPP_COUNT": str(count)}, env_prefix="MYAPP_")
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
            argv=["--name", name, "--count", str(count), "--rate", str(rate)],
            env={"VERBOSE": "true" if verbose else "false"},
        )
        confarg.dump_file(base, file_path)

        # Reload from the saved file only
        reloaded = confarg.merge(WithDefaults, argv=[], env={}, files=[file_path])
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
        raw = confarg.merge(Outer, argv=args, env={})
        out = tmp_path / "snap.yaml"
        confarg.dump_file(raw, out)
        reloaded = confarg.merge(Outer, argv=[], env={}, files=[out])
        assert raw == reloaded


class _Pt(NamedTuple):
    x: int
    y: int


@dataclass
class _WithOps:
    """A list and a namedtuple, whose patches the merge can hold for ``build()`` to apply."""

    xs: list[int] = field(default_factory=list)
    pt: _Pt = field(default_factory=lambda: _Pt(0, 0))


class TestMergeOpRoundTrip:
    """An op the merged dict still holds is dumped by the name a file writes it with (FEAT-3)."""

    @pytest.mark.parametrize(
        ("argv", "files"),
        [
            (["--xs+", "3"], {}),
            (["--xs.0-"], {}),
            (["--xs+", "3", "--xs.0-"], {}),
            (["--pt.x", "9"], {"pt": [1, 2]}),
        ],
        ids=["append", "delete", "delete-after", "deferred-base"],
    )
    def test_merged_op_survives_dump_file(self, tmp_path, argv: list[str], files: dict[str, Any]) -> None:
        """``dump_file(merge(...))`` reads back as the same merged dict, the op included."""
        sources = []
        if files:
            sources.append(tmp_path / "base.json")
            sources[0].write_text(json.dumps(files))
        raw = confarg.merge(_WithOps, argv=argv, env={}, files=sources)
        out = tmp_path / "snap.yaml"
        confarg.dump_file(raw, out)
        assert confarg.merge(_WithOps, argv=[], env={}, files=[out]) == raw
        assert "__" in out.read_text()


@dataclass
class _WithData:
    d: dict[str, int] = field(default_factory=dict)


class TestAFileKeyIsData:
    """A key ending in ``+`` or ``-`` is data in a file: a dict holding one survives dump and reload (FEAT-43)."""

    @pytest.mark.parametrize("suffix", [".yaml", ".toml", ".json"])
    def test_a_suffixed_key_survives_dump_file(self, tmp_path, suffix: str) -> None:
        """``c++``, ``a-`` and ``0-`` are keys of the dict, written and read back as they are."""
        raw = confarg.merge(_WithData, argv=["--d", '{"c++": 1, "a-": 2, "0-": 3}'], env={})
        out = tmp_path / f"snap{suffix}"
        confarg.dump_file(raw, out)
        assert confarg.merge(_WithData, argv=[], env={}, files=[out]) == raw == {"d": {"c++": 1, "a-": 2, "0-": 3}}
        assert confarg.load(_WithData, argv=[], env={}, files=[out]).d == {"c++": 1, "a-": 2, "0-": 3}


@dataclass
class _Sec:
    a: int = 0
    b: int = 0


@dataclass
class _WithKeyDeletes:
    data: dict[str, int] = field(default_factory=dict)
    sec: _Sec = field(default_factory=_Sec)


class TestAKeyDeleteSurvivesDumpFile:
    """A key delete the merged dict still holds is dumped as the ``__unset__`` a file writes it with (BUG-202)."""

    @pytest.mark.parametrize("suffix", [".yaml", ".toml", ".json"])
    def test_a_key_delete_with_nothing_below_reads_back(self, tmp_path, suffix: str) -> None:
        """``dump_file(merge(...))`` writes the delete BUG-98 leaves, and reads back as the merged dict."""
        raw = confarg.merge(_WithKeyDeletes, argv=["--data.x-"], env={})
        out = tmp_path / f"snap{suffix}"
        confarg.dump_file(raw, out)
        assert confarg.merge(_WithKeyDeletes, argv=[], env={}, files=[out]) == raw
        assert "__unset__" in out.read_text(encoding="utf-8")

    def test_a_deleted_base_is_dumped_beside_its_keys(self, tmp_path) -> None:
        """A node whose layers below were cut off keeps that meaning in the file: it replaces a lower file's node."""
        out = tmp_path / "snap.yaml"
        confarg.dump_file({"sec": {confarg.ListOp.BASE: DICT_DELETE, "a": 1}}, out)
        assert yaml.safe_load(out.read_text(encoding="utf-8")) == {"sec": {"__unset__": True, "a": 1}}
        lower = tmp_path / "lower.yaml"
        lower.write_text("sec: {a: 5, b: 6}\n", encoding="utf-8")
        assert confarg.load(_WithKeyDeletes, argv=[], env={}, files=[lower, out]).sec == _Sec(a=1)
