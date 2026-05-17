# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Config file loading."""

from __future__ import annotations

import csv
import json
import tomllib
from pathlib import Path
from typing import Any

from confarg._merge import _deep_merge
from confarg.exceptions import ConfargError, InvalidConfigFileError

INCLUDE_KEY = "__include__"


def _load_toml(path: Path) -> dict[str, Any]:
    """Load and parse a TOML config file.

    Args:
        path: Path to the TOML file.

    Returns:
        A dict of the parsed TOML contents.

    Raises:
        InvalidConfigFileError: If the file is not found or contains invalid TOML.
    """
    try:
        with Path(path).open("rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        raise InvalidConfigFileError.not_found(path) from None
    except tomllib.TOMLDecodeError as e:
        msg = "TOML"
        raise InvalidConfigFileError.malformed(msg, path, e) from e


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load and parse a YAML config file.

    Args:
        path: Path to the YAML file.

    Returns:
        A dict of the parsed YAML contents, or an empty dict if the file
        contains a non-dict value.

    Raises:
        InvalidConfigFileError: If PyYAML is not installed, the file is not found,
            or the file contains invalid YAML.
    """
    try:
        import yaml  # noqa: PLC0415
    except ImportError:
        msg = "PyYAML"
        raise InvalidConfigFileError.missing_library(msg, "pyyaml", "YAML support") from None
    try:
        with Path(path).open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        raise InvalidConfigFileError.not_found(path) from None
    except yaml.YAMLError as e:
        msg = "YAML"
        raise InvalidConfigFileError.malformed(msg, path, e) from e


def _load_json(path: Path) -> dict[str, Any]:
    """Load and parse a JSON config file.

    Args:
        path: Path to the JSON file.

    Returns:
        A dict of the parsed JSON contents.

    Raises:
        InvalidConfigFileError: If the file is not found, contains invalid JSON,
            or the top-level value is not a JSON object.
    """
    try:
        with Path(path).open(encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise InvalidConfigFileError.not_found(path) from None
    except json.JSONDecodeError as e:
        msg = "JSON"
        raise InvalidConfigFileError.malformed(msg, path, e) from e
    if not isinstance(data, dict):
        msg = f"JSON config must be an object, got {type(data).__name__}: {path}"
        raise InvalidConfigFileError(msg)
    return data


_LOADERS = {".toml": _load_toml, ".yaml": _load_yaml, ".yml": _load_yaml, ".json": _load_json}


def _load_yaml_item(path: Path) -> Any:
    """Load YAML, returning the raw top-level value (dict, list, or scalar)."""
    try:
        import yaml  # noqa: PLC0415
    except ImportError:
        msg = "PyYAML"
        raise InvalidConfigFileError.missing_library(msg, "pyyaml", "YAML support") from None
    try:
        with Path(path).open(encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        raise InvalidConfigFileError.not_found(path) from None
    except yaml.YAMLError as e:
        msg = "YAML"
        raise InvalidConfigFileError.malformed(msg, path, e) from e


def _load_json_item(path: Path) -> Any:
    """Load JSON, returning the raw top-level value (dict, list, or scalar)."""
    try:
        with Path(path).open(encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise InvalidConfigFileError.not_found(path) from None
    except json.JSONDecodeError as e:
        msg = "JSON"
        raise InvalidConfigFileError.malformed(msg, path, e) from e


def _load_csv_no_header(all_rows: list[list[str]], orient: str) -> Any:
    """Build the result for CSV loaded without a header row."""
    if orient == "rows":
        if not all_rows:
            return []
        return [row[0] for row in all_rows] if all(len(row) == 1 for row in all_rows) else all_rows
    # orient == "columns": positional index keys "0", "1", …
    if not all_rows:
        return {}
    ncols = len(all_rows[0])
    col_data: dict[str, list[str]] = {str(i): [] for i in range(ncols)}
    for row in all_rows:
        for i, v in enumerate(row):
            col_data[str(i)].append(v)
    return col_data


def _load_csv_with_header(f: Any, orient: str, delimiter: str) -> Any:
    """Build the result for CSV loaded with a header row."""
    reader = csv.DictReader(f, delimiter=delimiter)
    fieldnames = list(reader.fieldnames or [])
    if orient == "columns":
        result: dict[str, list[str]] = {name: [] for name in fieldnames}
        for row in reader:
            for k, v in row.items():
                result[k].append(v)
        return result
    rows = [dict(row) for row in reader]
    if len(fieldnames) == 1:
        return [row[fieldnames[0]] for row in rows]
    return rows


def _load_csv(path: Path, *, orient: str = "rows", delimiter: str = ",", header: bool = True) -> Any:
    """Load a CSV/TSV file, returning a Python structure determined by orient and header.

    orient='rows' (default):
        header=True:  single-column → list[str]; multi-column → list[dict[str, str]].
        header=False: single-column → list[str]; multi-column → list[list[str]].
    orient='columns':
        header=True:  dict[str, list[str]] keyed by column names from the header row.
        header=False: dict[str, list[str]] keyed by positional index ("0", "1", …).
    orient='raw':
        list[list[str]] — every row returned as-is; header option is ignored.
    """
    if orient not in ("rows", "columns", "raw"):
        msg = f"Invalid CSV orient {orient!r}. Must be 'rows', 'columns', or 'raw'."
        raise ConfargError(msg)
    try:
        with path.open(newline="", encoding="utf-8-sig") as f:
            if orient == "raw":
                return [list(row) for row in csv.reader(f, delimiter=delimiter)]
            if not header:
                return _load_csv_no_header([list(row) for row in csv.reader(f, delimiter=delimiter)], orient)
            return _load_csv_with_header(f, orient, delimiter)
    except FileNotFoundError:
        raise InvalidConfigFileError.not_found(path) from None


_ITEM_LOADERS: dict[str, Any] = {
    ".toml": _load_toml,  # TOML root is always a dict
    ".yaml": _load_yaml_item,
    ".yml": _load_yaml_item,
    ".json": _load_json_item,
    ".csv": lambda path: _load_csv(path, orient="rows"),
    ".tsv": lambda path: _load_csv(path, orient="rows", delimiter="\t"),
}


def _load_file_item(path: Path) -> Any:
    """Load a config file for append mode, returning the raw top-level value.

    Unlike _load_file(), accepts top-level lists (YAML/JSON) so that a file
    whose root is a list is treated as the single element to append.

    Args:
        path: Path to the config file.

    Returns:
        The raw top-level value: a dict, list, or scalar.

    Raises:
        InvalidConfigFileError: If the file format is unsupported, the file is
            not found, or the file contents are invalid.
    """
    path = Path(path)
    loader = _ITEM_LOADERS.get(path.suffix.lower())
    if loader is None:
        raise InvalidConfigFileError.unsupported_format(path.suffix.lower())
    return loader(path)


def _parse_include_val(val: Any) -> tuple[str, dict[str, Any]]:
    """Parse an INCLUDE_KEY value into (path_str, options).

    Accepts either a plain string path or a dict with a required 'path' key and
    optional per-format options (e.g. orient for CSV).
    """
    if isinstance(val, str):
        return val, {}
    if isinstance(val, dict) and isinstance(val.get("path"), str):
        options = {k: v for k, v in val.items() if k != "path"}
        return val["path"], options
    msg = f"{INCLUDE_KEY} must be a path string or a dict with a string 'path' key, got {val!r}"
    raise ConfargError(msg)


def _resolve_node(data: Any, base_dir: Path, seen: frozenset[Path]) -> Any:
    """Dispatch include resolution by node type."""
    if isinstance(data, dict):
        return _resolve_dict(data, base_dir, seen)
    if isinstance(data, list):
        return _resolve_list(data, base_dir, seen)
    return data


def _resolve_dict(data: dict[str, Any], base_dir: Path, seen: frozenset[Path]) -> Any:
    """Resolve INCLUDE_KEY in a dict node.

    A pure include (no siblings) may return any type. An include with sibling
    keys requires the included file to be a dict (for deep-merge).
    """
    include_val = data.get(INCLUDE_KEY)
    if include_val is not None:
        path_str, options = _parse_include_val(include_val)
        inc_path = (base_dir / path_str).resolve()
        if inc_path in seen:
            msg = f"Circular include detected: {inc_path}"
            raise ConfargError(msg)
        included = _load_any(inc_path, seen | {inc_path}, options=options)
        siblings = {k: v for k, v in data.items() if k != INCLUDE_KEY}
        if not siblings:
            return included
        if not isinstance(included, dict):
            msg = (
                f"{INCLUDE_KEY} produced {type(included).__name__} but sibling keys are"
                f" also present; can only merge sibling keys into a dict include"
            )
            raise ConfargError(msg)
        result: dict[str, Any] = _deep_merge(included, siblings)
    else:
        result = dict(data)

    for k, v in result.items():
        result[k] = _resolve_node(v, base_dir, seen)

    return result


def _resolve_list(data: list[Any], base_dir: Path, seen: frozenset[Path]) -> list[Any]:
    """Resolve INCLUDE_KEY in list items.

    A list item that is a pure {INCLUDE_KEY: path} dict is replaced by the
    included file's content; if that content is itself a list it is spliced
    (flattened) into the parent list. Items with sibling keys follow the same
    rules as dict nodes.
    """
    result: list[Any] = []
    for item in data:
        if isinstance(item, dict) and INCLUDE_KEY in item:
            path_str, options = _parse_include_val(item[INCLUDE_KEY])
            inc_path = (base_dir / path_str).resolve()
            if inc_path in seen:
                msg = f"Circular include detected: {inc_path}"
                raise ConfargError(msg)
            included = _load_any(inc_path, seen | {inc_path}, options=options)
            siblings = {k: v for k, v in item.items() if k != INCLUDE_KEY}
            if not siblings:
                if isinstance(included, list):
                    result.extend(included)
                else:
                    result.append(included)
            elif isinstance(included, dict):
                merged = _deep_merge(included, siblings)
                result.append(_resolve_node(merged, base_dir, seen))
            else:
                msg = (
                    f"{INCLUDE_KEY} produced {type(included).__name__} but sibling keys are"
                    f" also present; can only merge sibling keys into a dict include"
                )
                raise ConfargError(msg)
        else:
            result.append(_resolve_node(item, base_dir, seen))
    return result


def _load_any(path: Path, seen: frozenset[Path], *, options: dict[str, Any] | None = None) -> Any:
    """Load an included file as any type (dict, list, or scalar).

    For CSV/TSV, options may contain 'orient' and 'header'.
    """
    ext = path.suffix.lower()
    opts = options or {}
    if ext in (".csv", ".tsv"):
        delimiter = "\t" if ext == ".tsv" else ","
        header_opt = opts.get("header", True)
        if not isinstance(header_opt, bool):
            msg = f"'header' option must be a boolean (true/false), got {header_opt!r}"
            raise ConfargError(msg)
        data = _load_csv(
            path,
            orient=opts.get("orient", "rows"),
            delimiter=delimiter,
            header=header_opt,
        )
    else:
        loader = _ITEM_LOADERS.get(ext)
        if loader is None:
            raise InvalidConfigFileError.unsupported_format(ext)
        data = loader(path)
    return _resolve_node(data, path.parent, seen)


def _load_raw(path: Path, seen: frozenset[Path]) -> dict[str, Any]:
    """Load a root config file; result must be a dict."""
    loader = _LOADERS.get(path.suffix.lower())
    if loader is None:
        raise InvalidConfigFileError.unsupported_format(path.suffix.lower())
    data = loader(path)
    result = _resolve_node(data, path.parent, seen)
    if not isinstance(result, dict):
        msg = f"Top-level config file must resolve to a dict, got {type(result).__name__}: {path}"
        raise ConfargError(msg)
    return result


def _load_file(path: Path) -> dict[str, Any]:
    """Load a config file, dispatching by extension.

    Supports .toml, .yaml, .yml, and .json files. INCLUDE_KEY entries are
    resolved recursively after loading.

    Args:
        path: Path to the config file.

    Returns:
        A dict of the parsed file contents with all includes resolved.

    Raises:
        InvalidConfigFileError: If the file format is unsupported, the file is
            not found, or the file contents are invalid.
        ConfargError: If an include value is not a string or a circular include
            is detected.
    """
    path = Path(path)
    return _load_raw(path, frozenset({path.resolve()}))


def _load_subpath_files(entries: list[tuple[str, Path]], union_tag: str) -> dict[str, Any]:
    """Load and merge a sequence of (subpath, file-path) pairs into a single dict.

    Each file is nested under its dot-separated subpath before merging.
    An empty subpath means the file is merged at the root. Later entries win
    on conflict.
    """
    result: dict[str, Any] = {}
    for subpath, fpath in entries:
        fdata = _load_file(fpath)
        if subpath:
            for part in reversed(subpath.split(".")):
                fdata = {part: fdata}
        result = _deep_merge(result, fdata, union_tag=union_tag)
    return result


def _dump_toml(data: dict[str, Any], path: Path) -> None:
    """Write a dict to a TOML file.

    Args:
        data: The dict to write.
        path: Path to the output file.

    Raises:
        InvalidConfigFileError: If tomli_w is not installed.
    """
    try:
        import tomli_w  # noqa: PLC0415
    except ImportError:
        msg = "tomli_w"
        raise InvalidConfigFileError.missing_library(msg, "tomli_w", "writing TOML files") from None
    with Path(path).open("wb") as f:
        tomli_w.dump(data, f)


def _dump_yaml(data: dict[str, Any], path: Path) -> None:
    """Write a dict to a YAML file.

    Args:
        data: The dict to write.
        path: Path to the output file.

    Raises:
        InvalidConfigFileError: If PyYAML is not installed.
    """
    try:
        import yaml  # noqa: PLC0415
    except ImportError:
        msg = "PyYAML"
        raise InvalidConfigFileError.missing_library(msg, "pyyaml", "writing YAML files") from None
    with Path(path).open("w", encoding="utf-8") as f:
        yaml.dump(data, f, Dumper=yaml.SafeDumper)


def _dump_json(data: dict[str, Any], path: Path) -> None:
    """Write a dict to a JSON file.

    Args:
        data: The dict to write.
        path: Path to the output file.
    """
    with Path(path).open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


_DUMPERS = {".toml": _dump_toml, ".yaml": _dump_yaml, ".yml": _dump_yaml, ".json": _dump_json}


def _dump_file(data: dict[str, Any], path: Path) -> None:
    """Write a dict to a config file, dispatching by extension.

    Args:
        data: The dict to write.
        path: Path to the output file.

    Raises:
        InvalidConfigFileError: If the file format is unsupported or the
            required library is not installed.
    """
    path = Path(path)
    dumper = _DUMPERS.get(path.suffix.lower())
    if dumper is None:
        raise InvalidConfigFileError.unsupported_format(path.suffix.lower())
    dumper(data, path)
