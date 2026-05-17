# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Config file loading and dumping, dispatched by extension; ``__include__`` resolution.

A config source is named by a location string -- a local path or a URL -- and every question
that location implies is answered by :mod:`confarg._sources`, so nothing here branches on
whether a document is local or remote. Loaders receive the document's bytes and parse them.

Files are mounted at a path of the merged document (``__include__``, ``--config.<path>``,
``CONFIG__<PATH>``); expression references are prefixed accordingly while mounting.

Dev Notes:
    docs-dev/architecture/02-files-and-env.md
    docs-dev/architecture/07-expressions.md#reference-anchoring
    docs-dev/architecture/10-design-decisions.md#the-mount-keyword-is-spelled-per-channel
"""

from __future__ import annotations

import csv
import io
import json
import tomllib
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

from confarg import _defaults, _sources
from confarg._merge import _deep_merge
from confarg._types import _StrToken
from confarg.dictexpr._expressions import check_anchor_depth, contains_expression, prefix_references
from confarg.exceptions import ConfargError, InvalidConfigFileError

INCLUDE_KEY = "__include__"


def _load_toml(data: bytes, loc: str) -> dict[str, Any]:
    """Parse TOML bytes into a dict.

    Args:
        data: The document's raw bytes.
        loc: The location they came from, for error messages.

    Returns:
        A dict of the parsed TOML contents.

    Raises:
        InvalidConfigFileError: If the bytes are not valid UTF-8 TOML.
    """
    try:
        # tomllib.loads takes str and tomllib.load takes binary: neither takes bytes, and TOML
        # is specified as UTF-8, so the decode is the format's rule rather than a choice.
        return tomllib.loads(data.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        msg = "TOML"
        raise InvalidConfigFileError.malformed(msg, loc, e) from e


def _load_yaml_item(data: bytes, loc: str) -> Any:
    """Parse YAML bytes, returning the raw top-level value (dict, list, or scalar)."""
    try:
        import yaml  # noqa: PLC0415
    except ImportError:
        msg = "PyYAML"
        raise InvalidConfigFileError.missing_library(msg, "pyyaml", "YAML support") from None
    try:
        return yaml.safe_load(data)  # PyYAML decodes, honouring a BOM
    except yaml.YAMLError as e:
        msg = "YAML"
        raise InvalidConfigFileError.malformed(msg, loc, e) from e


def _load_json_item(data: bytes, loc: str) -> Any:
    """Parse JSON bytes, returning the raw top-level value (dict, list, or scalar)."""
    try:
        return json.loads(data)  # json.loads on bytes tolerates a BOM; on str it would not
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        msg = "JSON"
        raise InvalidConfigFileError.malformed(msg, loc, e) from e


#: Parsers for the configuration-layer formats, by extension — no data format (.csv/.tsv)
#: appears here, because data is a value rather than a layer and `_load_document` routes it to
#: `_load_csv` instead. Every entry returns the document's raw top-level value; requiring that
#: value to be a mapping is _require_layer's call alone, made once for all three formats, for
#: whatever `__include__` resolves them to and for every mount route.
#: See docs-dev/architecture/02-files-and-env.md#format-dispatch-and-optional-dependencies.
_LOADERS: dict[str, Any] = {
    ".toml": _load_toml,  # TOML root is always a dict
    ".yaml": _load_yaml_item,
    ".yml": _load_yaml_item,
    ".json": _load_json_item,
}


def _read_rows(f: Any, delimiter: str) -> list[list[_StrToken]]:
    """Read all CSV rows, wrapping every cell in _StrToken and dropping blank lines.

    Dev Notes:
        docs-dev/architecture/02-files-and-env.md#data-files-versus-configuration-layers
    """
    return [[_StrToken(cell) for cell in row] for row in csv.reader(f, delimiter=delimiter) if row]


def _check_rectangular(rows: list[list[_StrToken]], ncols: int, path: str, *, offset: int) -> None:
    """Raise if any row's cell count differs from ncols.

    Args:
        rows: The data rows to check.
        ncols: The expected cell count.
        path: The source location, for the error message.
        offset: Rows consumed before these (1 when a header row was split off), so the
            reported row number is 1-based over the whole file.
    """
    for i, row in enumerate(rows):
        if len(row) != ncols:
            raise InvalidConfigFileError.ragged_csv_row(path, i + 1 + offset, ncols, len(row))


def _load_csv_no_header(all_rows: list[list[_StrToken]], orient: str, path: str) -> Any:
    """Build the result for CSV loaded without a header row."""
    if not all_rows:
        return [] if orient == "rows" else {}
    if orient == "columns":  # positional index keys "0", "1", …
        ncols = len(all_rows[0])
        _check_rectangular(all_rows, ncols, path, offset=0)
        return {str(i): [row[i] for row in all_rows] for i in range(ncols)}
    return [row[0] for row in all_rows] if all(len(row) == 1 for row in all_rows) else all_rows


def _load_csv_with_header(all_rows: list[list[_StrToken]], orient: str, path: str) -> Any:
    """Build the result for CSV loaded with a header row."""
    if not all_rows:
        return [] if orient == "rows" else {}
    header, *rows = all_rows
    names = [str(cell) for cell in header]  # keys are structural, not values — keep them plain str
    dupes = [n for n, count in Counter(names).items() if count > 1]
    if dupes:
        raise InvalidConfigFileError.duplicate_csv_columns(path, dupes)
    _check_rectangular(rows, len(names), path, offset=1)
    if orient == "columns":
        return {name: [row[i] for row in rows] for i, name in enumerate(names)}
    if len(names) == 1:
        return [row[0] for row in rows]
    return [dict(zip(names, row, strict=True)) for row in rows]


def _load_csv(data: bytes, loc: str, *, orient: str = "rows", delimiter: str = ",", header: bool = True) -> Any:
    """Parse CSV/TSV bytes, returning a Python structure determined by orient and header.

    Every cell is a _StrToken, so CSV values coerce to the target leaf type (int, float,
    bool, Enum, …) exactly like CLI arguments and environment variables do.

    orient='rows' (default):
        header=True:  single-column → list[str]; multi-column → list[dict[str, str]].
        header=False: single-column → list[str]; multi-column → list[list[str]].
    orient='columns':
        header=True:  dict[str, list[str]] keyed by column names from the header row.
        header=False: dict[str, list[str]] keyed by positional index ("0", "1", …).
    orient='raw':
        list[list[str]] — every row returned as-is; header option is ignored.

    Rows must be rectangular wherever the result is keyed (orient='columns', or
    orient='rows' with a header); a ragged row raises there. orient='raw' and
    orient='rows' with header=False allow ragged rows.
    """
    if orient not in ("rows", "columns", "raw"):
        msg = f"Invalid CSV orient {orient!r}. Must be 'rows', 'columns', or 'raw'."
        raise ConfargError(msg)
    # utf-8-sig drops a BOM that would otherwise become part of the first header name, and
    # newline="" keeps a CRLF inside a quoted field intact -- the two rules csv.reader needs.
    text = data.decode("utf-8-sig")
    all_rows = _read_rows(io.StringIO(text, newline=""), delimiter)
    if orient == "raw":
        return all_rows
    if not header:
        return _load_csv_no_header(all_rows, orient, loc)
    return _load_csv_with_header(all_rows, orient, loc)


#: Extensions whose content is data rather than a configuration layer. An include of one
#: replaces whatever earlier entries produced instead of merging key-wise into it.
#: See docs-dev/architecture/02-files-and-env.md#data-files-versus-configuration-layers.
_DATA_SUFFIXES = frozenset({".csv", ".tsv"})


def _loader_for(loc: str, table: dict[str, Any]) -> Any:
    """Return the loader *table* holds for the format *loc* names.

    The one place a location is turned into a parser, so an unsupported extension and a missing
    one produce their own error once, for every table and every channel.

    Raises:
        InvalidConfigFileError: If the location carries no extension, or one no loader handles.

    Dev Notes:
        docs-dev/architecture/02-files-and-env.md#format-dispatch-and-optional-dependencies
    """
    ext = _sources._suffix(loc)
    if not ext:
        raise InvalidConfigFileError.no_format(loc)
    loader = table.get(ext)
    if loader is None:
        raise InvalidConfigFileError.unsupported_format(ext)
    return loader


def _load_document(loc: str, options: dict[str, Any] | None = None) -> Any:
    """Read the document at *loc* and parse it, returning its raw top-level value.

    The one place a location becomes a parsed value, for every channel and both kinds of format:
    a data format (.csv/.tsv) is read with *options* (``orient``, ``header``), a configuration
    layer by the parser `_loader_for` picks. The root-is-a-mapping rule is not applied here --
    that is `_load_raw`'s alone -- and neither is ``__include__`` resolution, `_resolve_node`'s.

    Raises:
        InvalidConfigFileError: If the location carries no extension or one no parser handles,
            it cannot be read, or its contents are invalid.
        ConfargError: If the ``header`` option is not a boolean.

    Dev Notes:
        docs-dev/architecture/02-files-and-env.md#format-dispatch-and-optional-dependencies
    """
    ext = _sources._suffix(loc)
    if ext in _DATA_SUFFIXES:
        opts = options or {}
        header_opt = opts.get("header", True)
        if not isinstance(header_opt, bool):
            msg = f"'header' option must be a boolean (true/false), got {header_opt!r}"
            raise ConfargError(msg)
        return _load_csv(
            _sources._read_bytes(loc),
            loc,
            orient=opts.get("orient", "rows"),
            delimiter="\t" if ext == ".tsv" else ",",
            header=header_opt,
        )
    loader = _loader_for(loc, _LOADERS)
    return loader(_sources._read_bytes(loc), loc)


def _parse_include_entry(val: Any) -> tuple[str, dict[str, Any]]:
    """Parse one INCLUDE_KEY entry into (path_str, options).

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


def _parse_include_val(val: Any) -> list[tuple[str, dict[str, Any]]]:
    """Parse an INCLUDE_KEY value into an ordered list of (path_str, options) entries.

    A string or dict yields a single entry; a list yields one entry per item, layered
    left to right by _load_includes so later entries win.
    """
    if isinstance(val, list):
        if not val:
            msg = f"{INCLUDE_KEY} list must name at least one path"
            raise ConfargError(msg)
        return [_parse_include_entry(item) for item in val]
    return [_parse_include_entry(val)]


def _unwrap_root_key(value: Any) -> Any:
    """Unwrap a fragment that names its whole content under ROOT_KEY.

    A TOML document root can only be a table, so ``__root__ = [1, 2]`` is the only way a TOML
    fragment can carry a list or a scalar; honoring it here gives every mount route the same
    expressive range. Only a lone ROOT_KEY unwraps: with siblings the file is saying two
    contradictory things, and leaving it alone lets the usual unknown-field error name it.

    A *document* root is never unwrapped -- there ROOT_KEY carries a non-struct target's value
    and ``build()`` is what reads it -- which is why this sits on the include path rather than
    in :func:`_load_any`.

    Dev Notes:
        docs-dev/architecture/02-files-and-env.md#reserved-file-only-keys
    """
    if isinstance(value, dict) and len(value) == 1 and _defaults.ROOT_KEY in value:
        return value[_defaults.ROOT_KEY]
    return value


def _load_includes(
    entries: list[tuple[str, dict[str, Any]]],
    base: str | None,
    seen: frozenset[str],
    union_tag: str | None = None,
) -> Any:
    """Load every include entry and layer them left to right, later entries winning.

    Two dicts deep-merge under *union_tag*, so a class tag in a later entry discards the
    earlier node exactly as it does across ``--config`` files
    (10-design-decisions.md#a-class-tag-replaces-not-merges). Anything else is replaced by the
    later entry, and so is a CSV/TSV entry even when it loads as a dict. ``seen`` grows per
    entry, not across the list: naming the same document twice is legal, a genuine cycle raises.

    *base* is the location of the including document, which each entry resolves against; it is
    ``None`` for the channel routes, which have no including document and resolve against the
    process working directory instead.

    Dev Notes:
        docs-dev/architecture/02-files-and-env.md#include-semantics
        docs-dev/architecture/02-files-and-env.md#mounting
    """
    result: Any = None
    for i, (path_str, options) in enumerate(entries):
        inc_loc = _sources._join(base, path_str)
        key = _sources._identity(inc_loc)
        if key in seen:
            msg = f"Circular include detected: {inc_loc}"
            raise ConfargError(msg)
        loaded = _unwrap_root_key(_load_any(inc_loc, seen | {key}, options=options, union_tag=union_tag))
        is_data = _sources._suffix(inc_loc) in _DATA_SUFFIXES
        if i == 0 or is_data or not (isinstance(result, dict) and isinstance(loaded, dict)):
            result = loaded
        else:
            result = _deep_merge(result, loaded, union_tag=union_tag)
    return result


def _join_path(prefix: str, seg: str) -> str:
    """Join a within-file path with one more segment."""
    return f"{prefix}.{seg}" if prefix else seg


def _include_with_siblings(included: Any, siblings: dict[str, Any], union_tag: str | None) -> dict[str, Any]:
    """Merge an include's sibling keys on top of *included*, which must be a dict.

    Siblings were written by the including file, so they win; a non-dict include has nothing
    for them to merge into.
    """
    if not isinstance(included, dict):
        raise ConfargError.include_siblings_need_a_dict(INCLUDE_KEY, included)
    return _deep_merge(included, siblings, union_tag=union_tag)


def _resolve_node(
    data: Any,
    base: str,
    seen: frozenset[str],
    path_in_file: str = "",
    union_tag: str | None = None,
) -> Any:
    """Dispatch include resolution by node type.

    *path_in_file* is the position of *data* relative to the root of the document
    currently being resolved; it is what an included document gets prefixed by,
    and it resets to ``""`` on entry to each document (see :func:`_load_any`).  It
    is also the depth a node-relative reference is clamped to, which is why the
    check below sits on this walk rather than on the mounting pass.

    Dev Notes:
        docs-dev/architecture/07-expressions.md#reference-anchoring
    """
    if isinstance(data, dict):
        return _resolve_dict(data, base, seen, path_in_file, union_tag)
    if isinstance(data, list):
        return _resolve_list(data, base, seen, path_in_file, union_tag)
    if contains_expression(data):
        check_anchor_depth(data, path_in_file)
    return data


def _resolve_dict(
    data: dict[str, Any],
    base: str,
    seen: frozenset[str],
    path_in_file: str = "",
    union_tag: str | None = None,
) -> Any:
    """Resolve INCLUDE_KEY in a dict node.

    INCLUDE_KEY may name one document or a list of them; a list is layered left to
    right by _load_includes before anything else happens. A pure include (no
    siblings) may return any type. An include with sibling keys requires the
    layered result to be a dict (for deep-merge).

    The included document's references are prefixed by *path_in_file* before the
    sibling keys (which keep this document's anchoring) are merged on top.

    A present but unusable value (``__include__: null``) raises here exactly as it does in a
    list item: it is the same key in the same document, so one rule reads it.

    Dev Notes:
        docs-dev/architecture/07-expressions.md#reference-anchoring
    """
    if INCLUDE_KEY in data:
        included = prefix_references(
            _load_includes(_parse_include_val(data[INCLUDE_KEY]), base, seen, union_tag),
            path_in_file,
        )
        siblings = {k: v for k, v in data.items() if k != INCLUDE_KEY}
        if not siblings:
            return included
        result: dict[str, Any] = _include_with_siblings(included, siblings, union_tag)
    else:
        result = dict(data)

    for k, v in result.items():
        result[k] = _resolve_node(v, base, seen, _join_path(path_in_file, k), union_tag)

    return result


def _resolve_list(
    data: list[Any],
    base: str,
    seen: frozenset[str],
    path_in_file: str = "",
    union_tag: str | None = None,
) -> list[Any]:
    """Resolve INCLUDE_KEY in list items.

    A list item that is a pure ``{INCLUDE_KEY: path}`` dict is replaced by the included
    content as **one** element, whatever type that content has: an include contributes a
    value, and extending a list is the ``+`` merge operator's job
    (10-design-decisions.md#the--suffix-is-a-merge-operator-not-a-list-spelling). A list of
    paths is layered into a single value first, as in a dict node. Items with sibling keys
    follow the same rules as dict nodes.

    Each item's references are prefixed by the index it lands on.

    Dev Notes:
        docs-dev/architecture/07-expressions.md#reference-anchoring
    """
    result: list[Any] = []
    for item in data:
        here = _join_path(path_in_file, str(len(result)))
        if isinstance(item, dict) and INCLUDE_KEY in item:
            included = prefix_references(
                _load_includes(_parse_include_val(item[INCLUDE_KEY]), base, seen, union_tag),
                here,
            )
            siblings = {k: v for k, v in item.items() if k != INCLUDE_KEY}
            if not siblings:
                result.append(included)
            else:
                merged = _include_with_siblings(included, siblings, union_tag)
                result.append(_resolve_node(merged, base, seen, here, union_tag))
        else:
            result.append(_resolve_node(item, base, seen, here, union_tag))
    return result


def _load_any(
    loc: str,
    seen: frozenset[str],
    *,
    options: dict[str, Any] | None = None,
    union_tag: str | None = None,
) -> Any:
    """Load one config source as any type (dict, list, or scalar), with its includes resolved.

    The single loader: every mount route reaches a document through here, so the accepted
    formats, the CSV options and the include resolution are one rule rather than three
    (02-files-and-env.md#mounting). Whether the result is allowed to be a *document root* is
    the separate question :func:`_require_layer` asks.

    For CSV/TSV, *options* may contain 'orient' and 'header'.

    Dev Notes:
        docs-dev/architecture/02-files-and-env.md#format-dispatch-and-optional-dependencies
    """
    return _resolve_node(_load_document(loc, options), loc, seen, "", union_tag)


def _require_layer(value: Any, loc: str) -> dict[str, Any]:
    """Return *value* as a configuration layer, or raise.

    The one place the root-is-a-mapping rule is applied, so every format, every
    ``__include__`` that rewrites a root and every mount route answers to the same check and
    the same error. An empty document (``None`` -- an empty YAML file, or an explicit
    ``null``) contributes nothing, matching an empty TOML file.

    Dev Notes:
        docs-dev/architecture/02-files-and-env.md#format-dispatch-and-optional-dependencies
    """
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise InvalidConfigFileError.non_dict_root(loc, value)
    return value


def _load_raw(loc: str, seen: frozenset[str], union_tag: str | None = None) -> dict[str, Any]:
    """Load a config source whose content is a document root, so a configuration layer.

    A data file contributes a value rather than a layer, so it is rejected here even though
    :func:`_load_any` can read it.

    Dev Notes:
        docs-dev/architecture/02-files-and-env.md#data-files-versus-configuration-layers
    """
    _loader_for(loc, _LOADERS)  # a root is a layer: .csv/.tsv is unsupported here, not data
    return _require_layer(_load_any(loc, seen, union_tag=union_tag), loc)


def _load_file(loc: str | Path, union_tag: str | None = None) -> dict[str, Any]:
    """Load a config source, dispatching by extension.

    Supports .toml, .yaml, .yml, and .json documents, local or remote -- a data file is a
    value, not a document root. INCLUDE_KEY entries are resolved recursively after loading.

    Args:
        loc: Location of the config source -- a local path, a ``Path``, or a URL.
        union_tag: Discriminator field name, so a class tag inside an include replaces the
            node it lands on exactly as it does across ``--config`` files.

    Returns:
        A dict of the parsed contents with all includes resolved.

    Raises:
        InvalidConfigFileError: If the format is unsupported, the source cannot be
            read, its contents are invalid, or the value it resolves to is not a
            dict (an empty document excepted).
        ConfargError: If an include value is not a string or a circular include
            is detected.
    """
    loc = _sources._location(loc)
    return _load_raw(loc, frozenset({_sources._identity(loc)}), union_tag)


def _nest(value: Any, subpath: str) -> Any:
    """Wrap *value* in the chain of dicts named by the dot-separated *subpath*."""
    for part in reversed(subpath.split(".")):
        value = {part: value}
    return value


def _mount(value: Any, subpath: str) -> Any:
    """Place *value* at *subpath* of a fresh document, re-anchoring its references.

    The one implementation of mounting a loaded value: ``__include__`` under a key reaches the
    same outcome through :func:`_resolve_dict`'s *path_in_file*, and ``--config.<path>`` and
    ``CONFIG__<PATH>`` reach it here. An empty *subpath* is the root, and the identity.

    Dev Notes:
        docs-dev/architecture/02-files-and-env.md#mounting
        docs-dev/architecture/07-expressions.md#reference-anchoring
    """
    if not subpath:
        return value
    return _nest(prefix_references(value, subpath), subpath)


def _decode_mount_value(value: Any) -> Any:
    """Read one channel-supplied mount value as an ``__include__`` value.

    A ``Path`` or a plain string is a location. A string starting with ``{`` or ``[`` is the
    JSON spelling of the dict and list forms, so a ``--config.users`` token can say on argv what
    a file says with a mapping; invalid JSON is a hard error there, as it is for the ``.json``
    cast (03-cli-parsing.md#force-casts). Anything else is already in the include grammar -- a
    ``files=`` caller may pass the dict or list form directly -- and passes through.

    Dev Notes:
        docs-dev/architecture/02-files-and-env.md#mounting
    """
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str) and value[:1] in ("{", "["):
        try:
            return json.loads(value)
        except json.JSONDecodeError as e:
            msg = f"Invalid JSON in config-file value {value!r}: {e}"
            raise ConfargError(msg) from e
    return value


def _parse_mount_value(value: Any) -> list[tuple[str, dict[str, Any]]]:
    """Read one channel-supplied mount value as ``__include__`` entries.

    The one parse: a ``--config[.<path>]`` token, a ``CONFIG[__PATH]`` variable and a ``files=``
    entry all say what an ``__include__`` value says, so they are read by the code that reads
    ``__include__``.

    Dev Notes:
        docs-dev/architecture/02-files-and-env.md#mounting
    """
    return _parse_include_val(_decode_mount_value(value))


def _load_mount_value(value: Any, base: str | None = None, union_tag: str | None = None) -> Any:
    """Resolve one channel-supplied mount value to the value it contributes.

    The shared half of every non-file mount route: read *value* as an ``__include__`` value and
    layer its entries. Relative locations resolve against *base* -- the including document for
    ``__include__`` and, for these routes, the process working directory, which is what the
    default ``None`` names and the one difference between them.

    Dev Notes:
        docs-dev/architecture/02-files-and-env.md#mounting
        docs-dev/architecture/10-design-decisions.md#the-mount-keyword-is-spelled-per-channel
    """
    return _load_includes(_parse_mount_value(value), base, frozenset(), union_tag)


def _load_mount(value: Any, subpath: str, base: str | None = None, union_tag: str | None = None) -> dict[str, Any]:
    """Load one mount and return it nested at *subpath*.

    An empty *subpath* mounts at the document root, where the result must be a configuration
    layer and a data file has nothing to contribute. A non-empty one mounts at a node, where
    -- as for a pure ``__include__`` -- the result may be any type.

    Dev Notes:
        docs-dev/architecture/02-files-and-env.md#mounting
    """
    if subpath:
        return _mount(_load_mount_value(value, base, union_tag), subpath)
    locations = [_sources._join(base, path_str) for path_str, _ in _parse_mount_value(value)]
    for loc in locations:
        _loader_for(loc, _LOADERS)  # a root is a layer: .csv/.tsv is unsupported here, not data
    return _require_layer(_load_mount_value(value, base, union_tag), locations[-1])


def _load_subpath_files(entries: Sequence[tuple[str, Any]], union_tag: str) -> dict[str, Any]:
    """Load and merge a sequence of (subpath, mount value) pairs into a single dict.

    Carries ``files=`` and the ``CONFIG[__SUBPATH]`` environment pointers. Each value is
    mounted at its subpath by :func:`_load_mount`, so these routes accept exactly what
    ``__include__`` accepts. An empty subpath means the root. Later entries win on conflict.
    """
    result: dict[str, Any] = {}
    for subpath, value in entries:
        fdata = _load_mount(value, subpath, union_tag=union_tag)
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
    with Path(path).open("w", encoding="utf-8", newline="\n") as f:
        yaml.dump(data, f, Dumper=yaml.SafeDumper)


def _dump_json(data: dict[str, Any], path: Path) -> None:
    """Write a dict to a JSON file.

    Args:
        data: The dict to write.
        path: Path to the output file.
    """
    with Path(path).open("w", encoding="utf-8", newline="\n") as f:
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
