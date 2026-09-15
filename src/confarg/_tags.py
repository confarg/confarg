# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Find the classes a configuration names by its union tag, and import them.

The scans are framework-neutral: they read argv and the config files argv points at, never a
parse result, so vanilla, every adapter and shell completion share one answer.

Dev Notes:
    docs-dev/architecture/10-design-decisions.md#a-named-tag-is-imported-before-registration
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

from confarg._files import _load_file
from confarg._import import _import_dotted
from confarg._merge import _deep_merge
from confarg._types import (
    _is_struct,
    _is_union,
    _resolve_type,
    _struct_fields,
    _union_args_no_none,
)


def _partial_config_from_argv(argv: Sequence[str], config_flag: str) -> dict[str, Any]:
    """Return the merged contents of the root ``--<config_flag>`` files named in argv.

    Only the root flag, not its ``--<config_flag>.<subpath>`` variants.  Missing files and
    parse failures are ignored: callers run before the pipeline has had its say, and the real
    error belongs to the pipeline.
    """
    merged: dict[str, Any] = {}
    flag_prefix = f"--{config_flag}"
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == flag_prefix:
            # Space-separated form: --config file1 file2 ...
            i += 1
            while i < len(argv) and not argv[i].startswith("--"):
                with contextlib.suppress(Exception):
                    merged = _deep_merge(merged, _load_file(Path(argv[i])))
                i += 1
        elif tok.startswith(f"{flag_prefix}="):
            # Equals form: --config=file
            path_str = tok[len(flag_prefix) + 1 :]
            if path_str:
                with contextlib.suppress(Exception):
                    merged = _deep_merge(merged, _load_file(Path(path_str)))
            i += 1
        else:
            i += 1
    return merged


def _tag_prefix(flag: str, union_tag: str) -> str | None:
    """Return the field path a tag flag addresses, or None if it is not a tag flag.

    ``"db.class"`` -> ``"db"``; the bare ``"class"`` -> ``""``, the root target.
    """
    if flag == union_tag:
        return ""
    suffix = f".{union_tag}"
    return flag[: -len(suffix)] if flag.endswith(suffix) else None


def _tags_from_argv(argv: Sequence[str], union_tag: str) -> dict[str, str]:
    """Scan argv for ``--<path>.<union_tag> VALUE`` and the bare root ``--<union_tag> VALUE``.

    Returns ``{field_path: class_path_string}``, the root keyed by ``""``.  A flag with no
    value after it (the trailing word of a partial command line) is skipped.
    """
    tags: dict[str, str] = {}
    i = 0
    while i < len(argv):
        tok = argv[i]
        if not tok.startswith("--"):
            i += 1
            continue
        if "=" in tok:
            flag, _, val = tok.partition("=")
            prefix = _tag_prefix(flag[2:], union_tag)
            if prefix is not None:
                tags[prefix] = val
        else:
            prefix = _tag_prefix(tok[2:], union_tag)
            if prefix is not None and i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                tags[prefix] = argv[i + 1]
                i += 2
                continue
        i += 1
    return tags


def _union_field_tags(
    merged: dict[str, Any],
    name: str,
    flag: str,
    resolved: Any,
    union_tag: str,
) -> dict[str, str]:
    """Return resolved class-tag entries for one union field in the merged config."""
    tags: dict[str, str] = {}
    non_none = _union_args_no_none(resolved)
    if len(non_none) > 1:
        sub = merged.get(name)
        if isinstance(sub, dict) and union_tag in sub:
            val = sub[union_tag]
            if isinstance(val, str):
                tags[flag] = val
    elif len(non_none) == 1:
        sub = merged.get(name, {})
        if isinstance(sub, dict):
            tags.update(_tags_from_config(sub, _resolve_type(non_none[0]), flag, union_tag))
    return tags


def _tags_from_config(
    merged: dict[str, Any],
    target: Any,
    prefix: str,
    union_tag: str,
) -> dict[str, str]:
    """Walk merged config in parallel with target; return ``{field_path: class_path}``."""
    tags: dict[str, str] = {}
    tp = _resolve_type(target)
    if not _is_struct(tp):
        return tags

    if isinstance(merged.get(union_tag), str):
        tags[prefix] = merged[union_tag]  # a tag on this struct itself, root included

    try:
        flds = _struct_fields(tp)
    except (ValueError, TypeError, NameError, AttributeError):
        return tags

    for name, ft in flds.items():
        flag = f"{prefix}.{name}" if prefix else name
        resolved = _resolve_type(ft)
        if _is_union(resolved):
            tags.update(_union_field_tags(merged, name, flag, resolved, union_tag))
        elif _is_struct(resolved):
            sub = merged.get(name, {})
            if isinstance(sub, dict):
                tags.update(_tags_from_config(sub, resolved, flag, union_tag))

    return tags


def collect_tags(
    argv: Sequence[str],
    target: Any,
    *,
    union_tag: str,
    config_flag: str,
) -> dict[str, str]:
    """Return ``{field_path: class_path}`` for every union tag argv names, directly or in a file.

    argv wins over a config file for the same field path, as everywhere else.
    """
    config_tags: dict[str, str] = {}
    if config_flag:
        config_dict = _partial_config_from_argv(argv, config_flag)
        if config_dict:
            config_tags = _tags_from_config(config_dict, target, "", union_tag)
    return {**config_tags, **_tags_from_argv(argv, union_tag)}


def import_tagged_classes(
    argv: Sequence[str],
    target: Any,
    *,
    union_tag: str,
    config_flag: str,
) -> None:
    """Import every class the configuration names by its union tag, ignoring failures.

    Call before anything reads ``__subclasses__()``: a subclass is invisible to the type walk
    and to CLI path resolution until its module has run, and the tag is the only thing that
    says which module that is.  A bad class path is *not* reported here — the authoritative
    import happens later in ``construct``, which raises
    :class:`~confarg.exceptions.SymbolImportError` naming it.

    Dev Notes:
        docs-dev/architecture/10-design-decisions.md#a-named-tag-is-imported-before-registration
    """
    for class_path in collect_tags(argv, target, union_tag=union_tag, config_flag=config_flag).values():
        # Importing an arbitrary module runs its top level, which can raise anything at all.
        with contextlib.suppress(Exception):
            _import_dotted(class_path)
