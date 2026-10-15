# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for source merge priority: CLI > env > config, partial merge, collection index override."""

from __future__ import annotations

import dataclasses
import enum
import json
import re
from collections.abc import Callable  # noqa: TC003  # the dataclasses below are read at runtime
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, NamedTuple

if TYPE_CHECKING:
    from pathlib import Path

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
# Config-file append: __append__
# ---------------------------------------------------------------------------


class TestConfigFileAppendSyntax:
    """``__append__`` in a config file appends to a list instead of replacing it."""

    def test_yaml_append_to_base_list(self, loader: ConfargLoader, tmp_yaml) -> None:
        """``users: {__append__: [...]}`` in a YAML file appends to the list from another file."""
        WithList = make_target("users", list[str], default_factory=list)
        base = tmp_yaml("users: [alice, bob]\n", "base.yaml")
        derived = tmp_yaml("users: {__append__: [frankenstein]}\n", "derived.yaml")
        result = loader.load(WithList, argv=[], env={}, files=[base, derived])
        assert result.users == ["alice", "bob", "frankenstein"]

    def test_yaml_append_no_base(self, loader: ConfargLoader, tmp_yaml) -> None:
        """An append with no prior list creates the list from scratch."""
        WithList = make_target("users", list[str], default_factory=list)
        path = tmp_yaml("users: {__append__: [alice, bob]}\n")
        result = loader.load(WithList, argv=[], env={}, files=[path])
        assert result.users == ["alice", "bob"]

    def test_yaml_append_then_cli_append(self, tmp_yaml) -> None:
        """A file's ``__append__`` and CLI --users+ both append — CLI append is vanilla-only."""
        WithList = make_target("users", list[str], default_factory=list)
        base = tmp_yaml("users: [alice]\n", "base.yaml")
        derived = tmp_yaml("users: {__append__: [bob]}\n", "derived.yaml")
        result = confarg.load(WithList, argv=["--users+", "carol"], env={}, files=[base, derived])
        assert result.users == ["alice", "bob", "carol"]

    def test_yaml_append_scalar(self, loader: ConfargLoader, tmp_yaml) -> None:
        """``__append__: single_value`` (scalar, not a list) appends it as one element."""
        WithList = make_target("users", list[str], default_factory=list)
        base = tmp_yaml("users: [alice]\n", "base.yaml")
        derived = tmp_yaml("users: {__append__: bob}\n", "derived.yaml")
        result = loader.load(WithList, argv=[], env={}, files=[base, derived])
        assert result.users == ["alice", "bob"]

    def test_yaml_multiple_files_each_append(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Three files each append; all items accumulate in order."""
        WithList = make_target("users", list[str], default_factory=list)
        f1 = tmp_yaml("users: {__append__: [alice]}\n", "f1.yaml")
        f2 = tmp_yaml("users: {__append__: [bob]}\n", "f2.yaml")
        f3 = tmp_yaml("users: {__append__: [carol]}\n", "f3.yaml")
        result = loader.load(WithList, argv=[], env={}, files=[f1, f2, f3])
        assert result.users == ["alice", "bob", "carol"]

    def test_yaml_nested_key_append(self, loader: ConfargLoader, tmp_yaml) -> None:
        """``__append__`` works inside a nested dict (nested struct field)."""

        @dataclass
        class Inner:
            items: list[int]

        Target = make_target("inner", Inner)
        base = tmp_yaml("inner:\n  items: [1, 2]\n", "base.yaml")
        derived = tmp_yaml("inner:\n  items: {__append__: [3]}\n", "derived.yaml")
        result = loader.load(Target, argv=[], env={}, files=[base, derived])
        assert result.inner.items == [1, 2, 3]

    def test_yaml_include_chain_append(self, loader: ConfargLoader, tmp_path) -> None:
        """An append in a derived file with __include__ appends after the included list."""
        base = tmp_path / "base.yaml"
        base.write_text("users: [alice, bob]\n")
        derived = tmp_path / "derived.yaml"
        derived.write_text("__include__: ./base.yaml\nusers: {__append__: [frankenstein]}\n")
        WithList = make_target("users", list[str], default_factory=list)
        result = loader.load(WithList, argv=[], env={}, files=[derived])
        assert result.users == ["alice", "bob", "frankenstein"]

    def test_json_append(self, loader: ConfargLoader, tmp_json) -> None:
        """An append is spelled ``{"__append__": [...]}`` in a JSON file."""
        WithList = make_target("items", list[int], default_factory=list)
        base = tmp_json('{"items": [1, 2]}', "base.json")
        derived = tmp_json('{"items": {"__append__": [3, 4]}}', "derived.json")
        result = loader.load(WithList, argv=[], env={}, files=[base, derived])
        assert result.items == [1, 2, 3, 4]

    def test_toml_append_quoted_key(self, loader: ConfargLoader, tmp_toml) -> None:
        """An append is spelled with an ``__append__`` key in a TOML table."""
        WithList = make_target("items", list[int], default_factory=list)
        base = tmp_toml("items = [1, 2]\n", "base.toml")
        derived = tmp_toml("[items]\n__append__ = [3, 4]\n", "derived.toml")
        result = loader.load(WithList, argv=[], env={}, files=[base, derived])
        assert result.items == [1, 2, 3, 4]

    def test_yaml_append_dict_item(self, loader: ConfargLoader, tmp_yaml) -> None:
        """``__append__`` with a dict value appends that dict as a single list element."""

        @dataclass
        class Server:
            host: str
            port: int

        Target = make_target("servers", list[Server])
        base = tmp_yaml("servers:\n  - host: a\n    port: 1\n", "base.yaml")
        derived = tmp_yaml("servers:\n  __append__:\n    host: b\n    port: 2\n", "derived.yaml")
        result = loader.load(Target, argv=[], env={}, files=[base, derived])
        assert len(result.servers) == 2
        assert result.servers[0].host == "a"
        assert result.servers[1].host == "b"
        assert result.servers[1].port == 2


# ---------------------------------------------------------------------------
# Config file deletion: __unset__ and __delete__
# ---------------------------------------------------------------------------


class TestConfigFileDeleteSyntax:
    """A node delete (``__unset__``) and an index delete (``__delete__``) in YAML/TOML/JSON config files."""

    def test_delete_field_resets_to_default(self, loader: ConfargLoader, tmp_yaml) -> None:
        """``name: {__unset__: true}`` in a derived file removes the field set in the base file."""
        base = tmp_yaml("name: from_base\n", "base.yaml")
        derived = tmp_yaml("name: {__unset__: true}\n", "derived.yaml")
        result = loader.load(WithDefaults, argv=[], env={}, files=[base, derived])
        assert result.name == "default"

    def test_delete_required_field_raises(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Deleting a required field via config file causes MissingFieldError."""
        base = tmp_yaml("name: cfg\ncount: 5\nrate: 1.0\nverbose: false\n", "base.yaml")
        derived = tmp_yaml("name: {__unset__: true}\n", "derived.yaml")
        with pytest.raises(confarg.exceptions.MissingFieldError):
            loader.load(Flat, argv=[], env={}, files=[base, derived])

    def test_delete_list_index_yaml(self, loader: ConfargLoader, tmp_yaml) -> None:
        """``__delete__: [1]`` removes the element at original index 1 from a list."""
        WithList = make_target("items", list[str], default_factory=list)
        base = tmp_yaml("items:\n  - a\n  - b\n  - c\n", "base.yaml")
        derived = tmp_yaml("items:\n  __delete__: [1]\n", "derived.yaml")
        result = loader.load(WithList, argv=[], env={}, files=[base, derived])
        assert result.items == ["a", "c"]

    def test_delete_multiple_indices_use_original_positions(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Multiple index deletions are applied to original positions simultaneously."""
        WithList = make_target("items", list[str], default_factory=list)
        base = tmp_yaml("items:\n  - a\n  - b\n  - c\n  - d\n", "base.yaml")
        derived = tmp_yaml("items:\n  __delete__: [1, 2]\n", "derived.yaml")
        result = loader.load(WithList, argv=[], env={}, files=[base, derived])
        assert result.items == ["a", "d"]

    def test_delete_list_index_toml(self, loader: ConfargLoader, tmp_toml) -> None:
        """A TOML table spells the index delete with a ``__delete__`` key too."""
        WithList = make_target("items", list[str], default_factory=list)
        base = tmp_toml('items = ["a", "b", "c"]\n', "base.toml")
        derived = tmp_toml("[items]\n__delete__ = [1]\n", "derived.toml")
        result = loader.load(WithList, argv=[], env={}, files=[base, derived])
        assert result.items == ["a", "c"]

    def test_delete_and_append_in_same_file(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Deleting an index and appending a value in a single file works."""
        WithList = make_target("items", list[str], default_factory=list)
        base = tmp_yaml("items:\n  - a\n  - b\n  - c\n", "base.yaml")
        derived = tmp_yaml("items:\n  __delete__: [1]\n  __append__: [d]\n", "derived.yaml")
        result = loader.load(WithList, argv=[], env={}, files=[base, derived])
        assert result.items == ["a", "c", "d"]

    def test_delete_out_of_range_raises(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Deleting an out-of-range index raises ConfargError."""
        WithList = make_target("items", list[str], default_factory=list)
        base = tmp_yaml("items:\n  - a\n  - b\n", "base.yaml")
        derived = tmp_yaml("items:\n  __delete__: [5]\n", "derived.yaml")
        with pytest.raises(confarg.exceptions.ConfargError):
            loader.load(WithList, argv=[], env={}, files=[base, derived])

    def test_delete_field_in_include_chain(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Deletion in the middle of a multi-file include chain is applied correctly."""
        WithList = make_target("items", list[str], default_factory=list)
        base = tmp_yaml("items:\n  - x\n  - y\n  - z\n", "base.yaml")
        mid = tmp_yaml("items:\n  __delete__: [1]\n", "mid.yaml")
        top = tmp_yaml("items:\n  __append__: [w]\n", "top.yaml")
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
        """``__delete__: [-1]`` deletes the last element."""
        WithList = make_target("items", list[str], default_factory=list)
        base = tmp_yaml("items:\n  - a\n  - b\n  - c\n", "base.yaml")
        derived = tmp_yaml("items:\n  __delete__: [-1]\n", "derived.yaml")
        result = loader.load(WithList, argv=[], env={}, files=[base, derived])
        assert result.items == ["a", "b"]

    @pytest.mark.parametrize(
        ("derived", "expected"),
        [
            pytest.param("items: {__unset__: true, __append__: [x]}\n", ["x"], id="append"),
            pytest.param("items: {__unset__: true, '0': x}\n", ["x"], id="index-patch"),
        ],
    )
    def test_op_beside_a_node_delete_applies_to_nothing_below(
        self,
        loader: ConfargLoader,
        tmp_yaml,
        derived: str,
        expected: list[str],
    ) -> None:
        """An op beside ``__unset__`` applies to nothing below, as one after ``--items-`` does (BUG-116)."""
        WithList = make_target("items", list[str], default_factory=list)
        base = tmp_yaml("items:\n  - a\n  - b\n", "base.yaml")
        top = tmp_yaml(derived, "derived.yaml")
        assert loader.load(WithList, argv=[], env={}, files=[base, top]).items == expected

    def test_index_delete_beside_a_node_delete_has_no_base(
        self,
        loader: ConfargLoader,
        tmp_yaml,
    ) -> None:
        """``__delete__`` beside ``__unset__`` fails as ``--items- --items.0-`` does (BUG-116)."""
        WithList = make_target("items", list[str], default_factory=list)
        base = tmp_yaml("items:\n  - a\n  - b\n", "base.yaml")
        top = tmp_yaml("items: {__unset__: true, __delete__: [0]}\n", "derived.yaml")
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


class TestAListItemReadsTheOps:
    """A dict standing in a file's list reads the merge ops as every other dict of the file does (BUG-237).

    It has no layer below it, so it reads as a document merged over nothing: a delete in it
    deletes nothing and ends there. Only an item beside an include read them, through the merge
    of the include's siblings.
    """

    @pytest.mark.parametrize(
        ("item", "expected"),
        [
            pytest.param("{j: 9, k: {__unset__: true}}", _Item(j=9), id="key-delete"),
            pytest.param("{__unset__: true, k: 4}", _Item(k=4), id="node-delete-beside-keys"),
            pytest.param("{tags: {__append__: [b]}}", _Item(tags=["b"]), id="append"),
        ],
    )
    def test_item_reads_the_ops(self, tmp_yaml, item: str, expected: _Item) -> None:
        """A reserved op key in a list item is the op it spells."""
        path = tmp_yaml(f"rows:\n  - {item}\n")
        assert confarg.load(_Items, argv=[], env={}, files=[path]).rows == [expected]

    def test_item_reads_it_as_the_same_item_beside_an_include(self, tmp_yaml) -> None:
        """Inline or beside an include, the item's delete leaves ``k`` out."""
        tmp_yaml("k: 4\nj: 9\n", "row.yaml")
        flat = tmp_yaml("rows:\n  - {j: 9, k: {__unset__: true}}\n", "flat.yaml")
        inc = tmp_yaml("rows:\n  - {__include__: row.yaml, k: {__unset__: true}}\n", "inc.yaml")
        assert (
            confarg.load(_Items, argv=[], env={}, files=[flat]).rows
            == confarg.load(_Items, argv=[], env={}, files=[inc]).rows
            == [_Item(k=0, j=9)]
        )

    def test_item_of_a_nested_list_reads_it(self, tmp_yaml) -> None:
        """An item two lists deep reads the ops too."""
        path = tmp_yaml("grid:\n  - - {k: {__unset__: true}, tags: {__append__: [x]}}\n")
        assert confarg.load(_Items, argv=[], env={}, files=[path]).grid == [[_Item(tags=["x"])]]

    @pytest.mark.parametrize(
        "spelling",
        [
            pytest.param("rows:\n  - {__unset__: true}\n", id="item"),
            pytest.param("grid:\n  - - {__unset__: true}\n", id="nested-item"),
            pytest.param("rows: {__append__: [{__unset__: true}]}\n", id="appended-item"),
            pytest.param("rows: {__append__: {__unset__: true}}\n", id="single-appended-item"),
        ],
    )
    def test_a_bare_delete_as_an_item_is_refused(self, tmp_yaml, spelling: str) -> None:
        """An item that is a bare node delete would delete nothing, and dropping it would drop an item silently."""
        path = tmp_yaml(spelling)
        with pytest.raises(confarg.exceptions.InvalidConfigFileError, match="a list item has no layer below it"):
            confarg.merge(_Items, argv=[], env={}, files=[path])

    def test_a_single_appended_item_drops_its_deletes(self, tmp_yaml) -> None:
        """An item appended alone is an item too: the delete beside its keys has nothing below it."""
        path = tmp_yaml("rows: {__append__: {__unset__: true, k: 4, j: {__unset__: true}}}\n")
        assert confarg.merge(_Items, argv=[], env={}, files=[path]) == {"rows": {ListOp.APPEND: {"k": 4}}}


@dataclass
class _Ops:
    name: str = "dflt"
    data: dict[str, Any] = dataclasses.field(default_factory=dict)
    anything: Any = None
    xs: list[int] = dataclasses.field(default_factory=list)
    rows: list[_Item] = dataclasses.field(default_factory=list)
    t: tuple[int, int] = (0, 0)


def _load_ops(tmp_yaml, *texts: str, **kw: Any) -> _Ops:
    """Load *texts* as files, lowest first, over no argv and no environment unless *kw* says otherwise."""
    files = [tmp_yaml(text, f"f{i}.yaml") for i, text in enumerate(texts)]
    kw.setdefault("argv", [])
    kw.setdefault("env", {})
    return confarg.load(_Ops, files=files, **kw)


class TestAFileSpellsAnOpInItsValue:
    """A file spells a merge op as a reserved key of the value at its path; every other key is data (FEAT-43)."""

    @pytest.mark.parametrize("key", ["xs+", "name-", "0-", "c++", "a--"])
    def test_a_suffixed_key_is_data(self, tmp_yaml, key: str) -> None:
        """A key ending in ``+`` or ``-`` is a key of the dict or the ``Any`` holding it."""
        cfg = _load_ops(tmp_yaml, f"data: {{'{key}': 1}}\nanything: {{'{key}': 1}}\n")
        assert cfg.data == cfg.anything == {key: 1}

    def test_the_old_shorthand_is_an_unknown_field_of_a_struct(self, tmp_yaml) -> None:
        """A struct refuses ``xs+`` as the unknown field it is, as it would a misspelled one."""
        with pytest.raises(confarg.exceptions.TypeCoercionError, match=re.escape("Unknown field(s) ['xs+']")):
            _load_ops(tmp_yaml, "xs+: [1]\n")

    def test_unset_deletes_the_node_below(self, tmp_yaml) -> None:
        """``name: {__unset__: true}`` leaves the field to its default, whatever the file below said."""
        assert _load_ops(tmp_yaml, "name: low\n", "name: {__unset__: true}\n").name == "dflt"

    def test_unset_beside_keys_replaces_the_node(self, tmp_yaml) -> None:
        """Nothing below, then the keys beside the delete: the lower dict's keys are gone."""
        assert _load_ops(tmp_yaml, "data: {a: 1, b: 2}\n", "data: {__unset__: true, c: 3}\n").data == {"c": 3}

    @pytest.mark.parametrize("value", ["false", "null", "1", "'true'", "[true]"])
    def test_unset_holds_true_only(self, tmp_yaml, value: str) -> None:
        """A delete has no meaning to guess from ``false`` or anything else but ``true``."""
        with pytest.raises(confarg.exceptions.InvalidConfigFileError, match="it must be true"):
            _load_ops(tmp_yaml, f"name: {{__unset__: {value}}}\n")

    def test_unset_beside_a_base_is_refused(self, tmp_yaml) -> None:
        """Both say what lies below the node: two bases."""
        with pytest.raises(confarg.exceptions.InvalidConfigFileError, match="'__base__' beside it"):
            _load_ops(tmp_yaml, "xs: {__unset__: true, __base__: [1]}\n")

    def test_unset_as_a_base_is_refused(self, tmp_yaml) -> None:
        """A base is a list: the delete below the ops is written beside them, which is its one spelling."""
        with pytest.raises(confarg.exceptions.InvalidConfigFileError, match="'__base__' holds a list"):
            _load_ops(tmp_yaml, "xs: {__base__: {__unset__: true}, __append__: [1]}\n")

    @pytest.mark.parametrize(
        "top",
        [
            pytest.param("__unset__: true\n", id="alone"),
            pytest.param("__unset__: true\nname: x\n", id="beside-keys"),
            pytest.param("__include__: unset.yaml\n", id="included"),
        ],
    )
    def test_a_root_that_deletes_itself_is_refused(self, tmp_yaml, top: str) -> None:
        """A configuration layer is merged over the layers below it and cannot cut them off."""
        tmp_yaml("__unset__: true\n", "unset.yaml")
        with pytest.raises(confarg.exceptions.InvalidConfigFileError, match="at the root of"):
            _load_ops(tmp_yaml, top)

    def test_a_mounted_fragment_may_delete_its_node(self, tmp_yaml) -> None:
        """A fragment's root is the value of the node it is mounted at, which a delete may be."""
        unset = tmp_yaml("__unset__: true\n", "unset.yaml")
        assert _load_ops(tmp_yaml, "name: low\n", argv=["--config.name", str(unset)]).name == "dflt"

    @pytest.mark.parametrize(
        ("argv", "env"),
        [
            pytest.param(["--config.xs+", "unset.yaml"], {}, id="flag"),
            pytest.param([], {"APP_CONFIG__XS+": "unset.yaml"}, id="variable"),
        ],
    )
    def test_an_appended_fragment_that_deletes_is_refused(
        self,
        tmp_yaml,
        tmp_path,
        monkeypatch,
        argv: list[str],
        env: dict[str, str],
    ) -> None:
        """An appended fragment is a list item, which has no layer below it to delete."""
        tmp_yaml("__unset__: true\n", "unset.yaml")
        monkeypatch.chdir(tmp_path)
        with pytest.raises(confarg.exceptions.InvalidConfigFileError, match="a list item has no layer below it"):
            _load_ops(tmp_yaml, argv=argv, env=env, env_prefix="APP_")

    def test_an_index_patch_beside_a_delete_replaces_the_item(self, tmp_yaml) -> None:
        """The old item lies below the patch: the delete drops its keys, then the patch's are written."""
        cfg = _load_ops(tmp_yaml, "rows: [{k: 1, j: 2}, {k: 3}]\n", "rows: {'0': {__unset__: true, k: 5}}\n")
        assert cfg.rows == [_Item(k=5), _Item(k=3)]

    @pytest.mark.parametrize(
        "texts",
        [
            pytest.param(("rows: [{k: 1}]\n", "rows: {'0': {__unset__: true}}\n"), id="over-a-list"),
            pytest.param(("rows: {'0': {__unset__: true}}\n",), id="with-nothing-below"),
            pytest.param(("t: {'0': {__unset__: true}}\n",), id="over-a-tuple-default"),
        ],
    )
    def test_a_bare_delete_at_an_index_is_refused(self, tmp_yaml, texts: tuple[str, ...]) -> None:
        """It would leave nothing in the slot; a list deletes an index by ``__delete__``."""
        with pytest.raises(confarg.exceptions.TypeCoercionError, match=re.escape("A list deletes an index with")):
            _load_ops(tmp_yaml, *texts)

    def test_a_bare_delete_at_a_dict_index_deletes_the_key(self, tmp_yaml) -> None:
        """Under a dict, ``"1"`` is a key like ``a``, and its delete removes it (BUG-174's file side)."""
        cfg = _load_ops(tmp_yaml, "data: {'1': 5, a: 6}\n", "data: {'1': {__unset__: true}}\n")
        assert cfg.data == {"a": 6}

    def test_root_value_beside_a_key_takes_a_delete(self, tmp_yaml) -> None:
        """At a document root, ``__root__`` is a key like any other: its delete cuts off the root value below.

        A key stands beside it because a lone ``__root__`` is unwrapped at a root file (BUG-242).
        """
        files = [
            tmp_yaml("locals: {}\n__root__: {a: 1}\n", "low.yaml"),
            tmp_yaml("locals: {}\n__root__: {__unset__: true, b: 2}\n", "top.yaml"),
        ]
        assert confarg.load(dict[str, int], files=files, argv=[], env={}) == {"b": 2}


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
            _deep_merge({"xs": {ListOp.DELETE: [0]}}, {"xs": {ListOp.DELETE: 1}})

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
class _OverAPin:
    extra: Any = None
    port: int | dict[str, int] = 0
    xs: list[int] = dataclasses.field(default_factory=list)


class TestADictOverAPinReplacesIt:
    """A dict over a lower layer's cast pin replaces it, as it replaces the plain value the pin stands for (BUG-239).

    The pin is a value; the merge read it as one in the override only, and a dict over it was
    merged into it key by key.
    """

    @pytest.mark.parametrize(
        ("field", "upper", "expected"),
        [
            pytest.param("extra", "{a: 1}", {"a": 1}, id="any"),
            pytest.param("port", "{https: 443}", {"https": 443}, id="union-holding-a-dict"),
        ],
    )
    @pytest.mark.parametrize("lower", ["{__cast__: int, __value__: '5'}", "5"], ids=["pin", "plain"])
    def test_a_higher_dict_replaces_it(self, tmp_yaml, field: str, upper: str, expected: Any, lower: str) -> None:
        """The pin's lines build what the plain value's do."""
        a = tmp_yaml(f"{field}: {lower}\n", "a.yaml")
        b = tmp_yaml(f"{field}: {upper}\n", "b.yaml")
        assert getattr(confarg.load(_OverAPin, argv=[], env={}, files=[a, b]), field) == expected

    def test_an_op_over_it_has_nothing_below(self) -> None:
        """An append over a pin replaces it, as over a scalar, and is left for ``build()``."""
        pin = {"__cast__": "int", "__value__": "5"}
        assert _deep_merge({"xs": pin}, {"xs": {ListOp.APPEND: [1]}}) == {"xs": {ListOp.APPEND: [1]}}

    def test_a_sibling_dict_replaces_an_included_pin(self, tmp_yaml) -> None:
        """Within one document, keys beside an include replace the pin it brings rather than joining it."""
        tmp_yaml("extra: {__cast__: int, __value__: '5'}\n", "pin.yaml")
        top = tmp_yaml("__include__: pin.yaml\nextra: {a: 1}\n", "top.yaml")
        assert confarg.load(_OverAPin, argv=[], env={}, files=[top]).extra == {"a": 1}


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


# ---------------------------------------------------------------------------
# Key identity: which keys are the same key is the type's to say (BUG-244)
# ---------------------------------------------------------------------------


class _Hue(enum.Enum):
    RED = 1
    BLUE = 2


class _KeyedPt(NamedTuple):
    x: int = 1
    y: int = 2


@dataclass
class _Keyed:
    d: dict[int, int] = dataclasses.field(default_factory=dict)
    od: dict[int, int] | None = None
    e: dict[_Hue, int] = dataclasses.field(default_factory=dict)
    b: dict[bool, int] = dataclasses.field(default_factory=dict)
    s: dict[str, int] = dataclasses.field(default_factory=dict)
    a: Any = None
    mixed: dict[int, int] | dict[_Hue, int] | None = None
    pt: _KeyedPt = dataclasses.field(default_factory=_KeyedPt)


def _yaml(tmp_path: Path, body: str, name: str = "base.yaml") -> str:
    path = tmp_path / name
    path.write_text(body)
    return str(path)


class TestKeyIdentityIsTheTypes:
    """Two keys are one key when the type reads them as one, whatever spells them (BUG-244)."""

    def test_a_file_key_delete_meets_a_yaml_integer_key(self, tmp_path: Path) -> None:
        """BUG-244's reproduction: a JSON layer's ``"1"`` deletes the YAML ``1``."""
        files = [_yaml(tmp_path, "d: {1: 5, 2: 6}\n"), _yaml(tmp_path, '{"d": {"1": {"__unset__": true}}}', "del.json")]
        assert confarg.load(_Keyed, files=files, argv=[], env={}).d == {2: 6}

    def test_an_argv_key_delete_meets_a_yaml_integer_key(self, tmp_path: Path) -> None:
        """``--d.1-`` deletes the YAML ``1`` of a ``dict[int, int]``."""
        files = [_yaml(tmp_path, "d: {1: 5, 2: 6}\n")]
        assert confarg.merge(_Keyed, files=files, argv=["--d.1-"], env={}) == {"d": {2: 6}}

    def test_a_patch_keeps_the_base_key_and_its_place(self, tmp_path: Path) -> None:
        """``--d.1 9`` refines the YAML ``1`` in place rather than adding ``'1'`` beside it."""
        files = [_yaml(tmp_path, "d: {1: 5, 2: 6}\n")]
        merged = confarg.merge(_Keyed, files=files, argv=["--d.1", "9"], env={})
        assert merged == {"d": {1: 9, 2: 6}}
        assert list(merged["d"]) == [1, 2]

    def test_an_optional_dict_reads_its_one_variant(self, tmp_path: Path) -> None:
        """A union with one non-None variant takes that variant's identity."""
        files = [_yaml(tmp_path, "od: {1: 5, 2: 6}\n")]
        assert confarg.merge(_Keyed, files=files, argv=["--od.1-"], env={}) == {"od": {2: 6}}

    def test_an_enum_key_meets_its_value_spelling(self, tmp_path: Path) -> None:
        """``RED`` and ``1`` are one key of a ``dict[_Hue, int]``, as construction builds both as RED."""
        files = [_yaml(tmp_path, "e: {RED: 5}\n")]
        assert confarg.merge(_Keyed, files=files, argv=["--e.1", "9"], env={}) == {"e": {"RED": 9}}

    def test_a_bool_key_meets_every_spelling_its_coercion_takes(self, tmp_path: Path) -> None:
        """A typed key coerces as construction does, so ``yes`` meets YAML's ``true``."""
        files = [_yaml(tmp_path, "b: {true: 5, false: 6}\n")]
        assert confarg.load(_Keyed, files=files, argv=["--b.yes-"], env={}).b == {False: 6}

    def test_a_key_that_does_not_coerce_meets_by_equality(self, tmp_path: Path) -> None:
        """A YAML integer key under ``dict[str, int]`` coerces to no ``str``, so ``'1'`` does not meet it."""
        files = [_yaml(tmp_path, "s: {1: 5}\n")]
        assert confarg.merge(_Keyed, files=files, argv=["--s.1", "9"], env={}) == {"s": {1: 5, "1": 9}}

    def test_a_namedtuple_position_is_one_key(self, tmp_path: Path) -> None:
        """An index meets the field name a lower layer wrote, which keeps its spelling (Q-1, BUG-244)."""
        files = [_yaml(tmp_path, "pt: {x: 7, y: 8}\n")]
        assert confarg.merge(_Keyed, files=files, argv=["--pt.0", "9"], env={}) == {"pt": {"x": 9, "y": 8}}
        assert confarg.load(_Keyed, files=files, argv=["--pt.0", "9"], env={}).pt == _KeyedPt(9, 8)


class TestKeyIdentityOnAnUntypedNode:
    """With no key type, a string meets a non-string key only as JSON spells that key (BUG-244)."""

    def test_the_index_spelling_meets_an_integer_key(self, tmp_path: Path) -> None:
        """``"1"`` is JSON's spelling of the YAML ``1``, so ``--a.1`` refines it."""
        files = [_yaml(tmp_path, "a: {1: 5, 2: 6}\n")]
        assert confarg.merge(_Keyed, files=files, argv=["--a.1", "9"], env={}) == {"a": {1: "9", 2: 6}}

    def test_another_spelling_of_the_integer_is_another_key(self, tmp_path: Path) -> None:
        """``"01"`` is no spelling JSON writes, so it is a key of its own."""
        files = [_yaml(tmp_path, "a: {1: 5}\n")]
        assert confarg.merge(_Keyed, files=files, argv=["--a.01", "9"], env={}) == {"a": {1: 5, "01": "9"}}

    def test_json_spells_a_bool_and_null_key(self, tmp_path: Path) -> None:
        """``true``, ``null`` and ``1.5`` meet the string JSON writes them as."""
        files = [_yaml(tmp_path, "a: {true: 5, null: 6, 1.5: 7}\n")]
        merged = confarg.merge(
            _Keyed, files=files, argv=["--a.true", "9", "--a.null-"], env={"APP_A__1.5": "8"}, env_prefix="APP_"
        )
        assert merged == {"a": {True: "9", 1.5: "8"}}

    def test_a_spelling_json_does_not_write_is_another_key(self, tmp_path: Path) -> None:
        """``"True"`` is not how JSON writes ``True``, so it stays a key of its own."""
        files = [_yaml(tmp_path, "a: {true: 5}\n")]
        assert confarg.merge(_Keyed, files=files, argv=["--a.True", "9"], env={}) == {"a": {True: 5, "True": "9"}}

    def test_a_union_whose_variants_disagree_reads_the_untyped_rule(self, tmp_path: Path) -> None:
        """``dict[int, int] | dict[_Hue, int]``: the variants disagree, so only JSON's spelling meets."""
        files = [_yaml(tmp_path, "mixed: {1: 5}\n")]
        assert confarg.merge(_Keyed, files=files, argv=["--mixed.1", "9"], env={}) == {"mixed": {1: 9}}


class TestKeyIdentityWithinOneSource:
    """A source's later spelling of a key writes over its earlier one (BUG-244)."""

    def test_a_later_delete_meets_an_earlier_spelling(self) -> None:
        """``--e.RED-`` deletes what ``--e.1`` wrote: ``1`` is RED's value."""
        assert confarg.load(_Keyed, argv=["--e.1", "6", "--e.RED-"], env={}).e == {}

    def test_a_later_write_lands_on_an_earlier_delete(self) -> None:
        """A later value written over an earlier delete of the same key wins."""
        assert confarg.load(_Keyed, argv=["--e.RED-", "--e.1", "6"], env={}).e == {_Hue.RED: 6}

    def test_a_later_write_keeps_the_earlier_spelling(self) -> None:
        """The key the source spelled first is the one it keeps."""
        assert confarg.merge(_Keyed, argv=["--e.1", "6", "--e.RED", "7"], env={}) == {"e": {"1": 7}}

    def test_the_environment_orders_a_delete_first_at_one_key(self) -> None:
        """The environment applies a delete before a value at one path, whatever spells the key."""
        env = {"APP_E__1": "6", "APP_E__RED-": ""}
        assert confarg.load(_Keyed, argv=[], env=env, env_prefix="APP_").e == {_Hue.RED: 6}

    def test_an_included_part_meets_its_sibling(self, tmp_path: Path) -> None:
        """An include's YAML integer key meets the string key written beside the include."""
        _yaml(tmp_path, "d: {1: 5, 2: 6}\n", "inc.yaml")
        (tmp_path / "main.json").write_text('{"__include__": "inc.yaml", "d": {"1": {"__unset__": true}}}')
        assert confarg.load(_Keyed, files=[str(tmp_path / "main.json")], argv=[], env={}).d == {2: 6}
