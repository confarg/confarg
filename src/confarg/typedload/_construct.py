# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Value construction and union disambiguation for confarg."""

from __future__ import annotations

import inspect
from typing import Any

from confarg import _defaults
from confarg._errors import (
    AmbiguousUnionError,
    ConfargError,
    MissingFieldError,
    TypeCoercionError,
)
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
    _is_set,
    _is_struct,
    _is_tuple,
    _is_type_ref,
    _is_union,
    _literal_values,
    _resolve_type,
    _StrToken,
    _struct_defaults,
    _struct_fields,
    _tuple_types,
    _union_args,
    _union_args_no_none,
    _var_keyword_name,
    _var_positional_name,
)
from confarg.typedload._coerce import _FALSY, _TRUTHY, _coerce_bool, _coerce_leaf, _coerce_type_ref, _src_type


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

    if data is None and _allows_none(tp):
        return None

    if _is_callable(tp):
        from confarg._callable import _resolve_callable_spec

        return _resolve_callable_spec(data, tp, path=path, union_tag=union_tag)

    if _is_union(tp):
        return _construct_union(tp, data, path, union_tag)

    if _is_struct(tp):
        if not isinstance(data, dict):
            raise TypeCoercionError(
                f"Cannot construct {tp.__name__} at '{path}': expected dict, got {_src_type(data)} {data!r}"
            )
        if union_tag in data:
            return _construct_by_class_path(tp, data, path, union_tag)
        return _construct_struct(tp, data, path, union_tag)

    if _is_list(tp):
        return _construct_list(tp, data, path, union_tag)

    if _is_set(tp) or _is_frozenset(tp):
        return _construct_set(tp, data, path, union_tag)

    if _is_tuple(tp):
        return _construct_tuple(tp, data, path, union_tag)

    if _is_dict(tp):
        return _construct_dict(tp, data, path, union_tag)

    if _is_type_ref(tp):
        return _coerce_type_ref(tp, data, path)

    return _coerce_leaf(tp, data, path)


def _construct_struct(tp: Any, data: dict[str, Any], path: str, union_tag: str) -> Any:
    """Construct a dataclass or plain-class instance from a dict of raw data."""
    flds = _struct_fields(tp)
    defs = _struct_defaults(tp)
    kwargs: dict[str, Any] = {}

    extra = {k for k in data if k not in flds and k != union_tag}
    if extra:
        raise TypeCoercionError(
            f"Unknown field(s) {sorted(extra)} for {tp.__name__} at '{path}'. Valid fields: {sorted(flds.keys())}"
        )

    for name, ft in flds.items():
        fp = f"{path}.{name}" if path else name
        if name in data:
            field_data = data[name]
            # Partial .idx dict for a tuple field: merge into default so only named
            # indices are overridden and the rest keep their default values.
            if isinstance(field_data, dict) and name in defs:
                tup_tp: Any = ft if _is_tuple(ft) else None
                if tup_tp is None and _is_union(ft):
                    tup_vars = [_resolve_type(v) for v in _union_args_no_none(ft) if _is_tuple(_resolve_type(v))]
                    if len(tup_vars) == 1:
                        tup_tp = tup_vars[0]
                if tup_tp is not None and defs[name] is not None:
                    base = list(defs[name])
                    for ik, iv in field_data.items():
                        try:
                            idx = int(ik)
                            if idx >= 0:
                                while len(base) <= idx:
                                    base.append(None)
                                base[idx] = iv
                        except ValueError:
                            pass
                    field_data = base
            kwargs[name] = construct(ft, field_data, path=fp, union_tag=union_tag)
        elif name in defs:
            kwargs[name] = defs[name]
        elif _is_struct(ft) and _all_have_defaults(ft):
            kwargs[name] = _construct_struct(ft, {}, fp, union_tag)
        else:
            raise MissingFieldError(
                f"Missing required field '{fp}' of type {ft!r}."
                f" Set it via CLI (--{fp}), environment variable, or config file."
            )

    var_pos_name = _var_positional_name(tp)
    var_kw_name = _var_keyword_name(tp)
    var_kw = dict(kwargs.pop(var_kw_name, {})) if var_kw_name else {}

    if var_pos_name is None:
        return tp(**kwargs, **var_kw)

    # *args present: pass pre-*args params positionally to avoid conflict.
    var_pos = list(kwargs.pop(var_pos_name, []))
    sig = inspect.signature(tp.__init__)
    pos_args: list[Any] = []
    for pname, param in sig.parameters.items():
        if pname == "self":
            continue
        if param.kind == inspect.Parameter.VAR_POSITIONAL:
            break
        if param.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.POSITIONAL_ONLY):
            if pname in kwargs:
                pos_args.append(kwargs.pop(pname))
    return tp(*pos_args, *var_pos, **kwargs, **var_kw)


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
        raise TypeCoercionError(
            f"Cannot construct list at '{path}': expected list or dict with integer keys,"
            f" got {type(data).__name__} {data!r}"
        )
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
        from confarg._merge import LIST_APPEND_KEY, LIST_DELETE_KEY, _to_append_list

        if LIST_APPEND_KEY in data:
            # Append-only dict produced when there is no base list (e.g. --foo+ with no config).
            items_data = _to_append_list(data[LIST_APPEND_KEY])
            return [construct(et, v, path=f"{path}[{i}]", union_tag=union_tag) for i, v in enumerate(items_data)]
        if LIST_DELETE_KEY in data:
            raise TypeCoercionError(
                f"List deletion (the '-' operator) at '{path}' requires a base list to delete from,"
                " but no base list was provided. Supply the full list via a config file or other source."
            )
        if not data:
            return []
        try:
            max_idx = max(int(k) for k in data)
        except ValueError:
            raise TypeCoercionError(
                f"Cannot construct collection at '{path}': dict keys must be integer indices"
            ) from None
        gaps = [i for i in range(max_idx + 1) if str(i) not in data]
        if gaps and not _allows_none(et):
            raise TypeCoercionError(
                f"List at '{path}' has gap(s) at index/indices {gaps}:"
                f" when using index-keyed form, all indices 0-{max_idx} must be provided,"
                f" or the element type must be Optional."
            )
        return [
            construct(et, data[str(i)] if str(i) in data else None, path=f"{path}[{i}]", union_tag=union_tag)
            for i in range(max_idx + 1)
        ]
    raise TypeCoercionError(
        f"Cannot construct collection at '{path}': expected sequence or dict with integer keys,"
        f" got {type(data).__name__} {data!r}"
    )


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
        raise TypeCoercionError(
            f"Cannot construct tuple at '{path}': expected list, tuple, or dict with integer keys,"
            f" got {type(data).__name__} {data!r}"
        )
    if isinstance(data, list | tuple):
        if len(data) > len(tt):
            raise TypeCoercionError(f"Cannot construct {tp} at '{path}': expected {len(tt)} elements, got {len(data)}")
        if len(data) < len(tt):
            missing = [i for i in range(len(data), len(tt)) if not _allows_none(tt[i])]
            if missing:
                raise TypeCoercionError(
                    f"Cannot construct {tp} at '{path}': expected {len(tt)} elements, got {len(data)}"
                )
        seq = list(data)
    else:
        try:
            mx = max(int(k) for k in data) if data else -1
        except ValueError:
            raise TypeCoercionError(f"Cannot construct tuple at '{path}': dict keys must be integer indices") from None
        if mx >= len(tt):
            raise TypeCoercionError(
                f"Cannot construct {tp} at '{path}': index {mx} out of range for tuple of length {len(tt)}"
            )
        seq = [data.get(str(i)) for i in range(len(tt))]
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
        raise TypeCoercionError(f"Cannot construct dict at '{path}': expected dict, got {_src_type(data)} {data!r}")
    return {
        _coerce_leaf(kt, _StrToken(k) if isinstance(k, str) else k, path): construct(
            vt, v, path=f"{path}.{k}", union_tag=union_tag
        )
        for k, v in data.items()
    }


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

    if data is None and type(None) in all_args:  # pragma: no cover
        return None  # construct() short-circuits at line 70-71 before reaching here

    # Single non-None variant
    if len(non_none) == 1:
        if type(None) in all_args and isinstance(data, _StrToken) and data.lower() in ("none", "null"):
            return None
        try:
            return construct(non_none[0], data, path=path, union_tag=union_tag)
        except (TypeCoercionError, MissingFieldError):
            if type(None) in all_args:
                raise TypeCoercionError(
                    f"Cannot coerce {_src_type(data)} {data!r} to"
                    f" {getattr(_resolve_type(non_none[0]), '__name__', repr(non_none[0]))} at '{path}'."
                    f" To set this field to None, pass 'none' or 'null'."
                ) from None
            raise  # pragma: no cover  # len(non_none)==1 without NoneType is impossible via normal Union typing

    # Class tag in data — import by full dotted path at runtime
    if isinstance(data, dict) and union_tag in data:
        tag = data[union_tag]
        cls = _import_class_by_path(tag, path, union_tag)
        matching = [v for v in non_none if _is_struct(_resolve_type(v)) and issubclass(cls, _resolve_type(v))]
        if len(matching) > 1:
            raise AmbiguousUnionError(
                f"Class {tag!r} at '{path}' matches multiple union variants: "
                + ", ".join(f"{_resolve_type(v).__module__}.{_resolve_type(v).__name__}" for v in matching)
            )
        if matching:
            cleaned = {k: v2 for k, v2 in data.items() if k != union_tag}
            return _construct_struct(cls, cleaned, path, union_tag)
        valid_variants = sorted(
            f"{_resolve_type(v).__module__}.{_resolve_type(v).__name__}"
            for v in non_none
            if _is_struct(_resolve_type(v))
        )
        raise TypeCoercionError(
            f"Class {tag!r} at '{path}' is not compatible with any union variant."
            f" Expected a subclass of one of: {valid_variants}"
        )

    # Structural disambiguation for struct (dataclass or plain class) variants
    dc_vars = [v for v in non_none if _is_struct(_resolve_type(v))]
    if isinstance(data, dict) and dc_vars:
        matches = _disambiguate_struct(dc_vars, data, union_tag)
        if len(matches) == 1:
            return construct(matches[0], data, path=path, union_tag=union_tag)
        if len(matches) > 1:
            raise AmbiguousUnionError(_ambiguous_union_msg(matches, data, path, union_tag))

    # Struct vs leaf: if data is a dict, try struct variants
    if isinstance(data, dict) and dc_vars:
        for var in dc_vars:
            try:
                return construct(var, data, path=path, union_tag=union_tag)
            except (ConfargError, TypeError):
                continue

    # Leaf union coercion
    leaf_vars = [v for v in non_none if not _is_struct(_resolve_type(v))]
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

    # Tuple variants — disambiguate by data length, then try each candidate
    if tuple_vars and isinstance(data, list | dict):
        if isinstance(data, list):
            data_len = len(data)
        else:
            try:
                data_len = (max(int(k) for k in data) + 1) if data else 0
            except ValueError:
                data_len = -1
        candidates = (
            [v for v in tuple_vars if (lambda tt: tt is None or len(tt) == data_len)(_tuple_types(_resolve_type(v)))]
            if data_len >= 0
            else []
        )
        if not candidates:
            candidates = tuple_vars
        for var in candidates:
            try:
                return construct(var, data, path=path, union_tag=union_tag)
            except (ConfargError, TypeError):
                continue

    # Collection leaf variants (dict, list, set, frozenset)
    if coll_vars and isinstance(data, dict | list | set | frozenset):
        for var in coll_vars:
            try:
                return construct(var, data, path=path, union_tag=union_tag)
            except (ConfargError, TypeError):
                continue

    # Scalar leaf variants — "none"/"null" tokens → None in any Optional union
    if type(None) in all_args and isinstance(data, _StrToken) and data.lower() in ("none", "null"):
        return None

    # Bool before int (bool is a subclass of int; must be checked first)
    if bool in scalar_leaf_vars and int in scalar_leaf_vars:
        if isinstance(data, bool):
            return data
        if isinstance(data, _StrToken) and data.lower() in (_TRUTHY | _FALSY):
            return _coerce_bool(data)

    # Steal rule: when str is present and value is a _StrToken, try non-str types first
    _has_str = any(_resolve_type(v) is str for v in scalar_leaf_vars)
    if _has_str and isinstance(data, _StrToken):
        _ordered = [v for v in scalar_leaf_vars if _resolve_type(v) is not str] + [
            v for v in scalar_leaf_vars if _resolve_type(v) is str
        ]
    else:
        _ordered = scalar_leaf_vars

    for var in _ordered:
        vr = _resolve_type(var)
        if vr is type(None):  # pragma: no cover  # NoneType is excluded from non_none by _union_args_no_none
            continue
        if vr is bool and int in scalar_leaf_vars:
            continue  # handled above
        try:
            return _coerce_leaf(vr, data, path)
        except (TypeCoercionError, ValueError, TypeError):
            continue

    variant_names = " | ".join(
        "None" if v is type(None) else getattr(_resolve_type(v), "__name__", repr(v)) for v in all_args
    )
    msg = f"Cannot coerce {_src_type(data)} {data!r} to {variant_names} at '{path}'"
    if type(None) in all_args:
        msg += ". To set this field to None, pass 'none' or 'null'."
    raise TypeCoercionError(msg)


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
        if not isinstance(value, dict):
            return False
        flds = _struct_fields(tp)
        defs = _struct_defaults(tp)
        keys = {k for k in value if k != union_tag}
        required = {n for n in flds if n not in defs}
        return required.issubset(keys) and keys.issubset(set(flds))

    if tp is bool:
        if isinstance(value, bool):
            return True
        if isinstance(value, _StrToken):
            return value.lower() in (_TRUTHY | _FALSY)
        return False

    if tp is int:
        if isinstance(value, int) and not isinstance(value, bool):
            return True
        if isinstance(value, _StrToken):
            try:
                int(value)
                return True
            except ValueError:
                return False
        return False

    if tp is float:
        if isinstance(value, float) and not isinstance(value, bool):
            return True
        if isinstance(value, _StrToken):
            try:
                float(value)
                return True
            except ValueError:
                return False
        return False

    if tp is str:
        return isinstance(value, str)

    if _is_literal(tp):
        vals = _literal_values(tp)
        if isinstance(value, _StrToken):
            s = str(value)
            return any(str(v) == s for v in vals)
        return any(type(v) is type(value) and v == value for v in vals)

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
        f" The field name can be changed via the union_tag= parameter."
    )
    return "\n".join(lines)


def _disambiguate_struct(variants: list[Any], data: dict[str, Any], union_tag: str) -> list[Any]:
    """Filter struct union variants to those matching data structurally."""
    keys = {k for k in data if k != union_tag}
    candidates = []

    for var in variants:
        var = _resolve_type(var)
        flds = _struct_fields(var)
        defs = _struct_defaults(var)
        required = {n for n in flds if n not in defs}
        all_names = set(flds)

        if not required.issubset(keys):
            continue
        if not keys.issubset(all_names):
            continue
        candidates.append(var)

    if len(candidates) <= 1:
        return candidates

    # Refine by value-type compatibility
    refined = []
    for var in candidates:
        flds = _struct_fields(var)
        ok = True
        for k in keys:
            if k in flds and not _value_matches_type(data[k], flds[k], union_tag):
                ok = False
                break
        if ok:
            refined.append(var)

    if not refined:
        return candidates
    if len(refined) <= 1:
        return refined

    return refined


def _import_class_by_path(tag: str, path: str, union_tag: str) -> type:
    """Import and validate a class by its full dotted module path.

    Raises TypeCoercionError if the path cannot be imported or does not resolve
    to a class. The tag must be a fully-qualified dotted path such as
    ``'mypackage.mymodule.MyClass'``.
    """
    from confarg._callable import _import_dotted

    try:
        obj = _import_dotted(tag)
    except TypeCoercionError as e:
        raise TypeCoercionError(
            f"Cannot import class {tag!r} from {union_tag!r} tag at '{path}': {e}."
            f" The value must be a full dotted path, e.g. 'mypackage.mymodule.MyClass'."
        ) from e
    if not isinstance(obj, type):
        raise TypeCoercionError(
            f"Value of {union_tag!r} tag at '{path}' must be a class path,"
            f" but {tag!r} resolved to {type(obj).__name__!r}, not a class."
        )
    return obj


def _construct_by_class_path(tp: type, data: dict[str, Any], path: str, union_tag: str) -> Any:
    """Import the class named by union_tag, validate it is a subclass of tp, and construct it."""
    tag = data[union_tag]
    cls = _import_class_by_path(tag, path, union_tag)
    if not issubclass(cls, tp):
        raise TypeCoercionError(f"Class {tag!r} at '{path}' is not a subclass of {tp.__module__}.{tp.__name__}.")
    cleaned = {k: v for k, v in data.items() if k != union_tag}
    return _construct_struct(cls, cleaned, path, union_tag)
