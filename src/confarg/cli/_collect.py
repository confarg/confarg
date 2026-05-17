# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Collect CLI-provided values from a flat ``{dotted.flag: value}`` dict into a nested dict.

Backend-neutral: every CLI adapter (argparse, click, cyclopts) first flattens its
framework-specific parse result into a plain dict of dotted flag names, then calls
:func:`_collect_ns_fields` to walk the target type and copy matching entries into
the nested structure expected by the merge pipeline.
"""

from __future__ import annotations

from typing import Any

from confarg._callable import _Directives, active_directives
from confarg._cast import JSON_CAST_NAME, SCALAR_CAST_TYPES, resolve_forced_value
from confarg._import import _import_dotted
from confarg._merge import _deep_merge, _set_nested
from confarg._parse_cli import _segment_names_real_field, _try_parse_json_list
from confarg._types import (
    _elem_type,
    _is_callable,
    _is_dict,
    _is_namedtuple,
    _is_struct,
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
    one-element list holding the raw string. Routes through the same
    ``_try_parse_json_list`` the vanilla ``_consume_collection_or_scalar`` path uses,
    so the backends interpret it exactly as ``confarg.load`` does. The parsed list is
    returned raw (plain values, not ``_StrToken``) to match vanilla, which stores
    ``json.loads`` output verbatim — keeping JSON elements exempt from the stealing
    rule (e.g. ``"yes"`` stays a string rather than becoming ``True``).
    """
    if isinstance(v, list) and len(v) == 1 and isinstance(v[0], str) and v[0].startswith("["):
        return _try_parse_json_list(v[0])
    return None


def _coerce_leaf_value(core: Any, v: Any) -> Any:
    """Eagerly coerce a CLI leaf value (scalar or list) to its field type.

    Ensures the merged dict carries the same typed values as the vanilla
    ``confarg.load`` path, so expressions over CLI-provided numbers resolve and
    the four integrations produce byte-for-byte identical merged dicts.
    """
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
    unchanged. Keeps adapter merged dicts byte-identical to ``confarg.load``.

    An empty list raises ``ConfargError`` when the union has no varlen variant
    (e.g. ``str | tuple[str, str]``), matching vanilla's parse-time
    ``_consume_union_seq_args``: an empty list can build nothing valid for a
    fixed-tuple-only union, so the front-end rejects it instead of synthesizing a
    doomed value for ``construct`` to fail on later.
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
    :func:`resolve_forced_value`, so the adapter result is byte-identical to the vanilla
    ``_handle_force_cast`` path.  ``.json`` is handled uniformly for every field type in
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
    must be a JSON object for a structured target.  Called once at the top level by each
    adapter's context builder.
    """
    raw = flat.get(JSON_CAST_NAME)
    if raw is None or _segment_names_real_field(target, JSON_CAST_NAME, union_tag):
        return
    decoded = resolve_forced_value(JSON_CAST_NAME, raw, flag=f"--{JSON_CAST_NAME}")
    if not isinstance(decoded, dict):
        msg = f"--{JSON_CAST_NAME} for a structured target must be a JSON object, got {type(decoded).__name__}."
        raise ConfargError(msg)
    merged = _deep_merge(decoded, result, union_tag=union_tag)
    result.clear()
    result.update(merged)


def _str_token(v: Any) -> Any:
    """Wrap str in _StrToken; pass through non-str unchanged."""
    return _StrToken(v) if isinstance(v, str) else v


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

    Keyed by the *active* (plain or escaped) directive names so the produced spec is
    byte-identical to a config file and re-detected by ``_select_directives`` downstream.
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


def _collect_callable_spec(
    flat: dict[str, Any],
    flag: str,
    result: dict[str, Any],
) -> None:
    """Build and store the callable spec dict from flat namespace entries for flag.

    Directive flags come in a plain and an escaped (single-underscore) form; the opener
    present in the flat namespace selects the mode via the canonical
    :func:`~confarg._callable.active_directives`, so every produced key uses the active
    names and stays byte-identical to the config-file / vanilla paths.
    """
    d = active_directives(lambda name: f"{flag}.{name}" in flat)
    bind_prefix = f"{flag}.{d.bind}."
    flag_prefix = f"{flag}."
    reserved = {f"{flag}.{name}" for name in d.openers}

    spec = _collect_fn_identity(flat, flag, d)

    bind: dict[str, Any] = {k[len(bind_prefix) :]: _str_token(v) for k, v in flat.items() if k.startswith(bind_prefix)}
    if bind:
        spec[d.bind] = bind

    # Sibling --<field>.<param> flags are init kwargs when a class/fn identity is given:
    # 'class:' instantiates with them; 'fn: Class.method' constructs the method's owning
    # class with them. (Plain 'fn: Class' factories carry their args under bind instead.)
    # The old return-type-derived implicit form is gone, so a bare return type no longer
    # triggers collection.
    if f"{flag}.{d.cls}" in flat or f"{flag}.{d.fn}" in flat:
        spec.update(_collect_factory_kwargs(flat, flag_prefix, bind_prefix, reserved))

    if flag in flat:
        blob = flat[flag]
        if isinstance(blob, str) and not spec:
            _set_nested(result, flag.split("."), _StrToken(blob))
            return
        if isinstance(blob, dict):
            spec = _merge_blob_into_spec(blob, spec, bind, d.bind)

    if spec:
        _set_nested(result, flag.split("."), spec)


def _collect_ns_union_field(
    flat: dict[str, Any],
    flag: str,
    resolved: Any,
    union_tag: str,
    result: dict[str, Any],
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
                _collect_ns_fields(flat, cls, flag, union_tag, result)
        except (SymbolImportError, TypeError, ValueError, NameError, AttributeError):
            pass
    else:
        for variant in concrete:
            _collect_ns_fields(flat, variant, flag, union_tag, result)


def _collect_ns_inheritance(
    flat: dict[str, Any],
    tp: Any,
    prefix: str,
    union_tag: str,
    result: dict[str, Any],
) -> None:
    """Handle inheritance dispatch for a base class with subclasses.

    When the union_tag key is explicitly present in flat, recurse only into
    the named subclass (the `cls is not tp` guard prevents infinite recursion).
    When it is absent, collect fields for all direct struct subclasses so that
    structural inference in typedload can pick the right one.
    """
    tag_key = f"{prefix}.{union_tag}" if prefix else union_tag
    if tag_key in flat:
        class_tag = flat[tag_key]
        try:
            cls = _import_dotted(str(class_tag))
            if isinstance(cls, type) and _is_struct(_resolve_type(cls)) and cls is not tp:
                tag_path = ([*prefix.split(".")] if prefix else []) + [union_tag]
                _set_nested(result, tag_path, _str_token(class_tag))
                _collect_ns_fields(flat, cls, prefix, union_tag, result)
        except (SymbolImportError, TypeError, ValueError, NameError, AttributeError):
            pass


def _collect_ns_namedtuple(
    flat: dict[str, Any],
    core: Any,
    flag: str,
    result: dict[str, Any],
) -> None:
    """Collect a namedtuple field from the flat namespace.

    Priority per field: field-name sub-flag > index sub-flag > nargs position.
    When sub-flags and the nargs flag are both set, sub-flags override specific
    positions and the nargs value fills the rest — they are merged, not exclusive.
    """
    flds = _namedtuple_fields(core)
    field_names = list(flds.keys())

    # Collect individual sub-flags (by name and by index)
    sub: dict[str, Any] = {}
    for i, fname in enumerate(field_names):
        name_key = f"{flag}.{fname}"
        idx_key = f"{flag}.{i}"
        if name_key in flat and flat[name_key] is not None:
            sub[fname] = _str_token(flat[name_key])
        elif idx_key in flat and flat[idx_key] is not None:
            sub[fname] = _str_token(flat[idx_key])

    nargs_value = flat.get(flag)
    has_nargs = nargs_value is not None

    if not sub and not has_nargs:
        return

    if sub and has_nargs:
        # Merge: nargs provides the base, sub-flags override individual positions.
        nargs_list = nargs_value if isinstance(nargs_value, list) else [nargs_value]
        merged: dict[str, Any] = {}
        for i, fname in enumerate(field_names):
            if fname in sub:
                merged[fname] = sub[fname]
            elif i < len(nargs_list):
                merged[fname] = _str_token(nargs_list[i])
        _set_nested(result, flag.split("."), merged)
    elif sub:
        _set_nested(result, flag.split("."), sub)
    else:
        v = [_str_token(item) for item in nargs_value] if isinstance(nargs_value, list) else _str_token(nargs_value)
        _set_nested(result, flag.split("."), v)


def _collect_ns_union_root(
    flat: dict[str, Any],
    variants: list[Any],
    prefix: str,
    union_tag: str,
    result: dict[str, Any],
) -> None:
    """Collect CLI values for a root-level union target (variants are concrete struct types)."""
    tag_key = f"{prefix}.{union_tag}" if prefix else union_tag
    if tag_key in flat:
        tag_path = ([*prefix.split(".")] if prefix else []) + [union_tag]
        _set_nested(result, tag_path, _str_token(flat[tag_key]))
    for variant in variants:
        _collect_ns_fields(flat, variant, prefix, union_tag, result)


def _collect_ns_fields(  # noqa: C901, PLR0912  # one branch per type case
    flat: dict[str, Any],
    target: Any,
    prefix: str,
    union_tag: str,
    result: dict[str, Any],
) -> None:
    """Walk target and copy matching flat-namespace entries into nested dict."""
    setup = _resolve_struct(target)
    if setup is None:
        tp = _resolve_type(target)
        if _is_union(tp):
            non_none = _union_args_no_none(tp)
            concrete = [_resolve_type(v) for v in non_none if _is_struct(_resolve_type(v))]
            if concrete:
                _collect_ns_union_root(flat, concrete, prefix, union_tag, result)
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

        if core is None:
            # Struct unions: collect via class-tag
            _collect_ns_union_field(flat, flag, resolved, union_tag, result)
            # Scalar unions: collect plain value or explicit scalar cast
            cast_val = _find_scalar_cast_override(flat, flag)
            if cast_val is not _NO_CAST:
                _set_nested(result, flag.split("."), cast_val)
            elif flag in flat:
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
            _collect_ns_fields(flat, core, flag, union_tag, result)
            continue

        if _is_dict(core):
            continue

        if _is_callable(core):
            _collect_callable_spec(flat, flag, result)
            continue

        cast_val = _find_scalar_cast_override(flat, flag)
        if cast_val is not _NO_CAST:
            _set_nested(result, flag.split("."), cast_val)
        elif flag in flat:
            _set_nested(result, flag.split("."), _coerce_leaf_value(core, flat[flag]))

    _collect_ns_inheritance(flat, _tp, prefix, union_tag, result)
