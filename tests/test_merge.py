# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for source merge priority: CLI > env > config, partial merge, collection index override."""

from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Callable  # noqa: TC003  # the dataclasses below are read at runtime
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tests._loaders import ConfargLoader

import pytest

import confarg
from confarg._merge import (
    ListOp,
    MergeDict,
    _deep_merge,
)
from confarg.exceptions import ConfargError
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

    def test_cli_overrides_env(self, loader: ConfargLoader) -> None:
        """CLI value takes precedence over env var."""
        result = loader.load(
            WithDefaults,
            argv=["--name", "from_cli"],
            env={"MYAPP_NAME": "from_env"},
            env_prefix="MYAPP_",
        )
        assert result.name == "from_cli"

    def test_env_overrides_config(self, loader: ConfargLoader, tmp_toml) -> None:
        """Env var takes precedence over config file."""
        path = tmp_toml('name = "from_config"\n')
        result = loader.load(
            WithDefaults,
            argv=[],
            env={"MYAPP_NAME": "from_env"},
            env_prefix="MYAPP_",
            files=[path],
        )
        assert result.name == "from_env"

    def test_cli_overrides_config(self, loader: ConfargLoader, tmp_toml) -> None:
        """CLI value takes precedence over config file."""
        path = tmp_toml('name = "from_config"\ncount = 1\nrate = 0.0\nverbose = false\n')
        result = loader.load(
            Flat,
            argv=["--name", "from_cli", "--count", "1", "--rate", "0", "--verbose", "true"],
            env={},
            files=[path],
        )
        assert result.name == "from_cli"

    def test_cli_overrides_env_overrides_config(self, loader: ConfargLoader, tmp_toml) -> None:
        """Full three-way priority: CLI > env > config."""
        path = tmp_toml("name = 'from_config'\ncount = 100\nrate = 1.0\nverbose = false\n")
        result = loader.load(
            Flat,
            argv=["--name", "from_cli", "--count", "1", "--rate", "0", "--verbose", "true"],
            env={"MYAPP_NAME": "from_env", "MYAPP_COUNT": "200"},
            env_prefix="MYAPP_",
            files=[path],
        )
        assert result.name == "from_cli"  # CLI wins over env
        assert result.count == 1  # CLI wins over env

    def test_env_fills_missing_cli(self, loader: ConfargLoader, tmp_toml) -> None:
        """Env fills fields not provided by CLI; config fills the rest."""
        path = tmp_toml("name = 'cfg'\ncount = 10\nrate = 0.5\nverbose = false\n")
        result = loader.load(
            Flat,
            argv=["--name", "cli"],
            env={"MYAPP_COUNT": "20", "MYAPP_RATE": "2.0", "MYAPP_VERBOSE": "true"},
            env_prefix="MYAPP_",
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

    def test_nested_partial_merge(self, loader: ConfargLoader, tmp_toml) -> None:
        """Each source provides different nested fields."""
        path = tmp_toml("""\
            [db]
            host = "config_host"
            port = 5432
            name = "config_db"
        """)
        result = loader.load(
            AppConfig,
            argv=["--db.host", "cli_host"],
            env={"MYAPP_DB__PORT": "3306"},
            env_prefix="MYAPP_",
            files=[path],
        )
        assert result.db.host == "cli_host"  # CLI overrides config
        assert result.db.port == 3306  # env overrides config
        assert result.db.name == "config_db"  # from config

    def test_defaults_fill_gaps(self, loader: ConfargLoader) -> None:
        """Defaults fill fields not provided by any source."""
        result = loader.load(
            WithDefaults,
            argv=["--name", "only_name"],
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

    def test_cli_list_overrides_config_list_space_sep(self, space_sep_loader: ConfargLoader, tmp_toml) -> None:
        """CLI list (space-separated) replaces the entire config list."""
        WithList = make_target("items", list[int], default_factory=list)
        path = tmp_toml("items = [1, 2, 3]\n")
        result = space_sep_loader.load(
            WithList,
            argv=["--items", "10", "20"],
            env={},
            files=[path],
        )
        assert result.items == [10, 20]

    def test_cli_list_overrides_config_list_repeated(self, loader: ConfargLoader, tmp_toml) -> None:
        """CLI list (repeated flags) replaces the entire config list, in every front-end."""
        WithList = make_target("items", list[int], default_factory=list)
        path = tmp_toml("items = [1, 2, 3]\n")
        result = loader.load(
            WithList,
            argv=["--items", "10", "--items", "20"],
            env={},
            files=[path],
        )
        assert result.items == [10, 20]

    def test_cli_index_overrides_config_item(self, tmp_toml) -> None:
        """CLI index override (--items.N) replaces a single item — vanilla only."""
        WithList = make_target("items", list[int], default_factory=list)
        path = tmp_toml("items = [1, 2, 3]\n")
        result = confarg.load(
            WithList,
            argv=["--items.1", "99"],
            env={},
            files=[path],
        )
        assert result.items[1] == 99
        assert result.items[0] == 1
        assert result.items[2] == 3

    def test_env_index_overrides_config_item(self, loader: ConfargLoader, tmp_toml) -> None:
        """Env index override replaces a single item in config list."""
        WithList = make_target("items", list[int], default_factory=list)
        path = tmp_toml("items = [1, 2, 3]\n")
        result = loader.load(
            WithList,
            argv=[],
            env={"MYAPP_ITEMS__0": "99"},
            env_prefix="MYAPP_",
            files=[path],
        )
        assert result.items[0] == 99
        assert result.items[1] == 2

    def test_dict_merge_across_sources(self, tmp_toml) -> None:
        """A CLI dict key merges into the config file's mapping (parity: TestCollectionPatchContract)."""
        WithDict = make_target("metadata", dict[str, int], default_factory=dict)
        path = tmp_toml("[metadata]\na = 1\n")
        result = confarg.load(
            WithDict,
            argv=["--metadata.b", "2"],
            env={},
            files=[path],
        )
        assert result.metadata == {"a": 1, "b": 2}

    def test_cli_dict_key_overrides_config_key(self, tmp_toml) -> None:
        """A CLI dict key wins over the config file's (parity: TestCollectionPatchContract)."""
        WithDict = make_target("metadata", dict[str, int], default_factory=dict)
        path = tmp_toml("[metadata]\na = 1\n")
        result = confarg.load(
            WithDict,
            argv=["--metadata.a", "99"],
            env={},
            files=[path],
        )
        assert result.metadata == {"a": 99}


# ---------------------------------------------------------------------------
# Empty sources
# ---------------------------------------------------------------------------


class TestEmptySources:
    """Behaviour when sources are empty or disabled."""

    def test_all_sources_empty_uses_defaults(self, loader: ConfargLoader) -> None:
        """All sources empty -> defaults used."""
        result = loader.load(WithDefaults, argv=[], env={})
        assert result.name == "default"

    def test_only_config(self, loader: ConfargLoader, tmp_toml) -> None:
        """Only config file provides values."""
        path = tmp_toml("name = 'cfg'\ncount = 5\nrate = 1.0\nverbose = true\n")
        result = loader.load(Flat, argv=[], env={}, files=[path])
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
        result = confarg.load(WithList, argv=["--items+", "3", "4"], env={}, files=[path])
        assert result.items == [1, 2, 3, 4]

    def test_cli_append_empty_adds_nothing(self, tmp_toml) -> None:
        """--items+ with no values leaves the config list unchanged."""
        WithList = make_target("items", list[int], default_factory=list)
        path = tmp_toml("items = [1, 2]\n")
        result = confarg.load(WithList, argv=["--items+"], env={}, files=[path])
        assert result.items == [1, 2]

    def test_cli_replacement_still_works(self, tmp_toml) -> None:
        """--items.N with N inside the existing list still replaces that element."""
        WithList = make_target("items", list[int], default_factory=list)
        path = tmp_toml("items = [1, 2, 3]\n")
        result = confarg.load(WithList, argv=["--items.1", "99"], env={}, files=[path])
        assert result.items == [1, 99, 3]

    def test_cli_index_out_of_range_raises(self, tmp_toml) -> None:
        """--items.N with N >= len(config list) raises ConfargError (use + instead)."""
        WithList = make_target("items", list[int], default_factory=list)
        path = tmp_toml("items = [1, 2]\n")
        with pytest.raises(confarg.exceptions.ConfargError, match="append syntax"):
            confarg.load(WithList, argv=["--items.2", "3"], env={}, files=[path])

    def test_env_index_out_of_range_raises(self, tmp_toml) -> None:
        """Env index beyond config list length raises ConfargError."""
        WithList = make_target("items", list[int], default_factory=list)
        path = tmp_toml("items = [1, 2]\n")
        with pytest.raises(confarg.exceptions.ConfargError, match="append syntax"):
            confarg.load(WithList, argv=[], env={"MYAPP_ITEMS__2": "3"}, env_prefix="MYAPP_", files=[path])


# ---------------------------------------------------------------------------
# Config-file key+ append syntax
# ---------------------------------------------------------------------------


class TestConfigFileAppendSyntax:
    """key+: in config files appends to a list instead of replacing it."""

    def test_yaml_append_to_base_list(self, loader: ConfargLoader, tmp_yaml) -> None:
        """users+: [...] in a YAML file appends to the list from another file."""
        WithList = make_target("users", list[str], default_factory=list)
        base = tmp_yaml("users: [alice, bob]\n", "base.yaml")
        derived = tmp_yaml("users+: [frankenstein]\n", "derived.yaml")
        result = loader.load(WithList, argv=[], env={}, files=[base, derived])
        assert result.users == ["alice", "bob", "frankenstein"]

    def test_yaml_append_no_base(self, loader: ConfargLoader, tmp_yaml) -> None:
        """users+: [...] with no prior list creates the list from scratch."""
        WithList = make_target("users", list[str], default_factory=list)
        path = tmp_yaml("users+: [alice, bob]\n")
        result = loader.load(WithList, argv=[], env={}, files=[path])
        assert result.users == ["alice", "bob"]

    def test_yaml_append_then_cli_append(self, tmp_yaml) -> None:
        """File key+ and CLI --users+ both append — CLI append is vanilla-only."""
        WithList = make_target("users", list[str], default_factory=list)
        base = tmp_yaml("users: [alice]\n", "base.yaml")
        derived = tmp_yaml("users+: [bob]\n", "derived.yaml")
        result = confarg.load(WithList, argv=["--users+", "carol"], env={}, files=[base, derived])
        assert result.users == ["alice", "bob", "carol"]

    def test_yaml_append_scalar(self, loader: ConfargLoader, tmp_yaml) -> None:
        """users+: single_value (scalar, not a list) appends it as one element."""
        WithList = make_target("users", list[str], default_factory=list)
        base = tmp_yaml("users: [alice]\n", "base.yaml")
        derived = tmp_yaml("users+: bob\n", "derived.yaml")
        result = loader.load(WithList, argv=[], env={}, files=[base, derived])
        assert result.users == ["alice", "bob"]

    def test_yaml_multiple_files_each_append(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Three files each use key+: ; all items accumulate in order."""
        WithList = make_target("users", list[str], default_factory=list)
        f1 = tmp_yaml("users+: [alice]\n", "f1.yaml")
        f2 = tmp_yaml("users+: [bob]\n", "f2.yaml")
        f3 = tmp_yaml("users+: [carol]\n", "f3.yaml")
        result = loader.load(WithList, argv=[], env={}, files=[f1, f2, f3])
        assert result.users == ["alice", "bob", "carol"]

    def test_yaml_nested_key_append(self, loader: ConfargLoader, tmp_yaml) -> None:
        """key+: works inside a nested dict (nested struct field)."""

        @dataclass
        class Inner:
            items: list[int]

        Target = make_target("inner", Inner)
        base = tmp_yaml("inner:\n  items: [1, 2]\n", "base.yaml")
        derived = tmp_yaml("inner:\n  items+: [3]\n", "derived.yaml")
        result = loader.load(Target, argv=[], env={}, files=[base, derived])
        assert result.inner.items == [1, 2, 3]

    def test_yaml_include_chain_append(self, loader: ConfargLoader, tmp_path) -> None:
        """users+: in derived file with __include__ appends after the included list."""
        base = tmp_path / "base.yaml"
        base.write_text("users: [alice, bob]\n")
        derived = tmp_path / "derived.yaml"
        derived.write_text("__include__: ./base.yaml\nusers+: [frankenstein]\n")
        WithList = make_target("users", list[str], default_factory=list)
        result = loader.load(WithList, argv=[], env={}, files=[derived])
        assert result.users == ["alice", "bob", "frankenstein"]

    def test_json_append(self, loader: ConfargLoader, tmp_json) -> None:
        """Append syntax works in JSON files via the "key+" notation."""
        WithList = make_target("items", list[int], default_factory=list)
        base = tmp_json('{"items": [1, 2]}', "base.json")
        derived = tmp_json('{"items+": [3, 4]}', "derived.json")
        result = loader.load(WithList, argv=[], env={}, files=[base, derived])
        assert result.items == [1, 2, 3, 4]

    def test_toml_append_quoted_key(self, loader: ConfargLoader, tmp_toml) -> None:
        """Append syntax works in TOML via quoted key ("key+" = [...]) since bare keys cannot contain +."""
        WithList = make_target("items", list[int], default_factory=list)
        base = tmp_toml("items = [1, 2]\n", "base.toml")
        derived = tmp_toml('"items+" = [3, 4]\n', "derived.toml")
        result = loader.load(WithList, argv=[], env={}, files=[base, derived])
        assert result.items == [1, 2, 3, 4]

    def test_yaml_append_dict_item(self, loader: ConfargLoader, tmp_yaml) -> None:
        """key+: with a dict value appends that dict as a single list element."""

        @dataclass
        class Server:
            host: str
            port: int

        Target = make_target("servers", list[Server])
        base = tmp_yaml("servers:\n  - host: a\n    port: 1\n", "base.yaml")
        derived = tmp_yaml("servers+:\n  host: b\n  port: 2\n", "derived.yaml")
        result = loader.load(Target, argv=[], env={}, files=[base, derived])
        assert len(result.servers) == 2
        assert result.servers[0].host == "a"
        assert result.servers[1].host == "b"
        assert result.servers[1].port == 2


# ---------------------------------------------------------------------------
# Config file deletion syntax: key- and list index N-
# ---------------------------------------------------------------------------


class TestConfigFileDeleteSyntax:
    """Tests for key- and N- deletion syntax in YAML/TOML/JSON config files."""

    def test_delete_field_resets_to_default(self, loader: ConfargLoader, tmp_yaml) -> None:
        """key-: ~ in a derived file removes the field set in the base file."""
        base = tmp_yaml("name: from_base\n", "base.yaml")
        derived = tmp_yaml("name-: ~\n", "derived.yaml")
        result = loader.load(WithDefaults, argv=[], env={}, files=[base, derived])
        assert result.name == "default"

    def test_delete_required_field_raises(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Deleting a required field via config file causes MissingFieldError."""
        base = tmp_yaml("name: cfg\ncount: 5\nrate: 1.0\nverbose: false\n", "base.yaml")
        derived = tmp_yaml("name-: ~\n", "derived.yaml")
        with pytest.raises(confarg.exceptions.MissingFieldError):
            loader.load(Flat, argv=[], env={}, files=[base, derived])

    def test_delete_of_a_key_set_earlier_in_the_file_needs_nothing_below(self, tmp_yaml) -> None:
        """A delete that met its key in its own document is done: with no file below it does not leak (BUG-98).

        Found fixing BUG-227: the same delete beside an include met its key and was kept spent.
        """
        WithMap = make_target("data", dict[str, int], default_factory=dict)
        path = tmp_yaml("data:\n  x: 1\n  y: 2\n  x-: ~\n")
        assert confarg.load(WithMap, argv=[], env={}, files=[path]).data == {"y": 2}

    def test_append_after_a_delete_of_a_key_set_earlier_ignores_the_file_below(self, tmp_yaml) -> None:
        """``items``, then ``items-``, then ``items+`` in one file append to nothing, the lower file's list included."""
        WithList = make_target("items", list[str], default_factory=list)
        base = tmp_yaml("items: [a, b]\n", "base.yaml")
        derived = tmp_yaml("items: [c]\nitems-: ~\nitems+: [d]\n", "derived.yaml")
        assert confarg.load(WithList, argv=[], env={}, files=[base, derived]).items == ["d"]

    def test_delete_list_index_yaml(self, loader: ConfargLoader, tmp_yaml) -> None:
        """1-: ~ syntax removes the element at original index 1 from a list."""
        WithList = make_target("items", list[str], default_factory=list)
        base = tmp_yaml("items:\n  - a\n  - b\n  - c\n", "base.yaml")
        derived = tmp_yaml("items:\n  1-: ~\n", "derived.yaml")
        result = loader.load(WithList, argv=[], env={}, files=[base, derived])
        assert result.items == ["a", "c"]

    def test_delete_multiple_indices_use_original_positions(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Multiple index deletions are applied to original positions simultaneously."""
        WithList = make_target("items", list[str], default_factory=list)
        base = tmp_yaml("items:\n  - a\n  - b\n  - c\n  - d\n", "base.yaml")
        derived = tmp_yaml("items:\n  1-: ~\n  2-: ~\n", "derived.yaml")
        result = loader.load(WithList, argv=[], env={}, files=[base, derived])
        assert result.items == ["a", "d"]

    def test_delete_list_index_toml(self, loader: ConfargLoader, tmp_toml) -> None:
        r"""TOML requires quoting: "1-" = true syntax removes element at original index 1."""
        WithList = make_target("items", list[str], default_factory=list)
        base = tmp_toml('items = ["a", "b", "c"]\n', "base.toml")
        derived = tmp_toml('[items]\n"1-" = true\n', "derived.toml")
        result = loader.load(WithList, argv=[], env={}, files=[base, derived])
        assert result.items == ["a", "c"]

    def test_delete_and_append_in_same_file(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Deleting an index and appending a value in a single file works."""
        WithList = make_target("items", list[str], default_factory=list)
        base = tmp_yaml("items:\n  - a\n  - b\n  - c\n", "base.yaml")
        derived = tmp_yaml("items:\n  1-: ~\nitems+:\n  - d\n", "derived.yaml")
        result = loader.load(WithList, argv=[], env={}, files=[base, derived])
        assert result.items == ["a", "c", "d"]

    def test_delete_out_of_range_raises(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Deleting an out-of-range index raises ConfargError."""
        WithList = make_target("items", list[str], default_factory=list)
        base = tmp_yaml("items:\n  - a\n  - b\n", "base.yaml")
        derived = tmp_yaml("items:\n  5-: ~\n", "derived.yaml")
        with pytest.raises(confarg.exceptions.ConfargError):
            loader.load(WithList, argv=[], env={}, files=[base, derived])

    def test_delete_field_in_include_chain(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Deletion in the middle of a multi-file include chain is applied correctly."""
        WithList = make_target("items", list[str], default_factory=list)
        base = tmp_yaml("items:\n  - x\n  - y\n  - z\n", "base.yaml")
        mid = tmp_yaml("items:\n  1-: ~\n", "mid.yaml")
        top = tmp_yaml("items+:\n  - w\n", "top.yaml")
        result = loader.load(WithList, argv=[], env={}, files=[base, mid, top])
        assert result.items == ["x", "z", "w"]

    def test_negative_index_update_yaml(self, loader: ConfargLoader, tmp_yaml) -> None:
        """-1 key in YAML updates the last element."""
        WithList = make_target("items", list[str], default_factory=list)
        base = tmp_yaml("items:\n  - a\n  - b\n  - c\n", "base.yaml")
        derived = tmp_yaml('items:\n  "-1": z\n', "derived.yaml")
        result = loader.load(WithList, argv=[], env={}, files=[base, derived])
        assert result.items == ["a", "b", "z"]

    def test_negative_index_delete_yaml(self, loader: ConfargLoader, tmp_yaml) -> None:
        """-1- key in YAML deletes the last element."""
        WithList = make_target("items", list[str], default_factory=list)
        base = tmp_yaml("items:\n  - a\n  - b\n  - c\n", "base.yaml")
        derived = tmp_yaml("items:\n  -1-: ~\n", "derived.yaml")
        result = loader.load(WithList, argv=[], env={}, files=[base, derived])
        assert result.items == ["a", "b"]

    @pytest.mark.parametrize(
        ("derived", "expected"),
        [
            ("items-: ~\nitems+:\n  - x\n", ["x"]),
            ("items-: ~\nitems:\n  '0': x\n", ["x"]),
            ("items+:\n  - x\nitems-: ~\n", []),
        ],
    )
    def test_op_after_a_whole_field_delete_in_one_file(
        self,
        loader: ConfargLoader,
        tmp_yaml,
        derived: str,
        expected: list[str],
    ) -> None:
        """A key written after ``items-`` in the same file applies to nothing below, as on the CLI (BUG-116)."""
        WithList = make_target("items", list[str], default_factory=list)
        base = tmp_yaml("items:\n  - a\n  - b\n", "base.yaml")
        top = tmp_yaml(derived, "derived.yaml")
        assert loader.load(WithList, argv=[], env={}, files=[base, top]).items == expected

    def test_index_delete_after_a_whole_field_delete_in_one_file_has_no_base(
        self,
        loader: ConfargLoader,
        tmp_yaml,
    ) -> None:
        """``items-`` then ``items: {0-: ~}`` in one file fails as ``--items- --items.0-`` does (BUG-116)."""
        WithList = make_target("items", list[str], default_factory=list)
        base = tmp_yaml("items:\n  - a\n  - b\n", "base.yaml")
        top = tmp_yaml("items-: ~\nitems:\n  0-: ~\n", "derived.yaml")
        with pytest.raises(confarg.exceptions.TypeCoercionError, match="requires a base list"):
            loader.load(WithList, argv=[], env={}, files=[base, top])

    def test_negative_index_without_base_raises(self) -> None:
        """from_dict with a negative index key and no base list raises TypeCoercionError."""
        WithList = make_target("items", list[int], default_factory=list)
        with pytest.raises(confarg.exceptions.TypeCoercionError, match=r"[Nn]egative"):
            confarg.build(WithList, {"items": {"-1": 99}})


@dataclass
class _Item:
    k: int = 0
    j: int = 0
    tags: list[str] = dataclasses.field(default_factory=list)


@dataclass
class _Items:
    rows: list[_Item] = dataclasses.field(default_factory=list)
    grid: list[list[_Item]] = dataclasses.field(default_factory=list)


class TestAListItemReadsTheShorthand:
    """A dict standing in a file's list reads the merge shorthand as every other dict of the file does (BUG-237).

    It has no layer below it, so it reads as a document merged over nothing. Only an item beside
    an include read it, through the merge of the include's siblings.
    """

    @pytest.mark.parametrize(
        ("item", "expected"),
        [
            pytest.param("{k: 4, j: 9, k-: null}", _Item(k=0, j=9), id="delete-met"),
            pytest.param("{k: 4, j: 9, zz-: null}", _Item(k=4, j=9), id="delete-unmet"),
            pytest.param("{tags: [a], tags+: [b]}", _Item(tags=["a", "b"]), id="append"),
            pytest.param("{tags: {__append__: [b]}}", _Item(tags=["b"]), id="reserved-op-key"),
        ],
    )
    def test_item_reads_the_shorthand(self, tmp_yaml, item: str, expected: _Item) -> None:
        """A key's suffix and a reserved op key in a list item are the ops they spell."""
        path = tmp_yaml(f"rows:\n  - {item}\n")
        assert confarg.load(_Items, argv=[], env={}, files=[path]).rows == [expected]

    def test_item_reads_it_as_the_same_item_beside_an_include(self, tmp_yaml) -> None:
        """Inline or beside an include, the item's delete removes ``k``."""
        tmp_yaml("k: 4\nj: 9\n", "row.yaml")
        flat = tmp_yaml("rows:\n  - {k: 4, j: 9, k-: null}\n", "flat.yaml")
        inc = tmp_yaml("rows:\n  - {__include__: row.yaml, k-: null}\n", "inc.yaml")
        assert (
            confarg.load(_Items, argv=[], env={}, files=[flat]).rows
            == confarg.load(_Items, argv=[], env={}, files=[inc]).rows
            == [_Item(k=0, j=9)]
        )

    def test_item_of_a_nested_list_reads_it(self, tmp_yaml) -> None:
        """An item two lists deep reads the shorthand too."""
        path = tmp_yaml("grid:\n  - - {k: 4, k-: null, tags+: [x]}\n")
        assert confarg.load(_Items, argv=[], env={}, files=[path]).grid == [[_Item(k=0, tags=["x"])]]


class TestNestedIndexMerge:
    """An index patch over a list/tuple element composes recursively, not replaces.

    The per-index patch in _apply_list_ops delegates to the canonical
    _merge_existing_value dispatcher, so a list-typed element + an index-keyed
    dict recurses instead of being overwritten — at any depth.
    """

    def test_index_into_list_element_patches(self) -> None:
        """{'0': {'0': 42}} over [[1,2,3],[4,5]] patches [0][0], keeping the rest."""
        merged = _deep_merge({"input": [[1, 2, 3], [4, 5]]}, {"input": {"0": {"0": 42}}})
        assert merged == {"input": [[42, 2, 3], [4, 5]]}

    def test_index_into_list_element_arbitrary_depth(self) -> None:
        """Three-deep index patch composes through every level."""
        base: MergeDict = {"input": [[[1, 2], [3, 4]], [[5, 6]]]}
        merged = _deep_merge(base, {"input": {"0": {"1": {"0": 99}}}})
        assert merged == {"input": [[[1, 2], [99, 4]], [[5, 6]]]}

    def test_index_into_list_element_via_loader(self, loader: ConfargLoader, tmp_yaml) -> None:
        """End-to-end: a config base list + a nested-index config patch compose identically."""
        WithGrid = make_target("grid", list[list[int]], default_factory=list)
        base = tmp_yaml("grid:\n  - [1, 2, 3]\n  - [4, 5]\n", "base.yaml")
        derived = tmp_yaml("grid:\n  0:\n    0: 42\n", "derived.yaml")
        result = loader.load(WithGrid, argv=[], env={}, files=[base, derived])
        assert result.grid == [[42, 2, 3], [4, 5]]

    def test_a_later_base_and_patch_replace_an_earlier_deferred_patch(self, tmp_yaml) -> None:
        """A channel's whole list plus a patch replaces what lower layers deferred, stale keys included.

        Two files defer ``{__base__: [1], 1: 5}``; the env's ``[7, 9]`` and its ``.0`` patch arrive as
        ``{__base__: [7, 9], '0': 8}``, which once deep-merged into the files' patch and kept its ``1``.
        """
        WithPair = make_target("t", tuple[int, int])
        a = tmp_yaml("t: [1]\n", "a.yaml")
        b = tmp_yaml("t: {1: 5}\n", "b.yaml")
        env = {"APP_T": "[7, 9]", "APP_T__0": "8"}
        assert confarg.load(WithPair, argv=[], env=env, env_prefix="APP_", files=[a, b]).t == (8, 9)


class TestReplaceBaseIsAList:
    """A patch over a list base carries its own base as a list, or the merge refuses it (BUG-170)."""

    @pytest.mark.parametrize("base", [5, "12"], ids=["int", "str"])
    def test_base_that_is_no_list_is_refused(self, base: object) -> None:
        """A file's ``__base__`` holding no list is refused rather than read with ``list()``."""
        with pytest.raises(confarg.exceptions.ConfargError, match=re.escape("at 'input': '__base__' must hold a list")):
            _deep_merge({"input": [1, 2]}, {"input": {ListOp.BASE: base, "0": 3}})


class TestDictKeyStar:
    """A dict's own key ``*`` merges as any other key: it holds no base, so it replaces nothing (BUG-185)."""

    def test_star_key_over_a_dict_is_merged_beside_its_keys(self) -> None:
        """``{'*': 5}`` over ``{'k': 1}`` adds the key, as ``{'z': 5}`` does."""
        assert _deep_merge({"d": {"k": 1}}, {"d": {"*": 5}}) == {"d": {"k": 1, "*": 5}}

    def test_star_key_from_the_env_keeps_the_files_keys(self, tmp_json) -> None:
        """``APP_D__*`` over a file's ``d`` adds the key ``*`` beside the file's."""
        WithDict = make_target("d", dict[str, int], default_factory=dict)
        base = tmp_json('{"d": {"k": 1}}')
        cfg = confarg.load(WithDict, argv=[], env={"APP_D__*": "5"}, env_prefix="APP_", files=[base])
        assert cfg.d == {"k": 1, "*": 5}

    def test_star_key_from_a_later_file_keeps_the_earlier_files_keys(self, tmp_json) -> None:
        """A later file's ``{"*": 5}`` under ``d`` adds the key beside the earlier file's."""
        WithDict = make_target("d", dict[str, int], default_factory=dict)
        a = tmp_json('{"d": {"k": 1}}', "a.json")
        b = tmp_json('{"d": {"*": 5}}', "b.json")
        assert confarg.load(WithDict, argv=[], env={}, files=[a, b]).d == {"k": 1, "*": 5}

    def test_star_key_holding_a_list_from_the_env_keeps_the_files_keys(self, tmp_json) -> None:
        """``APP_D__*=[3]`` adds the key ``*`` holding a list beside the file's (BUG-199)."""
        WithDict = make_target("d", dict[str, list[int]], default_factory=dict)
        base = tmp_json('{"d": {"k": [1]}}')
        cfg = confarg.load(WithDict, argv=[], env={"APP_D__*": "[3]"}, env_prefix="APP_", files=[base])
        assert cfg.d == {"k": [1], "*": [3]}


class TestMergeOpsAreSpelledByNoChannel:
    """The merge's list ops are keys no channel types; a file writes one by its reserved name (FEAT-3)."""

    @pytest.mark.parametrize("key", ["*", "+", "-", "~"])
    def test_dict_key_spelled_like_a_list_op_merges_as_any_other(self, tmp_json, key: str) -> None:
        """A later file's value of the key replaces the earlier file's, and the dict keeps its other keys."""
        WithDict = make_target("d", dict[str, list[int]], default_factory=dict)
        a = tmp_json(json.dumps({"d": {"k": [1], key: [2]}}), "a.json")
        b = tmp_json(json.dumps({"d": {key: [3]}}), "b.json")
        assert confarg.load(WithDict, argv=[], env={}, files=[a, b]).d == {"k": [1], key: [3]}

    @pytest.mark.parametrize(
        ("ops", "built"),
        [
            ({"__append__": [3]}, [1, 2, 3]),
            ({"__delete__": [0]}, [2]),
            ({"__base__": [7], "0": 8}, [8]),
            ({"__append__": [3], "__delete_after__": [0]}, [2, 3]),
        ],
        ids=["append", "delete", "base", "delete-after"],
    )
    def test_file_writes_a_list_op_by_its_reserved_key(self, tmp_json, ops: dict[str, Any], built: list[int]) -> None:
        """``__append__``, ``__delete__``, ``__base__`` and ``__delete_after__`` are the ops a merged dict holds."""
        WithList = make_target("xs", list[int], default_factory=list)
        a = tmp_json('{"xs": [1, 2]}', "a.json")
        b = tmp_json(json.dumps({"xs": ops}), "b.json")
        assert confarg.load(WithList, argv=[], env={}, files=[a, b]).xs == built

    @pytest.mark.parametrize("key", ["*", "+", "-", "~"])
    def test_file_key_spelled_like_a_list_op_is_no_op(self, tmp_json, key: str) -> None:
        """Below a list, a file's ``{"+": [3]}`` is a key the list has no position for, not an append."""
        WithList = make_target("xs", list[int], default_factory=list)
        a = tmp_json('{"xs": [1, 2]}', "a.json")
        b = tmp_json(json.dumps({"xs": {key: [3]}}), "b.json")
        with pytest.raises(ConfargError, match=re.escape(f"Cannot patch list 'xs' with non-integer key {key!r}")):
            confarg.load(WithList, argv=[], env={}, files=[a, b])

    def test_merged_dict_holds_no_op_a_channel_could_type(self) -> None:
        """The append ``--xs+ 3`` records is neither the key ``+`` nor the key ``__append__``."""
        WithList = make_target("xs", list[int], default_factory=list)
        (op,) = confarg.merge(WithList, argv=["--xs+", "3"], env={})["xs"]
        assert op not in {"+", "__append__"}

    def test_merged_dict_holds_an_op_as_the_public_list_op(self) -> None:
        """The append ``--xs+ 3`` records is ``confarg.ListOp.APPEND``, which a caller can test for."""
        WithList = make_target("xs", list[int], default_factory=list)
        (op,) = confarg.merge(WithList, argv=["--xs+", "3"], env={})["xs"]
        assert op is confarg.ListOp.APPEND

    @pytest.mark.parametrize("op", list(ListOp), ids=lambda op: op.name)
    def test_a_list_op_spells_as_a_file_writes_it_and_equals_no_string(self, op: ListOp) -> None:
        """``str()`` is the reserved key, ``repr()`` the member, and the reserved key is no lookup of it."""
        assert (str(op), repr(op)) == (op.value, f"ListOp.{op.name}")
        assert op != op.value
        assert {op.value: 1}.get(op) is None


class TestListDeleteKeysHoldIndices:
    """A file's list-delete key holding no index list is refused with the field it patches (BUG-175)."""

    @pytest.mark.parametrize(
        ("ops", "key"),
        [({"__delete__": 0}, "__delete__"), ({"__append__": [3], "__delete_after__": 0}, "__delete_after__")],
        ids=["delete", "delete-after"],
    )
    def test_delete_key_holding_no_index_list_is_refused(self, tmp_json, ops: dict[str, Any], key: str) -> None:
        """``xs: {__delete__: 0}`` names the field and the key, rather than escaping as a ``TypeError``."""
        WithList = make_target("xs", list[int], default_factory=list)
        a = tmp_json('{"xs": [1, 2]}', "a.json")
        b = tmp_json(json.dumps({"xs": ops}), "b.json")
        with pytest.raises(ConfargError, match=re.escape(f"at 'xs': {key!r} must hold a list of indices, got int 0")):
            confarg.load(WithList, argv=[], env={}, files=[a, b])

    def test_delete_keys_of_two_layers_holding_no_index_list_are_refused(self) -> None:
        """Two layers' deletes are combined only once each is read as indices."""
        with pytest.raises(ConfargError, match=re.escape("at 'xs': '__delete__' must hold a list of indices")):
            _deep_merge({"xs": {"__delete__": [0]}}, {"xs": {"__delete__": 1}})

    @pytest.mark.parametrize("ops", [{"-": 0}, {"+": [3], "~": 0}], ids=["dash", "tilde"])
    def test_file_writing_the_former_delete_keys_is_refused_as_a_confarg_error(
        self,
        tmp_json,
        ops: dict[str, Any],
    ) -> None:
        """The literal ``-`` and ``~`` keys of the original report no longer escape as a ``TypeError``."""
        WithList = make_target("xs", list[int], default_factory=list)
        a = tmp_json('{"xs": [1, 2]}', "a.json")
        b = tmp_json(json.dumps({"xs": ops}), "b.json")
        with pytest.raises(ConfargError, match=re.escape("Cannot patch list 'xs' with non-integer key")):
            confarg.load(WithList, argv=[], env={}, files=[a, b])


class TestAnOverrideThatReplacesTheListBelow:
    """An override that carries its own base or a cast pin replaces a lower layer's list.

    It is no patch over that list: a carried base is the list it patches (5a), and a pin
    is a value, which a scalar override would replace the list with too (5b).
    """

    def test_a_carried_base_with_a_name_key_stays_deferred(self) -> None:
        """``--pt 1 2 --pt.y 5`` over a lower ``[7, 8]`` keeps its name patch for the namedtuple."""
        merged = _deep_merge({"pt": [7, 8]}, {"pt": {ListOp.BASE: [1, 2], "y": 5}})
        assert merged == {"pt": {ListOp.BASE: [1, 2], "y": 5}}

    def test_a_pin_replaces_a_list_below(self) -> None:
        """A file's ``{__cast__, __value__}`` over a lower file's list is the pin alone."""
        pin = {"__cast__": "int", "__value__": 5}
        assert _deep_merge({"u": [1, 2]}, {"u": pin}) == {"u": pin}

    def test_a_pin_replaces_a_dict_below(self) -> None:
        """Over a lower dict, the pin's keys are not merged into it."""
        pin = {"__cast__": "int", "__value__": 5}
        assert _deep_merge({"u": {"a": 1}}, {"u": pin}) == {"u": pin}


@dataclass
class _CallPoint:
    a: int = 0
    b: int = 0


def _square(a: int = 1) -> _CallPoint:
    return _CallPoint(a, a)


def _pair(a: int) -> list[int]:
    return [a, a]


@dataclass
class _CallLayers:
    p: _CallPoint = dataclasses.field(default_factory=_CallPoint)
    xs: list[int] = dataclasses.field(default_factory=list)


class TestACallReplacesWhatLiesBelow:
    """A ``call:`` is a finished value, so it replaces what a lower layer set, as a union tag does (BUG-190).

    No key beside it but ``args`` belongs to it, so a lower layer's keys merged beside it were
    read as nothing a call takes, or, before ``args``, silently as its arguments.
    """

    def test_a_call_replaces_a_dict_below(self) -> None:
        """A lower layer's struct keys are not merged beside the call."""
        assert _deep_merge({"p": {"a": 5}}, {"p": {"call": "m.square"}}) == {"p": {"call": "m.square"}}

    def test_a_call_replaces_a_list_below(self) -> None:
        """A lower layer's list does not become the call's ``__base__``."""
        call = {"call": "m.pair", "args": {"a": 3}}
        assert _deep_merge({"xs": [1, 2]}, {"xs": call}) == {"xs": call}

    def test_a_call_replaces_a_call_below(self) -> None:
        """The lower call's arguments belong to its own target, not to the one above it."""
        merged = _deep_merge({"p": {"call": "m.f", "args": {"a": 1}}}, {"p": {"call": "m.g"}})
        assert merged == {"p": {"call": "m.g"}}

    def test_a_call_at_the_root_replaces_the_root_below(self) -> None:
        """The root follows the same rule as every node, as the union tag does there."""
        assert _deep_merge({"a": 5}, {"call": "m.f"}) == {"call": "m.f"}

    def test_args_without_a_call_refine_the_call_below(self) -> None:
        """A layer holding only ``args`` patches the arguments of the call below it."""
        below: MergeDict = {"p": {"call": "m.f", "args": {"a": 1, "b": 2}}}
        merged = _deep_merge(below, {"p": {"args": {"a": 3}}})
        assert merged == {"p": {"call": "m.f", "args": {"a": 3, "b": 2}}}

    def test_load_builds_the_call_alone(self, tmp_path) -> None:
        """The ticket's reproduction: a struct and a list field each take the call, not what lay below."""
        base = tmp_path / "base.yaml"
        base.write_text("p: {a: 5}\nxs: [1, 2]\n")
        over = tmp_path / "over.yaml"
        over.write_text(f"p: {{call: {__name__}._square}}\nxs: {{call: {__name__}._pair, args: {{a: 3}}}}\n")
        cfg = confarg.load(_CallLayers, argv=[], env={}, files=[base, over])
        assert cfg.p == _CallPoint(a=1, b=1)
        assert cfg.xs == [3, 3]


def _shout(name: str, punct: str = ".") -> str:
    return name.upper() + punct


def _f(a: int = 0, b: int = 0) -> tuple[int, int]:
    return (a, b)


def _g(a: int = 0) -> int:
    return a


def _make() -> Callable[..., Any]:
    return _f


def _takes_labels(labels: dict[str, str]) -> dict[str, str]:
    return labels


class _Hold:
    def __init__(self, x: int = 0) -> None:
        self.x = x

    def __call__(self, p: int = 0) -> tuple[int, int]:
        return (self.x, p)


class _Scaler:
    def __init__(self, k: int = 1) -> None:
        self.k = k

    def scale(self, k: int) -> int:
        return self.k * k


@dataclass
class _Job:
    kind: str = "batch"
    retries: int = 0


@dataclass
class _Task:
    retries: int = 0


@dataclass
class _SubTask(_Task):
    extra: int = 0
    notes: dict[str, str] = dataclasses.field(default_factory=dict)


@dataclass
class _HoldsCall:
    call: str = ""
    n: int = 0


@dataclass
class _TypeLayers:
    job: _Job = dataclasses.field(default_factory=_Job)
    task: _Task = dataclasses.field(default_factory=_Task)
    tasks: list[_Task] = dataclasses.field(default_factory=list)
    labels: dict[str, str] = dataclasses.field(default_factory=dict)
    held: _HoldsCall = dataclasses.field(default_factory=_HoldsCall)
    extra: Any = None
    fn: Callable[..., Any] = _shout
    maybe: Callable[..., Any] | None = None
    n: int = 0
    name: str = f"{__name__}._shout"


def _layered(tmp_path, *layers: str, **opts: Any) -> _TypeLayers:
    files = []
    for i, text in enumerate(layers):
        files.append(tmp_path / f"layer{i}.yaml")
        files[-1].write_text(text)
    return confarg.load(_TypeLayers, argv=[], env={}, files=files, **opts)


class TestTheTypeDecidesWhetherAKeyReplaces:
    """A key replaces what lower layers set only where construction reads it as a new value (BUG-232).

    The merge decided by the key alone, so a union tag or a ``call`` key the type holds as
    data dropped the lower layers' keys, and the openers a Callable reads other than ``call``
    merged key by key with the spec below them (BUG-231).
    """

    def test_a_tag_a_field_owns_refines(self, tmp_path) -> None:
        """A struct field spelled like a custom tag is a field: the lower layers' keys stay."""
        cfg = _layered(tmp_path, "job: {kind: batch, retries: 3}\n", "job: {kind: stream}\n", union_tag="kind")
        assert cfg.job == _Job(kind="stream", retries=3)

    def test_a_tag_key_in_a_dict_field_refines(self, tmp_path) -> None:
        """A ``dict`` field holds ``class`` as data."""
        cfg = _layered(tmp_path, "labels: {team: ml, tier: gold}\n", "labels: {class: confidential}\n")
        assert cfg.labels == {"team": "ml", "tier": "gold", "class": "confidential"}

    def test_a_call_key_in_a_dict_field_refines(self, tmp_path) -> None:
        """A ``dict`` field holds ``call`` as data too: the cost BUG-190's rule had there is gone."""
        cfg = _layered(tmp_path, "labels: {team: ml}\n", "labels: {call: me}\n")
        assert cfg.labels == {"team": "ml", "call": "me"}

    def test_a_call_key_a_member_owns_refines(self, tmp_path) -> None:
        """A struct with a member named ``call`` keeps its other fields."""
        cfg = _layered(tmp_path, "held: {n: 3}\n", "held: {call: me}\n")
        assert cfg.held == _HoldsCall(call="me", n=3)

    def test_a_tag_still_replaces_a_struct(self, tmp_path) -> None:
        """Where the key is the tag, the new class takes none of the old one's fields."""
        cfg = _layered(tmp_path, "task: {retries: 3}\n", f"task: {{class: {__name__}._SubTask, extra: 1}}\n")
        assert cfg.task == _SubTask(retries=0, extra=1)

    def test_a_tag_replaces_a_list_element(self, tmp_path) -> None:
        """An index patch carrying the tag replaces the element, as it would the field."""
        cfg = _layered(tmp_path, "tasks: [{retries: 3}]\n", f"tasks: {{'0': {{class: {__name__}._SubTask}}}}\n")
        assert cfg.tasks == [_SubTask()]

    def test_a_class_spec_replaces_what_an_any_field_held(self, tmp_path) -> None:
        """An ``Any`` node reads ``class:`` as a spec (FEAT-42), so the lower data is not its fields."""
        cfg = _layered(tmp_path, "extra: {a: 1, b: 2}\n", f"extra: {{class: {__name__}._Hold, x: 2}}\n")
        assert isinstance(cfg.extra, _Hold)
        assert cfg.extra.x == 2

    def test_a_bind_replaces_what_an_any_field_held(self, tmp_path) -> None:
        """So does ``bind:``, which an ``Any`` node reads since FEAT-42."""
        assert _layered(tmp_path, "extra: {a: 1, b: 2}\n", f"extra: {{bind: {__name__}._g}}\n").extra is _g

    @pytest.mark.parametrize("field", ["fn", "maybe"])
    @pytest.mark.parametrize(
        "lower",
        [
            f"{{bind: {__name__}._f, args: {{a: 1}}}}",
            f"{{bind: {__name__}._f, args: {{a: 1, b: 2}}}}",
            f"{{call: {__name__}._make}}",
            f"{{class: {__name__}._Hold, x: 1}}",
        ],
    )
    def test_a_bind_replaces_the_spec_below(self, tmp_path, field: str, lower: str) -> None:
        """BUG-231: the lower spec's arguments do not follow the new target."""
        cfg = _layered(tmp_path, f"{field}: {lower}\n", f"{field}: {{bind: {__name__}._g}}\n")
        assert getattr(cfg, field)() == 0

    def test_a_class_replaces_the_spec_below(self, tmp_path) -> None:
        """A ``class:`` over a ``bind:`` takes none of its arguments."""
        cfg = _layered(tmp_path, f"fn: {{bind: {__name__}._f, args: {{a: 1}}}}\n", f"fn: {{class: {__name__}._Hold}}\n")
        assert cfg.fn(5) == (0, 5)

    def test_a_classfn_replaces_the_spec_below(self, tmp_path) -> None:
        """Nor does a ``classfn:``."""
        lower = f"fn: {{class: {__name__}._Hold, x: 7}}\n"
        cfg = _layered(tmp_path, lower, f"fn: {{classfn: {__name__}._Scaler.scale, k: 2}}\n")
        assert cfg.fn(3) == 6

    def test_args_still_refine_the_spec_below(self, tmp_path) -> None:
        """A layer holding only ``args`` patches the target's arguments."""
        cfg = _layered(tmp_path, f"fn: {{bind: {__name__}._f, args: {{a: 1, b: 2}}}}\n", "fn: {args: {b: 5}}\n")
        assert cfg.fn() == (1, 5)

    def test_a_path_through_a_bind_refines_its_target(self, tmp_path) -> None:
        """``bind: {x: 5}`` holds no opener: it refines the nested target, it names none."""
        lower = f"fn: {{bind: {{class: {__name__}._Hold, x: 1}}, args: {{p: 2}}}}\n"
        assert _layered(tmp_path, lower, "fn: {bind: {x: 5}}\n").fn() == (5, 2)

    def test_a_path_through_a_call_refines_its_target(self, tmp_path) -> None:
        """The same through ``call:``, which replaced the whole spec with ``{call: {k: 3}}``."""
        lower = f"n: {{call: {{classfn: {__name__}._Scaler.scale, k: 1}}, args: {{k: 2}}}}\n"
        assert _layered(tmp_path, lower, "n: {call: {k: 3}}\n").n == 6

    def test_a_subclass_the_tag_names_types_its_fields(self, tmp_path) -> None:
        """Below a struct, the fields are those of the class the lower layer's tag named."""
        lower = f"task: {{class: {__name__}._SubTask, notes: {{a: x}}}}\n"
        cfg = _layered(tmp_path, lower, "task: {notes: {class: y}}\n")
        assert cfg.task == _SubTask(notes={"a": "x", "class": "y"})

    def test_a_spec_in_an_any_field_refines_its_fields(self, tmp_path) -> None:
        """A layer naming no class refines the spec an ``Any`` node holds below it."""
        cfg = _layered(tmp_path, f"extra: {{class: {__name__}._Hold, x: 1}}\n", "extra: {x: 2}\n")
        assert isinstance(cfg.extra, _Hold)
        assert cfg.extra.x == 2

    def test_a_value_an_any_field_holds_is_any_too(self, tmp_path) -> None:
        """Below an ``Any`` holding no opener, every value reads openers in turn."""
        cfg = _layered(tmp_path, "extra: {inner: {a: 1}}\n", f"extra: {{inner: {{bind: {__name__}._g}}}}\n")
        assert cfg.extra == {"inner": _g}

    def test_a_target_that_does_not_import_leaves_its_args_to_the_shape(self, tmp_path) -> None:
        """Its parameters cannot be read, so its arguments merge key by key, and construction reports the name."""
        lower = tmp_path / "a.yaml"
        lower.write_text("fn: {bind: nowhere.f, args: {a: 1}}\n")
        upper = tmp_path / "b.yaml"
        upper.write_text("fn: {args: {b: 2}}\n")
        merged = confarg.merge(_TypeLayers, argv=[], env={}, files=[lower, upper])
        assert merged == {"fn": {"bind": "nowhere.f", "args": {"a": 1, "b": 2}}}

    def test_args_below_a_target_are_typed_by_its_signature(self, tmp_path) -> None:
        """A ``dict`` parameter under ``args`` holds ``class`` as data, as a ``dict`` field does."""
        lower = f"fn: {{bind: {__name__}._takes_labels, args: {{labels: {{team: ml}}}}}}\n"
        cfg = _layered(tmp_path, lower, "fn: {args: {labels: {class: x}}}\n")
        assert cfg.fn() == {"team": "ml", "class": "x"}


class TestALowerShorthandOpensUnderTheArgumentsAbove:
    """A bare string a Callable reads is ``{bind: <string>}``, so a higher layer's ``args`` refine it (BUG-232)."""

    @pytest.mark.parametrize("field", ["fn", "maybe"])
    def test_args_refine_the_shorthand_below(self, tmp_path, field: str) -> None:
        """The target the lower layer named stays."""
        cfg = _layered(tmp_path, f"{field}: {__name__}._shout\n", f"{field}: {{args: {{punct: '!'}}}}\n")
        assert getattr(cfg, field)("hi") == "HI!"

    def test_merge_writes_the_opened_spec(self, tmp_path) -> None:
        """``merge()`` returns the dict form, which ``dump_file`` writes and reads back."""
        lower = tmp_path / "a.yaml"
        lower.write_text(f"fn: {__name__}._shout\n")
        upper = tmp_path / "b.yaml"
        upper.write_text("fn: {args: {punct: '!'}}\n")
        merged = confarg.merge(_TypeLayers, argv=[], env={}, files=[lower, upper])
        assert merged == {"fn": {"bind": f"{__name__}._shout", "args": {"punct": "!"}}}

    def test_an_opener_above_replaces_the_shorthand(self, tmp_path) -> None:
        """A higher layer naming its own target does not refine the one below."""
        assert _layered(tmp_path, f"fn: {__name__}._shout\n", f"fn: {{bind: {__name__}._g}}\n").fn() == 0

    def test_an_expression_opens_too(self, tmp_path) -> None:
        """Whatever the expression yields, ``{bind: <it>}`` with no argument is the same spec."""
        cfg = _layered(tmp_path, "fn: ${name}\n", "fn: {args: {punct: '!'}}\n")
        assert cfg.fn("hi") == "HI!"

    def test_a_string_in_an_any_field_is_text(self, tmp_path) -> None:
        """An ``Any`` node reads a bare string as text (FEAT-42), so the dict above replaces it."""
        assert _layered(tmp_path, "extra: some.path\n", "extra: {a: 1}\n").extra == {"a": 1}
