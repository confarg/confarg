# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Find the classes a configuration names by its class key, and import them.

The scans are framework-neutral: they read argv and the config files argv points at, never a
parse result, so vanilla, every adapter and shell completion share one answer.

Dev Notes:
    docs-dev/architecture/design-decisions/a-named-tag-is-imported-before-registration.md#a-named-tag-is-imported-before-registration
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

from confarg import _defaults
from confarg._files import Reads, _load_file
from confarg._import import _import_dotted
from confarg._merge import MergeDict, _deep_merge
from confarg._types import (
    _is_struct,
    _is_union,
    _resolve_type,
    _struct_fields,
    _union_args_no_none,
)
from confarg.dictexpr import contains_expression
from confarg.typedload._construct import tag_selects_a_class


def class_named(path: Any) -> type | None:
    """Return the class a dotted *path* names, or ``None`` when it names none.

    The one reader of a class a configuration names by a tag or an opener before it is
    built. ``None`` covers a value that is no string, an expression, a path naming no class,
    and an import that fails, because every caller's response is the same: leave the value
    where its channel put it and move on. Construction imports it again and raises the error
    naming the path, so no caller reports the failure itself.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-named-tag-is-imported-before-registration.md#a-named-tag-is-imported-before-registration
    """
    if not isinstance(path, str) or contains_expression(path):
        return None
    try:
        cls = _import_dotted(path)
    except Exception:  # noqa: BLE001  # a module's top level may raise anything; construction reports it
        return None
    return cls if isinstance(cls, type) else None


def _tag_named_struct(class_tag: Any) -> Any:
    """Return the struct type a class tag names, or ``None`` when it names none (:func:`class_named`)."""
    cls = class_named(class_tag)
    return cls if cls is not None and _is_struct(_resolve_type(cls)) else None


def _partial_config_from_argv(argv: Sequence[str], config_flag: str) -> MergeDict:
    """Return the merged contents of the root ``--<config_flag>`` files named in argv.

    Only the root flag, not its ``--<config_flag>.<subpath>`` variants.  Missing files and
    parse failures are ignored: callers run before the pipeline has had its say, and the real
    error belongs to the pipeline. The scan reads with a :class:`~confarg._files.Reads` of its own, as the
    pipeline reads the files again.
    """
    reads = Reads()
    merged: MergeDict = {}
    flag_prefix = f"--{config_flag}"
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == flag_prefix:
            # Space-separated form: --config file1 file2 ...
            i += 1
            while i < len(argv) and not argv[i].startswith("--"):
                with contextlib.suppress(Exception):
                    merged = _deep_merge(merged, _load_file(argv[i], reads=reads))
                i += 1
        elif tok.startswith(f"{flag_prefix}="):
            # Equals form: --config=file
            path_str = tok.removeprefix(f"{flag_prefix}=")
            if path_str:
                with contextlib.suppress(Exception):
                    merged = _deep_merge(merged, _load_file(path_str, reads=reads))
            i += 1
        else:
            i += 1
    return merged


def _tag_prefix(flag: str) -> str | None:
    """Return the field path a tag flag addresses, or None if it is not a tag flag.

    ``"db.class"`` -> ``"db"``; the bare ``"class"`` -> ``""``, the root target.
    """
    if flag == _defaults.CLASS_KEY:
        return ""
    suffix = f".{_defaults.CLASS_KEY}"
    return flag[: -len(suffix)] if flag.endswith(suffix) else None


def _tags_from_argv(argv: Sequence[str]) -> dict[str, str]:
    """Scan argv for ``--<path>.class VALUE`` and the bare root ``--class VALUE``.

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
            prefix = _tag_prefix(flag[2:])
            if prefix is not None:
                tags[prefix] = val
        else:
            prefix = _tag_prefix(tok[2:])
            if prefix is not None and i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                tags[prefix] = argv[i + 1]
                i += 2
                continue
        i += 1
    return tags


def _union_field_tags(
    merged: MergeDict,
    name: str,
    flag: str,
    resolved: Any,
) -> dict[str, str]:
    """Return resolved class-tag entries for one union field in the merged config.

    A tag-spelled key is one only where it selects a variant (:func:`tag_selects_a_class`): a
    dict variant's entry is data, and a tag no variant is selected by is refused unimported.
    """
    tags: dict[str, str] = {}
    non_none = _union_args_no_none(resolved)
    if len(non_none) > 1:
        sub = merged.get(name)
        if isinstance(sub, dict) and _defaults.CLASS_KEY in sub and tag_selects_a_class(resolved):
            val = sub[_defaults.CLASS_KEY]
            if isinstance(val, str):
                tags[flag] = val
    elif len(non_none) == 1:
        sub = merged.get(name)
        if isinstance(sub, dict):
            tags.update(_tags_from_config(sub, _resolve_type(non_none[0]), flag))
    return tags


def _tags_from_config(
    merged: MergeDict,
    target: Any,
    prefix: str,
) -> dict[str, str]:
    """Walk merged config in parallel with target; return ``{field_path: class_path}``."""
    tags: dict[str, str] = {}
    tp = _resolve_type(target)
    if not _is_struct(tp):
        return tags

    if isinstance(merged.get(_defaults.CLASS_KEY), str):
        tags[prefix] = merged[_defaults.CLASS_KEY]  # a tag on this struct itself, root included

    try:
        flds = _struct_fields(tp)
    except (ValueError, TypeError, NameError, AttributeError):
        return tags

    for name, ft in flds.items():
        flag = f"{prefix}.{name}" if prefix else name
        resolved = _resolve_type(ft)
        if _is_union(resolved):
            tags.update(_union_field_tags(merged, name, flag, resolved))
        elif _is_struct(resolved):
            # The data says where to look: a key it does not hold holds no tag, and
            # descending into one as {} never ends on a type that holds itself.
            sub = merged.get(name)
            if isinstance(sub, dict):
                tags.update(_tags_from_config(sub, resolved, flag))

    return tags


def collect_tags(
    argv: Sequence[str],
    target: Any,
    *,
    config_flag: str,
    below: MergeDict | None = None,
    cli_prefix: str = "",
) -> dict[str, str]:
    """Return ``{field_path: class_path}`` for every class key argv names, directly or in a file.

    argv wins over a config file for the same field path, as everywhere else. *below*, what
    the layers below argv hold, stands for its ``--config`` files when given: it holds them.
    argv's flags are read below *cli_prefix*, which is stripped first; a flag outside it is
    the host's, and names nothing.
    """
    # Imported here: _parse_cli imports this module.
    from confarg._parse_cli import _strip_argv_prefix  # noqa: PLC0415  # import cycle: _parse_cli imports this module

    argv = _strip_argv_prefix(argv, cli_prefix)
    config_tags: dict[str, str] = {}
    if below is not None:
        config_tags = _tags_from_config(below, target, "")
    elif config_flag:
        config_dict = _partial_config_from_argv(argv, config_flag)
        if config_dict:
            config_tags = _tags_from_config(config_dict, target, "")
    argv_tags = {
        field_path: class_path
        for field_path, class_path in _tags_from_argv(argv).items()
        if _argv_tag_may_select_a_class(target, field_path)
    }
    return {**config_tags, **argv_tags}


def _argv_tag_may_select_a_class(target: Any, field_path: str) -> bool:
    """Return True unless every way the type walk reaches *field_path* holds its class flag as no class's tag.

    The argv scan is lexical, so it cannot tell a class key from a dict's entry or a leaf's
    refused tag spelled like it; the type walk can, and asks :func:`tag_selects_a_class` of
    each way, as construction asks it of the node it builds. Each way is asked apart, never
    their common type: a union whose variants type the path apart builds the one the data
    picks, so a tag any of them reads as a class may select one. A way below an untyped spec,
    and a path no way reaches, which a subclass nobody imported yet may declare, keep the tag.
    """
    # Imported here: _parse_cli imports this module.
    from confarg._parse_cli import _walk_path  # noqa: PLC0415  # import cycle: _parse_cli imports this module

    parts = field_path.split(".") if field_path else []
    states = _walk_path(target, parts).end_states()
    return not states or any(state.str_subtree or tag_selects_a_class(state.reached) for state in states)


def import_tagged_classes(
    argv: Sequence[str],
    target: Any,
    *,
    config_flag: str,
    below: MergeDict | None = None,
    cli_prefix: str = "",
) -> None:
    """Import every class the configuration names by its class key, ignoring failures.

    Call before anything reads ``__subclasses__()``: a subclass is invisible to the type walk
    and to CLI path resolution until its module has run, and the tag is the only thing that
    says which module that is.  A bad class path is *not* reported here — the authoritative
    import happens later in ``construct``, which raises
    :class:`~confarg.exceptions.SymbolImportError` naming it.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-named-tag-is-imported-before-registration.md#a-named-tag-is-imported-before-registration
    """
    for class_path in collect_tags(argv, target, config_flag=config_flag, below=below, cli_prefix=cli_prefix).values():
        # Importing an arbitrary module runs its top level, which can raise anything at all.
        with contextlib.suppress(Exception):
            _import_dotted(class_path)
