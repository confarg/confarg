# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Value construction and union disambiguation.

Dev Notes:
    docs-dev/architecture/types/README.md
"""

from __future__ import annotations

import types
import warnings
from typing import TYPE_CHECKING, Any, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

from confarg import _defaults
from confarg._callable import _OPENERS, _resolve_callable_spec, holds_an_opener, resolve_held_spec, resolve_typed_call
from confarg._cast import cast_name_for_type, holds_the_cast, type_for_cast_name
from confarg._import import _import_dotted, dotted_name
from confarg._merge import (
    MERGE_OP_KEYS,
    ListOp,
    MergeAt,
    MergeDict,
    _apply_list_ops,
    _DeleteSentinel,
    _is_pin_dict,
    _merge_existing_value,
    _replace_base,
)
from confarg._types import (
    _all_have_defaults,
    _allows_none,
    _dict_kv,
    _elem_type,
    _fixed_position,
    _fixed_seq_types,
    _init_params,
    _is_callable,
    _is_dict,
    _is_frozenset,
    _is_list,
    _is_literal,
    _is_namedtuple,
    _is_seq_variant,
    _is_set,
    _is_struct,
    _is_type_ref,
    _is_union,
    _is_varlen_collection,
    _literal_values,
    _namedtuple_defaults,
    _namedtuple_fields,
    _Pinned,
    _resolve_type,
    _spelled_position,
    _src_type,
    _StrToken,
    _struct_defaults,
    _struct_fields,
    _struct_member_names,
    _struct_required,
    _struct_subclasses,
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
    FieldPath,
    FloatOverflowWarning,
    MissingFieldError,
    SymbolImportError,
    SymbolNotFoundError,
    TypeCoercionError,
    _spell_field_path,
)
from confarg.typedload._coerce import (
    _FALSY,
    _NONE_TOKENS,
    _TRUTHY,
    _coerce_leaf,
    _coerce_type_ref,
    _held_by_any,
    _is_coercible_leaf,
    _is_struct_variant,
    _is_taggable_leaf,
    _refuse_a_forbidden_literal,
    _steal_order,
    _type_kind,
    _TypeKind,
)


def _try_pinned_dict(data: Any) -> _Pinned | None:
    """Detect a ``{__cast__: typename, __value__: raw}`` tagged dict and convert to _Pinned.

    Only a dict with exactly these two keys is a cast.

    Dev Notes:
        docs-dev/architecture/types/stealing-rule.md#cast-pinning-in-files
    """
    if not _is_pin_dict(data):
        return None
    tp = type_for_cast_name(data[_defaults.CAST_KEY])
    raw = data[_defaults.VALUE_KEY]
    value = _StrToken(str(raw)) if isinstance(raw, str) else raw
    return _Pinned(tp, value)


def _refuse_unheld_cast(tp: Any, cast_tp: Any, path: FieldPath) -> None:
    """Refuse a pin whose type the field's type does not hold.

    The construction half of the cast-admission rule: the CLI asks it at parse, so
    only a pin the merge supplied by hand can reach it.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-cast-names-a-type-the-field-holds.md#a-cast-names-a-type-the-field-holds
    """
    if not holds_the_cast(tp, cast_tp):
        raise TypeCoercionError.cast_not_held(cast_name_for_type(cast_tp), str(tp), _spell_field_path(path))


def _check_namedtuple_length(tp: Any, got: int, path: FieldPath) -> None:
    """Refuse *got* positions for a namedtuple that has fewer fields."""
    n = len(_namedtuple_fields(tp))
    if got > n:
        msg = f"Cannot construct {tp.__name__} at '{_spell_field_path(path)}': expected {n} elements, got {got}"
        raise TypeCoercionError(msg)


_LENGTH_OPS = (ListOp.APPEND, ListOp.DELETE, ListOp.DELETE_AFTER)


def _merge_at(tp: Any, union_tag: str) -> MergeAt:
    """Return where the merge stands at a node of type *tp*, for a patch construction applies in its place."""
    from confarg._typed_merge import merge_at  # noqa: PLC0415  # import cycle: the typed merge asks this module

    return merge_at(tp, union_tag)


def _apply_carried_ops(data: MergeDict, tp: Any, what: str, path: FieldPath, union_tag: str) -> MergeDict | list[Any]:
    """Apply the list ops *data* carries over the ``ListOp.BASE`` beside them, for a fixed-arity sequence.

    A fixed tuple or a namedtuple (*what* names it for the message) has no length an op
    could grow or shrink, so an append with no base below it is refused, as the dict field
    refuses one; with a base it applies as the merge would have, and the list it leaves is
    checked against the arity like any other. A list delete is refused either way: a position
    is unset in place (BUG-243). A dict holding no op is returned unchanged.

    Dev Notes:
        docs-dev/architecture/pipeline/deep-merge.md#no-channel-types-an-op
    """
    op = next((k for k in _LENGTH_OPS if k in data), None)
    if op is None:
        return data
    spelled = _spell_field_path(path)
    if deleted := next((k for k in (ListOp.DELETE, ListOp.DELETE_AFTER) if k in data), None):
        raise TypeCoercionError.position_list_delete(str(deleted), _defaults.UNSET_KEY, what, spelled)
    if ListOp.BASE not in data:
        raise TypeCoercionError.list_op_on(str(op), what, spelled)
    return _apply_list_ops(_replace_base(data, spelled), data, spelled, _merge_at(tp, union_tag))


def _lay_patch_over_positions(tp: Any, data: dict[Any, Any], path: FieldPath, union_tag: str) -> dict[Any, Any]:
    """Key a namedtuple's ``ListOp.BASE`` base list by field name and lay the patch beside it over it.

    The merge carries a positional list under ``ListOp.BASE`` beside a patch it
    cannot apply without the type, and the CLI's arity flag leaves one under its sub-flags.
    Each patch key is laid at the field whose position it names
    (:func:`~confarg._types._fixed_position`), a name and an index alike, in the patch's
    order (Q-1); a key naming no position is kept as spelled, for construction to refuse. A
    patch value refines what the base holds at its position, through the merge's own combiner.

    Dev Notes:
        docs-dev/architecture/design-decisions/namedtuple-arity-flag-argv-order.md#build-reconciles-the-positions-with-the-patch
    """
    field_names = list(_namedtuple_fields(tp))
    base = _replace_base(data, _spell_field_path(path))
    _check_namedtuple_length(tp, len(base), path)
    laid: dict[Any, Any] = dict(zip(field_names, base, strict=False))
    at = _merge_at(tp, union_tag)
    for spelled, v in data.items():
        if spelled is ListOp.BASE:
            continue
        position = _fixed_position(tp, spelled)
        k = spelled if position is None else field_names[position]
        if isinstance(v, _DeleteSentinel):
            laid.pop(k, None)  # the position is unset (BUG-243)
        elif k in laid:
            laid[k] = _merge_existing_value(laid[k], v, _spell_field_path((*path, k)), at.child(k, None, None))
        else:
            laid[k] = v
    return laid


def _construct_namedtuple(tp: Any, data: Any, path: FieldPath, union_tag: str) -> Any:
    """Construct a namedtuple from a list (positional) or dict (by name or index).

    An index key counts from the end when negative, exactly as a fixed tuple's
    index patches do. A list shorter than the arity takes the defaults of the fields it
    stops before, and raises ``MissingFieldError`` for the first one that has none, as a
    dict omitting it does.

    Dev Notes:
        docs-dev/architecture/design-decisions/namedtuple-is-a-fixed-length-sequence.md#a-namedtuple-is-a-fixed-length-sequence
    """
    flds = _namedtuple_fields(tp)
    field_names = list(flds.keys())
    field_types = list(flds.values())

    if isinstance(data, dict):
        data = _apply_carried_ops(data, tp, f"namedtuple {tp.__name__}", path, union_tag)
    if isinstance(data, dict) and ListOp.BASE in data:
        data = _lay_patch_over_positions(tp, data, path, union_tag)

    if isinstance(data, list | tuple):
        _check_namedtuple_length(tp, len(data), path)
        data = dict(zip(field_names, data, strict=False))

    if isinstance(data, dict):
        # A name and an index each name a position, the fixed tuple's own resolver for both.
        kwargs: dict[str, Any] = {}
        for idx, v in _indexed_dict_to_positions(tp, data, path, tp.__name__).items():
            if isinstance(v, _DeleteSentinel):
                continue  # the position is unset (BUG-243)
            fname = field_names[idx]
            kwargs[fname] = construct(field_types[idx], v, path=(*path, fname), union_tag=union_tag)

        # Fill in each unset field as construction fills it, or raise MissingFieldError
        for i, (fname, ft) in enumerate(flds.items()):
            if fname not in kwargs:
                if (value := unset_position(tp, i)) is _UNSET:
                    raise MissingFieldError((*path, fname), ft)
                kwargs[fname] = value

        return tp(**kwargs)

    raise TypeCoercionError.wrong_shape(
        _src_type(data),
        data,
        tp.__name__,
        "list, tuple, or dict",
        _spell_field_path(path),
    )


def _warn_shadowed_tag_key(path: FieldPath, union_tag: str, what: str) -> None:
    """Emit the on-use warning for a tag-shaped key a member owns at a dispatch position.

    *what* names what the fields select at this position, "variant" or "subclass", so
    a key consumed at two positions (a union into a variant that itself dispatches)
    says two true things instead of one twice.

    Dev Notes:
        docs-dev/architecture/cli-parsing/casts-and-reserved-words.md#real-field-wins
    """
    warnings.warn(
        ConfargWarning.tag_shadowed_by_member(_spell_field_path(path) or _defaults.ROOT_KEY, union_tag, what),
        stacklevel=2,
    )


def _construct_struct_dispatch(tp: Any, data: Any, path: FieldPath, union_tag: str) -> Any:
    """Dispatch struct construction, handling the union_tag class-path variant.

    A tag-shaped key is the class path only when no member of ``tp`` bears the tag's
    spelling; a member that does owns the key. The struct's own field builds from its
    fields, and a subclass-only field constructs through the subclass that owns it,
    the union's structural answer (BUG-103).

    Dev Notes:
        docs-dev/architecture/cli-parsing/casts-and-reserved-words.md#real-field-wins
    """
    if not isinstance(data, dict):
        raise TypeCoercionError.wrong_shape(_src_type(data), data, tp.__name__, "dict", _spell_field_path(path))
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
                f"Cannot construct '{tp.__name__}' at '{_spell_field_path(path)}': it has subclasses ({sub_names})"
                f" and a member spelled {union_tag!r} owns the tag's spelling, so no"
                " class-path tag can select one. Provide the fields of the subclass you"
                f" want, its {union_tag!r} field included, or rename the field or pass a"
                " different union_tag."
            )
            raise TypeCoercionError(msg)
        msg = (
            f"Cannot construct '{tp.__name__}' at '{_spell_field_path(path)}': it has subclasses ({sub_names})"
            f" but no {union_tag!r} discriminator was provided."
            f" Add a {union_tag!r} field with the fully-qualified class name."
        )
        raise TypeCoercionError(msg)
    return _construct_struct(tp, data, path, union_tag)


def _construct_shadowed_subclass(tp: Any, data: MergeDict, path: FieldPath, union_tag: str) -> Any:
    """Construct through the subclass that owns the tag-shaped subclass-only field.

    The key is field data, so the subclass is selected the way the union's structural
    fallback selects a variant: the subclass whose fields cover the keys. Several
    matches are a loud ambiguity and none a loud refusal — never a silent pick, and
    never a strip of the value the tag-shaped key holds.

    Dev Notes:
        docs-dev/architecture/cli-parsing/casts-and-reserved-words.md#real-field-wins
    """
    subs = _struct_subclasses(tp)
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
        f"Cannot construct '{tp.__name__}' at '{_spell_field_path(path)}': the {union_tag!r} key is a field's"
        f" value, and no subclass accepts the provided fields (subclasses: {sub_names})."
        " Provide the fields of the subclass you want, or rename the field or pass a"
        " different union_tag."
    )
    raise TypeCoercionError(msg)


def _ambiguous_structs_msg(
    matches: list[Any], provided: set[str | ListOp], path: FieldPath, header: str, remedy: str
) -> str:
    """Build the per-variant field breakdown the two ambiguity refusals share.

    *header* names what the provided fields cannot tell apart, *remedy* how to make them
    tell it, and *provided* the keys the data carries — the caller deciding whether the
    tag-shaped key counts as one.
    """
    lines = [
        f"{header} at '{_spell_field_path(path)}': cannot distinguish between "
        + ", ".join(m.__name__ for m in matches)
        + ".",
    ]
    for var in matches:
        required = _struct_required(var)
        optional = sorted(n for n in _struct_fields(var) if n not in required)
        parts = []
        if required:
            parts.append("required: " + ", ".join(sorted(required)))
        if optional:
            parts.append("optional: " + ", ".join(optional))
        lines.append(f"  {var.__name__}: {'; '.join(parts) if parts else '(no fields)'}")
    lines.append(f"Provided fields: {sorted(str(k) for k in provided) if provided else '(none)'}")
    lines.append(remedy)
    return "\n".join(lines)


def _ambiguous_subclass_msg(matches: list[Any], data: MergeDict, path: FieldPath, union_tag: str) -> str:
    """Build a diagnostic message for subclasses the provided fields cannot tell apart."""
    return _ambiguous_structs_msg(
        matches,
        set(data),
        path,
        "Ambiguous subclasses",
        f"A member spelled {union_tag!r} owns the tag's spelling, so no class-path tag"
        " can select between them. Rename the field or pass a different union_tag.",
    )


def _construct_taggable_leaf(tp: Any, data: MergeDict, path: FieldPath, union_tag: str) -> Any:
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
            f"Cannot coerce dict {data!r} to {tp.__name__} at '{_spell_field_path(path)}'."
            f" {tp.__name__} is a registered leaf type and a member spelled {union_tag!r}"
            f" consumes the tag's spelling, so no tag can open it:"
            f" rename the field or pass a different union_tag."
        )
        raise TypeCoercionError(msg)
    msg = (
        f"Cannot coerce dict {data!r} to {tp.__name__} at '{_spell_field_path(path)}'."
        f" {tp.__name__} is a registered leaf type: pass a value it coerces from, or add a"
        f" {union_tag!r} field naming {dotted_name(tp)} to build it from its fields."
    )
    raise TypeCoercionError(msg)


def _construct_collection(tp: Any, data: Any, path: FieldPath, union_tag: str) -> Any:
    """Construct a list, set, or frozenset from raw data.

    Lists accept only a list or an index-keyed dict; sets and frozensets accept
    any sequence-like value ``_build_items`` handles. The result is wrapped with
    the constructor matching the type's origin.

    Dev Notes:
        docs-dev/architecture/types/construction.md#structs-collections-and-defaults
    """
    if _is_list(tp) and not isinstance(data, list | dict):
        raise TypeCoercionError.wrong_shape(
            _src_type(data),
            data,
            "list",
            "list or dict with integer keys",
            _spell_field_path(path),
        )
    items = _build_items(_elem_type(tp), data, path, union_tag)
    if _is_frozenset(tp):
        return frozenset(items)
    if _is_set(tp):
        return set(items)
    return items


def _construct_scalar(tp: Any, data: Any, path: FieldPath, union_tag: str) -> Any:
    """Construct a type reference or leaf value.

    Raises:
        TypeCoercionError: If *data* is a dict carrying the union tag on a field that is
            no struct — the tag has no subclass to select, so the refusal names the key
            and the ``call:`` spec that computes a value the field accepts.

    Dev Notes:
        docs-dev/architecture/design-decisions/class-names-a-subclass-call-computes.md#class-names-a-subclass-call-computes
    """
    if _is_type_ref(tp):
        return _coerce_type_ref(tp, data, _spell_field_path(path))
    resolved = _resolve_type(tp)
    if _is_taggable_leaf(resolved) and isinstance(data, dict):
        return _construct_taggable_leaf(resolved, data, path, union_tag)
    if isinstance(data, dict) and union_tag in data:
        call = _defaults.CALL_KEY
        tp_name = getattr(resolved, "__name__", repr(resolved))
        msg = (
            f"Cannot coerce dict {data!r} to {tp_name} at '{_spell_field_path(path)}'."
            f" The {union_tag!r} key is the union tag, which names a subclass of a struct-typed"
            f" field's annotation; {tp_name} accepts no struct, so the tag cannot select one."
            f" A '{call}:' spec computes a value the field's type accepts."
        )
        raise TypeCoercionError(msg)
    return _coerce_leaf(tp, data, _spell_field_path(path))


def _construct_typed(tp: Any, data: Any, path: FieldPath, union_tag: str) -> Any:  # noqa: PLR0911  # one return per kind
    """Dispatch construction on the shape :func:`_type_kind` names, after a pin and None are handled."""
    match _type_kind(tp):
        case _TypeKind.ANY:
            return _construct_any(data, path, union_tag)
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


def _construct_any(data: Any, path: FieldPath, union_tag: str) -> Any:
    """Construct what an ``Any`` node holds of *data*: a spec's value, a container of ``Any`` nodes, or a leaf.

    A dict holding an opener is a spec, read with every opener (:func:`resolve_held_spec`);
    any other dict is a ``dict[Any, Any]`` and a list a ``list[Any]``, so a spec at any depth
    is read too. A leaf is held as it is, a token as its text (:func:`_held_by_any`). A
    container in which nothing changed is returned as the very object given.

    Dev Notes:
        docs-dev/architecture/callables.md#an-any-node-reads-every-opener
    """
    if isinstance(data, dict):
        if holds_an_opener(data):
            return resolve_held_spec(data, path, union_tag, construct)
        held = _construct_dict(dict[Any, Any], data, path, union_tag)
        unchanged = all(
            type(hk) is type(k) and hk == k and hv is v
            for (hk, hv), (k, v) in zip(held.items(), data.items(), strict=True)
        )
        return data if unchanged else held
    if isinstance(data, list):
        items = [construct(Any, v, path=(*path, i), union_tag=union_tag) for i, v in enumerate(data)]
        return data if all(h is v for h, v in zip(items, data, strict=True)) else items
    return _held_by_any(data)


def _is_typed_call(data: Any, tp: Any) -> bool:
    """True if *data* is a ``call:`` spec for a field of type *tp*, and that field is not a Callable.

    A ``call:`` key is a spec only where no member of the annotation could hold that key as data: a
    dict type and a Callable keep their own meaning, and a struct member named ``call``
    keeps the field's data. ``class:`` is the union tag, which already selects a struct, its
    other keys the struct's fields; a ``bind:`` beside ``call:`` is a second opener, which the
    call refuses.

    Dev Notes:
        docs-dev/architecture/callables.md#call-in-a-typed-field
    """
    if not isinstance(data, dict):
        return False
    if _defaults.CALL_KEY not in data or _defaults.CLASS_KEY in data:
        return False
    return _takes_typed_call(tp)


def _takes_typed_call(tp: Any, key: str = _defaults.CALL_KEY) -> bool:
    """True if a ``call:`` spec fills a field of type *tp*, its *key* (``call`` or ``args``) no member's.

    The type half of :func:`_is_typed_call`, which the CLI walk asks of a path, where there
    is no spec to read yet: no member of the annotation may hold ``call`` as data, nor *key*,
    which a member reached by that name keeps. A lone Callable has a ``call:`` of its own, and
    a dict type holds the key as data; in a union beside a member that reads specs, a Callable
    or ``Any``, neither does, and the call's value is the union's to take.

    Dev Notes:
        docs-dev/architecture/callables.md#call-in-a-typed-field
        docs-dev/architecture/callables.md#a-callable-beside-another-variant
    """
    tp = _resolve_type(tp)
    members = [_resolve_type(arg) for arg in _union_args_no_none(tp)] if _is_union(tp) else [tp]
    reads_specs = len(members) > 1 and any(_reads_specs(m) for m in members)
    for member in members:
        if not reads_specs and _type_kind(member) in (_TypeKind.DICT, _TypeKind.CALLABLE):
            return False
        if _is_struct(member) and not {_defaults.CALL_KEY, key}.isdisjoint(_struct_member_names(member)):
            return False
    return True


def _reads_specs(tp: Any) -> bool:
    """True if a value of type *tp* is built from a callable spec it holds: a Callable or an ``Any``."""
    return _type_kind(_resolve_type(tp)) in (_TypeKind.CALLABLE, _TypeKind.ANY)


def spec_reading_variant(tp: Any, data: Any, union_tag: str) -> Any:
    """Return the variant of the union *tp* that reads the dict *data* as a callable spec, None when none does.

    The one answer for construction and the merge. A union reads a dict holding an opener as
    its Callable variant's spec, or its ``Any`` variant's when it has no Callable, before any
    struct or dict variant tries it as data, unless a struct variant owns the key of an opener
    *data* holds, as a member owns the union tag's spelling. The union tag is not an opener
    here: it selects a struct variant first, and only a class no struct variant holds is the
    spec (:func:`_construct_union_by_tag`). A ``call:`` is no variant's: the union takes its
    value (:func:`_takes_typed_call`).

    Dev Notes:
        docs-dev/architecture/callables.md#a-callable-beside-another-variant
    """
    if not isinstance(data, dict):
        return None
    present = {k for k in _OPENERS if k in data} - {union_tag, _defaults.CALL_KEY}
    if not present:
        return None
    members = _union_args_no_none(tp)
    if any(
        _is_struct_variant(_resolve_type(m)) and present & set(_struct_member_names(_resolve_type(m))) for m in members
    ):
        return None
    return _first_spec_reader(members)


def _first_spec_reader(members: Sequence[Any]) -> Any:
    """Return the Callable among *members*, else the ``Any``, else None: the variant that builds what a spec names."""
    callables = [m for m in members if _type_kind(_resolve_type(m)) is _TypeKind.CALLABLE]
    return next(iter(callables), None) or next((m for m in members if _holds_anything(m)), None)


def reads_as_new_value(data: MergeDict, tp: Any, union_tag: str) -> bool:  # noqa: PLR0911  # one return per kind
    """True if construction reads the dict *data*, at a field of type *tp*, as naming what it builds.

    So a key a lower layer set beside it cannot belong to it, and the merge lets *data* replace
    what lies below rather than refine it. It does where construction dispatches on a key
    rather than reading it as data: a typed call (:func:`_is_typed_call`), an opener on a
    Callable or an ``Any`` node, and the union tag on a struct, a union of several members or a
    leaf, unless a member owns its spelling (``_union_tag_shadowed``). A union of several
    members reads an opener as its Callable or ``Any`` member would. An opener whose target is
    a dict holding no opener of its own (``{call: {k: 3}}``) refines the target below; a dict,
    a sequence and a struct owning the key hold it as data.

    Dev Notes:
        docs-dev/architecture/design-decisions/the-type-decides-replace-or-refine.md#the-type-decides-whether-a-value-replaces-or-refines
    """
    tp = _resolve_type(tp)
    if _is_typed_call(data, tp):
        return _names_a_target(data, (_defaults.CALL_KEY,))
    match _type_kind(tp):
        case _TypeKind.CALLABLE | _TypeKind.ANY:
            return _names_a_target(data, _OPENERS)
        case _TypeKind.UNION:
            members = [_resolve_type(m) for m in _union_args_no_none(tp)]
            if len(members) == 1:
                return reads_as_new_value(data, members[0], union_tag)
            if union_tag in data and not _union_tag_shadowed(tp, union_tag):
                return True
            reader = spec_reading_variant(tp, data, union_tag)
            return reader is not None and reads_as_new_value(data, reader, union_tag)
        case _TypeKind.STRUCT | _TypeKind.TAGGABLE_LEAF:
            return union_tag in data and not _union_tag_shadowed(tp, union_tag)
        case _TypeKind.LEAF:
            return union_tag in data
        case _:
            return False


def _names_a_target(data: MergeDict, openers: Sequence[str]) -> bool:
    """True if *data* names a target under one of *openers*: anything but a delete or a dict holding no opener."""
    return any(
        k in data
        and not isinstance(data[k], _DeleteSentinel)
        and not (isinstance(data[k], dict) and not holds_an_opener(data[k]))
        for k in openers
    )


def construct(tp: Any, data: Any, *, path: FieldPath = (), union_tag: str = _defaults.UNION_TAG) -> Any:
    """Construct a typed value from raw data.

    Dispatches to specialized constructors based on the target type.

    Args:
        tp: The target type to construct.
        data: The raw data to construct from.
        path: Where *data* sits below the target, one segment per step (a field or dict
            key by name, a sequence element by its integer index), which error messages
            name; ``()`` is the target itself.
        union_tag: The field name used as a discriminator tag in unions.

    Returns:
        The constructed value matching the target type.

    Raises:
        MissingFieldError: If a required dataclass field is missing.
        TypeCoercionError: If a value cannot be coerced to the target type.
    """
    tp = _resolve_type(tp)
    if isinstance(data, _Pinned):
        _refuse_unheld_cast(tp, data.tp, path)
        return _coerce_leaf(data.tp, data.value, _spell_field_path(path))
    pinned = _try_pinned_dict(data)
    if pinned is not None:
        _refuse_unheld_cast(tp, pinned.tp, path)
        return _coerce_leaf(pinned.tp, pinned.value, _spell_field_path(path))
    if _is_union(tp):
        # Before a None is taken and before any branch is tried: a branch refusing the value is
        # skipped, so an invalid Literal must not be left for the branch walk to meet.
        _refuse_a_forbidden_literal(tp, _spell_field_path(path))
    if data is None and _allows_none(tp):
        return None
    if _is_typed_call(data, tp):
        return resolve_typed_call(data, tp, path=path, union_tag=union_tag, construct_fn=construct)
    return _construct_typed(tp, data, path, union_tag)


def _refuse_an_index_delete(data: dict[Any, Any], path: FieldPath) -> None:
    """Raise if an index of the index-keyed *data* holds a bare node delete.

    A file's ``"N": {__unset__: true}`` would leave nothing in the slot; a list deletes an
    index by ``__delete__``. Asked by both index readers of construction, which the merge's
    ``_apply_list_ops`` mirrors.

    Raises:
        TypeCoercionError: If a value of *data* is a delete.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-file-spells-an-op-in-its-value.md#where-a-delete-has-no-meaning
    """
    for k, v in data.items():
        if isinstance(v, _DeleteSentinel):
            raise TypeCoercionError.index_unset(_defaults.UNSET_KEY, _defaults.DELETE_KEY, k, _spell_field_path(path))


def _indexed_dict_to_positions(
    tp: Any,
    data: dict[Any, Any],
    path: FieldPath,
    what: str,
) -> dict[int, Any]:
    """Map the keyed form of the fixed-length sequence *tp* to ``{position: value}``.

    Every key is read by :func:`~confarg._types._fixed_position`: an index as ``str()``
    writes one, or an integer, a negative one counting from the end, and a namedtuple's field
    name. Two keys naming one position resolve in the dict's order, the later winning, as a
    later write does (Q-1). A delete at a position is returned as it is, for the caller to
    read as the position unset (BUG-243).

    Args:
        tp: The fixed tuple or namedtuple type.
        data: The keyed dict to normalise.
        path: The construction path, which error messages name.
        what: Human-readable description of the target type for error messages.

    Raises:
        TypeCoercionError: on a key spelling one of the reserved list ops (``_merge.MERGE_OP_KEYS``
            — a marker, never the plain string, is the op), on an index out of range, or on a key
            naming no position (an unknown field of a namedtuple).

    Dev Notes:
        docs-dev/architecture/design-decisions/namedtuple-is-a-fixed-length-sequence.md#a-namedtuple-is-a-fixed-length-sequence
    """
    length = len(_fixed_seq_types(tp) or ())
    out: dict[int, Any] = {}
    unknown: list[Any] = []
    for k, v in data.items():
        if isinstance(k, str) and k in MERGE_OP_KEYS:
            msg = (
                f"Cannot construct {what} at '{_spell_field_path(path)}':"
                f" {k!r} spells a list op, which only a configuration file writes"
            )
            raise TypeCoercionError(msg)
        position = _fixed_position(tp, k)
        if position is not None:
            out[position] = v
        elif (index := _spelled_position(k)) is not None:
            spelled = _spell_field_path(path)
            msg = f"Cannot construct {what} at '{spelled}': index {index} out of range for length {length}"
            raise TypeCoercionError(msg)
        else:
            unknown.append(k)
    if unknown and _is_namedtuple(tp):
        fields = list(_namedtuple_fields(tp))
        raise TypeCoercionError.unknown_fields(set(unknown), tp.__name__, _spell_field_path(path), fields)
    if unknown:
        msg = f"Cannot construct {what} at '{_spell_field_path(path)}': dict keys must be integer indices"
        raise TypeCoercionError(msg)
    return out


def _call_struct(
    tp: Any,
    kwargs: dict[str, Any],
    var_pos_name: str | None,
    var_kw: dict[str, Any],
) -> Any:
    """Call the struct *tp* with *kwargs* by name, the list under *var_pos_name* as its ``*args``, and *var_kw*.

    The named arguments go by position or by keyword as
    :meth:`~confarg._types._PositionalParams.split` decides, so a positional-only parameter
    is reached (BUG-152), and the ``*args`` values follow the positional ones.

    Raises:
        TypeError: If *var_pos_name* holds values while a positional parameter is unfilled,
            since no call reaches ``*args`` past it.

    Dev Notes:
        docs-dev/architecture/types/introspection.md#introspection-is-cached-per-class
    """
    var_pos = list(kwargs.pop(var_pos_name, [])) if var_pos_name else []
    positional = _init_params(tp).positional
    pos_args, by_keyword = positional.split(kwargs)
    if var_pos and len(pos_args) < len(positional.names):
        unset = positional.names[len(pos_args)]
        msg = f"{tp.__name__}() cannot take *{var_pos_name} while positional parameter {unset!r} is unset"
        raise TypeError(msg)
    return tp(*pos_args, *var_pos, **by_keyword, **var_kw)


class _Naming(NamedTuple):
    """How the user named a class built from nothing: its name as written, and what its fields sit beside."""

    name: str
    beside: str


def build_from_nothing(build: Callable[[], Any], tp: Any, path: FieldPath, naming: _Naming | None = None) -> Any:
    """Return ``build()``, which builds *tp* from no key at all, reading a refused empty call.

    The one reader of "this class was asked to build from nothing, and refused": defaulting
    every ``__init__`` parameter does not promise that ``tp()`` works (``UUID``), so a
    ``TypeError`` out of the call means the guess was wrong. Where nothing was supplied (no
    *naming*: a defaulted field, the root), the value is missing, ``MissingFieldError``. Where
    a tag or an opener named the class, the user supplied it, so the refusal is a coercion
    naming the class and quoting Python's own text. Only an empty build is passed here, so a
    constructor's ``TypeError`` about supplied data still escapes as its own.

    Dev Notes:
        docs-dev/architecture/types/construction.md#a-class-built-from-nothing
    """
    try:
        return build()
    except TypeError as e:
        if naming is None:
            raise MissingFieldError(path, tp) from None
        raise TypeCoercionError.refused_empty_call(naming.name, _spell_field_path(path), str(e), naming.beside) from e


def _construct_named_struct(cls: type, data: MergeDict, path: FieldPath, union_tag: str, naming: _Naming) -> Any:
    """Build the struct *cls* a tag or an opener named, from the keys *data* holds beside it.

    With none, the class builds from nothing, and its refusal is a coercion naming it
    (:func:`build_from_nothing`, BUG-213, BUG-215).
    """
    if data:
        return _construct_struct(cls, data, path, union_tag)
    return build_from_nothing(lambda: _construct_struct(cls, {}, path, union_tag), cls, path, naming)


def _construct_struct(tp: Any, data: MergeDict, path: FieldPath, union_tag: str) -> Any:
    """Construct a dataclass or plain-class instance from a dict of raw data."""
    flds = _struct_fields(tp)
    defs = _struct_defaults(tp)
    kwargs: dict[str, Any] = {}

    extra = {k for k in data if k not in flds and k != union_tag}
    if extra:
        raise TypeCoercionError.unknown_fields(extra, tp.__name__, _spell_field_path(path), sorted(flds))

    for name, ft in flds.items():
        fp = (*path, name)
        if name in data:
            kwargs[name] = construct(ft, data[name], path=fp, union_tag=union_tag)
        elif name in defs:
            kwargs[name] = defs[name]
        elif _is_struct_variant(ft) and _all_have_defaults(ft):
            kwargs[name] = build_from_nothing(lambda ft=ft, fp=fp: _construct_struct(ft, {}, fp, union_tag), ft, fp)
        else:
            raise MissingFieldError(fp, ft)

    var = _var_params(tp)
    var_kw = dict(kwargs.pop(var.keyword, {})) if var.keyword else {}
    return _call_struct(tp, kwargs, var.positional, var_kw)


def _build_items(et: Any, data: Any, path: FieldPath, union_tag: str) -> list[Any]:
    """Build a list of constructed items from sequence-like raw data.

    Args:
        et: The element type to construct each item as.
        data: The raw data (list, set, frozenset, tuple, or dict with integer keys).
        path: The construction path, which error messages name.
        union_tag: The field name used as a discriminator tag in unions.

    Returns:
        A list of constructed items.

    Raises:
        TypeCoercionError: If data is not a sequence or dict with integer keys.
    """
    if isinstance(data, list | set | frozenset | tuple):
        return [construct(et, v, path=(*path, i), union_tag=union_tag) for i, v in enumerate(data)]
    if isinstance(data, dict):
        if ListOp.BASE in data:
            # CLI-produced dict with an explicit base list; apply ops in order.
            at = _merge_at(list[et], union_tag)
            working = _apply_list_ops(_replace_base(data, _spell_field_path(path)), data, _spell_field_path(path), at)
            return [construct(et, v, path=(*path, i), union_tag=union_tag) for i, v in enumerate(working)]
        if ListOp.APPEND in data:
            # Append-only dict: apply all list ops (appends, deletions, index patches) against an empty base.
            working = _apply_list_ops([], data, _spell_field_path(path), _merge_at(list[et], union_tag))
            return [construct(et, v, path=(*path, i), union_tag=union_tag) for i, v in enumerate(working)]
        if ListOp.DELETE in data or ListOp.DELETE_AFTER in data:
            msg = (
                f"List deletion (the '-' operator) at '{_spell_field_path(path)}' requires a base list to delete from,"
                " but no base list was provided. Supply the full list via a config file or other source."
            )
            raise TypeCoercionError(msg)
        if not data:
            return []
        try:
            # One reading of an index key, whether a file spelled it as text or as a YAML integer.
            positions = {int(k): v for k, v in data.items()}
        except (TypeError, ValueError):
            msg = f"Cannot construct collection at '{_spell_field_path(path)}': dict keys must be integer indices"
            raise TypeCoercionError(msg) from None
        _refuse_an_index_delete(positions, path)
        neg = [k for k in positions if k < 0]
        if neg:
            msg = (
                f"Negative index/indices {sorted(neg)} at '{_spell_field_path(path)}' require a base list to"
                " resolve against, but no base list was provided. Supply the full list via"
                " a config file or other source."
            )
            raise TypeCoercionError(msg)
        max_idx = max(positions)
        gaps = [i for i in range(max_idx + 1) if i not in positions]
        if gaps and not _allows_none(et):
            msg = (
                f"List at '{_spell_field_path(path)}' has gap(s) at index/indices {gaps}:"
                f" when using index-keyed form, all indices 0-{max_idx} must be provided,"
                f" or the element type must be Optional."
            )
            raise TypeCoercionError(msg)
        return [construct(et, positions.get(i), path=(*path, i), union_tag=union_tag) for i in range(max_idx + 1)]
    raise TypeCoercionError.wrong_shape(
        _src_type(data),
        data,
        "collection",
        "sequence or dict with integer keys",
        _spell_field_path(path),
    )


def _construct_tuple(tp: Any, data: Any, path: FieldPath, union_tag: str) -> tuple[Any, ...]:
    """Construct a tuple from raw data.

    Handles both fixed-length and variable-length (tuple[X, ...]) tuples.

    Args:
        tp: The tuple type.
        data: The raw data (list, tuple, or dict with integer keys).
        path: The construction path, which error messages name.
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
            _spell_field_path(path),
        )
    if isinstance(data, dict):
        data = _apply_carried_ops(data, tp, f"{tp}", path, union_tag)
    if isinstance(data, list | tuple):
        if len(data) > len(tt):
            msg = f"Cannot construct {tp} at '{_spell_field_path(path)}': expected {len(tt)} elements, got {len(data)}"
            raise TypeCoercionError(msg)
        if len(data) < len(tt):
            missing = [i for i in range(len(data), len(tt)) if not _allows_none(tt[i])]
            if missing:
                msg = (
                    f"Cannot construct {tp} at '{_spell_field_path(path)}'"
                    f": expected {len(tt)} elements, got {len(data)}"
                )
                raise TypeCoercionError(msg)
        seq = list(data)
    else:
        seq = _patched_positions(tp, tt, data, path, union_tag)
    return tuple(
        _construct_position(tp, i, seq[i] if i < len(seq) else None, (*path, i), union_tag) for i in range(len(tt))
    )


def _patched_positions(tp: Any, tt: Sequence[Any], data: MergeDict, path: FieldPath, union_tag: str) -> list[Any]:
    """Lay a fixed tuple's index patch over the base it carries, ``_UNSET`` where neither fills a position."""
    base_seq: list[Any] = []
    patches = data
    if ListOp.BASE in data:
        # A deferred index patch carrying a base (e.g. a config list completed by --field.N).
        base_seq = _replace_base(data, _spell_field_path(path))
        if len(base_seq) > len(tt):
            spelled = _spell_field_path(path)
            msg = f"Cannot construct {tp} at '{spelled}': expected {len(tt)} elements, got {len(base_seq)}"
            raise TypeCoercionError(msg)
        patches = {k: v for k, v in data.items() if k != ListOp.BASE}
    seq = [base_seq[i] if i < len(base_seq) else _UNSET for i in range(len(tt))]
    # A patch refines what the base holds at its position, as the merge would have.
    at = _merge_at(tp, union_tag)
    for i, v in _indexed_dict_to_positions(tp, patches, path, f"{tp}").items():
        if isinstance(v, _DeleteSentinel):
            seq[i] = _UNSET  # the position is unset (BUG-243)
        elif i < len(base_seq):
            seq[i] = _merge_existing_value(seq[i], v, _spell_field_path((*path, i)), at.child(str(i), None, None))
        else:
            seq[i] = v
    return seq


# A fixed tuple's position that neither a base nor a patch filled.
_UNSET: Any = object()


def _construct_position(tp: Any, i: int, value: Any, path: FieldPath, union_tag: str) -> Any:
    """Construct the position *i* of the fixed tuple *tp*, an unset one as :func:`unset_position` fills it."""
    et = (_tuple_types(tp) or [])[i]
    if value is _UNSET and (value := unset_position(tp, i)) is _UNSET:
        raise MissingFieldError(path, et)
    return construct(et, value, path=path, union_tag=union_tag)


def unset_position(tp: Any, i: int) -> Any:
    """Return what construction fills position *i* of the fixed-length *tp* with when unset, ``_UNSET`` if nothing.

    A namedtuple field's class default, and a fixed tuple's ``None`` where its type takes
    ``None``; elsewhere the position is a missing field. The one answer construction and the
    default layer share, which lays it so that a reference reads what the field builds to
    (BUG-243).

    Dev Notes:
        docs-dev/architecture/design-decisions/a-fixed-length-delete-unsets-a-position.md#a-fixed-length-delete-unsets-a-position
    """
    if _is_namedtuple(tp):
        return _namedtuple_defaults(tp).get(list(_namedtuple_fields(tp))[i], _UNSET)
    positions = _fixed_seq_types(tp) or []
    return None if i < len(positions) and _allows_none(positions[i]) else _UNSET


def _construct_dict(tp: Any, data: Any, path: FieldPath, union_tag: str) -> dict[Any, Any]:
    """Construct a typed dict from raw data.

    Args:
        tp: The dict type (e.g. dict[str, int]).
        data: The raw data dict.
        path: The construction path, which error messages name.
        union_tag: The field name used as a discriminator tag in unions.

    Returns:
        The constructed dict with coerced keys and constructed values.

    Raises:
        TypeCoercionError: If data is not a dict, or holds a list op the merge recorded.
    """
    kt, vt = _dict_kv(tp)
    if not isinstance(data, dict):
        raise TypeCoercionError.wrong_shape(_src_type(data), data, "dict", "dict", _spell_field_path(path))
    if op := next((k for k in data if isinstance(k, ListOp)), None):
        raise TypeCoercionError.list_op_on(str(op), "dict", _spell_field_path(path))
    return {
        _coerce_leaf(kt, _StrToken(k) if isinstance(k, str) else k, _spell_field_path(path)): construct(
            vt,
            v,
            path=(*path, str(k)),
            union_tag=union_tag,
        )
        for k, v in data.items()
    }


_UNION_NO_MATCH: object = object()


def _holds_anything(variant: Any) -> bool:
    """Return whether union *variant* is ``Any``, the variant every value is held by.

    Dev Notes:
        docs-dev/architecture/types/construction.md#an-any-variant-is-tried-last
    """
    return _type_kind(_resolve_type(variant)) is _TypeKind.ANY


def _first_constructible(variants: list[Any], data: Any, path: FieldPath, union_tag: str) -> Any:
    """Construct *data* as the first of *variants* that accepts it, or return _UNION_NO_MATCH."""
    for var in variants:
        try:
            return construct(var, data, path=path, union_tag=union_tag)
        except (ConfargError, TypeError):
            continue
    return _UNION_NO_MATCH


def _reads_none_word(all_args: list[Any], data: Any) -> bool:
    """Return whether a union of *all_args* reads *data* as a none word when it spells one.

    Only a token is read as one, and only for a union counting ``None`` among its variants: a
    file writes ``None`` as its own null, and its ``"none"`` stays a string. The one test for
    selecting ``None`` off a value and for offering the none-word remedy when the value fails.

    Dev Notes:
        docs-dev/architecture/types/construction.md#an-optional-field-fails-as-its-variant
    """
    return types.NoneType in all_args and isinstance(data, _StrToken)


def _selects_none(all_args: list[Any], data: Any) -> bool:
    """Return whether a union of *all_args* reads *data* as ``None``: a token spelling a none word.

    The one test for selecting ``None`` off a value. The CLI parser asks it too, to store a
    lone none-word run bare, as the environment stores it, rather than as a one-item list.

    Dev Notes:
        docs-dev/architecture/types/construction.md#an-optional-field-fails-as-its-variant
    """
    return _reads_none_word(all_args, data) and str(data).lower() in _NONE_TOKENS


def _construct_single_variant_union(
    all_args: list[Any],
    non_none: list[Any],
    data: Any,
    path: FieldPath,
    union_tag: str,
) -> Any:
    """Construct a union that has exactly one non-None variant.

    A token spelling a none word is ``None``. Any other value is the variant's, and fails with
    the variant's own error; for a token, that error also says how to pass ``None``.

    Dev Notes:
        docs-dev/architecture/types/construction.md#an-optional-field-fails-as-its-variant
    """
    if _selects_none(all_args, data):
        return None
    reads_none_word = _reads_none_word(all_args, data)
    try:
        return construct(non_none[0], data, path=path, union_tag=union_tag)
    except (TypeCoercionError, MissingFieldError) as e:
        if reads_none_word:
            raise e._with_none_remedy() from None
        raise


def _construct_union_by_tag(non_none: list[Any], data: MergeDict, path: FieldPath, union_tag: str) -> Any:
    """Construct a union value using its class tag field.

    The candidates are every ``_is_struct`` variant, registered leaves included: a tag names a
    class to build from fields, which is the one thing a leaf stays open to. A class no
    candidate holds is the spec of the variant that reads specs, a Callable or else an ``Any``,
    when the union has one; a tag that does not import is refused either way.

    Dev Notes:
        docs-dev/architecture/design-decisions/an-explicit-tag-opts-a-leaf-back-in.md#an-explicit-tag-opts-a-leaf-back-in
        docs-dev/architecture/callables.md#an-any-node-reads-every-opener
    """
    tag = data[union_tag]
    cls = _import_class_by_path(tag, path, union_tag)
    matching = [v for v in non_none if _is_struct(_resolve_type(v)) and issubclass(cls, _resolve_type(v))]
    if len(matching) > 1:
        raise AmbiguousUnionError(
            f"Class {tag!r} at '{_spell_field_path(path)}' matches multiple union variants: "
            + ", ".join(dotted_name(_resolve_type(v)) for v in matching),
        )
    if matching:
        cleaned = {k: v2 for k, v2 in data.items() if k != union_tag}
        return _construct_named_struct(cls, cleaned, path, union_tag, _Naming(tag, "tag"))
    reader = _first_spec_reader(non_none)
    if reader is not None:
        # A class no variant holds is the spec of the variant that reads one, which builds the class it names.
        return construct(reader, data, path=path, union_tag=union_tag)
    valid_variants = sorted(dotted_name(_resolve_type(v)) for v in non_none if _is_struct(_resolve_type(v)))
    msg = (
        f"Class {tag!r} at '{_spell_field_path(path)}' is not compatible with any union variant."
        f" Expected a subclass of one of: {valid_variants}"
    )
    raise TypeCoercionError(msg)


def _try_construct_union_struct(dc_vars: list[Any], data: MergeDict, path: FieldPath, union_tag: str) -> Any:
    """Try structural disambiguation then fallback for struct variants.

    Returns _UNION_NO_MATCH if no struct variant accepts the data.
    """
    matches = _disambiguate_struct(dc_vars, data, union_tag)
    if len(matches) == 1:
        return construct(matches[0], data, path=path, union_tag=union_tag)
    if len(matches) > 1:
        raise AmbiguousUnionError(_ambiguous_union_msg(matches, data, path, union_tag))
    return _first_constructible(dc_vars, data, path, union_tag)


def _try_fixed_seq_variants(fixed_vars: list[Any], data: Any, path: FieldPath, union_tag: str) -> Any:
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
        except (TypeError, ValueError):  # a key spelling no index, or a pending list op
            data_len = -1
    candidates = (
        [v for v in fixed_vars if len(_fixed_seq_types(_resolve_type(v)) or ()) == data_len] if data_len >= 0 else []
    ) or fixed_vars
    return _first_constructible(candidates, data, path, union_tag)


def _try_coll_variants(coll_vars: list[Any], data: Any, path: FieldPath, union_tag: str) -> Any:
    """Try constructing from collection variants; returns _UNION_NO_MATCH if none accept data."""
    if not (coll_vars and isinstance(data, dict | list | set | frozenset)):
        return _UNION_NO_MATCH
    return _first_constructible(coll_vars, data, path, union_tag)


class _LeafVariants(NamedTuple):
    """A union's variants that are no struct, by the rung of ``_construct_union_leaf`` that tries them."""

    fixed: list[Any]
    collections: list[Any]
    scalars: list[Any]
    anything: list[Any]


def _leaf_variants(non_none: list[Any]) -> _LeafVariants:
    """Sort the non-``None`` variants *non_none* of a union into the rungs a value meets them on."""
    anything = [v for v in non_none if _holds_anything(v)]
    leaf_vars = [v for v in non_none if not _is_struct_variant(_resolve_type(v)) and v not in anything]
    fixed = [v for v in leaf_vars if _fixed_seq_types(_resolve_type(v)) is not None]
    collections = [
        v
        for v in leaf_vars
        if v not in fixed and (_is_dict(_resolve_type(v)) or _is_varlen_collection(_resolve_type(v)))
    ]
    scalars = [v for v in leaf_vars if v not in fixed and v not in collections]
    return _LeafVariants(fixed, collections, scalars, anything)


def _ranked_scalar_variants(all_args: list[Any], scalar_leaf_vars: list[Any], data: Any) -> list[Any]:
    """Return the scalar variants *data* is offered to, in stealing rank, ``None`` among them for a none word.

    Every value is ranked, a token and a file's value alike: only a token is converted, but any
    value is recognized by a variant that names it. ``None`` is ranked among the variants rather
    than taken first, and only a token's none word brings it in.

    Dev Notes:
        docs-dev/architecture/types/stealing-rule.md#stealing-rule
    """
    with_none = scalar_leaf_vars + ([types.NoneType] if _reads_none_word(all_args, data) else [])
    return _steal_order(with_none, key=_resolve_type)


def _first_scalar_variant_taking(
    ordered: list[Any],
    all_args: list[Any],
    data: Any,
    path: FieldPath,
    union_tag: str,
) -> tuple[Any, Any] | None:
    """Return the first variant of *ordered* that takes *data* with the value it builds, None when none does.

    The one walk of a union's scalar variants, for construction and for what an expression
    reads. ``None`` is the one variant not built by ``_construct_scalar``: only a none word
    selects it, never the empty token ``_coerce_leaf`` accepts for a bare ``None`` target. A
    module that fails while a type reference imports it is not a refusal, and stops the union.

    Dev Notes:
        docs-dev/architecture/types/stealing-rule.md#stealing-rule
    """
    for var in ordered:
        vr = _resolve_type(var)
        if vr is types.NoneType:
            if _selects_none(all_args, data):
                return var, None
            continue
        try:
            return var, _construct_scalar_variant(var, data, path, union_tag)
        except (TypeCoercionError, SymbolNotFoundError, ValueError, TypeError):
            continue
    return None


def _construct_scalar_variant(var: Any, data: Any, path: FieldPath, union_tag: str) -> Any:
    """Build *data* as the scalar variant *var*: a Callable from the spec it names, any other leaf as one.

    Raises:
        SymbolNotFoundError: If a Callable's path names nothing, which the walk reads as a refusal.
        SymbolImportError: If a module on a path exists but fails while it is imported.
    """
    if _type_kind(_resolve_type(var)) is _TypeKind.CALLABLE:
        return _resolve_callable_spec(data, var, path=path, union_tag=union_tag, construct_fn=construct)
    # Not _coerce_leaf: it cannot build type refs (`type`, `type[X]`).
    # See docs-dev/architecture/types/stealing-rule.md#stealing-rule.
    return _construct_scalar(var, data, path, union_tag)


def _coerce_scalar_variants(
    all_args: list[Any],
    scalar_leaf_vars: list[Any],
    data: Any,
    path: FieldPath,
    union_tag: str,
) -> Any:
    """Coerce data to one of the scalar leaf variants, in stealing rank; returns _UNION_NO_MATCH on failure.

    Dev Notes:
        docs-dev/architecture/types/stealing-rule.md#stealing-rule
    """
    ordered = _ranked_scalar_variants(all_args, scalar_leaf_vars, data)
    taken = _first_scalar_variant_taking(ordered, all_args, data, path, union_tag)
    return _UNION_NO_MATCH if taken is None else taken[1]


def read_union_leaf(tp: Any, value: Any) -> Any:
    """Return what an expression reads of the leaf *value* at the union *tp*: the value a variant builds, or *value*.

    The variant is the one construction picks, through the same walk: *value* reads as the
    object, the number or the bool that variant builds, so a token ``5`` at ``int | str`` reads
    ``5`` and a file's ``1`` at ``float | str`` reads ``1.0``. Text, which the ``str`` variant
    takes, reads as written, and so does a value no variant takes, for construction to refuse.
    A Callable variant is skipped, so the reading builds no callable, and the reading never
    warns: construction warns of what it builds.

    Dev Notes:
        docs-dev/architecture/expressions/values-and-references.md#a-typed-leaf-reads-as-its-object
    """
    all_args = _union_args(tp)
    scalars = _leaf_variants(_union_args_no_none(tp)).scalars
    ordered = [v for v in _ranked_scalar_variants(all_args, scalars, value) if not _is_callable(_resolve_type(v))]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FloatOverflowWarning)
        taken = _first_scalar_variant_taking(ordered, all_args, value, (), _defaults.UNION_TAG)
    if taken is None or _resolve_type(taken[0]) is str:
        return value
    return taken[1]


def _construct_union_leaf(all_args: list[Any], non_none: list[Any], data: Any, path: FieldPath, union_tag: str) -> Any:
    """Construct a union value by trying leaf variants in priority order.

    An ``Any`` variant is the last rung: it takes what every other variant refused. A value no
    variant accepts fails naming the whole union; for a token, the refusal also says how to pass
    ``None`` (BUG-162).

    Dev Notes:
        docs-dev/architecture/types/construction.md#an-optional-field-fails-as-its-variant
        docs-dev/architecture/types/construction.md#an-any-variant-is-tried-last
    """
    fixed_vars, coll_vars, scalar_leaf_vars, any_vars = _leaf_variants(non_none)

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

    if any_vars:
        return construct(any_vars[0], data, path=path, union_tag=union_tag)

    variant_names = " | ".join(_variant_name(v) for v in all_args)
    if isinstance(data, dict) and ListOp.BASE in data:
        # A patch the merge deferred with its base ({__base__: base, **patch}) is a sequence
        # patch; every variant refused it above, so the first sequence variant tried has its
        # own refusal name the key it cannot place, where printing *data* would show the
        # merge's internal base key (BUG-200).
        seq_var = next((v for v in (*fixed_vars, *coll_vars) if _is_seq_variant(v)), None)
        if seq_var is not None:
            construct(seq_var, data, path=path, union_tag=union_tag)
    raise TypeCoercionError.cannot_coerce_to_union(
        _src_type(data),
        data,
        variant_names,
        _spell_field_path(path),
        unread=[_variant_name(v) for v in scalar_leaf_vars if _reads_nothing(v)],
        none_sentinel=_reads_none_word(all_args, data),
    )


def _variant_name(variant: Any) -> str:
    """Return how a union refusal names *variant*: its class name, ``None``, or the type as written."""
    if variant is types.NoneType:
        return "None"
    return getattr(_resolve_type(variant), "__name__", repr(variant))


def _reads_nothing(variant: Any) -> bool:
    """True if the scalar union branch *variant* is a leaf construction reads no value as, such as ``bytes``.

    A union skips such a branch; its refusal names it, since no value could have reached it.
    """
    vr = _resolve_type(variant)
    return not (_is_coercible_leaf(vr) or _is_type_ref(vr) or _type_kind(vr) is _TypeKind.CALLABLE)


def _construct_union(tp: Any, data: Any, path: FieldPath, union_tag: str) -> Any:
    """Construct a value for a Union type.

    Tries tag-based disambiguation, structural disambiguation for struct
    (dataclass or plain-class) variants, and finally leaf coercion in order.
    A tag-shaped key is the tag only when no struct variant owns its spelling
    as a field.

    Args:
        tp: The Union type.
        data: The raw data.
        path: The construction path, which error messages name.
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

    reader = spec_reading_variant(tp, data, union_tag)
    if reader is not None:
        return construct(reader, data, path=path, union_tag=union_tag)

    dc_vars = [v for v in non_none if _is_struct_variant(_resolve_type(v))]
    if isinstance(data, dict) and dc_vars:
        result = _try_construct_union_struct(dc_vars, data, path, union_tag)
        if result is not _UNION_NO_MATCH:
            return result

    return _construct_union_leaf(all_args, non_none, data, path, union_tag)


def _struct_matches_value(tp: Any, value: Any, union_tag: str) -> bool:
    """Check if value could be a valid dict for struct tp."""
    return isinstance(value, dict) and _structurally_matches(tp, _field_keys([tp], value, union_tag))


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


def _ambiguous_union_msg(matches: list[Any], data: MergeDict, path: FieldPath, union_tag: str) -> str:
    """Build a diagnostic AmbiguousUnionError message with per-variant field breakdowns."""
    return _ambiguous_structs_msg(
        matches,
        {k for k in data if k != union_tag},
        path,
        "Ambiguous union",
        f"To select a variant add a {union_tag!r} field, e.g. {union_tag!r}: {matches[0].__name__!r}."
        f" The field name can be changed via the union_tag= parameter.",
    )


def _structurally_matches(var: Any, keys: set[str | ListOp]) -> bool:
    """Return True if var's fields cover keys and all required fields are present."""
    return _struct_required(var).issubset(keys) and keys.issubset(_struct_fields(var))


def _type_compatible(var: Any, data: MergeDict, keys: set[str | ListOp], union_tag: str) -> bool:
    """Return True if data values are compatible with var's field types."""
    flds = _struct_fields(var)
    return all(_value_matches_type(data[k], flds[k], union_tag) for k in keys if isinstance(k, str) and k in flds)


def _field_keys(variants: list[Any], data: MergeDict, union_tag: str) -> set[str | ListOp]:
    """Return the keys of *data* the struct *variants* would read as fields.

    A tag-shaped key no variant owns as a field is the tag, not data (BUG-102); one a
    variant owns is a field, at every depth the structural check reaches (BUG-107).

    Dev Notes:
        docs-dev/architecture/cli-parsing/casts-and-reserved-words.md#real-field-wins
    """
    keys = set(data)
    if not any(_union_tag_shadowed(var, union_tag) for var in variants):
        keys.discard(union_tag)
    return keys


def _disambiguate_struct(variants: list[Any], data: MergeDict, union_tag: str) -> list[Any]:
    """Filter struct union variants to those matching data structurally."""
    keys = _field_keys(variants, data, union_tag)
    candidates = [_resolve_type(var) for var in variants if _structurally_matches(_resolve_type(var), keys)]

    if len(candidates) <= 1:
        return candidates

    refined = [var for var in candidates if _type_compatible(var, data, keys, union_tag)]

    if not refined:
        return candidates
    return refined


def _import_class_by_path(tag: str, path: FieldPath, union_tag: str) -> type:
    """Import and validate a class by its full dotted module path.

    Raises TypeCoercionError if the path cannot be imported or does not resolve
    to a class. The tag must be a fully-qualified dotted path such as
    ``'mypackage.mymodule.MyClass'``.
    """
    try:
        obj = _import_dotted(tag)
    except SymbolImportError as e:
        msg = (
            f"Cannot import class {tag!r} from {union_tag!r} tag at '{_spell_field_path(path)}': {e}."
            f" The value must be a full dotted path, e.g. 'mypackage.mymodule.MyClass'."
        )
        raise TypeCoercionError(msg) from e
    if not isinstance(obj, type):
        msg = (
            f"Value of {union_tag!r} tag at '{_spell_field_path(path)}' must be a class path,"
            f" but {tag!r} resolved to {type(obj).__name__!r}, not a class."
        )
        raise TypeCoercionError(msg)
    return obj


def _construct_by_class_path(tp: type, data: MergeDict, path: FieldPath, union_tag: str) -> Any:
    """Import the class named by union_tag, validate it is a subclass of tp, and construct it."""
    tag = data[union_tag]
    cls = _import_class_by_path(tag, path, union_tag)
    if not issubclass(cls, tp):
        call = _defaults.CALL_KEY
        raise TypeCoercionError.tag_not_a_subclass(tag, dotted_name(tp), _spell_field_path(path), call)
    cleaned = {k: v for k, v in data.items() if k != union_tag}
    return _construct_named_struct(cls, cleaned, path, union_tag, _Naming(tag, "tag"))


def construct_named_class(  # noqa: PLR0913  # the class, its keys, and how the spec named it
    cls: type,
    data: MergeDict,
    *,
    path: FieldPath,
    union_tag: str,
    name: str,
    opener: str,
) -> Any:
    """Build exactly *cls* from *data*, whatever subclasses it has.

    *cls* is the class a callable spec names: the one ``class:`` names, or the owner a
    ``classfn:`` path names. Subclass dispatch has nothing left to choose, as after a union
    tag selected the class. A tag key in *data* would name a second class, so it is refused
    as an unknown field, unless *cls* declares a field of that spelling. A class that is no
    struct is built as :func:`construct` builds it. *name* is the class as the spec wrote it
    and *opener* the key that named it, which a refused empty call quotes
    (:func:`build_from_nothing`).

    Dev Notes:
        docs-dev/architecture/design-decisions/class-names-the-type-it-builds.md#class-names-the-type-it-builds
    """
    if not _is_struct(cls):
        return construct(cls, data, path=path, union_tag=union_tag)
    flds = _struct_fields(cls)
    if union_tag in data and union_tag not in flds:
        raise TypeCoercionError.unknown_fields([union_tag], cls.__name__, _spell_field_path(path), sorted(flds))
    return _construct_named_struct(cls, data, path, union_tag, _Naming(name, f"{opener!r} opener"))
