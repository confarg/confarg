# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Value construction and union disambiguation."""

from __future__ import annotations

import inspect
from typing import Any

from confarg import _defaults
from confarg._callable import _resolve_callable_spec
from confarg._import import _import_dotted
from confarg._merge import LIST_APPEND_KEY, LIST_DELETE_KEY, LIST_REPLACE_BASE_KEY, _apply_list_ops
from confarg._types import (
    _all_have_defaults,
    _allows_none,
    _dict_kv,
    _elem_type,
    _is_callable,
    _is_dict,
    _is_frozenset,
    _is_list,
    _is_literal,
    _is_namedtuple,
    _is_set,
    _is_struct,
    _is_tuple,
    _is_type_ref,
    _is_union,
    _literal_values,
    _namedtuple_defaults,
    _namedtuple_fields,
    _Pinned,
    _resolve_type,
    _StrToken,
    _struct_defaults,
    _struct_fields,
    _tuple_types,
    _union_args,
    _union_args_no_none,
    _UnionSeqToken,
    _var_keyword_name,
    _var_positional_name,
)
from confarg.exceptions import (
    AmbiguousUnionError,
    ConfargError,
    MissingFieldError,
    SymbolImportError,
    TypeCoercionError,
)
from confarg.typedload._coerce import (
    _FALSY,
    _LEAF_COERCIONS,
    _NONE_TOKENS,
    _TRUTHY,
    _coerce_bool,
    _coerce_leaf,
    _coerce_type_ref,
    _src_type,
    _steal_order,
)

_CAST_TYPE_NAMES: dict[str, type] = {"str": str, "int": int, "float": float, "bool": bool}


def _try_pinned_dict(data: Any) -> _Pinned | None:
    """Detect a ``{__cast__: typename, __value__: raw}`` tagged dict and convert to _Pinned."""
    if not (isinstance(data, dict) and data.keys() == {"__cast__", "__value__"}):
        return None
    typename = data["__cast__"]
    tp: type | None = _CAST_TYPE_NAMES.get(typename)
    if tp is None:
        tp = next((t for t in _LEAF_COERCIONS if getattr(t, "__name__", None) == typename), None)
    if tp is None:
        valid = sorted(_CAST_TYPE_NAMES) + sorted(
            t.__name__ for t in _LEAF_COERCIONS if t not in _CAST_TYPE_NAMES.values()
        )
        msg = f"Unknown __cast__ type: {typename!r}. Valid: {valid}"
        raise TypeCoercionError(msg)
    raw = data["__value__"]
    value = _StrToken(str(raw)) if isinstance(raw, str) else raw
    return _Pinned(tp, value)


def _construct_namedtuple(tp: Any, data: Any, path: str, union_tag: str) -> Any:  # noqa: C901 PLR0912
    """Construct a namedtuple from a list (positional) or dict (by name or index)."""
    flds = _namedtuple_fields(tp)
    defs = _namedtuple_defaults(tp)
    field_names = list(flds.keys())
    field_types = list(flds.values())
    n = len(field_names)

    if isinstance(data, list | tuple):
        if len(data) > n:
            msg = f"Cannot construct {tp.__name__} at '{path}': expected {n} elements, got {len(data)}"
            raise TypeCoercionError(msg)
        values = [
            construct(
                field_types[i],
                data[i] if i < len(data) else defs.get(field_names[i]),
                path=f"{path}.{field_names[i]}",
                union_tag=union_tag,
            )
            for i in range(n)
        ]
        return tp._make(values)

    if isinstance(data, dict):
        # Determine if keys are field names or integer-string indices.
        # A key is an index key if it is a string representation of an integer.
        all_int_keys = all(k.isdigit() or (k.startswith("-") and k[1:].isdigit()) for k in data) if data else False
        kwargs: dict[str, Any] = {}
        if all_int_keys and data:
            # Index-keyed form: {"0": val0, "1": val1, ...}
            for k, v in data.items():
                try:
                    idx = int(k)
                except ValueError:
                    msg = f"Cannot construct {tp.__name__} at '{path}': invalid index key {k!r}"
                    raise TypeCoercionError(msg) from None
                if idx < 0 or idx >= n:
                    msg = f"Cannot construct {tp.__name__} at '{path}': index {idx} out of range for {n} fields"
                    raise TypeCoercionError(msg)
                fname = field_names[idx]
                kwargs[fname] = construct(field_types[idx], v, path=f"{path}.{fname}", union_tag=union_tag)
        else:
            # Field-name-keyed form (possibly mixed): {"x": val_x, "y": val_y}
            extra = {k for k in data if k not in flds}
            if extra:
                msg = f"Unknown field(s) {sorted(extra)} for {tp.__name__} at '{path}'. Valid fields: {field_names}"
                raise TypeCoercionError(msg)
            for fname, ft in flds.items():
                if fname in data:
                    kwargs[fname] = construct(ft, data[fname], path=f"{path}.{fname}", union_tag=union_tag)

        # Fill in missing fields from defaults or raise MissingFieldError
        for fname, ft in flds.items():
            if fname not in kwargs:
                if fname in defs:
                    kwargs[fname] = defs[fname]
                else:
                    fp = f"{path}.{fname}" if path else fname
                    msg = (
                        f"Missing required field '{fp}' of type {ft!r}."
                        f" Set it via CLI (--{fp}), environment variable, or config file."
                    )
                    raise MissingFieldError(msg)

        return tp(**kwargs)

    msg = (
        f"Cannot construct {tp.__name__} at '{path}': expected list, tuple, or dict, got {type(data).__name__} {data!r}"
    )
    raise TypeCoercionError(msg)


def _construct_struct_dispatch(tp: Any, data: Any, path: str, union_tag: str) -> Any:
    """Dispatch struct construction, handling the union_tag class-path variant."""
    if not isinstance(data, dict):
        msg = f"Cannot construct {tp.__name__} at '{path}': expected dict, got {_src_type(data)} {data!r}"
        raise TypeCoercionError(msg)
    if union_tag in data:
        return _construct_by_class_path(tp, data, path, union_tag)
    direct_subs = [s for s in tp.__subclasses__() if _is_struct(s)]
    if direct_subs:
        sub_names = ", ".join(f"{s.__module__}.{s.__qualname__}" for s in direct_subs)
        msg = (
            f"Cannot construct '{tp.__name__}' at '{path}': it has subclasses ({sub_names})"
            f" but no {union_tag!r} discriminator was provided."
            f" Add a {union_tag!r} field with the fully-qualified class name."
        )
        raise TypeCoercionError(msg)
    return _construct_struct(tp, data, path, union_tag)


def _construct_sequence(tp: Any, data: Any, path: str, union_tag: str) -> Any:
    """Construct a list, set, or frozenset."""
    if _is_list(tp):
        return _construct_list(tp, data, path, union_tag)
    return _construct_set(tp, data, path, union_tag)


def _construct_scalar(tp: Any, data: Any, path: str) -> Any:
    """Construct a type reference or leaf value."""
    if _is_type_ref(tp):
        return _coerce_type_ref(tp, data, path)
    return _coerce_leaf(tp, data, path)


def _construct_typed(tp: Any, data: Any, path: str, union_tag: str) -> Any:  # noqa: PLR0911
    """Dispatch construction by type after None and callable are handled."""
    if tp is Any:
        # typing.Any became a real type in Python 3.12; pass data through unchanged.
        return data
    if _is_union(tp):
        return _construct_union(tp, data, path, union_tag)
    if _is_namedtuple(tp):
        return _construct_namedtuple(tp, data, path, union_tag)
    if _is_struct(tp) and tp not in _LEAF_COERCIONS:
        return _construct_struct_dispatch(tp, data, path, union_tag)
    if _is_list(tp) or _is_set(tp) or _is_frozenset(tp):
        return _construct_sequence(tp, data, path, union_tag)
    if _is_tuple(tp):
        return _construct_tuple(tp, data, path, union_tag)
    if _is_dict(tp):
        return _construct_dict(tp, data, path, union_tag)
    return _construct_scalar(tp, data, path)


def construct(tp: Any, data: Any, *, path: str = "", union_tag: str = _defaults.UNION_TAG) -> Any:
    """Construct a typed value from raw data.

    Dispatches to specialized constructors based on the target type.

    Args:
        tp: The target type to construct.
        data: The raw data to construct from.
        path: Dot-separated field path for error messages.
        union_tag: The field name used as a discriminator tag in unions.

    Returns:
        The constructed value matching the target type.

    Raises:
        MissingFieldError: If a required dataclass field is missing.
        TypeCoercionError: If a value cannot be coerced to the target type.
    """
    tp = _resolve_type(tp)
    if isinstance(data, _Pinned):
        return _coerce_leaf(data.tp, data.value, path)
    pinned = _try_pinned_dict(data)
    if pinned is not None:
        return _coerce_leaf(pinned.tp, pinned.value, path)
    if data is None and _allows_none(tp):
        return None
    if _is_callable(tp):
        return _resolve_callable_spec(data, tp, path=path, union_tag=union_tag, construct_fn=construct)
    return _construct_typed(tp, data, path, union_tag)


def _indexed_dict_to_positions(
    data: dict[Any, Any],
    length: int,
    path: str,
    what: str,
    *,
    tolerate_non_int: bool = False,
) -> dict[int, Any]:
    """Map an index-keyed dict to ``{abs_index: value}`` for a sequence of known *length*.

    Negative keys count from the end (``-1`` → ``length - 1``), the canonical rule applied
    wherever a sequence's length is known (mirroring list patches against a runtime base).

    Args:
        data: The index-keyed dict to normalise.
        length: The known length of the target sequence.
        path: Dot-separated field path for error messages.
        what: Human-readable description of the target type for error messages.
        tolerate_non_int: when True, silently skip non-integer keys instead of raising — used
            when patching a default in place, where stray segments (e.g. an arbitrary env var
            path like ``COORDS__BAD``) are ignored rather than treated as an error.

    Raises:
        TypeCoercionError: on a non-integer key (unless *tolerate_non_int*) or an index out of
            range for *length*.
    """
    out: dict[int, Any] = {}
    for k, v in data.items():
        try:
            ik = int(k)
        except (TypeError, ValueError):
            if tolerate_non_int:
                continue
            msg = f"Cannot construct {what} at '{path}': dict keys must be integer indices"
            raise TypeCoercionError(msg) from None
        idx = ik + length if ik < 0 else ik
        if not 0 <= idx < length:
            msg = f"Cannot construct {what} at '{path}': index {ik} out of range for length {length}"
            raise TypeCoercionError(msg)
        out[idx] = v
    return out


def _resolve_tuple_partial(field_data: dict[str, Any], ft: Any, defs: dict[str, Any], name: str) -> Any:
    """If field_data is an index-keyed dict for a tuple field, patch the default tuple in-place.

    Returns the (possibly patched) data — unchanged if the conditions don't apply.
    """
    tup_tp: Any = ft if _is_tuple(ft) else None
    if tup_tp is None and _is_union(ft):
        tup_vars = [_resolve_type(v) for v in _union_args_no_none(ft) if _is_tuple(_resolve_type(v))]
        if len(tup_vars) == 1:
            tup_tp = tup_vars[0]
    if tup_tp is None or defs.get(name) is None:
        return field_data
    base = list(defs[name])
    for idx, iv in _indexed_dict_to_positions(field_data, len(base), name, "tuple", tolerate_non_int=True).items():
        base[idx] = iv
    return base


def _call_with_var_positional(
    tp: Any,
    kwargs: dict[str, Any],
    var_pos_name: str,
    var_kw: dict[str, Any],
) -> Any:
    """Call tp(*pos_args, *var_pos, **kwargs, **var_kw) with *args support."""
    var_pos = list(kwargs.pop(var_pos_name, []))
    sig = inspect.signature(tp.__init__)
    pos_args: list[Any] = []
    for pname, param in sig.parameters.items():
        if pname == "self":
            continue
        if param.kind == inspect.Parameter.VAR_POSITIONAL:
            break
        if (
            param.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.POSITIONAL_ONLY)
            and pname in kwargs
        ):
            pos_args.append(kwargs.pop(pname))
    return tp(*pos_args, *var_pos, **kwargs, **var_kw)


def _construct_struct(tp: Any, data: dict[str, Any], path: str, union_tag: str) -> Any:
    """Construct a dataclass or plain-class instance from a dict of raw data."""
    flds = _struct_fields(tp)
    defs = _struct_defaults(tp)
    kwargs: dict[str, Any] = {}

    extra = {k for k in data if k not in flds and k != union_tag}
    if extra:
        msg = f"Unknown field(s) {sorted(extra)} for {tp.__name__} at '{path}'. Valid fields: {sorted(flds.keys())}"
        raise TypeCoercionError(msg)

    for name, ft in flds.items():
        fp = f"{path}.{name}" if path else name
        if name in data:
            field_data = data[name]
            if isinstance(field_data, dict) and name in defs:
                field_data = _resolve_tuple_partial(field_data, ft, defs, name)
            kwargs[name] = construct(ft, field_data, path=fp, union_tag=union_tag)
        elif name in defs:
            kwargs[name] = defs[name]
        elif _is_struct(ft) and _all_have_defaults(ft):
            kwargs[name] = _construct_struct(ft, {}, fp, union_tag)
        else:
            msg = (
                f"Missing required field '{fp}' of type {ft!r}."
                f" Set it via CLI (--{fp}), environment variable, or config file."
            )
            raise MissingFieldError(msg)

    var_pos_name = _var_positional_name(tp)
    var_kw_name = _var_keyword_name(tp)
    var_kw = dict(kwargs.pop(var_kw_name, {})) if var_kw_name else {}

    if var_pos_name is None:
        return tp(**kwargs, **var_kw)

    return _call_with_var_positional(tp, kwargs, var_pos_name, var_kw)


def _construct_list(tp: Any, data: Any, path: str, union_tag: str) -> list[Any]:
    """Construct a list from raw data.

    Handles both list and dict (with integer keys) input data.

    Args:
        tp: The list type (e.g. list[int]).
        data: The raw data (list or dict with integer keys).
        path: Dot-separated field path for error messages.
        union_tag: The field name used as a discriminator tag in unions.

    Returns:
        The constructed list.

    Raises:
        TypeCoercionError: If data is not a list or dict with integer keys.
    """
    if not isinstance(data, list | dict):
        msg = (
            f"Cannot construct list at '{path}': expected list or dict with integer keys,"
            f" got {type(data).__name__} {data!r}"
        )
        raise TypeCoercionError(msg)
    return _build_items(_elem_type(tp), data, path, union_tag)


def _construct_set(tp: Any, data: Any, path: str, union_tag: str) -> set[Any] | frozenset[Any]:
    """Construct a set or frozenset from raw data.

    Args:
        tp: The set or frozenset type.
        data: The raw data (list, set, tuple, or dict with integer keys).
        path: Dot-separated field path for error messages.
        union_tag: The field name used as a discriminator tag in unions.

    Returns:
        The constructed set or frozenset.

    Raises:
        TypeCoercionError: If data cannot be interpreted as a sequence.
    """
    et = _elem_type(tp)
    items = _build_items(et, data, path, union_tag)
    return frozenset(items) if _is_frozenset(tp) else set(items)


def _build_items(et: Any, data: Any, path: str, union_tag: str) -> list[Any]:
    """Build a list of constructed items from sequence-like raw data.

    Args:
        et: The element type to construct each item as.
        data: The raw data (list, set, frozenset, tuple, or dict with integer keys).
        path: Dot-separated field path for error messages.
        union_tag: The field name used as a discriminator tag in unions.

    Returns:
        A list of constructed items.

    Raises:
        TypeCoercionError: If data is not a sequence or dict with integer keys.
    """
    if isinstance(data, list | set | frozenset | tuple):
        return [construct(et, v, path=f"{path}[{i}]", union_tag=union_tag) for i, v in enumerate(data)]
    if isinstance(data, dict):
        if LIST_REPLACE_BASE_KEY in data:
            # CLI-produced dict with an explicit base list; apply ops in order.
            working = _apply_list_ops(list(data[LIST_REPLACE_BASE_KEY]), data, path, None)
            return [construct(et, v, path=f"{path}[{i}]", union_tag=union_tag) for i, v in enumerate(working)]
        if LIST_APPEND_KEY in data:
            # Append-only dict: apply all list ops (appends, deletions, index patches) against an empty base.
            working = _apply_list_ops([], data, path, None)
            return [construct(et, v, path=f"{path}[{i}]", union_tag=union_tag) for i, v in enumerate(working)]
        if LIST_DELETE_KEY in data:
            msg = (
                f"List deletion (the '-' operator) at '{path}' requires a base list to delete from,"
                " but no base list was provided. Supply the full list via a config file or other source."
            )
            raise TypeCoercionError(msg)
        if not data:
            return []
        try:
            int_keys = [int(k) for k in data]
        except ValueError:
            msg = f"Cannot construct collection at '{path}': dict keys must be integer indices"
            raise TypeCoercionError(msg) from None
        neg = [k for k in int_keys if k < 0]
        if neg:
            msg = (
                f"Negative index/indices {sorted(neg)} at '{path}' require a base list to"
                " resolve against, but no base list was provided. Supply the full list via"
                " a config file or other source."
            )
            raise TypeCoercionError(msg)
        max_idx = max(int_keys)
        gaps = [i for i in range(max_idx + 1) if str(i) not in data]
        if gaps and not _allows_none(et):
            msg = (
                f"List at '{path}' has gap(s) at index/indices {gaps}:"
                f" when using index-keyed form, all indices 0-{max_idx} must be provided,"
                f" or the element type must be Optional."
            )
            raise TypeCoercionError(msg)
        return [
            construct(et, data.get(str(i), None), path=f"{path}[{i}]", union_tag=union_tag) for i in range(max_idx + 1)
        ]
    msg = (
        f"Cannot construct collection at '{path}': expected sequence or dict with integer keys,"
        f" got {type(data).__name__} {data!r}"
    )
    raise TypeCoercionError(msg)


def _construct_tuple(tp: Any, data: Any, path: str, union_tag: str) -> tuple[Any, ...]:
    """Construct a tuple from raw data.

    Handles both fixed-length and variable-length (tuple[X, ...]) tuples.

    Args:
        tp: The tuple type.
        data: The raw data (list, tuple, or dict with integer keys).
        path: Dot-separated field path for error messages.
        union_tag: The field name used as a discriminator tag in unions.

    Returns:
        The constructed tuple.

    Raises:
        TypeCoercionError: If data cannot be interpreted as a sequence.
    """
    tt = _tuple_types(tp)
    if tt is None:
        # variable length
        et = _elem_type(tp)
        return tuple(_build_items(et, data, path, union_tag))

    if not isinstance(data, list | tuple | dict):
        msg = (
            f"Cannot construct tuple at '{path}': expected list, tuple, or dict with integer keys,"
            f" got {type(data).__name__} {data!r}"
        )
        raise TypeCoercionError(msg)
    if isinstance(data, list | tuple):
        if len(data) > len(tt):
            msg = f"Cannot construct {tp} at '{path}': expected {len(tt)} elements, got {len(data)}"
            raise TypeCoercionError(msg)
        if len(data) < len(tt):
            missing = [i for i in range(len(data), len(tt)) if not _allows_none(tt[i])]
            if missing:
                msg = f"Cannot construct {tp} at '{path}': expected {len(tt)} elements, got {len(data)}"
                raise TypeCoercionError(msg)
        seq = list(data)
    else:
        pos = _indexed_dict_to_positions(data, len(tt), path, f"{tp}")
        seq = [pos.get(i) for i in range(len(tt))]
    return tuple(
        construct(et, seq[i] if i < len(seq) else None, path=f"{path}[{i}]", union_tag=union_tag)
        for i, et in enumerate(tt)
    )


def _construct_dict(tp: Any, data: Any, path: str, union_tag: str) -> dict[Any, Any]:
    """Construct a typed dict from raw data.

    Args:
        tp: The dict type (e.g. dict[str, int]).
        data: The raw data dict.
        path: Dot-separated field path for error messages.
        union_tag: The field name used as a discriminator tag in unions.

    Returns:
        The constructed dict with coerced keys and constructed values.

    Raises:
        TypeCoercionError: If data is not a dict.
    """
    kt, vt = _dict_kv(tp)
    if not isinstance(data, dict):
        msg = f"Cannot construct dict at '{path}': expected dict, got {_src_type(data)} {data!r}"
        raise TypeCoercionError(msg)
    return {
        _coerce_leaf(kt, _StrToken(k) if isinstance(k, str) else k, path): construct(
            vt,
            v,
            path=f"{path}.{k}",
            union_tag=union_tag,
        )
        for k, v in data.items()
    }


_UNION_NO_MATCH: object = object()


def _construct_single_variant_union(
    all_args: list[Any],
    non_none: list[Any],
    data: Any,
    path: str,
    union_tag: str,
) -> Any:
    """Construct a union that has exactly one non-None variant."""
    if type(None) in all_args and isinstance(data, _StrToken) and data.lower() in _NONE_TOKENS:
        return None
    try:
        return construct(non_none[0], data, path=path, union_tag=union_tag)
    except (TypeCoercionError, MissingFieldError):
        if type(None) in all_args:
            msg = (
                f"Cannot coerce {_src_type(data)} {data!r} to"
                f" {getattr(_resolve_type(non_none[0]), '__name__', repr(non_none[0]))} at '{path}'."
                f" To set this field to None, pass 'none' or 'null'."
            )
            raise TypeCoercionError(msg) from None
        raise  # pragma: no cover  # len(non_none)==1 without NoneType is impossible via normal Union typing


def _construct_union_by_tag(non_none: list[Any], data: dict[str, Any], path: str, union_tag: str) -> Any:
    """Construct a union value using its class tag field."""
    tag = data[union_tag]
    cls = _import_class_by_path(tag, path, union_tag)
    matching = [v for v in non_none if _is_struct(_resolve_type(v)) and issubclass(cls, _resolve_type(v))]
    if len(matching) > 1:
        raise AmbiguousUnionError(
            f"Class {tag!r} at '{path}' matches multiple union variants: "
            + ", ".join(f"{_resolve_type(v).__module__}.{_resolve_type(v).__name__}" for v in matching),
        )
    if matching:
        cleaned = {k: v2 for k, v2 in data.items() if k != union_tag}
        return _construct_struct(cls, cleaned, path, union_tag)
    valid_variants = sorted(
        f"{_resolve_type(v).__module__}.{_resolve_type(v).__name__}" for v in non_none if _is_struct(_resolve_type(v))
    )
    msg = (
        f"Class {tag!r} at '{path}' is not compatible with any union variant."
        f" Expected a subclass of one of: {valid_variants}"
    )
    raise TypeCoercionError(msg)


def _try_construct_union_struct(dc_vars: list[Any], data: dict[str, Any], path: str, union_tag: str) -> Any:
    """Try structural disambiguation then fallback for struct variants.

    Returns _UNION_NO_MATCH if no struct variant accepts the data.
    """
    matches = _disambiguate_struct(dc_vars, data, union_tag)
    if len(matches) == 1:
        return construct(matches[0], data, path=path, union_tag=union_tag)
    if len(matches) > 1:
        raise AmbiguousUnionError(_ambiguous_union_msg(matches, data, path, union_tag))
    for var in dc_vars:
        try:
            return construct(var, data, path=path, union_tag=union_tag)
        except (ConfargError, TypeError):
            continue
    return _UNION_NO_MATCH


def _try_tuple_variants(tuple_vars: list[Any], data: Any, path: str, union_tag: str) -> Any:
    """Try constructing from tuple variants; returns _UNION_NO_MATCH if none accept data."""
    if not (tuple_vars and isinstance(data, list | dict)):
        return _UNION_NO_MATCH
    if isinstance(data, list):
        data_len = len(data)
    else:
        try:
            data_len = (max(int(k) for k in data) + 1) if data else 0
        except ValueError:
            data_len = -1
    candidates = (
        [v for v in tuple_vars if (tt := _tuple_types(_resolve_type(v))) is None or len(tt) == data_len]
        if data_len >= 0
        else []
    ) or tuple_vars
    for var in candidates:
        try:
            return construct(var, data, path=path, union_tag=union_tag)
        except (ConfargError, TypeError):
            continue
    return _UNION_NO_MATCH


def _try_coll_variants(coll_vars: list[Any], data: Any, path: str, union_tag: str) -> Any:
    """Try constructing from collection variants; returns _UNION_NO_MATCH if none accept data."""
    if not (coll_vars and isinstance(data, dict | list | set | frozenset)):
        return _UNION_NO_MATCH
    for var in coll_vars:
        try:
            return construct(var, data, path=path, union_tag=union_tag)
        except (ConfargError, TypeError):
            continue
    return _UNION_NO_MATCH


def _coerce_scalar_variants(all_args: list[Any], scalar_leaf_vars: list[Any], data: Any, path: str) -> Any:
    """Coerce data to one of the scalar leaf variants; returns _UNION_NO_MATCH on failure."""
    if type(None) in all_args and isinstance(data, _StrToken) and data.lower() in _NONE_TOKENS:
        return None
    if bool in scalar_leaf_vars and int in scalar_leaf_vars:
        if isinstance(data, bool):
            return data
        if isinstance(data, _StrToken) and data.lower() in (_TRUTHY | _FALSY):
            return _coerce_bool(data)
    ordered = _steal_order(scalar_leaf_vars, key=_resolve_type) if isinstance(data, _StrToken) else scalar_leaf_vars
    for var in ordered:
        vr = _resolve_type(var)
        if vr is type(None):  # pragma: no cover  # NoneType is excluded from non_none
            continue
        if vr is bool and int in scalar_leaf_vars:
            continue  # handled above
        try:
            return _coerce_leaf(vr, data, path)
        except (TypeCoercionError, ValueError, TypeError):
            continue
    return _UNION_NO_MATCH


def _construct_union_leaf(all_args: list[Any], non_none: list[Any], data: Any, path: str, union_tag: str) -> Any:
    """Construct a union value by trying leaf variants in priority order."""
    leaf_vars = [v for v in non_none if not _is_struct(_resolve_type(v)) or _resolve_type(v) in _LEAF_COERCIONS]
    tuple_vars = [v for v in leaf_vars if _is_tuple(_resolve_type(v))]
    coll_vars = [
        v
        for v in leaf_vars
        if not _is_tuple(_resolve_type(v))
        and (
            _is_dict(_resolve_type(v))
            or _is_list(_resolve_type(v))
            or _is_set(_resolve_type(v))
            or _is_frozenset(_resolve_type(v))
        )
    ]
    scalar_leaf_vars = [v for v in leaf_vars if not _is_tuple(_resolve_type(v)) and v not in coll_vars]

    result = _try_tuple_variants(tuple_vars, data, path, union_tag)
    if result is not _UNION_NO_MATCH:
        return result

    result = _try_coll_variants(coll_vars, data, path, union_tag)
    if result is not _UNION_NO_MATCH:
        return result

    result = _coerce_scalar_variants(all_args, scalar_leaf_vars, data, path)
    if result is not _UNION_NO_MATCH:
        return result

    # A lone CLI token (e.g. `--input hello` for `bool | list[str]`) that no scalar
    # variant accepts falls back to filling the sequence variant as a one-element list,
    # mirroring a sole `list[str]` field. Gated on _UnionSeqToken so env/config scalars
    # (plain _StrToken / native values) stay strict — they express lists explicitly.
    if isinstance(data, _UnionSeqToken):
        result = _try_coll_variants(coll_vars, [_StrToken(data)], path, union_tag)
        if result is not _UNION_NO_MATCH:
            return result

    variant_names = " | ".join(
        "None" if v is type(None) else getattr(_resolve_type(v), "__name__", repr(v)) for v in all_args
    )
    msg = f"Cannot coerce {_src_type(data)} {data!r} to {variant_names} at '{path}'"
    if type(None) in all_args:
        msg += ". To set this field to None, pass 'none' or 'null'."
    raise TypeCoercionError(msg)


def _construct_union(tp: Any, data: Any, path: str, union_tag: str) -> Any:
    """Construct a value for a Union type.

    Tries tag-based disambiguation, structural disambiguation for struct
    (dataclass or plain-class) variants, and finally leaf coercion in order.

    Args:
        tp: The Union type.
        data: The raw data.
        path: Dot-separated field path for error messages.
        union_tag: The field name used as a discriminator tag in unions.

    Returns:
        The constructed value matching one of the Union variants.

    Raises:
        AmbiguousUnionError: If multiple dataclass variants match structurally.
        TypeCoercionError: If no variant can accept the data.
    """
    all_args = _union_args(tp)
    non_none = _union_args_no_none(tp)

    if data is None:  # pragma: no cover  # construct() short-circuits before reaching here
        return None

    if len(non_none) == 1:
        return _construct_single_variant_union(all_args, non_none, data, path, union_tag)

    if isinstance(data, dict) and union_tag in data:
        return _construct_union_by_tag(non_none, data, path, union_tag)

    dc_vars = [v for v in non_none if _is_struct(_resolve_type(v))]
    if isinstance(data, dict) and dc_vars:
        result = _try_construct_union_struct(dc_vars, data, path, union_tag)
        if result is not _UNION_NO_MATCH:
            return result

    return _construct_union_leaf(all_args, non_none, data, path, union_tag)


def _struct_matches_value(tp: Any, value: Any, union_tag: str) -> bool:
    """Check if value could be a valid dict for struct tp."""
    if not isinstance(value, dict):
        return False
    flds = _struct_fields(tp)
    defs = _struct_defaults(tp)
    keys = {k for k in value if k != union_tag}
    required = {n for n in flds if n not in defs}
    return required.issubset(keys) and keys.issubset(set(flds))


def _bool_matches_value(value: Any) -> bool:
    """Check if value is compatible with bool."""
    if isinstance(value, bool):
        return True
    if isinstance(value, _StrToken):
        return value.lower() in (_TRUTHY | _FALSY)
    return False


def _int_matches_value(value: Any) -> bool:
    """Check if value is compatible with int."""
    if isinstance(value, int) and not isinstance(value, bool):
        return True
    if isinstance(value, _StrToken):
        try:
            int(value)
        except ValueError:
            return False
        else:
            return True
    return False


def _float_matches_value(value: Any) -> bool:
    """Check if value is compatible with float."""
    if isinstance(value, float) and not isinstance(value, bool):
        return True
    if isinstance(value, _StrToken):
        try:
            float(value)
        except ValueError:
            return False
        else:
            return True
    return False


def _literal_matches_value(tp: Any, value: Any) -> bool:
    """Check if value matches any member of a Literal type."""
    vals = _literal_values(tp)
    if isinstance(value, _StrToken):
        s = str(value)
        return any(str(v) == s for v in vals)
    return any(type(v) is type(value) and v == value for v in vals)


_SCALAR_MATCHES: dict[type, Any] = {
    bool: _bool_matches_value,
    int: _int_matches_value,
    float: _float_matches_value,
    str: lambda v: isinstance(v, str),
}


def _value_matches_type(value: Any, tp: Any, union_tag: str) -> bool:
    """Check if a raw value could match the target type structurally.

    Used during union disambiguation to test whether a value is compatible
    with a candidate type.

    Args:
        value: The raw value to check.
        tp: The candidate type.
        union_tag: The field name used as a discriminator tag in unions.

    Returns:
        True if the value could plausibly be coerced to the target type.
    """
    tp = _resolve_type(tp)
    if value is None:
        return _allows_none(tp)
    if _is_struct(tp):
        return _struct_matches_value(tp, value, union_tag)
    if tp in _SCALAR_MATCHES:
        return _SCALAR_MATCHES[tp](value)
    if _is_literal(tp):
        return _literal_matches_value(tp, value)
    return True


def _ambiguous_union_msg(matches: list[Any], data: dict[str, Any], path: str, union_tag: str) -> str:
    """Build a diagnostic AmbiguousUnionError message with per-variant field breakdowns."""
    lines = [f"Ambiguous union at '{path}': cannot distinguish between " + ", ".join(m.__name__ for m in matches) + "."]
    provided = {k for k in data if k != union_tag}
    for var in matches:
        flds = _struct_fields(var)
        defs = _struct_defaults(var)
        required = sorted(n for n in flds if n not in defs)
        optional = sorted(n for n in flds if n in defs)
        parts = []
        if required:
            parts.append("required: " + ", ".join(required))
        if optional:
            parts.append("optional: " + ", ".join(optional))
        lines.append(f"  {var.__name__}: {'; '.join(parts) if parts else '(no fields)'}")
    lines.append(f"Provided fields: {sorted(provided) if provided else '(none)'}")
    lines.append(
        f"To select a variant add a {union_tag!r} field, e.g. {union_tag!r}: {matches[0].__name__!r}."
        f" The field name can be changed via the union_tag= parameter.",
    )
    return "\n".join(lines)


def _structurally_matches(var: Any, keys: set[str]) -> bool:
    """Return True if var's fields cover keys and all required fields are present."""
    flds = _struct_fields(var)
    defs = _struct_defaults(var)
    required = {n for n in flds if n not in defs}
    return required.issubset(keys) and keys.issubset(set(flds))


def _type_compatible(var: Any, data: dict[str, Any], keys: set[str], union_tag: str) -> bool:
    """Return True if data values are compatible with var's field types."""
    flds = _struct_fields(var)
    return all(k not in flds or _value_matches_type(data[k], flds[k], union_tag) for k in keys)


def _disambiguate_struct(variants: list[Any], data: dict[str, Any], union_tag: str) -> list[Any]:
    """Filter struct union variants to those matching data structurally."""
    keys = {k for k in data if k != union_tag}
    candidates = [_resolve_type(var) for var in variants if _structurally_matches(_resolve_type(var), keys)]

    if len(candidates) <= 1:
        return candidates

    refined = [var for var in candidates if _type_compatible(var, data, keys, union_tag)]

    if not refined:
        return candidates
    return refined


def _import_class_by_path(tag: str, path: str, union_tag: str) -> type:
    """Import and validate a class by its full dotted module path.

    Raises TypeCoercionError if the path cannot be imported or does not resolve
    to a class. The tag must be a fully-qualified dotted path such as
    ``'mypackage.mymodule.MyClass'``.
    """
    try:
        obj = _import_dotted(tag)
    except SymbolImportError as e:
        msg = (
            f"Cannot import class {tag!r} from {union_tag!r} tag at '{path}': {e}."
            f" The value must be a full dotted path, e.g. 'mypackage.mymodule.MyClass'."
        )
        raise TypeCoercionError(msg) from e
    if not isinstance(obj, type):
        msg = (
            f"Value of {union_tag!r} tag at '{path}' must be a class path,"
            f" but {tag!r} resolved to {type(obj).__name__!r}, not a class."
        )
        raise TypeCoercionError(msg)
    return obj


def _construct_by_class_path(tp: type, data: dict[str, Any], path: str, union_tag: str) -> Any:
    """Import the class named by union_tag, validate it is a subclass of tp, and construct it."""
    tag = data[union_tag]
    cls = _import_class_by_path(tag, path, union_tag)
    if not issubclass(cls, tp):
        msg = f"Class {tag!r} at '{path}' is not a subclass of {tp.__module__}.{tp.__name__}."
        raise TypeCoercionError(msg)
    cleaned = {k: v for k, v in data.items() if k != union_tag}
    return _construct_struct(cls, cleaned, path, union_tag)
