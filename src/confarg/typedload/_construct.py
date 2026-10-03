# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Value construction and union disambiguation.

Dev Notes:
    docs-dev/architecture/types/README.md
"""

from __future__ import annotations

import inspect
import types
import warnings
from typing import Any

from confarg import _defaults
from confarg._callable import _resolve_callable_spec
from confarg._cast import SCALAR_CAST_TYPES
from confarg._import import _import_dotted, dotted_name
from confarg._merge import LIST_APPEND_KEY, LIST_DELETE_KEY, LIST_REPLACE_BASE_KEY, _apply_list_ops
from confarg._types import (
    _all_have_defaults,
    _allows_none,
    _dataclass_subclasses,
    _dict_kv,
    _elem_type,
    _fixed_seq_types,
    _is_dict,
    _is_frozenset,
    _is_list,
    _is_literal,
    _is_set,
    _is_struct,
    _is_tuple,
    _is_type_ref,
    _is_union,
    _is_varlen_collection,
    _literal_values,
    _namedtuple_defaults,
    _namedtuple_fields,
    _Pinned,
    _resolve_type,
    _src_type,
    _StrToken,
    _struct_defaults,
    _struct_fields,
    _tuple_types,
    _union_args,
    _union_args_no_none,
    _union_tag_shadowed,
    _UnionSeqToken,
    _var_params,
)
from confarg.exceptions import (
    AmbiguousUnionError,
    ConfargError,
    ConfargWarning,
    MissingFieldError,
    SymbolImportError,
    TypeCoercionError,
)
from confarg.typedload._coerce import (
    _FALSY,
    _LEAF_COERCIONS,
    _NONE_TOKENS,
    _TRUTHY,
    _coerce_leaf,
    _coerce_type_ref,
    _is_struct_variant,
    _is_taggable_leaf,
    _steal_order,
    _type_kind,
    _TypeKind,
)


def _missing_field_error(fp: str, ft: Any) -> MissingFieldError:
    """Return the error for a field of type *ft* that no channel supplied at path *fp*.

    Dev Notes:
        docs-dev/architecture/types/construction.md#structs-collections-and-defaults
    """
    msg = (
        f"Missing required field '{fp}' of type {ft!r}. Set it via CLI (--{fp}), environment variable, or config file."
    )
    return MissingFieldError(msg)


def _try_pinned_dict(data: Any) -> _Pinned | None:
    """Detect a ``{__cast__: typename, __value__: raw}`` tagged dict and convert to _Pinned.

    Only a dict with exactly these two keys is a cast.

    Dev Notes:
        docs-dev/architecture/types/stealing-rule.md#cast-pinning-in-files
    """
    if not (isinstance(data, dict) and data.keys() == {"__cast__", "__value__"}):
        return None
    typename = data["__cast__"]
    tp: type | None = SCALAR_CAST_TYPES.get(typename)
    if tp is None:
        tp = next((t for t in _LEAF_COERCIONS if getattr(t, "__name__", None) == typename), None)
    if tp is None:
        valid = sorted(SCALAR_CAST_TYPES) + sorted(
            t.__name__ for t in _LEAF_COERCIONS if t not in SCALAR_CAST_TYPES.values()
        )
        msg = f"Unknown __cast__ type: {typename!r}. Valid: {valid}"
        raise TypeCoercionError(msg)
    raw = data["__value__"]
    value = _StrToken(str(raw)) if isinstance(raw, str) else raw
    return _Pinned(tp, value)


def _is_index_key(k: Any) -> bool:
    """Return True if *k* is an integer, or a string spelling of one.

    A YAML file parses a bare ``-1:`` key as the integer, while an index patch
    arrives as its string; both are the same index to a namedtuple.
    """
    if isinstance(k, int):  # bool is an int subclass, but spells no position
        return not isinstance(k, bool)
    return isinstance(k, str) and (k.isdigit() or (k.startswith("-") and k[1:].isdigit()))


def _construct_namedtuple(tp: Any, data: Any, path: str, union_tag: str) -> Any:  # noqa: C901 PLR0912
    """Construct a namedtuple from a list (positional) or dict (by name or index).

    An index key counts from the end when negative, exactly as a fixed tuple's
    index patches do.

    Dev Notes:
        docs-dev/architecture/design-decisions/namedtuple-is-a-fixed-length-sequence.md#a-namedtuple-is-a-fixed-length-sequence
    """
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
        # Determine if keys are field names or integer indices.
        # A key is an index key if it is an integer, or a string spelling of one.
        all_int_keys = all(_is_index_key(k) for k in data) if data else False
        kwargs: dict[str, Any] = {}
        if all_int_keys and data:
            # Index-keyed form: {"0": val0, "-1": val_last, ...} — one resolver for
            # "a negative key counts from the end", the fixed tuple's own.
            for idx, v in _indexed_dict_to_positions(data, n, path, f"{tp.__name__}").items():
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
                    raise _missing_field_error(fp, ft)

        return tp(**kwargs)

    raise TypeCoercionError.wrong_shape(_src_type(data), data, tp.__name__, "list, tuple, or dict", path)


def _warn_shadowed_tag_key(path: str, union_tag: str, what: str) -> None:
    """Emit the on-use warning for a tag-shaped key a member owns at a dispatch position.

    *what* names what the fields select at this position, "variant" or "subclass", so
    a key consumed at two positions (a union into a variant that itself dispatches)
    says two true things instead of one twice.

    Dev Notes:
        docs-dev/architecture/cli-parsing/casts-and-reserved-words.md#real-field-wins
    """
    warnings.warn(
        ConfargWarning.tag_shadowed_by_member(path or _defaults.ROOT_KEY, union_tag, what),
        stacklevel=2,
    )


def _construct_struct_dispatch(tp: Any, data: Any, path: str, union_tag: str) -> Any:
    """Dispatch struct construction, handling the union_tag class-path variant.

    A tag-shaped key is the class path only when no member of ``tp`` bears the tag's
    spelling; a member that does owns the key. The struct's own field builds from its
    fields, and a subclass-only field constructs through the subclass that owns it,
    the union's structural answer (BUG-103).

    Dev Notes:
        docs-dev/architecture/cli-parsing/casts-and-reserved-words.md#real-field-wins
    """
    if not isinstance(data, dict):
        raise TypeCoercionError.wrong_shape(_src_type(data), data, tp.__name__, "dict", path)
    direct_subs = [s for s in tp.__subclasses__() if _is_struct(s)]
    if union_tag in data:
        if not _union_tag_shadowed(tp, union_tag):
            return _construct_by_class_path(tp, data, path, union_tag)
        if direct_subs:
            # The tag could have dispatched here; the member's value forces the
            # structural route instead, so say so once, on use.
            _warn_shadowed_tag_key(path, union_tag, "subclass")
        if union_tag in _struct_fields(tp):
            return _construct_struct(tp, data, path, union_tag)
        return _construct_shadowed_subclass(tp, data, path, union_tag)
    if direct_subs:
        sub_names = ", ".join(dotted_name(s) for s in direct_subs)
        if _union_tag_shadowed(tp, union_tag):
            msg = (
                f"Cannot construct '{tp.__name__}' at '{path}': it has subclasses ({sub_names})"
                f" and a member spelled {union_tag!r} owns the tag's spelling, so no"
                " class-path tag can select one. Provide the fields of the subclass you"
                f" want, its {union_tag!r} field included, or rename the field or pass a"
                " different union_tag."
            )
            raise TypeCoercionError(msg)
        msg = (
            f"Cannot construct '{tp.__name__}' at '{path}': it has subclasses ({sub_names})"
            f" but no {union_tag!r} discriminator was provided."
            f" Add a {union_tag!r} field with the fully-qualified class name."
        )
        raise TypeCoercionError(msg)
    return _construct_struct(tp, data, path, union_tag)


def _construct_shadowed_subclass(tp: Any, data: dict[str, Any], path: str, union_tag: str) -> Any:
    """Construct through the subclass that owns the tag-shaped subclass-only field.

    The key is field data, so the subclass is selected the way the union's structural
    fallback selects a variant: the subclass whose fields cover the keys. Several
    matches are a loud ambiguity and none a loud refusal — never a silent pick, and
    never a strip of the value the tag-shaped key holds.

    Dev Notes:
        docs-dev/architecture/cli-parsing/casts-and-reserved-words.md#real-field-wins
    """
    subs = _dataclass_subclasses(tp)
    matches = _disambiguate_struct(subs, data, union_tag)
    if len(matches) == 1:
        return _construct_struct(matches[0], data, path, union_tag)
    if len(matches) > 1:
        raise TypeCoercionError(_ambiguous_subclass_msg(matches, data, path, union_tag))
    for sub in subs:
        try:
            return _construct_struct(sub, data, path, union_tag)
        except (ConfargError, TypeError):
            continue
    sub_names = ", ".join(dotted_name(s) for s in subs)
    msg = (
        f"Cannot construct '{tp.__name__}' at '{path}': the {union_tag!r} key is a field's"
        f" value, and no subclass accepts the provided fields (subclasses: {sub_names})."
        " Provide the fields of the subclass you want, or rename the field or pass a"
        " different union_tag."
    )
    raise TypeCoercionError(msg)


def _ambiguous_structs_msg(matches: list[Any], provided: set[str], path: str, header: str, remedy: str) -> str:
    """Build the per-variant field breakdown the two ambiguity refusals share.

    *header* names what the provided fields cannot tell apart, *remedy* how to make them
    tell it, and *provided* the keys the data carries — the caller deciding whether the
    tag-shaped key counts as one.
    """
    lines = [f"{header} at '{path}': cannot distinguish between " + ", ".join(m.__name__ for m in matches) + "."]
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
    lines.append(remedy)
    return "\n".join(lines)


def _ambiguous_subclass_msg(matches: list[Any], data: dict[str, Any], path: str, union_tag: str) -> str:
    """Build a diagnostic message for subclasses the provided fields cannot tell apart."""
    return _ambiguous_structs_msg(
        matches,
        set(data),
        path,
        "Ambiguous subclasses",
        f"A member spelled {union_tag!r} owns the tag's spelling, so no class-path tag"
        " can select between them. Rename the field or pass a different union_tag.",
    )


def _construct_taggable_leaf(tp: Any, data: dict[str, Any], path: str, union_tag: str) -> Any:
    """Construct a struct-shaped registered leaf from the dict that tags it.

    Raises:
        TypeCoercionError: If the dict carries no ``union_tag`` naming the class.

    Dev Notes:
        docs-dev/architecture/design-decisions/an-explicit-tag-opts-a-leaf-back-in.md#an-explicit-tag-opts-a-leaf-back-in
    """
    if union_tag in data and not _union_tag_shadowed(tp, union_tag):
        return _construct_struct_dispatch(tp, data, path, union_tag)
    if _union_tag_shadowed(tp, union_tag):
        msg = (
            f"Cannot coerce dict {data!r} to {tp.__name__} at '{path}'."
            f" {tp.__name__} is a registered leaf type and a member spelled {union_tag!r}"
            f" consumes the tag's spelling, so no tag can open it:"
            f" rename the field or pass a different union_tag."
        )
        raise TypeCoercionError(msg)
    msg = (
        f"Cannot coerce dict {data!r} to {tp.__name__} at '{path}'."
        f" {tp.__name__} is a registered leaf type: pass a value it coerces from, or add a"
        f" {union_tag!r} field naming {dotted_name(tp)} to build it from its fields."
    )
    raise TypeCoercionError(msg)


def _construct_collection(tp: Any, data: Any, path: str, union_tag: str) -> Any:
    """Construct a list, set, or frozenset from raw data.

    Lists accept only a list or an index-keyed dict; sets and frozensets accept
    any sequence-like value ``_build_items`` handles. The result is wrapped with
    the constructor matching the type's origin.

    Dev Notes:
        docs-dev/architecture/types/construction.md#structs-collections-and-defaults
    """
    if _is_list(tp) and not isinstance(data, list | dict):
        raise TypeCoercionError.wrong_shape(_src_type(data), data, "list", "list or dict with integer keys", path)
    items = _build_items(_elem_type(tp), data, path, union_tag)
    if _is_frozenset(tp):
        return frozenset(items)
    if _is_set(tp):
        return set(items)
    return items


def _construct_scalar(tp: Any, data: Any, path: str, union_tag: str) -> Any:
    """Construct a type reference or leaf value."""
    if _is_type_ref(tp):
        return _coerce_type_ref(tp, data, path)
    resolved = _resolve_type(tp)
    if _is_taggable_leaf(resolved) and isinstance(data, dict):
        return _construct_taggable_leaf(resolved, data, path, union_tag)
    return _coerce_leaf(tp, data, path)


def _construct_typed(tp: Any, data: Any, path: str, union_tag: str) -> Any:  # noqa: PLR0911  # one return per kind
    """Dispatch construction on the shape :func:`_type_kind` names, after a pin and None are handled."""
    match _type_kind(tp):
        case _TypeKind.ANY:
            return data
        case _TypeKind.UNION:
            return _construct_union(tp, data, path, union_tag)
        case _TypeKind.NAMEDTUPLE:
            return _construct_namedtuple(tp, data, path, union_tag)
        case _TypeKind.STRUCT:
            return _construct_struct_dispatch(tp, data, path, union_tag)
        case _TypeKind.LIST | _TypeKind.SET | _TypeKind.FROZENSET:
            return _construct_collection(tp, data, path, union_tag)
        case _TypeKind.TUPLE:
            return _construct_tuple(tp, data, path, union_tag)
        case _TypeKind.DICT:
            return _construct_dict(tp, data, path, union_tag)
        case _TypeKind.CALLABLE:
            return _resolve_callable_spec(data, tp, path=path, union_tag=union_tag, construct_fn=construct)
        case _TypeKind.TAGGABLE_LEAF | _TypeKind.LEAF:
            return _construct_scalar(tp, data, path, union_tag)


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

    Negative keys count from the end (``-1`` → ``length - 1``), as list patches do.

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
            if isinstance(field_data, dict) and name in defs and LIST_REPLACE_BASE_KEY not in field_data:
                # A carried base (deferred from merge) wins over the default — let
                # _construct_tuple resolve it rather than patching the default in place.
                field_data = _resolve_tuple_partial(field_data, ft, defs, name)
            kwargs[name] = construct(ft, field_data, path=fp, union_tag=union_tag)
        elif name in defs:
            kwargs[name] = defs[name]
        elif _is_struct_variant(ft) and _all_have_defaults(ft):
            try:
                kwargs[name] = _construct_struct(ft, {}, fp, union_tag)
            except TypeError:
                # Defaulted __init__ parameters do not promise that tp() works: the
                # shortcut guessed wrong, so the field is simply missing.
                raise _missing_field_error(fp, ft) from None
        else:
            raise _missing_field_error(fp, ft)

    var = _var_params(tp)
    var_kw = dict(kwargs.pop(var.keyword, {})) if var.keyword else {}

    if var.positional is None:
        return tp(**kwargs, **var_kw)

    return _call_with_var_positional(tp, kwargs, var.positional, var_kw)


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
    raise TypeCoercionError.wrong_shape(_src_type(data), data, "collection", "sequence or dict with integer keys", path)


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
        raise TypeCoercionError.wrong_shape(
            _src_type(data),
            data,
            "tuple",
            "list, tuple, or dict with integer keys",
            path,
        )
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
        base_seq: list[Any] = []
        patches = data
        if LIST_REPLACE_BASE_KEY in data:
            # A deferred index patch carrying a base (e.g. a config list completed by --field.N).
            base_seq = list(data[LIST_REPLACE_BASE_KEY])
            if len(base_seq) > len(tt):
                msg = f"Cannot construct {tp} at '{path}': expected {len(tt)} elements, got {len(base_seq)}"
                raise TypeCoercionError(msg)
            patches = {k: v for k, v in data.items() if k != LIST_REPLACE_BASE_KEY}
        pos = _indexed_dict_to_positions(patches, len(tt), path, f"{tp}")
        seq = [pos.get(i, base_seq[i] if i < len(base_seq) else None) for i in range(len(tt))]
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
        raise TypeCoercionError.wrong_shape(_src_type(data), data, "dict", "dict", path)
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
    if types.NoneType in all_args and isinstance(data, _StrToken) and data.lower() in _NONE_TOKENS:
        return None
    try:
        return construct(non_none[0], data, path=path, union_tag=union_tag)
    except (TypeCoercionError, MissingFieldError):
        if types.NoneType in all_args:
            name = getattr(_resolve_type(non_none[0]), "__name__", repr(non_none[0]))
            raise TypeCoercionError.cannot_coerce(_src_type(data), data, name, path, none_sentinel=True) from None
        raise  # pragma: no cover  # len(non_none)==1 without NoneType is impossible via normal Union typing


def _construct_union_by_tag(non_none: list[Any], data: dict[str, Any], path: str, union_tag: str) -> Any:
    """Construct a union value using its class tag field.

    The candidates are every ``_is_struct`` variant, registered leaves included: a tag names a
    class to build from fields, which is the one thing a leaf stays open to.

    Dev Notes:
        docs-dev/architecture/design-decisions/an-explicit-tag-opts-a-leaf-back-in.md#an-explicit-tag-opts-a-leaf-back-in
    """
    tag = data[union_tag]
    cls = _import_class_by_path(tag, path, union_tag)
    matching = [v for v in non_none if _is_struct(_resolve_type(v)) and issubclass(cls, _resolve_type(v))]
    if len(matching) > 1:
        raise AmbiguousUnionError(
            f"Class {tag!r} at '{path}' matches multiple union variants: "
            + ", ".join(dotted_name(_resolve_type(v)) for v in matching),
        )
    if matching:
        cleaned = {k: v2 for k, v2 in data.items() if k != union_tag}
        return _construct_struct(cls, cleaned, path, union_tag)
    valid_variants = sorted(dotted_name(_resolve_type(v)) for v in non_none if _is_struct(_resolve_type(v)))
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


def _try_fixed_seq_variants(fixed_vars: list[Any], data: Any, path: str, union_tag: str) -> Any:
    """Try the fixed-arity sequence variants; returns _UNION_NO_MATCH if none accept data.

    A namedtuple variant belongs here beside ``tuple[X, Y]``: both take exactly their arity
    of positional values, so both are filtered on the arity ``_fixed_seq_types`` reports.

    Dev Notes:
        docs-dev/architecture/types/leaf-coercion.md#leaf-coercion
    """
    if not (fixed_vars and isinstance(data, list | dict)):
        return _UNION_NO_MATCH
    if isinstance(data, list):
        data_len = len(data)
    else:
        try:
            data_len = (max(int(k) for k in data) + 1) if data else 0
        except ValueError:
            data_len = -1
    candidates = (
        [v for v in fixed_vars if len(_fixed_seq_types(_resolve_type(v)) or ()) == data_len] if data_len >= 0 else []
    ) or fixed_vars
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


def _coerce_scalar_variants(
    all_args: list[Any],
    scalar_leaf_vars: list[Any],
    data: Any,
    path: str,
    union_tag: str,
) -> Any:
    """Coerce data to one of the scalar leaf variants; returns _UNION_NO_MATCH on failure.

    A token is offered to the variants in stealing rank, ``None`` ranked among them rather than
    taken first. ``None`` is the one variant not built by ``_construct_scalar``: only a none
    word selects it, never the empty token ``_coerce_leaf`` accepts for a bare ``None`` target.

    Dev Notes:
        docs-dev/architecture/types/stealing-rule.md#stealing-rule
    """
    if isinstance(data, _StrToken):
        with_none = scalar_leaf_vars + ([types.NoneType] if types.NoneType in all_args else [])
        ordered = _steal_order(with_none, key=_resolve_type)
    else:
        ordered = scalar_leaf_vars
    for var in ordered:
        vr = _resolve_type(var)
        if vr is types.NoneType:
            if str(data).lower() in _NONE_TOKENS:
                return None
            continue
        try:
            # Not _coerce_leaf: it cannot build type refs (`type`, `type[X]`).
            # See docs-dev/architecture/types/stealing-rule.md#stealing-rule.
            return _construct_scalar(var, data, path, union_tag)
        except (TypeCoercionError, ValueError, TypeError):
            continue
    return _UNION_NO_MATCH


def _construct_union_leaf(all_args: list[Any], non_none: list[Any], data: Any, path: str, union_tag: str) -> Any:
    """Construct a union value by trying leaf variants in priority order."""
    leaf_vars = [v for v in non_none if not _is_struct_variant(_resolve_type(v))]
    fixed_vars = [v for v in leaf_vars if _fixed_seq_types(_resolve_type(v)) is not None]
    coll_vars = [
        v
        for v in leaf_vars
        if v not in fixed_vars and (_is_dict(_resolve_type(v)) or _is_varlen_collection(_resolve_type(v)))
    ]
    scalar_leaf_vars = [v for v in leaf_vars if v not in fixed_vars and v not in coll_vars]

    result = _try_fixed_seq_variants(fixed_vars, data, path, union_tag)
    if result is not _UNION_NO_MATCH:
        return result

    result = _try_coll_variants(coll_vars, data, path, union_tag)
    if result is not _UNION_NO_MATCH:
        return result

    result = _coerce_scalar_variants(all_args, scalar_leaf_vars, data, path, union_tag)
    if result is not _UNION_NO_MATCH:
        return result

    # A lone CLI token (e.g. `--input hello` for `bool | list[str]`) that no scalar
    # variant accepts becomes a one-element list. Only _UnionSeqToken gets this fallback.
    if isinstance(data, _UnionSeqToken):
        result = _try_coll_variants(coll_vars, [_StrToken(data)], path, union_tag)
        if result is not _UNION_NO_MATCH:
            return result

    variant_names = " | ".join(
        "None" if v is types.NoneType else getattr(_resolve_type(v), "__name__", repr(v)) for v in all_args
    )
    raise TypeCoercionError.cannot_coerce(
        _src_type(data),
        data,
        variant_names,
        path,
        none_sentinel=types.NoneType in all_args,
    )


def _construct_union(tp: Any, data: Any, path: str, union_tag: str) -> Any:
    """Construct a value for a Union type.

    Tries tag-based disambiguation, structural disambiguation for struct
    (dataclass or plain-class) variants, and finally leaf coercion in order.
    A tag-shaped key is the tag only when no struct variant owns its spelling
    as a field.

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
        if not _union_tag_shadowed(tp, union_tag):
            return _construct_union_by_tag(non_none, data, path, union_tag)
        # The tag route was a real alternative; the member's value forces the
        # structural route instead, so say so once, on use.
        _warn_shadowed_tag_key(path, union_tag, "variant")

    dc_vars = [v for v in non_none if _is_struct_variant(_resolve_type(v))]
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
    if _is_struct_variant(tp):
        return _struct_matches_value(tp, value, union_tag)
    if tp in _SCALAR_MATCHES:
        return _SCALAR_MATCHES[tp](value)
    if _is_literal(tp):
        return _literal_matches_value(tp, value)
    return True


def _ambiguous_union_msg(matches: list[Any], data: dict[str, Any], path: str, union_tag: str) -> str:
    """Build a diagnostic AmbiguousUnionError message with per-variant field breakdowns."""
    return _ambiguous_structs_msg(
        matches,
        {k for k in data if k != union_tag},
        path,
        "Ambiguous union",
        f"To select a variant add a {union_tag!r} field, e.g. {union_tag!r}: {matches[0].__name__!r}."
        f" The field name can be changed via the union_tag= parameter.",
    )


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
    keys = set(data)
    if not any(_union_tag_shadowed(var, union_tag) for var in variants):
        # A tag-shaped key no variant owns as a field is the tag, not data.
        keys.discard(union_tag)
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
        raise TypeCoercionError.not_a_subclass(tag, dotted_name(tp), path)
    cleaned = {k: v for k, v in data.items() if k != union_tag}
    return _construct_struct(cls, cleaned, path, union_tag)
