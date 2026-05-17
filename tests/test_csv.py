# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for CSV/TSV file loading via __include__ and append mode."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import pytest

import confarg
from confarg._files import INCLUDE_KEY, _load_csv, _load_file
from confarg.exceptions import ConfargError, InvalidConfigFileError


def write(tmp_path: Path, name: str, content: str) -> Path:
    """Write content to a file inside tmp_path and return its Path."""
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# _load_csv — rows orient (default)
# ---------------------------------------------------------------------------


class TestLoadCsvRows:
    """Tests for _load_csv with default rows orient."""

    def test_single_column_returns_flat_list(self, tmp_path: Path) -> None:
        """Test that a single-column CSV returns a flat list."""
        p = write(tmp_path, "hosts.csv", "host\na.com\nb.com\n")
        assert _load_csv(p) == ["a.com", "b.com"]

    def test_single_column_no_trailing_newline(self, tmp_path: Path) -> None:
        """Test that a single-column CSV without trailing newline still works."""
        p = write(tmp_path, "hosts.csv", "host\na.com\nb.com")
        assert _load_csv(p) == ["a.com", "b.com"]

    def test_multi_column_returns_list_of_dicts(self, tmp_path: Path) -> None:
        """Test that a multi-column CSV returns a list of dicts."""
        p = write(tmp_path, "users.csv", "name,role\nalice,admin\nbob,user\n")
        assert _load_csv(p) == [
            {"name": "alice", "role": "admin"},
            {"name": "bob", "role": "user"},
        ]

    def test_empty_file_returns_empty_list(self, tmp_path: Path) -> None:
        """Test that an empty CSV file returns an empty list."""
        p = write(tmp_path, "empty.csv", "")
        assert _load_csv(p) == []

    def test_header_only_returns_empty_list(self, tmp_path: Path) -> None:
        """Test that a CSV with only a header row returns an empty list."""
        p = write(tmp_path, "hdr.csv", "name,role\n")
        assert _load_csv(p) == []

    def test_file_not_found(self, tmp_path: Path) -> None:
        """Test that a missing CSV file raises InvalidConfigFileError."""
        with pytest.raises(InvalidConfigFileError, match="not found"):
            _load_csv(tmp_path / "missing.csv")

    def test_bom_stripped(self, tmp_path: Path) -> None:
        """Test that a UTF-8 BOM is stripped from the CSV header."""
        p = tmp_path / "bom.csv"
        p.write_bytes(b"\xef\xbb\xbfcol\nval\n")  # UTF-8 BOM
        assert _load_csv(p) == ["val"]


# ---------------------------------------------------------------------------
# _load_csv — columns orient
# ---------------------------------------------------------------------------


class TestLoadCsvColumns:
    """Tests for _load_csv with columns orient."""

    def test_multi_column_returns_dict_of_lists(self, tmp_path: Path) -> None:
        """Test that a multi-column CSV returns a dict of lists."""
        p = write(tmp_path, "data.csv", "ts,value\n2024-01,1.0\n2024-02,2.0\n")
        assert _load_csv(p, orient="columns") == {
            "ts": ["2024-01", "2024-02"],
            "value": ["1.0", "2.0"],
        }

    def test_single_column_returns_dict_with_one_key(self, tmp_path: Path) -> None:
        """Test that a single-column CSV with columns orient returns a dict with one key."""
        p = write(tmp_path, "tags.csv", "tag\nalpha\nbeta\n")
        assert _load_csv(p, orient="columns") == {"tag": ["alpha", "beta"]}

    def test_header_only_returns_dict_empty_lists(self, tmp_path: Path) -> None:
        """Test that a header-only CSV with columns orient returns empty lists."""
        p = write(tmp_path, "hdr.csv", "a,b\n")
        assert _load_csv(p, orient="columns") == {"a": [], "b": []}

    def test_empty_file_returns_empty_dict(self, tmp_path: Path) -> None:
        """Test that an empty CSV with columns orient returns an empty dict."""
        p = write(tmp_path, "empty.csv", "")
        assert _load_csv(p, orient="columns") == {}


# ---------------------------------------------------------------------------
# _load_csv — header=False
# ---------------------------------------------------------------------------


class TestLoadCsvNoHeader:
    """Tests for _load_csv with header=False."""

    def test_rows_single_column_no_header(self, tmp_path: Path) -> None:
        """Test that a single-column CSV without header returns a flat list."""
        p = write(tmp_path, "hosts.csv", "a.com\nb.com\nc.com\n")
        assert _load_csv(p, header=False) == ["a.com", "b.com", "c.com"]

    def test_rows_multi_column_no_header_returns_list_of_lists(self, tmp_path: Path) -> None:
        """Test that a multi-column CSV without header returns a list of lists."""
        p = write(tmp_path, "data.csv", "alice,admin\nbob,user\n")
        assert _load_csv(p, header=False) == [["alice", "admin"], ["bob", "user"]]

    def test_columns_no_header_uses_positional_keys(self, tmp_path: Path) -> None:
        """Test that columns orient without header uses positional integer keys."""
        p = write(tmp_path, "data.csv", "1,2\n3,4\n")
        assert _load_csv(p, orient="columns", header=False) == {"0": ["1", "3"], "1": ["2", "4"]}

    def test_columns_single_column_no_header(self, tmp_path: Path) -> None:
        """Test that a single-column CSV without header uses positional key '0'."""
        p = write(tmp_path, "col.csv", "a\nb\nc\n")
        assert _load_csv(p, orient="columns", header=False) == {"0": ["a", "b", "c"]}

    def test_raw_ignores_header_option(self, tmp_path: Path) -> None:
        """Test that raw orient ignores the header option."""
        p = write(tmp_path, "data.csv", "x,y\n1,2\n")
        assert _load_csv(p, orient="raw", header=False) == [["x", "y"], ["1", "2"]]
        assert _load_csv(p, orient="raw", header=True) == [["x", "y"], ["1", "2"]]

    def test_empty_file_no_header_rows(self, tmp_path: Path) -> None:
        """Test that an empty file without header returns an empty list."""
        p = write(tmp_path, "empty.csv", "")
        assert _load_csv(p, header=False) == []

    def test_empty_file_no_header_columns(self, tmp_path: Path) -> None:
        """Test that an empty file without header and columns orient returns empty dict."""
        p = write(tmp_path, "empty.csv", "")
        assert _load_csv(p, orient="columns", header=False) == {}

    def test_include_dict_form_header_false(self, tmp_path: Path) -> None:
        """Test that the __include__ dict form with header: false works correctly."""
        write(tmp_path, "hosts.csv", "a.com\nb.com\n")
        write(
            tmp_path,
            "config.yaml",
            f"allowed:\n  {INCLUDE_KEY}:\n    path: ./hosts.csv\n    header: false\n",
        )
        result = _load_file(tmp_path / "config.yaml")
        assert result == {"allowed": ["a.com", "b.com"]}

    def test_header_option_non_bool_raises(self, tmp_path: Path) -> None:
        """Test that a non-boolean header option raises ConfargError."""
        write(tmp_path, "x.csv", "val\na\n")
        write(tmp_path, "config.yaml", f"x:\n  {INCLUDE_KEY}:\n    path: ./x.csv\n    header: maybe\n")
        with pytest.raises(ConfargError, match="boolean"):
            _load_file(tmp_path / "config.yaml")


# ---------------------------------------------------------------------------
# _load_csv — raw orient
# ---------------------------------------------------------------------------


class TestLoadCsvRaw:
    """Tests for _load_csv with raw orient."""

    def test_raw_includes_all_rows(self, tmp_path: Path) -> None:
        """Test that raw orient includes all rows as lists."""
        p = write(tmp_path, "matrix.csv", "1,2,3\n4,5,6\n")
        assert _load_csv(p, orient="raw") == [["1", "2", "3"], ["4", "5", "6"]]

    def test_raw_first_row_is_data_not_header(self, tmp_path: Path) -> None:
        """Test that raw orient treats the first row as data, not a header."""
        p = write(tmp_path, "data.csv", "name,age\nalice,30\n")
        result = _load_csv(p, orient="raw")
        assert result[0] == ["name", "age"]
        assert result[1] == ["alice", "30"]

    def test_raw_single_column(self, tmp_path: Path) -> None:
        """Test that raw orient with a single column returns list of single-element lists."""
        p = write(tmp_path, "col.csv", "a\nb\nc\n")
        assert _load_csv(p, orient="raw") == [["a"], ["b"], ["c"]]

    def test_empty_file_returns_empty_list(self, tmp_path: Path) -> None:
        """Test that an empty file with raw orient returns an empty list."""
        p = write(tmp_path, "empty.csv", "")
        assert _load_csv(p, orient="raw") == []


# ---------------------------------------------------------------------------
# _load_csv — TSV (tab delimiter)
# ---------------------------------------------------------------------------


class TestLoadTsv:
    """Tests for _load_csv with tab delimiter (TSV)."""

    def test_tsv_rows(self, tmp_path: Path) -> None:
        """Test that a TSV file is loaded correctly in rows orient."""
        p = write(tmp_path, "data.tsv", "name\trole\nalice\tadmin\n")
        assert _load_csv(p, delimiter="\t") == [{"name": "alice", "role": "admin"}]

    def test_tsv_columns(self, tmp_path: Path) -> None:
        """Test that a TSV file is loaded correctly in columns orient."""
        p = write(tmp_path, "data.tsv", "x\ty\n1\t2\n3\t4\n")
        assert _load_csv(p, orient="columns", delimiter="\t") == {
            "x": ["1", "3"],
            "y": ["2", "4"],
        }


# ---------------------------------------------------------------------------
# _load_csv — invalid orient
# ---------------------------------------------------------------------------


class TestLoadCsvBadOrient:
    """Tests for _load_csv with an invalid orient argument."""

    def test_unknown_orient_raises(self, tmp_path: Path) -> None:
        """Test that an unknown orient value raises ConfargError."""
        p = write(tmp_path, "data.csv", "a,b\n1,2\n")
        with pytest.raises(ConfargError, match="orient"):
            _load_csv(p, orient="diagonal")


# ---------------------------------------------------------------------------
# __include__ with dict form and orient option
# ---------------------------------------------------------------------------


class TestIncludeDictForm:
    """Tests for __include__ with dict form and orient option."""

    def test_plain_string_form_still_works(self, tmp_path: Path) -> None:
        """Test that the plain string __include__ form still works."""
        write(tmp_path, "hosts.csv", "host\na.com\nb.com\n")
        write(tmp_path, "config.yaml", f"allowed:\n  {INCLUDE_KEY}: ./hosts.csv\n")
        result = _load_file(tmp_path / "config.yaml")
        assert result == {"allowed": ["a.com", "b.com"]}

    def test_dict_form_rows_orient(self, tmp_path: Path) -> None:
        """Test that dict form with orient: rows loads a list of dicts."""
        write(tmp_path, "users.csv", "name,role\nalice,admin\n")
        write(
            tmp_path,
            "config.yaml",
            f"users:\n  {INCLUDE_KEY}:\n    path: ./users.csv\n    orient: rows\n",
        )
        result = _load_file(tmp_path / "config.yaml")
        assert result == {"users": [{"name": "alice", "role": "admin"}]}

    def test_dict_form_columns_orient(self, tmp_path: Path) -> None:
        """Test that dict form with orient: columns loads a dict of lists."""
        write(tmp_path, "metrics.csv", "ts,value\n2024-01,1\n2024-02,2\n")
        write(
            tmp_path,
            "config.yaml",
            f"metrics:\n  {INCLUDE_KEY}:\n    path: ./metrics.csv\n    orient: columns\n",
        )
        result = _load_file(tmp_path / "config.yaml")
        assert result == {"metrics": {"ts": ["2024-01", "2024-02"], "value": ["1", "2"]}}

    def test_dict_form_raw_orient(self, tmp_path: Path) -> None:
        """Test that dict form with orient: raw loads a list of lists."""
        write(tmp_path, "grid.csv", "1,2\n3,4\n")
        write(
            tmp_path,
            "config.yaml",
            f"matrix:\n  {INCLUDE_KEY}:\n    path: ./grid.csv\n    orient: raw\n",
        )
        result = _load_file(tmp_path / "config.yaml")
        assert result == {"matrix": [["1", "2"], ["3", "4"]]}

    def test_dict_form_without_orient_defaults_to_rows(self, tmp_path: Path) -> None:
        """Test that dict form without orient defaults to rows orient."""
        write(tmp_path, "users.csv", "name,role\nalice,admin\n")
        write(
            tmp_path,
            "config.yaml",
            f"users:\n  {INCLUDE_KEY}:\n    path: ./users.csv\n",
        )
        result = _load_file(tmp_path / "config.yaml")
        assert result == {"users": [{"name": "alice", "role": "admin"}]}

    def test_dict_form_missing_path_raises(self, tmp_path: Path) -> None:
        """Test that dict form without a 'path' key raises ConfargError."""
        write(tmp_path, "config.yaml", f"x:\n  {INCLUDE_KEY}:\n    orient: rows\n")
        with pytest.raises(ConfargError, match="'path'"):
            _load_file(tmp_path / "config.yaml")

    def test_dict_form_path_not_string_raises(self, tmp_path: Path) -> None:
        """Test that a non-string 'path' value raises ConfargError."""
        write(tmp_path, "config.yaml", f"x:\n  {INCLUDE_KEY}:\n    path: 42\n")
        with pytest.raises(ConfargError, match="'path'"):
            _load_file(tmp_path / "config.yaml")


# ---------------------------------------------------------------------------
# Integration: confarg.load() with CSV via __include__
# ---------------------------------------------------------------------------


@dataclass
class AppConfig:
    """Application configuration with a list of allowed hosts."""

    allowed_hosts: list[str] = field(default_factory=list)
    name: str = "default"


class TestIntegrationCsvLoad:
    """Integration tests for confarg.load() with CSV via __include__."""

    def test_csv_list_loaded_via_include(self, tmp_path: Path) -> None:
        """Test that a CSV list is loaded into the config via __include__."""
        write(tmp_path, "hosts.csv", "host\na.com\nb.com\n")
        write(
            tmp_path,
            "config.yaml",
            f"allowed_hosts:\n  {INCLUDE_KEY}: ./hosts.csv\nname: myapp\n",
        )
        result = confarg.load(AppConfig, args=[], files=[tmp_path / "config.yaml"])
        assert result.allowed_hosts == ["a.com", "b.com"]
        assert result.name == "myapp"

    def test_cli_overrides_csv_value(self, tmp_path: Path) -> None:
        """Test that CLI arguments override values loaded from a CSV file."""
        write(tmp_path, "hosts.csv", "host\na.com\n")
        write(
            tmp_path,
            "config.yaml",
            f"name: from_file\nallowed_hosts:\n  {INCLUDE_KEY}: ./hosts.csv\n",
        )
        result = confarg.load(
            AppConfig,
            args=["--name", "from_cli"],
            files=[tmp_path / "config.yaml"],
        )
        assert result.name == "from_cli"


# ---------------------------------------------------------------------------
# Append mode: --config.field+ ./data.csv
# Append mode wraps a list file as a single element (consistent with YAML/JSON
# list files). A single-column CSV ["a", "b"] appended to list[list[str]]
# gives [["a", "b"]].
# ---------------------------------------------------------------------------


@dataclass
class WithListOfLists:
    """Dataclass with a list-of-lists field for append mode tests."""

    rows: list[list[str]] = field(default_factory=list)


class TestAppendMode:
    """Tests for CSV append mode via --config.field+ flag."""

    def test_csv_append_wraps_as_single_list_element(self, tmp_path: Path) -> None:
        """Test that appending a CSV wraps it as a single list element."""
        p = write(tmp_path, "data.csv", "val\nalpha\nbeta\n")
        result = confarg.load(
            WithListOfLists,
            args=["--config.rows+", str(p)],
        )
        # CSV single-column → ["alpha", "beta"]; append mode wraps it as one element
        assert result.rows == [["alpha", "beta"]]
