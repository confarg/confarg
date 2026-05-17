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

from confarg._import import _import_dotted
from confarg._merge import _set_nested
from confarg._types import (
    _callable_return_type,
    _is_callable,
    _is_dict,
    _is_namedtuple,
    _is_struct,
    _is_union,
    _namedtuple_fields,
    _Pinned,
    _resolve_struct,
    _resolve_type,
    _StrToken,
    _union_args_no_none,
    _unwrap_optional,
)
from confarg.exceptions import SymbolImportError
from confarg.typedload._coerce import _is_registered_leaf

_CAST_TYPES: dict[str, type] = {"str": str, "int": int, "float": float, "bool": bool}


def _find_cast_override(flat: dict[str, Any], flag: str) -> _Pinned | None:
    """Check for explicit cast flags (e.g. ``flag.str``, ``flag.int``) in flat namespace."""
    for cast_name, tp in _CAST_TYPES.items():
        val = flat.get(f"{flag}.{cast_name}")
        if val is not None:
            return _Pinned(tp, _StrToken(val))
    return None


def _str_token(v: Any) -> Any:
    """Wrap str in _StrToken; pass through non-str unchanged."""
    return _StrToken(v) if isinstance(v, str) else v


def _merge_blob_into_spec(blob: dict[str, Any], spec: dict[str, Any], bind: dict[str, Any]) -> dict[str, Any]:
    """Merge a pre-existing blob dict with the newly assembled spec, combining bind entries."""
    merged = {**blob, **{k: v for k, v in spec.items() if k != "bind"}}
    blob_bind = blob.get("bind", {})
    if isinstance(blob_bind, dict) and bind:
        merged["bind"] = {**blob_bind, **bind}
    elif bind:
        merged["bind"] = bind
    return merged


def _collect_fn_identity(
    flat: dict[str, Any],
    fn_key: str,
    cls_key: str,
    call_key: str,
) -> dict[str, Any]:
    """Extract fn/class/call identity entries from flat into a spec dict."""
    spec: dict[str, Any] = {}
    for src_key, dest_name in ((fn_key, "fn"), (cls_key, "class"), (call_key, "call")):
        if src_key in flat:
            spec[dest_name] = _str_token(flat[src_key])
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
    core: Any,
    result: dict[str, Any],
) -> None:
    """Build and store the callable spec dict from flat namespace entries for flag."""
    fn_key = f"{flag}.fn"
    cls_key = f"{flag}.class"
    call_key = f"{flag}.call"
    bind_prefix = f"{flag}.bind."
    flag_prefix = f"{flag}."
    reserved = {fn_key, cls_key, call_key}

    spec = _collect_fn_identity(flat, fn_key, cls_key, call_key)

    bind: dict[str, Any] = {k[len(bind_prefix) :]: _str_token(v) for k, v in flat.items() if k.startswith(bind_prefix)}
    if bind:
        spec["bind"] = bind

    ret = _callable_return_type_for(core)
    if (ret is not None and isinstance(ret, type) and ret is not type(None)) or cls_key in flat or fn_key in flat:
        spec.update(_collect_factory_kwargs(flat, flag_prefix, bind_prefix, reserved))

    if flag in flat:
        blob = flat[flag]
        if isinstance(blob, str) and not spec:
            _set_nested(result, flag.split("."), _StrToken(blob))
            return
        if isinstance(blob, dict):
            spec = _merge_blob_into_spec(blob, spec, bind)

    if spec:
        _set_nested(result, flag.split("."), spec)


def _callable_return_type_for(core: Any) -> Any | None:
    """Return the return type of a Callable type hint, or None."""
    return _callable_return_type(core)


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


def _collect_ns_fields(  # noqa: C901, PLR0912, PLR0915  # one branch per type case
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
        if core is None:
            # Struct unions: collect via class-tag
            _collect_ns_union_field(flat, flag, resolved, union_tag, result)
            # Scalar unions: collect plain value or explicit cast
            cast_val = _find_cast_override(flat, flag)
            if cast_val is not None:
                _set_nested(result, flag.split("."), cast_val)
            elif flag in flat:
                v = flat[flag]
                v = [_str_token(item) for item in v] if isinstance(v, list) else _str_token(v)
                _set_nested(result, flag.split("."), v)
            continue

        if _is_namedtuple(core):
            _collect_ns_namedtuple(flat, core, flag, result)
            continue

        if _is_registered_leaf(core):
            if flag in flat:
                v = flat[flag]
                v = [_str_token(item) for item in v] if isinstance(v, list) else _str_token(v)
                _set_nested(result, flag.split("."), v)
            continue

        if _is_struct(core):
            _collect_ns_fields(flat, core, flag, union_tag, result)
            continue

        if _is_dict(core):
            continue

        if _is_callable(core):
            _collect_callable_spec(flat, flag, core, result)
            continue

        cast_val = _find_cast_override(flat, flag)
        if cast_val is not None:
            _set_nested(result, flag.split("."), cast_val)
        elif flag in flat:
            v = flat[flag]
            v = [_str_token(item) for item in v] if isinstance(v, list) else _str_token(v)
            _set_nested(result, flag.split("."), v)

    _collect_ns_inheritance(flat, _tp, prefix, union_tag, result)
