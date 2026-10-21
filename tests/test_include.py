# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for __include__ sub-file inclusion in config files."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from confarg._merge import MergeDict

import pytest

import confarg
from confarg._files import INCLUDE_KEY, Reads
from confarg._files import _load_file as _load_file_in
from confarg.exceptions import ConfargError, InvalidConfigFileError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_file(loc: str | Path) -> MergeDict:
    """Load *loc* as a public call does, with a copy budget of its own."""
    return _load_file_in(loc, reads=Reads())


def write(tmp_path: Path, name: str, content: str) -> Path:
    """Write content to a named file inside tmp_path and return the path."""
    p = tmp_path / name
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# Basic include
# ---------------------------------------------------------------------------


class TestBasicInclude:
    """Tests for basic __include__ functionality."""

    def test_yaml_include_basic(self, tmp_path: Path) -> None:
        """Test that a YAML file includes another YAML file."""
        write(tmp_path, "base.yaml", "port: 5432\nuser: admin\n")
        write(tmp_path, "config.yaml", f"{INCLUDE_KEY}: ./base.yaml\n")

        result = _load_file(tmp_path / "config.yaml")
        assert result == {"port": 5432, "user": "admin"}

    def test_json_include_basic(self, tmp_path: Path) -> None:
        """Test that a JSON file includes another JSON file."""
        write(tmp_path, "base.json", '{"port": 5432, "user": "admin"}')
        write(tmp_path, "config.json", f'{{"{INCLUDE_KEY}": "./base.json"}}')

        result = _load_file(tmp_path / "config.json")
        assert result == {"port": 5432, "user": "admin"}

    def test_toml_include_basic(self, tmp_path: Path) -> None:
        """Test that a TOML file includes another TOML file."""
        write(tmp_path, "base.toml", 'port = 5432\nuser = "admin"\n')
        write(tmp_path, "config.toml", f'{INCLUDE_KEY} = "./base.toml"\n')

        result = _load_file(tmp_path / "config.toml")
        assert result == {"port": 5432, "user": "admin"}

    def test_include_nested_under_key(self, tmp_path: Path) -> None:
        """Test that an included file can be nested under a specific key."""
        write(tmp_path, "db.yaml", "host: localhost\nport: 5432\n")
        write(tmp_path, "config.yaml", f"database:\n  {INCLUDE_KEY}: ./db.yaml\nname: myapp\n")

        result = _load_file(tmp_path / "config.yaml")
        assert result == {"database": {"host": "localhost", "port": 5432}, "name": "myapp"}


# ---------------------------------------------------------------------------
# Sibling keys override included content
# ---------------------------------------------------------------------------


class TestSiblingOverride:
    """Tests that sibling keys override included file content."""

    def test_sibling_wins_over_included(self, tmp_path: Path) -> None:
        """Test that a sibling key overrides the same key from an included file."""
        write(tmp_path, "base.yaml", "host: base_host\nport: 5432\n")
        write(tmp_path, "config.yaml", f"{INCLUDE_KEY}: ./base.yaml\nhost: override_host\n")

        result = _load_file(tmp_path / "config.yaml")
        assert result["host"] == "override_host"
        assert result["port"] == 5432

    def test_included_keys_not_in_siblings_are_present(self, tmp_path: Path) -> None:
        """Test that included keys not in siblings are still present in the result."""
        write(tmp_path, "base.yaml", "host: base_host\nport: 5432\nuser: admin\n")
        write(tmp_path, "config.yaml", f"{INCLUDE_KEY}: ./base.yaml\nport: 9999\n")

        result = _load_file(tmp_path / "config.yaml")
        assert result["user"] == "admin"
        assert result["port"] == 9999
        assert result["host"] == "base_host"

    def test_a_sibling_include_wins_over_included(self, tmp_path: Path) -> None:
        """A sibling that includes a file is the including file's word too, so it wins."""
        write(tmp_path, "base.yaml", "db: {host: base_host, port: 5432}\n")
        write(tmp_path, "db.yaml", "host: db_host\n")
        write(tmp_path, "config.yaml", f"{INCLUDE_KEY}: ./base.yaml\ndb: {{{INCLUDE_KEY}: ./db.yaml}}\n")

        assert _load_file(tmp_path / "config.yaml") == {"db": {"host": "db_host", "port": 5432}}

    def test_a_sibling_include_in_a_list_item_wins_over_included(self, tmp_path: Path) -> None:
        """The same holds for an include with siblings that sits in a list item."""
        write(tmp_path, "base.yaml", "db: {host: base_host, port: 5432}\n")
        write(tmp_path, "db.yaml", "host: db_host\n")
        write(tmp_path, "config.yaml", f"xs:\n  - {INCLUDE_KEY}: ./base.yaml\n    db: {{{INCLUDE_KEY}: ./db.yaml}}\n")

        assert _load_file(tmp_path / "config.yaml") == {"xs": [{"db": {"host": "db_host", "port": 5432}}]}


@dataclass
class _Labelled:
    labels: dict[str, str] = field(default_factory=dict)
    db: DbConfig | None = None


class TestPartsOfAFileMergeByType:
    """The parts of one file merge by the type at their position, as layers do (BUG-232).

    A ``dict`` field holds ``class`` as data, so a part writing it adds an entry rather than
    dropping the entries another part gave.
    """

    def test_a_sibling_refines_the_included_dict(self, tmp_path: Path) -> None:
        """The keys beside an include merge into what it brings in."""
        write(tmp_path, "base.yaml", "labels: {team: ml}\n")
        config = write(tmp_path, "config.yaml", f"{INCLUDE_KEY}: ./base.yaml\nlabels: {{class: x}}\n")
        assert confarg.load(_Labelled, argv=[], env={}, files=[config]).labels == {"team": "ml", "class": "x"}

    def test_a_sibling_refines_an_include_below_the_root(self, tmp_path: Path) -> None:
        """An include inside the field merges by the field's type too."""
        write(tmp_path, "lab.yaml", "team: ml\n")
        config = write(tmp_path, "config.yaml", f"labels: {{{INCLUDE_KEY}: ./lab.yaml, class: x}}\n")
        assert confarg.load(_Labelled, argv=[], env={}, files=[config]).labels == {"team": "ml", "class": "x"}

    def test_a_later_entry_of_an_include_list_refines(self, tmp_path: Path) -> None:
        """So do the entries of an ``__include__`` list."""
        write(tmp_path, "a.yaml", "labels: {team: ml}\n")
        write(tmp_path, "b.yaml", "labels: {class: x}\n")
        config = write(tmp_path, "config.yaml", f"{INCLUDE_KEY}: [./a.yaml, ./b.yaml]\n")
        assert confarg.load(_Labelled, argv=[], env={}, files=[config]).labels == {"team": "ml", "class": "x"}

    def test_a_later_entry_naming_a_class_replaces_the_earlier(self, tmp_path: Path) -> None:
        """Where the type reads the key as the tag, a later entry still starts the node afresh."""
        write(tmp_path, "a.yaml", "host: a\nport: 1\n")
        write(tmp_path, "b.yaml", f"class: {__name__}.DbConfig\nhost: b\n")
        config = write(tmp_path, "config.yaml", f"db: {{{INCLUDE_KEY}: [./a.yaml, ./b.yaml]}}\n")
        assert confarg.load(_Labelled, argv=[], env={}, files=[config]).db == DbConfig(host="b")

    def test_a_mounted_file_refines_by_its_mount_point(self, tmp_path: Path) -> None:
        """A file mounted at the field (``--config.labels``) merges over a lower file by the field's type."""
        base = write(tmp_path, "base.yaml", "labels: {team: ml}\n")
        write(tmp_path, "lab.yaml", "class: x\n")
        argv = ["--config.labels", str(tmp_path / "lab.yaml")]
        assert confarg.load(_Labelled, argv=argv, env={}, files=[base]).labels == {"team": "ml", "class": "x"}


# ---------------------------------------------------------------------------
# Relative path resolution
# ---------------------------------------------------------------------------


class TestRelativePaths:
    """Tests for relative path resolution in __include__."""

    def test_include_resolves_relative_to_including_file(self, tmp_path: Path) -> None:
        """Test that include paths are resolved relative to the including file."""
        subdir = tmp_path / "sub"
        subdir.mkdir()
        write(subdir, "db.yaml", "host: subhost\n")
        write(tmp_path, "config.yaml", "database:\n  __include__: ./sub/db.yaml\n")

        result = _load_file(tmp_path / "config.yaml")
        assert result == {"database": {"host": "subhost"}}

    def test_include_in_subdir_resolves_relative_to_subdir(self, tmp_path: Path) -> None:
        """Test that include paths in a subdirectory are resolved relative to that subdirectory."""
        subdir = tmp_path / "sub"
        subdir.mkdir()
        write(subdir, "db.yaml", "host: subhost\n")
        # config in subdir includes sibling file in subdir
        write(subdir, "config.yaml", f"{INCLUDE_KEY}: ./db.yaml\n")

        result = _load_file(subdir / "config.yaml")
        assert result == {"host": "subhost"}


# ---------------------------------------------------------------------------
# Recursive includes
# ---------------------------------------------------------------------------


class TestRecursiveIncludes:
    """Tests for chained/recursive __include__ directives."""

    def test_recursive_include(self, tmp_path: Path) -> None:
        """Test that chained includes (a→b→c) merge all content correctly."""
        write(tmp_path, "c.yaml", "z: 3\n")
        write(tmp_path, "b.yaml", f"{INCLUDE_KEY}: ./c.yaml\ny: 2\n")
        write(tmp_path, "a.yaml", f"{INCLUDE_KEY}: ./b.yaml\nx: 1\n")

        result = _load_file(tmp_path / "a.yaml")
        assert result == {"x": 1, "y": 2, "z": 3}

    def test_recursive_include_nested_under_key(self, tmp_path: Path) -> None:
        """Test that recursive includes nested under keys work correctly."""
        write(tmp_path, "leaf.yaml", "value: 42\n")
        write(tmp_path, "middle.yaml", f"item:\n  {INCLUDE_KEY}: ./leaf.yaml\n")
        write(tmp_path, "top.yaml", f"section:\n  {INCLUDE_KEY}: ./middle.yaml\n")

        result = _load_file(tmp_path / "top.yaml")
        assert result == {"section": {"item": {"value": 42}}}


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------


class TestCycleDetection:
    """Tests for circular include detection."""

    def test_direct_self_include(self, tmp_path: Path) -> None:
        """Test that a file including itself raises ConfargError."""
        p = write(tmp_path, "self.yaml", f"{INCLUDE_KEY}: ./self.yaml\n")
        with pytest.raises(ConfargError, match=r"[Cc]ircular"):
            _load_file(p)

    def test_indirect_cycle(self, tmp_path: Path) -> None:
        """Test that an indirect cycle (a→b→a) raises ConfargError."""
        write(tmp_path, "a.yaml", f"{INCLUDE_KEY}: ./b.yaml\n")
        write(tmp_path, "b.yaml", f"{INCLUDE_KEY}: ./a.yaml\n")
        with pytest.raises(ConfargError, match=r"[Cc]ircular"):
            _load_file(tmp_path / "a.yaml")


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestErrorCases:
    """Tests for error cases in __include__ processing."""

    def test_non_string_include_value(self, tmp_path: Path) -> None:
        """Test that a non-string __include__ value raises ConfargError."""
        write(tmp_path, "config.yaml", f"{INCLUDE_KEY}: 42\n")
        with pytest.raises(ConfargError, match="path"):
            _load_file(tmp_path / "config.yaml")

    def test_included_file_not_found(self, tmp_path: Path) -> None:
        """Test that a missing included file raises InvalidConfigFileError."""
        write(tmp_path, "config.yaml", f"{INCLUDE_KEY}: ./missing.yaml\n")
        with pytest.raises(InvalidConfigFileError, match="not found"):
            _load_file(tmp_path / "config.yaml")


# ---------------------------------------------------------------------------
# Integration: merge() respects priority ordering
# ---------------------------------------------------------------------------


@dataclass
class DbConfig:
    """Database connection configuration."""

    host: str
    port: int = 5432


@dataclass
class AppConfig:
    """Application configuration with a nested database config."""

    db: DbConfig
    name: str = "default"


# ---------------------------------------------------------------------------
# Pure include — non-dict file types
# ---------------------------------------------------------------------------


class TestPureIncludeNonDict:
    """Tests for __include__ when the included file is not a dict."""

    def test_pure_include_list_file(self, tmp_path: Path) -> None:
        """Test that a list YAML file can be included under a key."""
        write(tmp_path, "hosts.yaml", "- a.com\n- b.com\n")
        write(tmp_path, "config.yaml", "allowed_hosts:\n  __include__: ./hosts.yaml\n")

        result = _load_file(tmp_path / "config.yaml")
        assert result == {"allowed_hosts": ["a.com", "b.com"]}

    def test_pure_include_scalar_yaml(self, tmp_path: Path) -> None:
        """Test that a scalar YAML file can be included under a key."""
        write(tmp_path, "val.yaml", "42\n")
        write(tmp_path, "config.yaml", "timeout:\n  __include__: ./val.yaml\n")

        result = _load_file(tmp_path / "config.yaml")
        assert result == {"timeout": 42}

    def test_pure_include_scalar_json(self, tmp_path: Path) -> None:
        """Test that a top-level scalar JSON include raises ConfargError."""
        write(tmp_path, "val.json", "99")
        write(tmp_path, "config.json", f'{{"{INCLUDE_KEY}": "./val.json"}}')
        # top-level pure include of a scalar must error (root must be dict)
        with pytest.raises(ConfargError):
            _load_file(tmp_path / "config.json")


# ---------------------------------------------------------------------------
# List-item includes: an include contributes one element
# ---------------------------------------------------------------------------


class TestListItemInclude:
    """Tests for list-item __include__: the included content is always one element."""

    def test_list_file_is_one_element_yaml(self, tmp_path: Path) -> None:
        """Test that a YAML list file lands as one element, not spliced (only + splices)."""
        write(tmp_path, "extra.yaml", "- auth\n- audit\n")
        write(
            tmp_path,
            "config.yaml",
            "plugins:\n  - core\n  - __include__: ./extra.yaml\n  - debug\n",
        )

        result = _load_file(tmp_path / "config.yaml")
        assert result == {"plugins": ["core", ["auth", "audit"], "debug"]}

    def test_list_file_is_one_element_json(self, tmp_path: Path) -> None:
        """Test that a JSON list file lands as one element, not spliced (only + splices)."""
        write(tmp_path, "extra.json", '["auth", "audit"]')
        write(
            tmp_path,
            "config.json",
            f'{{"plugins": ["core", {{"{INCLUDE_KEY}": "./extra.json"}}, "debug"]}}',
        )

        result = _load_file(tmp_path / "config.json")
        assert result == {"plugins": ["core", ["auth", "audit"], "debug"]}

    def test_list_item_substitution_dict(self, tmp_path: Path) -> None:
        """Test that a dict file include in a list becomes a single dict element."""
        write(tmp_path, "item.yaml", "name: myitem\nvalue: 1\n")
        write(tmp_path, "config.yaml", "items:\n  - __include__: ./item.yaml\n")

        result = _load_file(tmp_path / "config.yaml")
        assert result == {"items": [{"name": "myitem", "value": 1}]}

    def test_list_item_substitution_scalar(self, tmp_path: Path) -> None:
        """Test that a scalar file include in a list becomes a single scalar element."""
        write(tmp_path, "val.yaml", "hello\n")
        write(tmp_path, "config.yaml", "tags:\n  - first\n  - __include__: ./val.yaml\n")

        result = _load_file(tmp_path / "config.yaml")
        assert result == {"tags": ["first", "hello"]}

    def test_list_item_with_siblings_and_dict_include(self, tmp_path: Path) -> None:
        """Test that siblings override included dict fields in a list item."""
        write(tmp_path, "base.yaml", "x: 1\ny: 2\n")
        write(
            tmp_path,
            "config.yaml",
            "items:\n  - __include__: ./base.yaml\n    y: 99\n",
        )

        result = _load_file(tmp_path / "config.yaml")
        assert result == {"items": [{"x": 1, "y": 99}]}


# ---------------------------------------------------------------------------
# Error: siblings + non-dict include
# ---------------------------------------------------------------------------


class TestSiblingNonDictError:
    """Tests for errors when siblings accompany a non-dict include."""

    def test_dict_context_sibling_with_list_include(self, tmp_path: Path) -> None:
        """Test that sibling keys alongside a list include raise ConfargError."""
        write(tmp_path, "list.yaml", "- a\n- b\n")
        write(tmp_path, "config.yaml", f"section:\n  {INCLUDE_KEY}: ./list.yaml\n  extra: key\n")
        with pytest.raises(ConfargError, match="sibling"):
            _load_file(tmp_path / "config.yaml")

    def test_list_item_sibling_with_list_include(self, tmp_path: Path) -> None:
        """Test that a list item with sibling keys alongside a list include raises ConfargError."""
        write(tmp_path, "list.yaml", "- a\n- b\n")
        write(
            tmp_path,
            "config.yaml",
            "items:\n  - __include__: ./list.yaml\n    extra: key\n",
        )
        with pytest.raises(ConfargError, match="sibling"):
            _load_file(tmp_path / "config.yaml")


# ---------------------------------------------------------------------------
# Recursive includes through lists
# ---------------------------------------------------------------------------


class TestRecursiveThroughLists:
    """Tests for recursive includes that pass through lists."""

    def test_recursive_include_via_list(self, tmp_path: Path) -> None:
        """Test that a list file included inside a list file is resolved, as one element."""
        write(tmp_path, "leaf.yaml", "- c\n- d\n")
        write(tmp_path, "middle.yaml", "- a\n- b\n- __include__: ./leaf.yaml\n")
        write(tmp_path, "config.yaml", "items:\n  __include__: ./middle.yaml\n")

        result = _load_file(tmp_path / "config.yaml")
        assert result == {"items": ["a", "b", ["c", "d"]]}

    def test_splice_items_that_contain_includes(self, tmp_path: Path) -> None:
        """Test that spliced list items that themselves contain includes are resolved."""
        write(tmp_path, "extra.yaml", "value: 42\n")
        write(tmp_path, "items.yaml", "- name: first\n- __include__: ./extra.yaml\n")
        write(tmp_path, "config.yaml", "things:\n  __include__: ./items.yaml\n")

        result = _load_file(tmp_path / "config.yaml")
        assert result == {"things": [{"name": "first"}, {"value": 42}]}


# ---------------------------------------------------------------------------
# Integration: merge() respects priority ordering
# ---------------------------------------------------------------------------


class TestIntegrationPriorityOrdering:
    """Integration tests that merge() respects priority ordering with __include__."""

    def test_cli_overrides_included_file(self, loader, tmp_path: Path) -> None:
        """Test that CLI arguments override values from an included file."""
        write(tmp_path, "db.yaml", "host: file_host\nport: 5432\n")
        write(tmp_path, "config.yaml", f"db:\n  {INCLUDE_KEY}: ./db.yaml\nname: myapp\n")

        result = loader.load(
            AppConfig,
            argv=["--db.host", "cli_host"],
            files=[tmp_path / "config.yaml"],
        )
        assert result.db.host == "cli_host"
        assert result.db.port == 5432
        assert result.name == "myapp"

    def test_env_overrides_included_file(self, loader, tmp_path: Path) -> None:
        """Test that env vars override values from an included file."""
        write(tmp_path, "db.yaml", "host: file_host\nport: 5432\n")
        write(tmp_path, "config.yaml", f"db:\n  {INCLUDE_KEY}: ./db.yaml\n")

        result = loader.load(
            AppConfig,
            argv=[],
            env={"CONFARG_DB__HOST": "env_host"},
            env_prefix="CONFARG_",
            files=[tmp_path / "config.yaml"],
        )
        assert result.db.host == "env_host"
        assert result.db.port == 5432


# ---------------------------------------------------------------------------
# List form: __include__ takes several files, layered in list order
# ---------------------------------------------------------------------------


class TestIncludeList:
    """Tests for a list-valued __include__, where later entries override earlier ones."""

    def test_later_entry_wins_on_shared_keys(self, tmp_path: Path) -> None:
        """Test that the last entry naming a key supplies its value."""
        write(tmp_path, "a.yaml", "host: a_host\nport: 1\n")
        write(tmp_path, "b.yaml", "host: b_host\n")
        write(tmp_path, "config.yaml", f"{INCLUDE_KEY}:\n  - ./a.yaml\n  - ./b.yaml\n")

        assert _load_file(tmp_path / "config.yaml") == {"host": "b_host", "port": 1}

    def test_keys_unique_to_an_earlier_entry_survive(self, tmp_path: Path) -> None:
        """Test that a key only the first entry defines is kept."""
        write(tmp_path, "a.yaml", "host: a_host\nonly_a: 1\n")
        write(tmp_path, "b.yaml", "host: b_host\nonly_b: 2\n")
        write(tmp_path, "config.yaml", f"{INCLUDE_KEY}: [./a.yaml, ./b.yaml]\n")

        assert _load_file(tmp_path / "config.yaml") == {"host": "b_host", "only_a": 1, "only_b": 2}

    def test_nested_dicts_deep_merge_across_entries(self, tmp_path: Path) -> None:
        """Test that nested mappings merge rather than replace wholesale."""
        write(tmp_path, "a.yaml", "db:\n  name: adb\n  pool: 5\n")
        write(tmp_path, "b.yaml", "db:\n  name: bdb\n")
        write(tmp_path, "config.yaml", f"{INCLUDE_KEY}: [./a.yaml, ./b.yaml]\n")

        assert _load_file(tmp_path / "config.yaml") == {"db": {"name": "bdb", "pool": 5}}

    def test_three_entries_fold_left_to_right(self, tmp_path: Path) -> None:
        """Test that entries are applied in order, the last one winning."""
        for name in ("a", "b", "c"):
            write(tmp_path, f"{name}.yaml", f"host: {name}_host\n{name}: 1\n")
        write(tmp_path, "config.yaml", f"{INCLUDE_KEY}: [./a.yaml, ./b.yaml, ./c.yaml]\n")

        result = _load_file(tmp_path / "config.yaml")
        assert result == {"host": "c_host", "a": 1, "b": 1, "c": 1}

    def test_single_entry_list_matches_scalar_form(self, tmp_path: Path) -> None:
        """Test that a one-element list behaves exactly like a plain string include."""
        write(tmp_path, "a.yaml", "host: a_host\n")
        write(tmp_path, "scalar.yaml", f"{INCLUDE_KEY}: ./a.yaml\n")
        write(tmp_path, "listed.yaml", f"{INCLUDE_KEY}: [./a.yaml]\n")

        assert _load_file(tmp_path / "listed.yaml") == _load_file(tmp_path / "scalar.yaml")

    def test_siblings_beat_every_entry(self, tmp_path: Path) -> None:
        """Test that sibling keys override the whole include stack."""
        write(tmp_path, "a.yaml", "host: a_host\nport: 1\n")
        write(tmp_path, "b.yaml", "host: b_host\n")
        write(
            tmp_path,
            "config.yaml",
            f"{INCLUDE_KEY}: [./a.yaml, ./b.yaml]\nhost: sibling_host\n",
        )

        assert _load_file(tmp_path / "config.yaml") == {"host": "sibling_host", "port": 1}

    def test_mixed_formats_in_one_list(self, tmp_path: Path) -> None:
        """Test that a list may mix YAML, JSON and TOML entries."""
        write(tmp_path, "a.yaml", "host: a_host\nport: 1\n")
        write(tmp_path, "b.json", '{"host": "b_host", "extra": true}')
        write(tmp_path, "c.toml", 'host = "c_host"\n')
        write(tmp_path, "config.yaml", f"{INCLUDE_KEY}: [./a.yaml, ./b.json, ./c.toml]\n")

        result = _load_file(tmp_path / "config.yaml")
        assert result == {"host": "c_host", "port": 1, "extra": True}

    def test_append_composes_across_entries(self, tmp_path: Path) -> None:
        """Test that a later entry's ``__append__`` appends to a list an earlier entry defined."""
        write(tmp_path, "a.yaml", "plugins:\n  - core\n")
        write(tmp_path, "b.yaml", "plugins:\n  __append__: [auth]\n")
        write(tmp_path, "config.yaml", f"{INCLUDE_KEY}: [./a.yaml, ./b.yaml]\n")

        assert _load_file(tmp_path / "config.yaml") == {"plugins": ["core", "auth"]}

    def test_per_entry_options_are_honoured(self, tmp_path: Path) -> None:
        """Test that each entry keeps its own per-format options."""
        write(tmp_path, "hosts.csv", "a.com\nb.com\n")
        write(tmp_path, "base.yaml", "allowed: []\n")
        write(
            tmp_path,
            "config.yaml",
            f"allowed:\n  {INCLUDE_KEY}:\n    - path: ./hosts.csv\n      header: false\n",
        )

        assert _load_file(tmp_path / "config.yaml") == {"allowed": ["a.com", "b.com"]}

    def test_same_file_twice_is_not_a_cycle(self, tmp_path: Path) -> None:
        """Test that repeating a file in one list is legal — entries are layers, not nesting."""
        write(tmp_path, "a.yaml", "host: a_host\n")
        write(tmp_path, "config.yaml", f"{INCLUDE_KEY}: [./a.yaml, ./a.yaml]\n")

        assert _load_file(tmp_path / "config.yaml") == {"host": "a_host"}

    def test_genuine_cycle_still_raises(self, tmp_path: Path) -> None:
        """Test that a cycle reached through the list form is still detected."""
        write(tmp_path, "c1.yaml", f"{INCLUDE_KEY}: [./c2.yaml]\n")
        write(tmp_path, "c2.yaml", f"{INCLUDE_KEY}: [./c1.yaml]\n")

        with pytest.raises(ConfargError, match="Circular include"):
            _load_file(tmp_path / "c1.yaml")

    def test_the_cycle_error_names_the_resolved_file(self, tmp_path: Path) -> None:
        """The reported location is the absolute file, not the path the includes walked to it.

        A relative entry reached through a parent step would otherwise read as
        ``.../env/../c1.yaml``, and each further level of nesting would add another step.
        """
        (tmp_path / "env").mkdir()
        write(tmp_path, "c1.yaml", f"{INCLUDE_KEY}: ./env/c2.yaml")
        write(tmp_path, "env/c2.yaml", f"{INCLUDE_KEY}: ../c1.yaml")

        with pytest.raises(ConfargError, match="Circular include") as excinfo:
            _load_file(tmp_path / "c1.yaml")
        reported = str(excinfo.value).removeprefix("Circular include detected: ")
        assert reported == str(tmp_path / "c1.yaml")

    def test_missing_entry_reports_the_file(self, tmp_path: Path) -> None:
        """Test that a missing file in the list raises with its path."""
        write(tmp_path, "a.yaml", "host: a_host\n")
        write(tmp_path, "config.yaml", f"{INCLUDE_KEY}: [./a.yaml, ./missing.yaml]\n")

        with pytest.raises(InvalidConfigFileError, match="not found"):
            _load_file(tmp_path / "config.yaml")


# ---------------------------------------------------------------------------
# List form: CSV entries replace rather than merge
# ---------------------------------------------------------------------------


class TestIncludeListCsvReplaces:
    """A CSV/TSV entry contributes a value, so it replaces what earlier entries produced."""

    def test_later_csv_replaces_earlier_csv_columns_wholesale(self, tmp_path: Path) -> None:
        """Test that a later column-oriented CSV replaces the earlier one, disjoint columns included."""
        write(tmp_path, "x.csv", "ts,value\n01,1\n02,2\n")
        write(tmp_path, "y.csv", "ts,weight\n03,9\n")
        write(
            tmp_path,
            "config.yaml",
            f"m:\n  {INCLUDE_KEY}:\n"
            f"    - {{path: ./x.csv, orient: columns}}\n"
            f"    - {{path: ./y.csv, orient: columns}}\n",
        )

        # 'value' is gone: the second CSV replaces the first rather than merging per column.
        assert _load_file(tmp_path / "config.yaml") == {"m": {"ts": ["03"], "weight": ["9"]}}

    def test_later_csv_replaces_an_earlier_mapping(self, tmp_path: Path) -> None:
        """Test that a CSV entry discards a mapping laid down by an earlier entry."""
        write(tmp_path, "base.yaml", "ts: [old]\nnote: hi\n")
        write(tmp_path, "x.csv", "ts,value\n01,1\n")
        write(
            tmp_path,
            "config.yaml",
            f"m:\n  {INCLUDE_KEY}:\n    - ./base.yaml\n    - {{path: ./x.csv, orient: columns}}\n",
        )

        assert _load_file(tmp_path / "config.yaml") == {"m": {"ts": ["01"], "value": ["1"]}}

    def test_row_oriented_csv_entries_replace(self, tmp_path: Path) -> None:
        """Test that the last row-oriented CSV supplies the rows."""
        write(tmp_path, "a.csv", "name\nalice\n")
        write(tmp_path, "b.csv", "name\nbob\n")
        write(tmp_path, "config.yaml", f"names:\n  {INCLUDE_KEY}: [./a.csv, ./b.csv]\n")

        assert _load_file(tmp_path / "config.yaml") == {"names": ["bob"]}

    def test_mapping_after_a_csv_still_deep_merges(self, tmp_path: Path) -> None:
        """Test that a mapping entry following a CSV merges into it."""
        write(tmp_path, "x.csv", "ts,value\n01,1\n")
        write(tmp_path, "extra.yaml", "note: hi\n")
        write(
            tmp_path,
            "config.yaml",
            f"m:\n  {INCLUDE_KEY}:\n    - {{path: ./x.csv, orient: columns}}\n    - ./extra.yaml\n",
        )

        result = _load_file(tmp_path / "config.yaml")
        assert result == {"m": {"ts": ["01"], "value": ["1"], "note": "hi"}}


# ---------------------------------------------------------------------------
# List form: list-item position and errors
# ---------------------------------------------------------------------------


class TestIncludeListInListItem:
    """In a list item the entries fold to one value, which is then the one element."""

    def test_entries_fold_to_one_element(self, tmp_path: Path) -> None:
        """Test that list files layer into one list, which becomes one element."""
        write(tmp_path, "l1.yaml", "- auth\n- audit\n")
        write(tmp_path, "l2.yaml", "- debug\n")
        write(
            tmp_path,
            "config.yaml",
            f"plugins:\n  - core\n  - {INCLUDE_KEY}: [./l1.yaml, ./l2.yaml]\n",
        )

        assert _load_file(tmp_path / "config.yaml") == {"plugins": ["core", ["debug"]]}

    def test_dict_entries_fold_to_one_element(self, tmp_path: Path) -> None:
        """Test that mapping entries merge into a single appended element."""
        write(tmp_path, "m1.yaml", "x: 1\ny: 2\n")
        write(tmp_path, "m2.yaml", "y: 99\n")
        write(
            tmp_path,
            "config.yaml",
            f"items:\n  - {INCLUDE_KEY}: [./m1.yaml, ./m2.yaml]\n",
        )

        assert _load_file(tmp_path / "config.yaml") == {"items": [{"x": 1, "y": 99}]}

    def test_siblings_override_the_folded_element(self, tmp_path: Path) -> None:
        """Test that sibling keys in a list item still beat the whole stack."""
        write(tmp_path, "m1.yaml", "x: 1\ny: 2\n")
        write(tmp_path, "m2.yaml", "y: 99\n")
        write(
            tmp_path,
            "config.yaml",
            f"items:\n  - {INCLUDE_KEY}: [./m1.yaml, ./m2.yaml]\n    y: 7\n",
        )

        assert _load_file(tmp_path / "config.yaml") == {"items": [{"x": 1, "y": 7}]}


class TestIncludeListErrors:
    """Error cases specific to the list form."""

    def test_empty_list_raises(self, tmp_path: Path) -> None:
        """Test that an empty include list raises rather than silently erasing the node."""
        write(tmp_path, "config.yaml", f"{INCLUDE_KEY}: []\n")

        with pytest.raises(ConfargError, match="at least one path"):
            _load_file(tmp_path / "config.yaml")

    def test_nested_list_raises(self, tmp_path: Path) -> None:
        """Test that a list nested inside the include list raises."""
        write(tmp_path, "config.yaml", f"{INCLUDE_KEY}:\n  - [./a.yaml]\n")

        with pytest.raises(ConfargError, match="path"):
            _load_file(tmp_path / "config.yaml")

    def test_non_string_entry_raises(self, tmp_path: Path) -> None:
        """Test that a non-string, non-dict entry raises."""
        write(tmp_path, "config.yaml", f"{INCLUDE_KEY}: [./a.yaml, 42]\n")

        with pytest.raises(ConfargError, match="path"):
            _load_file(tmp_path / "config.yaml")

    def test_entry_dict_without_path_raises(self, tmp_path: Path) -> None:
        """Test that a dict entry missing 'path' raises."""
        write(tmp_path, "config.yaml", f"{INCLUDE_KEY}:\n  - orient: rows\n")

        with pytest.raises(ConfargError, match="'path'"):
            _load_file(tmp_path / "config.yaml")

    def test_list_with_siblings_and_non_dict_result_raises(self, tmp_path: Path) -> None:
        """Test that sibling keys alongside a list-producing stack still raise."""
        write(tmp_path, "l1.yaml", "- a\n")
        write(tmp_path, "l2.yaml", "- b\n")
        write(
            tmp_path,
            "config.yaml",
            f"{INCLUDE_KEY}: [./l1.yaml, ./l2.yaml]\nextra: 1\n",
        )

        with pytest.raises(ConfargError, match="sibling"):
            _load_file(tmp_path / "config.yaml")


# ---------------------------------------------------------------------------
# Remote documents
# ---------------------------------------------------------------------------


class TestRemoteIncludes:
    """A document loaded over a URL resolves its includes inside its own origin."""

    def test_relative_include_resolves_against_the_served_url(self, tmp_path: Path, tmp_http: str) -> None:
        """A sibling name in a served document is fetched from the same directory."""
        write(tmp_path, "db.yaml", "db:\n  host: served-db\n")
        write(tmp_path, "config.yaml", f"{INCLUDE_KEY}: ./db.yaml\n")

        assert _load_file(f"{tmp_http}/config.yaml") == {"db": {"host": "served-db"}}

    def test_relative_include_climbs_with_dot_dot(self, tmp_path: Path, tmp_http: str) -> None:
        """A parent step inside the origin is resolved, not refused."""
        write(tmp_path, "base.yaml", "name: from-base\n")
        (tmp_path / "env").mkdir()
        write(tmp_path, "env/config.yaml", f"{INCLUDE_KEY}: ../base.yaml\n")

        assert _load_file(f"{tmp_http}/env/config.yaml") == {"name": "from-base"}

    def test_a_served_document_may_not_include_a_local_path(self, tmp_path: Path, tmp_http: str) -> None:
        """An absolute local location from a remote document is refused."""
        secret = write(tmp_path, "secret.yaml", "password: hunter2\n")
        write(tmp_path, "config.yaml", f"{INCLUDE_KEY}: {secret.as_uri()}\n")

        with pytest.raises(InvalidConfigFileError, match="may not include"):
            _load_file(f"{tmp_http}/config.yaml")

    def test_a_served_document_may_not_include_another_host(self, tmp_path: Path, tmp_http: str) -> None:
        """Leaving the origin for another host is refused."""
        write(tmp_path, "config.yaml", f"{INCLUDE_KEY}: http://evil.test/x.yaml\n")

        with pytest.raises(InvalidConfigFileError, match="may not include"):
            _load_file(f"{tmp_http}/config.yaml")

    def test_a_local_file_may_include_a_served_document(self, tmp_path: Path, tmp_http: str) -> None:
        """The reverse direction is allowed: a local author names any location."""
        write(tmp_path, "db.yaml", "db:\n  host: served-db\n")
        write(tmp_path, "config.yaml", f"{INCLUDE_KEY}: {tmp_http}/db.yaml\n")

        assert _load_file(tmp_path / "config.yaml") == {"db": {"host": "served-db"}}

    def test_a_cycle_between_served_documents_raises(self, tmp_path: Path, tmp_http: str) -> None:
        """Cycle detection works on URL identity as it does on resolved paths."""
        write(tmp_path, "c1.yaml", f"{INCLUDE_KEY}: ./c2.yaml\n")
        write(tmp_path, "c2.yaml", f"{INCLUDE_KEY}: ./c1.yaml\n")

        with pytest.raises(ConfargError, match="Circular include"):
            _load_file(f"{tmp_http}/c1.yaml")

    def test_naming_one_served_document_twice_is_not_a_cycle(self, tmp_path: Path, tmp_http: str) -> None:
        """Sibling entries are layers, not nesting, over URLs too."""
        write(tmp_path, "one.yaml", "a: 1\n")
        write(tmp_path, "config.yaml", f"{INCLUDE_KEY}: [./one.yaml, ./one.yaml]\n")

        assert _load_file(f"{tmp_http}/config.yaml") == {"a": 1}

    def test_a_missing_served_include_reports_the_url(self, tmp_path: Path, tmp_http: str) -> None:
        """The error names the location that could not be read."""
        write(tmp_path, "config.yaml", f"{INCLUDE_KEY}: ./missing.yaml\n")

        with pytest.raises(InvalidConfigFileError, match=r"missing\.yaml"):
            _load_file(f"{tmp_http}/config.yaml")

    def test_an_extensionless_include_is_rejected(self, tmp_path: Path, tmp_http: str) -> None:
        """Format comes from the suffix, so an endpoint without one cannot be included."""
        write(tmp_path, "config.yaml", f"{INCLUDE_KEY}: ./endpoint\n")

        with pytest.raises(InvalidConfigFileError, match="no file extension"):
            _load_file(f"{tmp_http}/config.yaml")

    def test_a_served_csv_include_still_replaces(self, tmp_path: Path, tmp_http: str) -> None:
        """A data file over the wire keeps its replace-rather-than-merge semantics."""
        write(tmp_path, "rows.csv", "host\na.com\nb.com\n")
        write(tmp_path, "config.yaml", f"hosts:\n  {INCLUDE_KEY}: ./rows.csv\n")

        assert _load_file(f"{tmp_http}/config.yaml") == {"hosts": ["a.com", "b.com"]}

    def test_a_file_url_document_includes_relatively(self, tmp_path: Path) -> None:
        """file:// is a scheme like any other, and resolves relatives the same way."""
        write(tmp_path, "db.yaml", "db:\n  host: via-file-url\n")
        write(tmp_path, "config.yaml", f"{INCLUDE_KEY}: ./db.yaml\n")

        url = (tmp_path / "config.yaml").as_uri()
        assert _load_file(url) == {"db": {"host": "via-file-url"}}


# ---------------------------------------------------------------------------
# Deletes: one document's parts, then the files below it
# ---------------------------------------------------------------------------


@dataclass
class _Sec:
    a: int = 1
    b: int = 2


@dataclass
class _Row:
    k: int = 0
    j: int = 0


@dataclass
class _Layered:
    name: str = "default"
    other: int = 0
    sec: _Sec = field(default_factory=_Sec)
    rows: list[_Row] = field(default_factory=list)
    m: dict[str, list[str]] = field(default_factory=dict)


def _load_over_base(tmp_path: Path, top: str, *, base: bool = True) -> _Layered:
    """Load ``top.yaml`` over ``base.yaml``, with every fragment the delete tests include written."""
    write(tmp_path, "base.yaml", "name: file\nsec: {a: 5}\nm: {note: [hi]}\n")
    write(tmp_path, "inc.yaml", "name: inc\n")
    write(tmp_path, "oth.yaml", "other: 3\n")
    write(tmp_path, "del.yaml", "name: {__unset__: true}\n")
    write(tmp_path, "chain.yaml", f"{INCLUDE_KEY}: ./inc.yaml\nname: {{__unset__: true}}\n")
    write(tmp_path, "seca.yaml", "a: 7\n")
    write(tmp_path, "delsec.yaml", "sec: {__unset__: true}\n")
    write(tmp_path, "secb.yaml", "sec: {b: 3}\n")
    write(tmp_path, "row.yaml", "k: 4\nj: 9\n")
    write(tmp_path, "delnote.yaml", "note: {__unset__: true}\n")
    write(tmp_path, "unset.yaml", "__unset__: true\n")
    write(tmp_path, "b3.yaml", "b: 3\n")
    write(tmp_path, "x.csv", "ts\n01\n")
    write(tmp_path, "top.yaml", top)
    files = [tmp_path / "base.yaml", tmp_path / "top.yaml"] if base else [tmp_path / "top.yaml"]
    return confarg.load(_Layered, argv=[], files=files, env={})


class TestDeleteBesideAnInclude:
    """A delete in any part of a document deletes in the files below it too (BUG-227).

    The parts were merged as layers, so a delete was spent on the part below it and dropped,
    and the lower file's value came back.
    """

    @pytest.mark.parametrize(
        "top",
        [
            pytest.param(f"{INCLUDE_KEY}: ./inc.yaml\nname: {{__unset__: true}}\n", id="sibling-met-in-the-include"),
            pytest.param(f"{INCLUDE_KEY}: ./oth.yaml\nname: {{__unset__: true}}\n", id="sibling-unmet-in-the-include"),
            pytest.param(f"{INCLUDE_KEY}: [./inc.yaml, ./del.yaml]\n", id="later-entry"),
            pytest.param(f"{INCLUDE_KEY}: ./del.yaml\nother: 1\n", id="included-beside-a-sibling"),
            pytest.param(f"{INCLUDE_KEY}: [./del.yaml, ./oth.yaml]\n", id="earlier-entry"),
            pytest.param(f"{INCLUDE_KEY}: ./chain.yaml\n", id="included-file-with-a-sibling-delete"),
            pytest.param(f"{INCLUDE_KEY}: ./chain.yaml\nother: 1\n", id="same-beside-a-sibling"),
            pytest.param(f"name:\n  {INCLUDE_KEY}: ./unset.yaml\n", id="included-fragment"),
            pytest.param(f"name:\n  {INCLUDE_KEY}: [./inc.yaml, ./unset.yaml]\n", id="later-fragment-entry"),
        ],
    )
    def test_delete_reaches_the_file_below(self, tmp_path: Path, top: str) -> None:
        """Wherever the delete stands in the document, the lower file's ``name`` is gone, as in a flat one."""
        assert _load_over_base(tmp_path, top).name == "default"

    def test_nested_sibling_delete_reaches_the_file_below(self, tmp_path: Path) -> None:
        """A delete beside an include at a nested node deletes the lower file's key there."""
        top = f"sec:\n  {INCLUDE_KEY}: ./seca.yaml\n  a: {{__unset__: true}}\n"
        assert _load_over_base(tmp_path, top).sec == _Sec(a=1, b=2)

    def test_later_value_wins_over_an_earlier_entrys_delete(self, tmp_path: Path) -> None:
        """A later entry setting the key overrides the delete before it, as a later key does in one file."""
        assert _load_over_base(tmp_path, f"{INCLUDE_KEY}: [./del.yaml, ./inc.yaml]\n").name == "inc"

    @pytest.mark.parametrize(
        "top",
        [
            pytest.param("sec: {__unset__: true, b: 3}\n", id="flat"),
            pytest.param(f"{INCLUDE_KEY}: [./delsec.yaml, ./secb.yaml]\n", id="entries"),
            pytest.param(f"{INCLUDE_KEY}: ./delsec.yaml\nsec: {{b: 3}}\n", id="sibling"),
            pytest.param(f"sec:\n  {INCLUDE_KEY}: ./unset.yaml\n  b: 3\n", id="fragment-sibling"),
            pytest.param(f"sec:\n  {INCLUDE_KEY}: [./unset.yaml, ./b3.yaml]\n", id="fragment-entries"),
            pytest.param(f"sec:\n  __unset__: true\n  {INCLUDE_KEY}: ./b3.yaml\n", id="beside-the-include"),
        ],
    )
    def test_dict_written_over_a_delete_cuts_the_files_below_off(self, tmp_path: Path, top: str) -> None:
        """A dict after a whole-field delete of one document starts from nothing, its parts split or not."""
        assert _load_over_base(tmp_path, top).sec == _Sec(a=1, b=3)

    def test_delete_that_met_its_key_needs_nothing_below(self, tmp_path: Path) -> None:
        """A delete the included part gave a key to is done: with no file below it does not leak (BUG-98)."""
        top = f"sec:\n  {INCLUDE_KEY}: ./seca.yaml\n  a: {{__unset__: true}}\n"
        assert _load_over_base(tmp_path, top, base=False).sec == _Sec(a=1, b=2)

    @pytest.mark.parametrize(
        ("delete", "expected"),
        [pytest.param("k", _Row(k=0, j=9), id="met"), pytest.param("zz", _Row(k=4, j=9), id="unmet")],
    )
    def test_delete_in_a_list_item_has_nothing_below(self, tmp_path: Path, delete: str, expected: _Row) -> None:
        """A list replaces the layers below whole, so a delete in one of its items ends there."""
        top = f"rows:\n  - {INCLUDE_KEY}: ./row.yaml\n    {delete}: {{__unset__: true}}\n"
        assert _load_over_base(tmp_path, top).rows == [expected]

    def test_csv_header_names_columns_only(self, tmp_path: Path) -> None:
        """A data file's header is data: a column whose name ends in ``-`` deletes nothing (Q-7)."""
        write(tmp_path, "cols.csv", "note-\nx\n")
        top = f"m:\n  {INCLUDE_KEY}: {{path: ./cols.csv, orient: columns}}\n  note: [hi]\n"
        assert _load_over_base(tmp_path, top, base=False).m == {"note-": ["x"], "note": ["hi"]}

    def test_csv_entry_replaces_an_earlier_entrys_delete(self, tmp_path: Path) -> None:
        """A data entry replaces what the earlier entries said, their deletes included."""
        top = f"m:\n  {INCLUDE_KEY}:\n    - ./delnote.yaml\n    - {{path: ./x.csv, orient: columns}}\n"
        assert _load_over_base(tmp_path, top).m == {"note": ["hi"], "ts": ["01"]}
