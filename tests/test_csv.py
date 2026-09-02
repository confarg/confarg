# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for CSV/TSV file loading via __include__ and append mode."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from pathlib import Path

import pytest

import confarg
from confarg._files import INCLUDE_KEY, _load_csv, _load_file
from confarg._types import _StrToken
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
        result = confarg.load(AppConfig, argv=[], files=[tmp_path / "config.yaml"])
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
            argv=["--name", "from_cli"],
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
            argv=["--config.rows+", str(p)],
        )
        # CSV single-column → ["alpha", "beta"]; append mode wraps it as one element
        assert result.rows == [["alpha", "beta"]]


# ---------------------------------------------------------------------------
# Leaf coercion: CSV cells are _StrToken, so they coerce like CLI args and env vars
# ---------------------------------------------------------------------------


class Tier(enum.Enum):
    """Enum used to check enum coercion from CSV cells."""

    GOLD = "gold"
    SILVER = "silver"


@dataclass
class Record:
    """Row record mixing every scalar leaf type."""

    name: str
    age: int
    score: float
    admin: bool
    tier: Tier
    kind: Literal["a", "b"]


@dataclass
class WithRecords:
    """Dataclass holding a list of CSV row records."""

    people: list[Record] = field(default_factory=list)


@dataclass
class WithInts:
    """Dataclass holding a list of ints."""

    nums: list[int] = field(default_factory=list)


@dataclass
class WithFloatColumns:
    """Dataclass holding CSV columns as float lists."""

    cols: dict[str, list[float]] = field(default_factory=dict)


@dataclass
class Series:
    """Named CSV columns landing in a dataclass."""

    ts: list[str]
    value: list[float]


@dataclass
class WithSeries:
    """Dataclass wrapping a Series built from CSV columns."""

    s: Series


@dataclass
class WithMatrix:
    """Dataclass holding a numeric matrix."""

    grid: list[list[int]] = field(default_factory=list)


@dataclass
class WithPairs:
    """Dataclass holding fixed-shape (str, int) pairs."""

    pairs: list[tuple[str, int]] = field(default_factory=list)


@dataclass
class WithStrs:
    """Dataclass holding plain strings (guards against over-coercion)."""

    vals: list[str] = field(default_factory=list)


def include_yaml(tmp_path: Path, csv_name: str, key: str, **options: object) -> Path:
    """Write a config.yaml whose `key` includes `csv_name`, with optional include options."""
    if options:
        opts = "".join(f"    {k}: {v}\n" for k, v in options.items())
        body = f"{key}:\n  {INCLUDE_KEY}:\n    path: ./{csv_name}\n{opts}"
    else:
        body = f"{key}:\n  {INCLUDE_KEY}: ./{csv_name}\n"
    return write(tmp_path, "config.yaml", body)


class TestCsvLeafCoercion:
    """CSV cells coerce to the target leaf type, exactly like CLI args and env vars."""

    def test_rows_header_coerces_every_scalar_leaf(self, tmp_path: Path) -> None:
        """Test that a multi-column CSV builds dataclasses with int/float/bool/enum fields."""
        write(tmp_path, "people.csv", "name,age,score,admin,tier,kind\nalice,30,1.5,true,gold,a\n")
        cfg_file = include_yaml(tmp_path, "people.csv", "people")
        cfg = confarg.load(WithRecords, argv=[], files=[cfg_file])
        assert cfg.people == [Record(name="alice", age=30, score=1.5, admin=True, tier=Tier.GOLD, kind="a")]

    def test_single_column_coerces_to_list_of_ints(self, tmp_path: Path) -> None:
        """Test that a single-column CSV lands in list[int]."""
        write(tmp_path, "nums.csv", "n\n1\n2\n3\n")
        cfg_file = include_yaml(tmp_path, "nums.csv", "nums")
        assert confarg.load(WithInts, argv=[], files=[cfg_file]).nums == [1, 2, 3]

    def test_columns_orient_coerces_to_dict_of_float_lists(self, tmp_path: Path) -> None:
        """Test that columns orient lands in dict[str, list[float]]."""
        write(tmp_path, "m.csv", "a,b\n1.5,2.5\n3.5,4.5\n")
        cfg_file = include_yaml(tmp_path, "m.csv", "cols", orient="columns")
        cfg = confarg.load(WithFloatColumns, argv=[], files=[cfg_file])
        assert cfg.cols == {"a": [1.5, 3.5], "b": [2.5, 4.5]}

    def test_columns_orient_coerces_into_dataclass(self, tmp_path: Path) -> None:
        """Test that named CSV columns land in a dataclass with typed list fields."""
        write(tmp_path, "s.csv", "ts,value\n2024-01,1.5\n2024-02,2.5\n")
        cfg_file = include_yaml(tmp_path, "s.csv", "s", orient="columns")
        cfg = confarg.load(WithSeries, argv=[], files=[cfg_file])
        assert cfg.s == Series(ts=["2024-01", "2024-02"], value=[1.5, 2.5])

    def test_raw_orient_coerces_to_list_of_int_lists(self, tmp_path: Path) -> None:
        """Test that raw orient lands in list[list[int]]."""
        write(tmp_path, "g.csv", "1,2\n3,4\n")
        cfg_file = include_yaml(tmp_path, "g.csv", "grid", orient="raw")
        assert confarg.load(WithMatrix, argv=[], files=[cfg_file]).grid == [[1, 2], [3, 4]]

    def test_no_header_coerces_to_fixed_tuples(self, tmp_path: Path) -> None:
        """Test that a headerless CSV lands in list[tuple[str, int]]."""
        write(tmp_path, "p.csv", "a,1\nb,2\n")
        cfg_file = include_yaml(tmp_path, "p.csv", "pairs", header="false")
        cfg = confarg.load(WithPairs, argv=[], files=[cfg_file])
        assert cfg.pairs == [("a", 1), ("b", 2)]

    def test_str_target_is_not_over_coerced(self, tmp_path: Path) -> None:
        """Test that numeric-looking cells stay strings when the target field is str."""
        write(tmp_path, "v.csv", "v\n1\ntrue\n")
        cfg_file = include_yaml(tmp_path, "v.csv", "vals")
        cfg = confarg.load(WithStrs, argv=[], files=[cfg_file])
        assert cfg.vals == ["1", "true"]
        assert all(type(v) is str for v in cfg.vals)

    def test_append_mode_coerces_numeric_csv(self, tmp_path: Path) -> None:
        """Test that a CSV appended via --config.field+ coerces its cells."""
        p = write(tmp_path, "row.csv", "n\n1\n2\n")
        result = confarg.load(WithMatrix, argv=["--config.grid+", str(p)])
        assert result.grid == [[1, 2]]

    def test_cells_are_str_tokens(self, tmp_path: Path) -> None:
        """Test that _load_csv marks cells as _StrToken so downstream coercion can fire."""
        p = write(tmp_path, "x.csv", "a,b\n1,2\n")
        row = _load_csv(p)[0]
        assert all(isinstance(v, _StrToken) for v in row.values())
        assert all(type(k) is str for k in row)  # keys are structural, kept as plain str


# ---------------------------------------------------------------------------
# Structural validation: ragged rows and duplicate headers
# ---------------------------------------------------------------------------


class TestCsvStructuralValidation:
    """Rows must be rectangular wherever the result is keyed."""

    def test_short_row_with_header_raises(self, tmp_path: Path) -> None:
        """Test that a row with too few cells raises, naming the row and counts."""
        p = write(tmp_path, "d.csv", "a,b,c\n1,2\n")
        with pytest.raises(InvalidConfigFileError, match=r"Ragged CSV row 2.*expected 3 cells, got 2"):
            _load_csv(p)

    def test_long_row_with_header_raises(self, tmp_path: Path) -> None:
        """Test that a row with too many cells raises."""
        p = write(tmp_path, "d.csv", "a,b\n1,2\n3,4,5\n")
        with pytest.raises(InvalidConfigFileError, match=r"Ragged CSV row 3.*expected 2 cells, got 3"):
            _load_csv(p)

    def test_ragged_rejected_in_columns_orient_with_header(self, tmp_path: Path) -> None:
        """Test that columns orient with a header rejects ragged rows."""
        p = write(tmp_path, "d.csv", "a,b\n1\n")
        with pytest.raises(InvalidConfigFileError, match="Ragged CSV row 2"):
            _load_csv(p, orient="columns")

    def test_ragged_rejected_in_columns_orient_without_header(self, tmp_path: Path) -> None:
        """Test that columns orient without a header rejects ragged rows."""
        p = write(tmp_path, "d.csv", "1\n2,3\n")
        with pytest.raises(InvalidConfigFileError, match="Ragged CSV row 2"):
            _load_csv(p, orient="columns", header=False)

    def test_duplicate_header_names_raise(self, tmp_path: Path) -> None:
        """Test that a repeated column name raises instead of silently dropping data."""
        p = write(tmp_path, "d.csv", "a,a\n1,2\n")
        with pytest.raises(InvalidConfigFileError, match=r"Duplicate CSV column name\(s\).*'a'"):
            _load_csv(p)

    def test_ragged_allowed_in_raw_orient(self, tmp_path: Path) -> None:
        """Test that raw orient still tolerates ragged rows."""
        p = write(tmp_path, "d.csv", "a\nb,c\n")
        assert _load_csv(p, orient="raw") == [["a"], ["b", "c"]]

    def test_ragged_allowed_in_rows_orient_without_header(self, tmp_path: Path) -> None:
        """Test that rows orient without a header still tolerates ragged rows."""
        p = write(tmp_path, "d.csv", "a\nb,c\n")
        assert _load_csv(p, header=False) == [["a"], ["b", "c"]]

    def test_blank_lines_are_ignored(self, tmp_path: Path) -> None:
        """Test that blank lines are dropped rather than counted as ragged rows."""
        p = write(tmp_path, "d.csv", "a,b\n1,2\n\n3,4\n")
        assert _load_csv(p) == [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}]

    def test_validation_error_surfaces_through_load(self, tmp_path: Path) -> None:
        """Test that a ragged CSV include fails loudly through confarg.load."""
        write(tmp_path, "d.csv", "a,b,c\n1,2\n")
        cfg_file = include_yaml(tmp_path, "d.csv", "vals")
        with pytest.raises(InvalidConfigFileError, match="Ragged CSV row 2"):
            confarg.load(WithStrs, argv=[], files=[cfg_file])
