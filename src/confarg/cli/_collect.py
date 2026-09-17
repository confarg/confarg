# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Collect CLI-provided values from a flat ``{dotted.flag: value}`` dict into a nested dict.

Backend-neutral: every CLI adapter (argparse, click, cyclopts) first flattens its
framework-specific parse result into a plain dict of dotted flag names, then calls
:func:`_collect_ns_fields` to walk the target type and copy matching entries into
the nested structure expected by the merge pipeline.  The result must equal what the
vanilla parser produces for the same argv.

Dev Notes:
    docs-dev/architecture/04-cli-adapters.md#byte-identical-merged-dicts
"""

from __future__ import annotations

import os
import sys
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

from confarg import _defaults
from confarg._api import build
from confarg._callable import _ESCAPED_DIRECTIVES, _PLAIN_DIRECTIVES, _Directives, active_directives, promote_bare_spec
from confarg._cast import JSON_CAST_NAME, SCALAR_CAST_TYPES, resolve_forced_value
from confarg._import import _import_dotted
from confarg._merge import _deep_merge, _set_nested
from confarg._parse_cli import (
    _accepts_object_value,
    _collect_cli_patch_ops,
    _collect_config_file_pairs,
    _parse_json_arg,
    _segment_names_real_field,
    _try_parse_json_list,
)
from confarg._pipeline import _merge_sources
from confarg._tags import collect_tags
from confarg._types import (
    _elem_type,
    _is_callable,
    _is_dict,
    _is_namedtuple,
    _is_struct,
    _is_struct_like,
    _is_union,
    _is_varlen_collection,
    _namedtuple_fields,
    _resolve_struct,
    _resolve_type,
    _StrToken,
    _union_args_no_none,
    _union_has_scalar_variant,
    _union_has_varlen_variant,
    _UnionSeqToken,
    _unwrap_optional,
)
from confarg.cli._prefix import strip_argv_prefix, strip_flat_prefix
from confarg.exceptions import ConfargError, SymbolImportError
from confarg.typedload._coerce import _is_registered_leaf, _try_coerce

#: Sentinel distinguishing "no cast flag present" from a cast that legitimately
#: resolves to ``None`` (e.g. ``--foo.json null``).
_NO_CAST: Any = object()


def _coerce_scalar(tp: Any, v: Any) -> Any:
    """Eagerly coerce a single CLI string value to its field type, mirroring _parse_cli.

    Non-strings pass through unchanged.  Multi-variant unions, dicts, ``Any``, and
    unknown types fall through to a bare :class:`_StrToken` (coercion deferred to
    ``construct()``), exactly as :func:`_try_coerce` does for the vanilla path.
    """
    if not isinstance(v, str):
        return v
    token = _StrToken(v)
    return _try_coerce(tp, token) if tp is not None else token


def _json_array_override(v: Any) -> list[Any] | None:
    """Return a parsed list when a collection field's value is a lone JSON-array token.

    A ``nargs="*"`` flag delivers a single inline JSON array (``['[1, 2]']``) as a
    one-element list holding the raw string. Parsed with the vanilla
    ``_try_parse_json_list`` and returned raw (plain values, not ``_StrToken``), as
    vanilla stores it.
    """
    if isinstance(v, list) and len(v) == 1 and isinstance(v[0], str) and v[0].startswith("["):
        return _try_parse_json_list(v[0])
    return None


def _coerce_leaf_value(core: Any, v: Any) -> Any:
    """Eagerly coerce a CLI leaf value (scalar or list) to its field type, as vanilla does."""
    parsed = _json_array_override(v)
    if parsed is not None:
        return parsed
    if isinstance(v, list):
        et = _elem_type(core) if _is_varlen_collection(core) else None
        return [_coerce_scalar(et, item) for item in v]
    return _coerce_scalar(core, v)


def _collect_union_seq_value(resolved: Any, v: Any, flag: str) -> Any:
    """Shape a multi-variant union's CLI value, mirroring the vanilla parse path.

    A framework-provided single-element list collapses to a bare scalar when the
    union has a scalar variant (so ``--input foo`` stays ``'foo'``), marked with
    ``_UnionSeqToken`` so ``construct`` can fall back to a one-element list if no
    scalar variant accepts it (e.g. ``--input hello`` for ``bool | list[str]`` →
    ``['hello']``); otherwise the str-tokenized list (or scalar) is returned
    unchanged.

    An empty list raises ``ConfargError`` when the union has no varlen variant
    (e.g. ``str | tuple[str, str]``), like vanilla's ``_consume_union_seq_args``.
    """
    parsed = _json_array_override(v)
    if parsed is not None:
        return parsed
    if isinstance(v, list):
        if not v and not _union_has_varlen_variant(resolved):
            token = f"--{flag}"
            msg = f"Missing value for {token!r}. Usage: {token} <value>"
            raise ConfargError(msg)
        if len(v) == 1 and _union_has_scalar_variant(resolved):
            return _UnionSeqToken(v[0]) if isinstance(v[0], str) else v[0]
        return [_str_token(item) for item in v]
    return _str_token(v)


def _find_scalar_cast_override(flat: dict[str, Any], flag: str) -> Any:
    """Return the pinned value for an explicit scalar cast flag, or ``_NO_CAST`` if absent.

    Recognizes ``flag.str``/``flag.int``/``flag.float``/``flag.bool`` via the shared
    :func:`resolve_forced_value`.  ``.json`` is handled for every field type in
    :func:`_collect_ns_fields`, not here.
    """
    for cast_name in SCALAR_CAST_TYPES:
        raw = flat.get(f"{flag}.{cast_name}")
        if raw is not None:
            return resolve_forced_value(cast_name, raw, flag=f"--{flag}.{cast_name}")
    return _NO_CAST


def _find_json_cast(flat: dict[str, Any], flag: str, field_type: Any, union_tag: str) -> Any:
    """Return the decoded value for a ``flag.json`` cast, or ``_NO_CAST`` if it does not apply.

    ``.json`` applies to any field type *unless* ``json`` names a real member of
    ``field_type`` (a struct/namedtuple field, or a dict key), in which case the real
    field wins and ``flag.json`` is an ordinary sub-path handled by the type walk.
    """
    raw = flat.get(f"{flag}.{JSON_CAST_NAME}")
    if raw is None or _segment_names_real_field(field_type, JSON_CAST_NAME, union_tag):
        return _NO_CAST
    return resolve_forced_value(JSON_CAST_NAME, raw, flag=f"--{flag}.{JSON_CAST_NAME}")


def apply_root_json(flat: dict[str, Any], target: Any, union_tag: str, result: dict[str, Any]) -> None:
    """Fold a root-level ``--json`` object into ``result`` as a base, in place.

    The mirror of the vanilla ``_handle_root_cast`` root fold: a bare ``--json`` injects
    the whole config, but per-field CLI flags (already collected into ``result``) win, so
    the decoded object is deep-merged *underneath* ``result``.  A real root field named
    ``json`` wins over the cast (same rule as :func:`_find_json_cast`).  The decoded value
    must be a JSON object for a structured target; for a non-struct (scalar) root it
    becomes ``__root__`` whatever its shape.  Called once at the top level by each
    adapter's context builder.
    """
    raw = flat.get(JSON_CAST_NAME)
    if raw is None or _segment_names_real_field(target, JSON_CAST_NAME, union_tag):
        return
    decoded = resolve_forced_value(JSON_CAST_NAME, raw, flag=f"--{JSON_CAST_NAME}")
    if not _is_struct_like(_resolve_type(target)):
        # Non-struct root: the decoded value *is* the configuration, whatever its
        # shape, as in vanilla's _handle_root_cast. setdefault keeps the bare
        # `--<cli_prefix>` flag winning, the same way the deep merge below lets
        # per-field flags win over the injected object.
        result.setdefault(_defaults.ROOT_KEY, decoded)
        return
    if not isinstance(decoded, dict):
        msg = f"--{JSON_CAST_NAME} for a structured target must be a JSON object, got {type(decoded).__name__}."
        raise ConfargError(msg)
    merged = _deep_merge(decoded, result, union_tag=union_tag)
    result.clear()
    result.update(merged)


def _str_token(v: Any) -> Any:
    """Wrap str in _StrToken; pass through non-str unchanged."""
    return _StrToken(v) if isinstance(v, str) else v


def _fixed_arity_whole_value(v: Any, core: Any, flag: str) -> Any:
    """Decode the lone whole-value token of a fixed-arity flag, or return :data:`_NO_CAST`.

    A ``FlagSpec.whole_value`` flag registers greedily, so the framework hands its single
    ``'[13, 42]'`` / ``'{"x": 13}'`` token over as a one-element list.  Both halves defer to
    the decoders the other branches use -- :func:`_json_array_override` for the array,
    :func:`_accepts_object_value` plus :func:`_parse_json_arg` for the object -- so a
    fixed-arity field cannot drift from what vanilla decodes for the same token.

    Dev Notes:
        docs-dev/architecture/04-cli-adapters.md#whole-value-flags
    """
    parsed = _json_array_override(v)
    if parsed is not None:
        return parsed
    if isinstance(v, list) and len(v) == 1 and isinstance(v[0], str):
        token = v[0]
        if token.startswith("{") and _accepts_object_value(core):
            return _parse_json_arg(token, f"--{flag}")
    return _NO_CAST


def _whole_value(flat: dict[str, Any], flag: str, resolved: Any) -> Any:
    """Return the bare ``--<flag>`` value decoded the way the vanilla parser decodes it.

    A ``{``-prefixed token becomes the object it spells (malformed JSON raises the same
    ``ConfargError`` vanilla raises); anything else is left for the caller's own branch.
    Returns :data:`_NO_CAST` when the flag carries no whole value to decode.

    Dev Notes:
        docs-dev/architecture/04-cli-adapters.md#whole-value-flags
    """
    if flag not in flat:
        return _NO_CAST
    v = flat[flag]
    if isinstance(v, str) and v.startswith("{") and _accepts_object_value(resolved):
        return _parse_json_arg(v, f"--{flag}")
    return _NO_CAST


def _merge_blob_into_spec(
    blob: dict[str, Any],
    spec: dict[str, Any],
    bind: dict[str, Any],
    bind_key: str,
) -> dict[str, Any]:
    """Merge a pre-existing blob dict with the newly assembled spec, combining bind entries."""
    merged = {**blob, **{k: v for k, v in spec.items() if k != bind_key}}
    blob_bind = blob.get(bind_key, {})
    if isinstance(blob_bind, dict) and bind:
        merged[bind_key] = {**blob_bind, **bind}
    elif bind:
        merged[bind_key] = bind
    return merged


def _collect_fn_identity(flat: dict[str, Any], flag: str, d: _Directives) -> dict[str, Any]:
    """Extract fn/class/call identity entries from flat into a spec dict.

    Keyed by the *active* (plain or escaped) directive names, as in a config file.
    """
    spec: dict[str, Any] = {}
    for name in d.openers:
        src_key = f"{flag}.{name}"
        if src_key in flat:
            spec[name] = _str_token(flat[src_key])
    return spec


def _collect_factory_kwargs(
    flat: dict[str, Any],
    flag_prefix: str,
    bind_prefix: str,
    reserved: set[str],
) -> dict[str, Any]:
    """Collect top-level factory kwargs (positional result fields) from flat namespace."""
    kwargs: dict[str, Any] = {}
    for k, v in flat.items():
        if k.startswith(flag_prefix) and k not in reserved and not k.startswith(bind_prefix):
            tail = k[len(flag_prefix) :]
            if "." not in tail:
                kwargs[tail] = _str_token(v)
    return kwargs


def _collect_bind_sections(flat: dict[str, Any], flag: str, d: _Directives) -> dict[str, dict[str, Any]]:
    """Nest the ``--<flag>.<bind>.<path>`` entries of the flat namespace, one dict per spelling.

    Both spellings are collected: the active one is the directive, and the one the opener
    left inactive is a kwarg, not a directive — but still a subtree, which construction
    is the one to accept or reject.  Neither depends on an opener being present, and
    dotted tails nest, so the sections match what the vanilla parser writes for the very
    same flags.

    Dev Notes:
        docs-dev/architecture/06-callables.md#plain-and-escaped-directives
    """
    other = _PLAIN_DIRECTIVES.bind if d.bind == _ESCAPED_DIRECTIVES.bind else _ESCAPED_DIRECTIVES.bind
    sections: dict[str, dict[str, Any]] = {}
    for key in (d.bind, other):
        prefix = f"{flag}.{key}."
        subtree: dict[str, Any] = {}
        for k, v in flat.items():
            if k.startswith(prefix):
                _set_nested(subtree, k[len(prefix) :].split("."), _str_token(v))
        if subtree:
            sections[key] = subtree
    return sections


def _collect_callable_spec(
    flat: dict[str, Any],
    flag: str,
    result: dict[str, Any],
    whole: Any = _NO_CAST,
) -> None:
    """Build and store the callable spec dict from flat namespace entries for flag.

    Directive flags come in a plain and an escaped (single-underscore) form; the opener
    selects the mode via :func:`~confarg._callable.active_directives`.  An opener spelled
    inside the whole-value blob counts as one: vanilla deep-merges the blob and its
    sibling flags into a single spec before anything reads an opener, so a blob's
    ``class`` must buy its sibling ``--<field>.<param>`` init kwargs exactly as the
    ``--<field>.class`` flag does.
    """
    blob = (flat[flag] if whole is _NO_CAST else whole) if flag in flat else _NO_CAST
    blob_keys: dict[str, Any] = blob if isinstance(blob, dict) else {}

    def _has(name: str) -> bool:
        return f"{flag}.{name}" in flat or name in blob_keys

    d = active_directives(_has)
    bind_prefix = f"{flag}.{d.bind}."
    flag_prefix = f"{flag}."
    reserved = {f"{flag}.{name}" for name in d.openers}

    spec = _collect_fn_identity(flat, flag, d)

    spec.update(_collect_bind_sections(flat, flag, d))
    bind: dict[str, Any] = spec.get(d.bind, {})

    # Sibling --<field>.<param> flags are init kwargs when a class/fn identity is given:
    # 'class:' instantiates with them; 'fn: Class.method' constructs the method's owning
    # class with them. (Plain 'fn: Class' factories carry their args under bind instead.)
    if _has(d.cls) or _has(d.fn):
        spec.update(_collect_factory_kwargs(flat, flag_prefix, bind_prefix, reserved))

    if blob is not _NO_CAST:
        if isinstance(blob, str):
            if not spec:
                _set_nested(result, flag.split("."), _StrToken(blob))
                return
            # The bare string is the shorthand for {fn: <string>}, so the sibling flags
            # refine the target it names instead of erasing it.  An opener flag is not a
            # refinement but a second spelling of that target, and still wins outright.
            if not any(_has(opener) for opener in d.openers):
                # Opener first, as the vanilla parser writes it: the merged dicts must
                # match key for key, not just compare equal.
                spec = {**promote_bare_spec(_StrToken(blob)), **spec}
        elif isinstance(blob, dict):
            spec = _merge_blob_into_spec(blob, spec, bind, d.bind)

    if spec:
        _set_nested(result, flag.split("."), spec)


def _collect_ns_union_field(  # noqa: PLR0913  # the type-walk context, threaded whole
    flat: dict[str, Any],
    flag: str,
    resolved: Any,
    union_tag: str,
    result: dict[str, Any],
    tags: Mapping[str, str],
) -> None:
    """Handle a multi-variant union field.

    When the class-tag is present, recurse only into the named variant.
    When it is absent, collect all struct variant fields so structural inference
    in typedload can select the right one.
    """
    non_none = _union_args_no_none(resolved)
    concrete = [_resolve_type(v) for v in non_none if _is_struct(_resolve_type(v))]
    if not concrete:
        return
    tag_key = f"{flag}.{union_tag}"
    if tag_key in flat:
        class_tag = flat[tag_key]
        _set_nested(result, [*flag.split("."), union_tag], _str_token(class_tag))
        try:
            cls = _import_dotted(str(class_tag))
            if isinstance(cls, type) and _is_struct(_resolve_type(cls)):
                _collect_ns_fields(flat, cls, flag, union_tag, result, tags)
        except (SymbolImportError, TypeError, ValueError, NameError, AttributeError):
            pass
    else:
        for variant in concrete:
            _collect_ns_fields(flat, variant, flag, union_tag, result, tags)


def _collect_ns_inheritance(  # noqa: PLR0913  # the type-walk context, threaded whole
    flat: dict[str, Any],
    tp: Any,
    prefix: str,
    union_tag: str,
    result: dict[str, Any],
    tags: Mapping[str, str],
) -> None:
    """Handle inheritance dispatch for a base class with subclasses.

    The subclass to descend into is whichever the configuration names at this path -- a
    ``--<path>.<union_tag>`` flag in *flat*, or a tag a ``--config`` file sets, which
    *tags* carries (`cls is not tp` then stops the recursion).  Only the flag is written
    back into *result*: a file's tag already reaches the merge at its own priority, and
    re-emitting it at CLI priority would make the merged dict differ from vanilla's.

    Dev Notes:
        docs-dev/architecture/04-cli-adapters.md#union-inheritance-and-cast-flags
    """
    tag_key = f"{prefix}.{union_tag}" if prefix else union_tag
    from_flat = tag_key in flat
    class_tag = flat[tag_key] if from_flat else tags.get(prefix)
    if class_tag is None:
        return
    try:
        cls = _import_dotted(str(class_tag))
        if isinstance(cls, type) and _is_struct(_resolve_type(cls)) and cls is not tp:
            if from_flat:
                tag_path = ([*prefix.split(".")] if prefix else []) + [union_tag]
                _set_nested(result, tag_path, _str_token(class_tag))
            _collect_ns_fields(flat, cls, prefix, union_tag, result, tags)
    except (SymbolImportError, TypeError, ValueError, NameError, AttributeError):
        pass


def _namedtuple_sub_flags(flat: dict[str, Any], flag: str, field_names: list[str]) -> dict[str, Any]:
    """Collect a namedtuple's per-name and per-index sub-flags, name winning over index."""
    sub: dict[str, Any] = {}
    for i, fname in enumerate(field_names):
        for key in (f"{flag}.{fname}", f"{flag}.{i}"):
            if flat.get(key) is not None:
                sub[fname] = _str_token(flat[key])
                break
    return sub


def _namedtuple_arity_value(nargs_value: Any, whole: Any) -> Any:
    """Return what the arity flag alone supplies: the decoded whole value, or its tokens."""
    if whole is not _NO_CAST:
        return whole
    if isinstance(nargs_value, list):
        return [_str_token(item) for item in nargs_value]
    return _str_token(nargs_value)


def _collect_ns_namedtuple(
    flat: dict[str, Any],
    core: Any,
    flag: str,
    result: dict[str, Any],
) -> None:
    """Collect a namedtuple field from the flat namespace.

    Priority per field: field-name sub-flag > index sub-flag > arity-flag position.
    When sub-flags and the arity flag are both set, sub-flags override specific
    positions and the arity value fills the rest — they are merged, not exclusive.
    A lone whole-value token refines the same way, by name when it spells an object
    and by position when it spells an array.

    Dev Notes:
        docs-dev/architecture/04-cli-adapters.md#whole-value-flags
    """
    field_names = list(_namedtuple_fields(core))
    sub = _namedtuple_sub_flags(flat, flag, field_names)
    nargs_value = flat.get(flag)
    path = flag.split(".")

    if nargs_value is None:
        if sub:
            _set_nested(result, path, sub)
        return

    whole = _fixed_arity_whole_value(nargs_value, core, flag)

    if not sub:
        # Store what the flag spelled and let build() judge its arity, as the same-arity
        # tuple field does — the framework no longer counts the tokens for us.
        _set_nested(result, path, _namedtuple_arity_value(nargs_value, whole))
        return

    if isinstance(whole, dict):
        _set_nested(result, path, {**whole, **sub})
        return

    value = _namedtuple_arity_value(nargs_value, whole)
    base = value if isinstance(value, list) else [value]
    merged: dict[str, Any] = {}
    for i, fname in enumerate(field_names):
        if fname in sub:
            merged[fname] = sub[fname]
        elif i < len(base):
            merged[fname] = base[i]
    _set_nested(result, path, merged)


def _collect_ns_union_root(  # noqa: PLR0913  # the type-walk context, threaded whole
    flat: dict[str, Any],
    variants: list[Any],
    prefix: str,
    union_tag: str,
    result: dict[str, Any],
    tags: Mapping[str, str],
) -> None:
    """Collect CLI values for a root-level union target (variants are concrete struct types)."""
    tag_key = f"{prefix}.{union_tag}" if prefix else union_tag
    if tag_key in flat:
        tag_path = ([*prefix.split(".")] if prefix else []) + [union_tag]
        _set_nested(result, tag_path, _str_token(flat[tag_key]))
    for variant in variants:
        _collect_ns_fields(flat, variant, prefix, union_tag, result, tags)


def _collect_ns_fields(  # noqa: C901, PLR0912, PLR0913, PLR0915  # one branch per type case
    flat: dict[str, Any],
    target: Any,
    prefix: str,
    union_tag: str,
    result: dict[str, Any],
    tags: Mapping[str, str] = MappingProxyType({}),
) -> None:
    """Walk target and copy matching flat-namespace entries into nested dict.

    *tags* is ``{field_path: class_path}`` for every class tag the configuration names
    outside *flat* -- a ``--config`` file's, typically -- so inheritance dispatch sees the
    same subclass the vanilla type walk does.
    """
    setup = _resolve_struct(target)
    if setup is None:
        tp = _resolve_type(target)
        if _is_union(tp):
            non_none = _union_args_no_none(tp)
            concrete = [_resolve_type(v) for v in non_none if _is_struct(_resolve_type(v))]
            if concrete:
                _collect_ns_union_root(flat, concrete, prefix, union_tag, result, tags)
                return
        if "" in flat:
            # Non-struct root: the empty key is the bare `--<cli_prefix>` flag, left
            # behind by strip_flat_prefix. Mirrors vanilla's _handle_scalar_root.
            result[_defaults.ROOT_KEY] = _coerce_scalar(tp, flat[""])
        return
    _tp, flds, hints = setup

    for name in flds:
        if name == union_tag:
            continue

        raw_type = hints.get(name, Any)
        resolved = _resolve_type(raw_type)
        flag = f"{prefix}.{name}" if prefix else name

        core = _unwrap_optional(resolved)

        # `--flag.json` forces a raw-JSON value for any field type, unless `json` names a
        # real member of the field (real field wins). Handled before the type dispatch so
        # struct/namedtuple/callable/collection fields honour it too.
        json_val = _find_json_cast(flat, flag, core if core is not None else resolved, union_tag)
        if json_val is not _NO_CAST:
            _set_nested(result, flag.split("."), json_val)
            continue

        # A bare `--<flag> '{...}'` assigns the whole field; sibling `--<flag>.<sub>`
        # entries are collected on top of it below, as they refine it in vanilla.
        whole = _whole_value(flat, flag, resolved)

        if core is None:
            # Struct unions: the whole object carries its own class-tag; variant fields refine it
            if whole is not _NO_CAST:
                _set_nested(result, flag.split("."), whole)
            _collect_ns_union_field(flat, flag, resolved, union_tag, result, tags)
            # Scalar unions: collect plain value or explicit scalar cast
            cast_val = _find_scalar_cast_override(flat, flag)
            if cast_val is not _NO_CAST:
                _set_nested(result, flag.split("."), cast_val)
            elif flag in flat and whole is _NO_CAST:
                _set_nested(result, flag.split("."), _collect_union_seq_value(resolved, flat[flag], flag))
            continue

        if _is_namedtuple(core):
            _collect_ns_namedtuple(flat, core, flag, result)
            continue

        if _is_registered_leaf(core):
            if flag in flat:
                _set_nested(result, flag.split("."), _coerce_leaf_value(core, flat[flag]))
            continue

        if _is_struct(core):
            if whole is not _NO_CAST:
                _set_nested(result, flag.split("."), whole)
            _collect_ns_fields(flat, core, flag, union_tag, result, tags)
            continue

        if _is_dict(core):
            # Keys are collected by the argv patch scan and deep-merged over this value.
            if whole is not _NO_CAST:
                _set_nested(result, flag.split("."), whole)
            elif flag in flat:
                _set_nested(result, flag.split("."), _coerce_leaf_value(core, flat[flag]))
            continue

        if _is_callable(core):
            _collect_callable_spec(flat, flag, result, whole)
            continue

        cast_val = _find_scalar_cast_override(flat, flag)
        if cast_val is not _NO_CAST:
            _set_nested(result, flag.split("."), cast_val)
        elif flag in flat:
            _set_nested(result, flag.split("."), _coerce_leaf_value(core, flat[flag]))

    _collect_ns_inheritance(flat, _tp, prefix, union_tag, result, tags)


def _merge_from_flat(  # noqa: PLR0913  # mirrors confarg.merge's keyword-only signature
    flat: dict[str, Any],
    target: object,
    *,
    argv: Sequence[str] | None,
    env: Mapping[str, str] | None,
    env_prefix: str | None,
    env_separator: str,
    cli_prefix: str,
    config_flag: str,
    files: Sequence[str | Path],
    env_config: str | None,
    union_tag: str,
) -> dict[str, Any]:
    """Merge every source into a raw dict, starting from an adapter's flat parse result.

    The shared tail of ``merge_namespace`` / ``merge_context`` / ``merge_app``: each
    adapter flattens its framework's parse result to ``{dotted.flag: value}`` and hands
    it here, so the three cannot drift.  Patch ops and ``--config`` ordering are read
    from *argv* rather than from *flat*, because a framework's parse result carries no
    command-line order.

    Args:
        flat: The adapter's parse result as ``{dotted.flag: value}``.
        target: The target type, used to guide the type walk.
        argv: CLI arguments to rescan for patch ops and config-file order.
            ``None`` means ``sys.argv[1:]``.
        env: Environment variable mapping; ``None`` means ``os.environ``.
        env_prefix: Prefix that env vars must start with.
        env_separator: Separator splitting env var names into nested keys.
        cli_prefix: Namespace the flags were registered under; stripped from both
            *flat* and *argv* so everything downstream stays prefix-blind.
        config_flag: Flag name used to specify config files.
        files: Config file paths to load at lowest priority.
        env_config: Name of an env var holding a config file path.
        union_tag: Field name used as a discriminator tag in unions.

    Returns:
        A plain dict of the merged configuration, with expression strings intact.

    Dev Notes:
        docs-dev/architecture/04-cli-adapters.md#the-triad
    """
    if env is None:
        env = os.environ

    # Strip the prefix at both inputs, so the type walk and the argv rescan below
    # resolve paths against *target* alone
    # (docs-dev/architecture/03-cli-parsing.md#cli_prefix).
    flat = strip_flat_prefix(flat, cli_prefix)

    # Patch ops, --config order and the class tags are read from argv, not the framework's
    # parse result (docs-dev/architecture/04-cli-adapters.md#collection-patch-parity).
    argv_ = sys.argv[1:] if argv is None else list(argv)
    argv_ = strip_argv_prefix(argv_, cli_prefix)

    # The same scan registration uses, so a tag a --config file sets steers the type walk
    # here exactly as it steers vanilla's
    # (docs-dev/architecture/04-cli-adapters.md#union-inheritance-and-cast-flags).
    tags = collect_tags(argv_, target, union_tag=union_tag, config_flag=config_flag)

    cli_data: dict[str, Any] = {}
    _collect_ns_fields(flat, target, prefix="", union_tag=union_tag, result=cli_data, tags=tags)

    cli_data = _deep_merge(cli_data, _collect_cli_patch_ops(argv_, target, config_flag, union_tag))
    apply_root_json(flat, target, union_tag, cli_data)  # fold root `--json` under collected fields
    cli_configs = _collect_config_file_pairs(argv_, config_flag) if config_flag else []

    return _merge_sources(
        target,
        cli_data,
        cli_configs,
        env=env,
        env_prefix=env_prefix,
        env_separator=env_separator,
        config_flag=config_flag,
        files=files,
        env_config=env_config,
        union_tag=union_tag,
    )


def _construct_from_merged(target: object, merged: dict[str, Any], union_tag: str) -> Any:
    """Construct *target* from an already-merged dict; the shared tail of every ``from_*``."""
    return build(target, merged, union_tag=union_tag)
