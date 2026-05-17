# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for source merge priority: CLI > env > config, partial merge, collection index override."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

import confarg
from tests.conftest import (
    AppConfig,
    Flat,
    WithDefaults,
    make_target,
)

# ---------------------------------------------------------------------------
# Priority: CLI > env > config
# ---------------------------------------------------------------------------


class TestMergePriority:
    """Merge priority: CLI beats env beats config."""

    def test_cli_overrides_env(self) -> None:
        """CLI value takes precedence over env var."""
        result = confarg.load(
            WithDefaults,
            args=["--name", "from_cli"],
            env={"NAME": "from_env"},
            env_prefix="",
        )
        assert result.name == "from_cli"

    def test_env_overrides_config(self, tmp_toml) -> None:
        """Env var takes precedence over config file."""
        path = tmp_toml('name = "from_config"\n')
        result = confarg.load(
            WithDefaults,
            args=[],
            env={"NAME": "from_env"},
            env_prefix="",
            files=[path],
        )
        assert result.name == "from_env"

    def test_cli_overrides_config(self, tmp_toml) -> None:
        """CLI value takes precedence over config file."""
        path = tmp_toml('name = "from_config"\ncount = 1\nrate = 0.0\nverbose = false\n')
        result = confarg.load(
            Flat,
            args=["--name", "from_cli", "--count", "1", "--rate", "0", "--verbose", "true"],
            env={},
            files=[path],
        )
        assert result.name == "from_cli"

    def test_cli_overrides_env_overrides_config(self, tmp_toml) -> None:
        """Full three-way priority: CLI > env > config."""
        path = tmp_toml("name = 'from_config'\ncount = 100\nrate = 1.0\nverbose = false\n")
        result = confarg.load(
            Flat,
            args=["--name", "from_cli", "--count", "1", "--rate", "0", "--verbose", "true"],
            env={"NAME": "from_env", "COUNT": "200"},
            env_prefix="",
            files=[path],
        )
        assert result.name == "from_cli"  # CLI wins over env
        assert result.count == 1  # CLI wins over env

    def test_env_fills_missing_cli(self, tmp_toml) -> None:
        """Env fills fields not provided by CLI; config fills the rest."""
        path = tmp_toml("name = 'cfg'\ncount = 10\nrate = 0.5\nverbose = false\n")
        result = confarg.load(
            Flat,
            args=["--name", "cli"],
            env={"COUNT": "20", "RATE": "2.0", "VERBOSE": "true"},
            env_prefix="",
            files=[path],
        )
        assert result.name == "cli"
        assert result.count == 20
        assert result.rate == pytest.approx(2.0)
        assert result.verbose is True


# ---------------------------------------------------------------------------
# Partial merge
# ---------------------------------------------------------------------------


class TestPartialMerge:
    """Partial data from each source is merged."""

    def test_nested_partial_merge(self, tmp_toml) -> None:
        """Each source provides different nested fields."""
        path = tmp_toml("""\
            [db]
            host = "config_host"
            port = 5432
            name = "config_db"
        """)
        result = confarg.load(
            AppConfig,
            args=["--db.host", "cli_host"],
            env={"DB__PORT": "3306"},
            env_prefix="",
            files=[path],
        )
        assert result.db.host == "cli_host"  # CLI overrides config
        assert result.db.port == 3306  # env overrides config
        assert result.db.name == "config_db"  # from config

    def test_defaults_fill_gaps(self) -> None:
        """Defaults fill fields not provided by any source."""
        result = confarg.load(
            WithDefaults,
            args=["--name", "only_name"],
            env={},
        )
        assert result.name == "only_name"
        assert result.count == 0
        assert result.rate == pytest.approx(1.0)
        assert result.verbose is False


# ---------------------------------------------------------------------------
# Collection override
# ---------------------------------------------------------------------------


class TestCollectionOverride:
    """Collection-level and index-level override across sources."""

    def test_cli_list_overrides_config_list(self, tmp_toml) -> None:
        """CLI list replaces the entire config list."""
        WithList = make_target("items", list[int], default_factory=list)
        path = tmp_toml("items = [1, 2, 3]\n")
        result = confarg.load(
            WithList,
            args=["--items", "10", "20"],
            env={},
            files=[path],
        )
        assert result.items == [10, 20]

    def test_cli_index_overrides_config_item(self, tmp_toml) -> None:
        """CLI index override replaces a single item in config list."""
        WithList = make_target("items", list[int], default_factory=list)
        path = tmp_toml("items = [1, 2, 3]\n")
        result = confarg.load(
            WithList,
            args=["--items.1", "99"],
            env={},
            files=[path],
        )
        assert result.items[1] == 99
        assert result.items[0] == 1
        assert result.items[2] == 3

    def test_env_index_overrides_config_item(self, tmp_toml) -> None:
        """Env index override replaces a single item in config list."""
        WithList = make_target("items", list[int], default_factory=list)
        path = tmp_toml("items = [1, 2, 3]\n")
        result = confarg.load(
            WithList,
            args=[],
            env={"ITEMS__0": "99"},
            env_prefix="",
            files=[path],
        )
        assert result.items[0] == 99
        assert result.items[1] == 2

    def test_dict_merge_across_sources(self, tmp_toml) -> None:
        """Dict keys from different sources are merged."""
        WithDict = make_target("metadata", dict[str, int], default_factory=dict)
        path = tmp_toml("[metadata]\na = 1\n")
        result = confarg.load(
            WithDict,
            args=["--metadata.b", "2"],
            env={},
            files=[path],
        )
        assert result.metadata == {"a": 1, "b": 2}

    def test_cli_dict_key_overrides_config_key(self, tmp_toml) -> None:
        """CLI dict key overrides the same key from config."""
        WithDict = make_target("metadata", dict[str, int], default_factory=dict)
        path = tmp_toml("[metadata]\na = 1\n")
        result = confarg.load(
            WithDict,
            args=["--metadata.a", "99"],
            env={},
            files=[path],
        )
        assert result.metadata == {"a": 99}


# ---------------------------------------------------------------------------
# Empty sources
# ---------------------------------------------------------------------------


class TestEmptySources:
    """Behaviour when sources are empty or disabled."""

    def test_all_sources_empty_uses_defaults(self) -> None:
        """All sources empty -> defaults used."""
        result = confarg.load(WithDefaults, args=[], env={})
        assert result.name == "default"

    def test_only_config(self, tmp_toml) -> None:
        """Only config file provides values."""
        path = tmp_toml("name = 'cfg'\ncount = 5\nrate = 1.0\nverbose = true\n")
        result = confarg.load(Flat, args=[], env={}, files=[path])
        assert result.name == "cfg"
        assert result.count == 5


# ---------------------------------------------------------------------------
# List append syntax with config files
# ---------------------------------------------------------------------------


class TestListAppendWithConfig:
    """Tests for the + append syntax when a config file provides the base list."""

    def test_cli_append_extends_config_list(self, tmp_toml) -> None:
        """--items+ appends elements after those from the config file."""
        WithList = make_target("items", list[int], default_factory=list)
        path = tmp_toml("items = [1, 2]\n")
        result = confarg.load(WithList, args=["--items+", "3", "4"], env={}, files=[path])
        assert result.items == [1, 2, 3, 4]

    def test_cli_append_empty_adds_nothing(self, tmp_toml) -> None:
        """--items+ with no values leaves the config list unchanged."""
        WithList = make_target("items", list[int], default_factory=list)
        path = tmp_toml("items = [1, 2]\n")
        result = confarg.load(WithList, args=["--items+"], env={}, files=[path])
        assert result.items == [1, 2]

    def test_cli_replacement_still_works(self, tmp_toml) -> None:
        """--items.N with N inside the existing list still replaces that element."""
        WithList = make_target("items", list[int], default_factory=list)
        path = tmp_toml("items = [1, 2, 3]\n")
        result = confarg.load(WithList, args=["--items.1", "99"], env={}, files=[path])
        assert result.items == [1, 99, 3]

    def test_cli_index_out_of_range_raises(self, tmp_toml) -> None:
        """--items.N with N >= len(config list) raises ConfargError (use + instead)."""
        WithList = make_target("items", list[int], default_factory=list)
        path = tmp_toml("items = [1, 2]\n")
        with pytest.raises(confarg.exceptions.ConfargError, match="append syntax"):
            confarg.load(WithList, args=["--items.2", "3"], env={}, files=[path])

    def test_env_index_out_of_range_raises(self, tmp_toml) -> None:
        """Env index beyond config list length raises ConfargError."""
        WithList = make_target("items", list[int], default_factory=list)
        path = tmp_toml("items = [1, 2]\n")
        with pytest.raises(confarg.exceptions.ConfargError, match="append syntax"):
            confarg.load(WithList, args=[], env={"ITEMS__2": "3"}, env_prefix="", files=[path])


# ---------------------------------------------------------------------------
# Config-file key+ append syntax
# ---------------------------------------------------------------------------


class TestConfigFileAppendSyntax:
    """key+: in config files appends to a list instead of replacing it."""

    def test_yaml_append_to_base_list(self, tmp_yaml) -> None:
        """users+: [...] in a YAML file appends to the list from another file."""
        WithList = make_target("users", list[str], default_factory=list)
        base = tmp_yaml("users: [alice, bob]\n", "base.yaml")
        derived = tmp_yaml("users+: [frankenstein]\n", "derived.yaml")
        result = confarg.load(WithList, args=[], env={}, files=[base, derived])
        assert result.users == ["alice", "bob", "frankenstein"]

    def test_yaml_append_no_base(self, tmp_yaml) -> None:
        """users+: [...] with no prior list creates the list from scratch."""
        WithList = make_target("users", list[str], default_factory=list)
        path = tmp_yaml("users+: [alice, bob]\n")
        result = confarg.load(WithList, args=[], env={}, files=[path])
        assert result.users == ["alice", "bob"]

    def test_yaml_append_then_cli_append(self, tmp_yaml) -> None:
        """File key+ and CLI --field+ both append; combined order is file then CLI."""
        WithList = make_target("users", list[str], default_factory=list)
        base = tmp_yaml("users: [alice]\n", "base.yaml")
        derived = tmp_yaml("users+: [bob]\n", "derived.yaml")
        result = confarg.load(WithList, args=["--users+", "carol"], env={}, files=[base, derived])
        assert result.users == ["alice", "bob", "carol"]

    def test_yaml_append_scalar(self, tmp_yaml) -> None:
        """users+: single_value (scalar, not a list) appends it as one element."""
        WithList = make_target("users", list[str], default_factory=list)
        base = tmp_yaml("users: [alice]\n", "base.yaml")
        derived = tmp_yaml("users+: bob\n", "derived.yaml")
        result = confarg.load(WithList, args=[], env={}, files=[base, derived])
        assert result.users == ["alice", "bob"]

    def test_yaml_multiple_files_each_append(self, tmp_yaml) -> None:
        """Three files each use key+: ; all items accumulate in order."""
        WithList = make_target("users", list[str], default_factory=list)
        f1 = tmp_yaml("users+: [alice]\n", "f1.yaml")
        f2 = tmp_yaml("users+: [bob]\n", "f2.yaml")
        f3 = tmp_yaml("users+: [carol]\n", "f3.yaml")
        result = confarg.load(WithList, args=[], env={}, files=[f1, f2, f3])
        assert result.users == ["alice", "bob", "carol"]

    def test_yaml_nested_key_append(self, tmp_yaml) -> None:
        """key+: works inside a nested dict (nested struct field)."""

        @dataclass
        class Inner:
            items: list[int]

        Target = make_target("inner", Inner)
        base = tmp_yaml("inner:\n  items: [1, 2]\n", "base.yaml")
        derived = tmp_yaml("inner:\n  items+: [3]\n", "derived.yaml")
        result = confarg.load(Target, args=[], env={}, files=[base, derived])
        assert result.inner.items == [1, 2, 3]

    def test_yaml_include_chain_append(self, tmp_path) -> None:
        """users+: in derived file with __include__ appends after the included list."""
        base = tmp_path / "base.yaml"
        base.write_text("users: [alice, bob]\n")
        derived = tmp_path / "derived.yaml"
        derived.write_text("__include__: ./base.yaml\nusers+: [frankenstein]\n")
        WithList = make_target("users", list[str], default_factory=list)
        result = confarg.load(WithList, args=[], env={}, files=[derived])
        assert result.users == ["alice", "bob", "frankenstein"]

    def test_json_append(self, tmp_json) -> None:
        """Append syntax works in JSON files via the "key+" notation."""
        WithList = make_target("items", list[int], default_factory=list)
        base = tmp_json('{"items": [1, 2]}', "base.json")
        derived = tmp_json('{"items+": [3, 4]}', "derived.json")
        result = confarg.load(WithList, args=[], env={}, files=[base, derived])
        assert result.items == [1, 2, 3, 4]

    def test_toml_append_quoted_key(self, tmp_toml) -> None:
        """Append syntax works in TOML via quoted key ("key+" = [...]) since bare keys cannot contain +."""
        WithList = make_target("items", list[int], default_factory=list)
        base = tmp_toml("items = [1, 2]\n", "base.toml")
        derived = tmp_toml('"items+" = [3, 4]\n', "derived.toml")
        result = confarg.load(WithList, args=[], env={}, files=[base, derived])
        assert result.items == [1, 2, 3, 4]

    def test_yaml_append_dict_item(self, tmp_yaml) -> None:
        """key+: with a dict value appends that dict as a single list element."""

        @dataclass
        class Server:
            host: str
            port: int

        Target = make_target("servers", list[Server])
        base = tmp_yaml("servers:\n  - host: a\n    port: 1\n", "base.yaml")
        derived = tmp_yaml("servers+:\n  host: b\n  port: 2\n", "derived.yaml")
        result = confarg.load(Target, args=[], env={}, files=[base, derived])
        assert len(result.servers) == 2
        assert result.servers[0].host == "a"
        assert result.servers[1].host == "b"
        assert result.servers[1].port == 2


# ---------------------------------------------------------------------------
# Config file deletion syntax: key- and list index N-
# ---------------------------------------------------------------------------


class TestConfigFileDeleteSyntax:
    """Tests for key- and N- deletion syntax in YAML/TOML/JSON config files."""

    def test_delete_field_resets_to_default(self, tmp_yaml) -> None:
        """key-: ~ in a derived file removes the field set in the base file."""
        base = tmp_yaml("name: from_base\n", "base.yaml")
        derived = tmp_yaml("name-: ~\n", "derived.yaml")
        result = confarg.load(WithDefaults, args=[], env={}, files=[base, derived])
        assert result.name == "default"

    def test_delete_required_field_raises(self, tmp_yaml) -> None:
        """Deleting a required field via config file causes MissingFieldError."""
        base = tmp_yaml("name: cfg\ncount: 5\nrate: 1.0\nverbose: false\n", "base.yaml")
        derived = tmp_yaml("name-: ~\n", "derived.yaml")
        with pytest.raises(confarg.exceptions.MissingFieldError):
            confarg.load(Flat, args=[], env={}, files=[base, derived])

    def test_delete_list_index_yaml(self, tmp_yaml) -> None:
        """1-: ~ syntax removes the element at original index 1 from a list."""
        WithList = make_target("items", list[str], default_factory=list)
        base = tmp_yaml("items:\n  - a\n  - b\n  - c\n", "base.yaml")
        derived = tmp_yaml("items:\n  1-: ~\n", "derived.yaml")
        result = confarg.load(WithList, args=[], env={}, files=[base, derived])
        assert result.items == ["a", "c"]

    def test_delete_multiple_indices_use_original_positions(self, tmp_yaml) -> None:
        """Multiple index deletions are applied to original positions simultaneously."""
        WithList = make_target("items", list[str], default_factory=list)
        base = tmp_yaml("items:\n  - a\n  - b\n  - c\n  - d\n", "base.yaml")
        derived = tmp_yaml("items:\n  1-: ~\n  2-: ~\n", "derived.yaml")
        result = confarg.load(WithList, args=[], env={}, files=[base, derived])
        assert result.items == ["a", "d"]

    def test_delete_list_index_toml(self, tmp_toml) -> None:
        r"""TOML requires quoting: "1-" = true syntax removes element at original index 1."""
        WithList = make_target("items", list[str], default_factory=list)
        base = tmp_toml('items = ["a", "b", "c"]\n', "base.toml")
        derived = tmp_toml('[items]\n"1-" = true\n', "derived.toml")
        result = confarg.load(WithList, args=[], env={}, files=[base, derived])
        assert result.items == ["a", "c"]

    def test_delete_and_append_in_same_file(self, tmp_yaml) -> None:
        """Deleting an index and appending a value in a single file works."""
        WithList = make_target("items", list[str], default_factory=list)
        base = tmp_yaml("items:\n  - a\n  - b\n  - c\n", "base.yaml")
        derived = tmp_yaml("items:\n  1-: ~\nitems+:\n  - d\n", "derived.yaml")
        result = confarg.load(WithList, args=[], env={}, files=[base, derived])
        assert result.items == ["a", "c", "d"]

    def test_delete_out_of_range_raises(self, tmp_yaml) -> None:
        """Deleting an out-of-range index raises ConfargError."""
        WithList = make_target("items", list[str], default_factory=list)
        base = tmp_yaml("items:\n  - a\n  - b\n", "base.yaml")
        derived = tmp_yaml("items:\n  5-: ~\n", "derived.yaml")
        with pytest.raises(confarg.exceptions.ConfargError):
            confarg.load(WithList, args=[], env={}, files=[base, derived])

    def test_delete_field_in_include_chain(self, tmp_yaml) -> None:
        """Deletion in the middle of a multi-file include chain is applied correctly."""
        WithList = make_target("items", list[str], default_factory=list)
        base = tmp_yaml("items:\n  - x\n  - y\n  - z\n", "base.yaml")
        mid = tmp_yaml("items:\n  1-: ~\n", "mid.yaml")
        top = tmp_yaml("items+:\n  - w\n", "top.yaml")
        result = confarg.load(WithList, args=[], env={}, files=[base, mid, top])
        assert result.items == ["x", "z", "w"]

    def test_negative_index_update_yaml(self, tmp_yaml) -> None:
        """-1 key in YAML updates the last element."""
        WithList = make_target("items", list[str], default_factory=list)
        base = tmp_yaml("items:\n  - a\n  - b\n  - c\n", "base.yaml")
        derived = tmp_yaml('items:\n  "-1": z\n', "derived.yaml")
        result = confarg.load(WithList, args=[], env={}, files=[base, derived])
        assert result.items == ["a", "b", "z"]

    def test_negative_index_delete_yaml(self, tmp_yaml) -> None:
        """-1- key in YAML deletes the last element."""
        WithList = make_target("items", list[str], default_factory=list)
        base = tmp_yaml("items:\n  - a\n  - b\n  - c\n", "base.yaml")
        derived = tmp_yaml("items:\n  -1-: ~\n", "derived.yaml")
        result = confarg.load(WithList, args=[], env={}, files=[base, derived])
        assert result.items == ["a", "b"]

    def test_negative_index_without_base_raises(self) -> None:
        """from_dict with a negative index key and no base list raises TypeCoercionError."""
        WithList = make_target("items", list[int], default_factory=list)
        with pytest.raises(confarg.exceptions.TypeCoercionError, match=r"[Nn]egative"):
            confarg.build(WithList, {"items": {"-1": 99}})
