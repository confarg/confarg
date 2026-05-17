# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for __include__ sub-file inclusion in config files."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import pytest

import confarg
from confarg._files import INCLUDE_KEY, _load_file
from confarg.exceptions import ConfargError, InvalidConfigFileError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
# List-item includes: splicing and substitution
# ---------------------------------------------------------------------------


class TestListItemInclude:
    """Tests for list-item __include__ with splicing and substitution."""

    def test_list_splice_yaml(self, tmp_path: Path) -> None:
        """Test that a YAML list file is spliced into the parent list."""
        write(tmp_path, "extra.yaml", "- auth\n- audit\n")
        write(
            tmp_path,
            "config.yaml",
            "plugins:\n  - core\n  - __include__: ./extra.yaml\n  - debug\n",
        )

        result = _load_file(tmp_path / "config.yaml")
        assert result == {"plugins": ["core", "auth", "audit", "debug"]}

    def test_list_splice_json(self, tmp_path: Path) -> None:
        """Test that a JSON list file is spliced into the parent list."""
        write(tmp_path, "extra.json", '["auth", "audit"]')
        write(
            tmp_path,
            "config.json",
            f'{{"plugins": ["core", {{"{INCLUDE_KEY}": "./extra.json"}}, "debug"]}}',
        )

        result = _load_file(tmp_path / "config.json")
        assert result == {"plugins": ["core", "auth", "audit", "debug"]}

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
        """Test that recursive includes through list files splice correctly."""
        write(tmp_path, "leaf.yaml", "- c\n- d\n")
        write(tmp_path, "middle.yaml", "- a\n- b\n- __include__: ./leaf.yaml\n")
        write(tmp_path, "config.yaml", "items:\n  __include__: ./middle.yaml\n")

        result = _load_file(tmp_path / "config.yaml")
        assert result == {"items": ["a", "b", "c", "d"]}

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

    def test_cli_overrides_included_file(self, tmp_path: Path) -> None:
        """Test that CLI arguments override values from an included file."""
        write(tmp_path, "db.yaml", "host: file_host\nport: 5432\n")
        write(tmp_path, "config.yaml", f"db:\n  {INCLUDE_KEY}: ./db.yaml\nname: myapp\n")

        result = confarg.load(
            AppConfig,
            argv=["--db.host", "cli_host"],
            files=[tmp_path / "config.yaml"],
        )
        assert result.db.host == "cli_host"
        assert result.db.port == 5432
        assert result.name == "myapp"

    def test_env_overrides_included_file(self, tmp_path: Path) -> None:
        """Test that env vars override values from an included file."""
        write(tmp_path, "db.yaml", "host: file_host\nport: 5432\n")
        write(tmp_path, "config.yaml", f"db:\n  {INCLUDE_KEY}: ./db.yaml\n")

        result = confarg.load(
            AppConfig,
            argv=[],
            env={"CONFARG_DB__HOST": "env_host"},
            env_prefix="CONFARG_",
            files=[tmp_path / "config.yaml"],
        )
        assert result.db.host == "env_host"
        assert result.db.port == 5432
