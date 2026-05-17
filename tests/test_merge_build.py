# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for the merge() / build() two-step API and dump() / dump_file() with raw dicts."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

import confarg
from confarg._types import _StrToken
from tests.conftest import AppConfig, DbConfig, WithDefaults

try:
    import yaml

    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

# ---------------------------------------------------------------------------
# merge()
# ---------------------------------------------------------------------------


class TestMerge:
    """merge() returns the raw merged dict without resolving expressions or constructing."""

    def test_returns_dict(self) -> None:
        """Test that merge() returns a plain dict."""
        result = confarg.merge(WithDefaults, argv=[], env={})
        assert isinstance(result, dict)

    def test_cli_values_present(self) -> None:
        """Test that CLI values are present in the merged dict."""
        result = confarg.merge(WithDefaults, argv=["--name", "hello"], env={})
        assert result["name"] == "hello"

    def test_env_values_present(self) -> None:
        """Test that env var values are present in the merged dict."""
        result = confarg.merge(WithDefaults, argv=[], env={"NAME": "fromenv"}, env_prefix="")
        assert result["name"] == "fromenv"

    def test_file_values_present(self, tmp_yaml) -> None:
        """Test that config file values are present in the merged dict."""
        path = tmp_yaml("name: fromfile\n")
        result = confarg.merge(WithDefaults, argv=[], env={}, files=[path])
        assert result["name"] == "fromfile"

    def test_expressions_preserved(self, tmp_yaml) -> None:
        """Test that ${...} expressions are preserved without evaluation by merge()."""
        # merge() must not evaluate ${...} — the raw expression string is kept
        path = tmp_yaml("name: hello\ncount: 42\nrate: 1.0\nverbose: false\nother: '${name}'\n")
        result = confarg.merge(WithDefaults, argv=[], env={}, files=[path])
        assert result["other"] == "${name}"

    def test_merge_priority(self, tmp_yaml) -> None:
        """Test that CLI > env > file priority is respected in merge()."""
        path = tmp_yaml("name: fromfile\n")
        result = confarg.merge(
            WithDefaults,
            argv=["--name", "fromcli"],
            env={"NAME": "fromenv"},
            files=[path],
        )
        assert result["name"] == "fromcli"

    def test_merge_is_equivalent_to_load_merge_step(self, tmp_yaml) -> None:
        """Test that merge() is equivalent to the internal merge step in load()."""
        path = tmp_yaml("name: fromfile\n")
        merged = confarg.merge(WithDefaults, argv=["--count", "7"], env={}, files=[path])
        instance = confarg.load(WithDefaults, argv=["--count", "7"], env={}, files=[path])
        assert merged["name"] == instance.name
        assert merged["count"] == instance.count  # CLI int now pre-coerced


# ---------------------------------------------------------------------------
# build()
# ---------------------------------------------------------------------------


class TestBuild:
    """build() resolves expressions and constructs an instance from a plain dict."""

    def test_constructs_instance(self) -> None:
        """Test that build() constructs a dataclass instance from a dict."""
        data = {"name": "hi", "count": 3, "rate": 1.5, "verbose": False}
        result = confarg.build(WithDefaults, data)
        assert isinstance(result, WithDefaults)
        assert result.name == "hi"

    def test_resolves_expressions_by_default(self) -> None:
        """Test that build() resolves ${...} expressions."""

        @dataclass
        class TwoStrings:
            base: str
            derived: str

        data = {"base": "hello", "derived": "${base}_suffix"}
        result = confarg.build(TwoStrings, data)
        assert result.derived == "hello_suffix"

    def test_nested_dataclass(self) -> None:
        """Test that build() constructs nested dataclasses correctly."""
        data = {
            "db": {"host": "localhost", "port": 5432, "name": "mydb"},
            "cache": {"enabled": True, "ttl": 60},
        }
        result = confarg.build(AppConfig, data)
        assert isinstance(result.db, DbConfig)
        assert result.db.host == "localhost"


# ---------------------------------------------------------------------------
# Two-step equivalence with load()
# ---------------------------------------------------------------------------


class TestTwoStepEquivalence:
    """merge() + build() must produce the same result as load()."""

    def test_flat(self) -> None:
        """Test that merge() + build() equals load() for flat dataclasses."""
        args = ["--name", "x", "--count", "5", "--rate", "2.0", "--verbose", "true"]
        via_load = confarg.load(WithDefaults, argv=args, env={})
        via_two_step = confarg.build(WithDefaults, confarg.merge(WithDefaults, argv=args, env={}))
        assert via_load.name == via_two_step.name
        assert via_load.count == via_two_step.count

    def test_with_expression(self, tmp_yaml) -> None:
        """Test that merge() + build() equals load() when expressions are involved."""

        @dataclass
        class TwoStrings:
            base: str
            derived: str

        path = tmp_yaml("base: hello\nderived: '${base}_world'\n")
        via_load = confarg.load(TwoStrings, argv=[], env={}, files=[path])
        via_two_step = confarg.build(TwoStrings, confarg.merge(TwoStrings, argv=[], env={}, files=[path]))
        assert via_load.derived == via_two_step.derived


# ---------------------------------------------------------------------------
# dump() and dump_file() with raw dicts
# ---------------------------------------------------------------------------


class TestDumpRaw:
    """Tests for dump_file() with raw dict inputs."""

    def test_dump_rejects_dict(self) -> None:
        """dump() raises TypeError for plain dicts — raw dicts go through dump_file()."""
        data = {"name": _StrToken("hello"), "count": 42}
        with pytest.raises(TypeError, match="dump_file"):
            confarg.dump(data)

    @pytest.mark.skipif(not _YAML_AVAILABLE, reason="pyyaml not installed")
    def test_dump_file_yaml(self, tmp_path) -> None:
        """Test that dump_file() writes a valid YAML file preserving expressions."""
        data = {"name": "hello", "count": "${name}"}
        path = tmp_path / "out.yaml"
        confarg.dump_file(data, path)
        assert path.exists()
        loaded = yaml.safe_load(path.read_text())
        assert loaded["name"] == "hello"
        assert loaded["count"] == "${name}"

    @pytest.mark.skipif(not _YAML_AVAILABLE, reason="pyyaml not installed")
    def test_raw_expressions_survive_file_round_trip(self, tmp_path, tmp_yaml) -> None:
        """Test that raw ${...} expressions survive a merge → dump_file round-trip."""
        src = tmp_yaml("name: base\ncount: '${name}'\nrate: 1.0\nverbose: false\n")
        raw = confarg.merge(WithDefaults, argv=[], env={}, files=[src])
        out = tmp_path / "snapshot.yaml"
        confarg.dump_file(raw, out)
        saved = yaml.safe_load(out.read_text())
        assert saved["count"] == "${name}"


# ---------------------------------------------------------------------------
# Post-init mutation: raw dict is unaffected
# ---------------------------------------------------------------------------


class TestPostInitIsolation:
    """Demonstrates that merge() captures the input before __post_init__ can mutate."""

    def test_postinit_does_not_affect_raw_dict(self) -> None:
        """Test that merge() captures input before __post_init__ can mutate the instance."""

        @dataclass
        class Uppercased:
            name: str

            def __post_init__(self):
                self.name = self.name.upper()

        raw = confarg.merge(Uppercased, argv=["--name", "hello"], env={})
        instance = confarg.build(Uppercased, raw)

        assert raw["name"] == "hello"
        assert instance.name == "HELLO"
