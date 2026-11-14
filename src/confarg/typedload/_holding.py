# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Whether a value is one of a type: the one predicate construction and the dump both ask.

Dev Notes:
    docs-dev/architecture/types/serialization.md#a-value-its-type-does-not-hold-dumps-as-an-any-node-holds-it
"""

from __future__ import annotations

from collections.abc import Collection
from itertools import repeat
from typing import TYPE_CHECKING, Any

from confarg._conformance import is_protocol
from confarg._depth import MAX_DEPTH
from confarg._types import (
    _allows_none,
    _class_of,
    _dict_kv,
    _elem_type,
    _fixed_seq_types,
    _generic_origin,
    _is_literal,
    _is_type_ref,
    _literal_members,
    _namedtuple_fields,
    _origin,
    _resolve_type,
    _struct_state_fields,
    _type_ref_admits,
    _union_branches,
)
from confarg.typedload._coerce import _type_kind, _TypeKind

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


def _holds(tp: Any, instance: Any) -> bool:
    """True if *instance* is a value of the resolved declared type *tp*, as a type checker reads it.

    A union holds what one of its variants holds (:func:`_find_variant_type`), ``None`` where
    it lists ``None``; any other type what :func:`_variant_holds` or :func:`_holds_widened` says it holds.

    Dev Notes:
        docs-dev/architecture/types/serialization.md#a-value-its-type-does-not-hold-dumps-as-an-any-node-holds-it
    """
    if _type_kind(tp) is not _TypeKind.UNION:
        return _variant_holds(tp, instance) or _holds_widened(tp, instance)
    if instance is None:
        return _allows_none(tp)
    return bool(_holding_variants(_union_branches(tp), instance))


def _find_variant_type(tp: Any, instance: Any) -> Any | None:
    """Find which Union variant the instance belongs to, in declaration order, ``Any`` last.

    ``Any`` holds every instance, so it is asked after every other variant, as construction
    offers it a value only after every other variant refused it. A variant that holds the
    value exactly (:func:`_variant_holds`) is preferred over one that holds it only widened
    (:func:`_holds_widened`), so ``float | int`` writes ``1`` as the int it is. A variant
    holding what the value contains is preferred over both (:func:`first_holding_variant`).

    Dev Notes:
        docs-dev/architecture/types/construction.md#an-any-variant-is-tried-last
    """
    return first_holding_variant(_union_branches(tp), instance)


def first_holding_variant(variants: Sequence[Any], instance: Any) -> Any | None:
    """Return the first of a union's *variants* holding *instance* whole, else the first holding it by its class.

    Dev Notes:
        docs-dev/architecture/types/serialization.md#a-collection-variant-is-picked-by-what-it-holds
    """
    holding = _holding_variants(variants, instance)
    if len(holding) < 2:  # noqa: PLR2004  # the walk only tells two holders apart
        return holding[0] if holding else None
    return next((variant for variant in holding if _holds_whole(variant, instance)), holding[0])


def _holding_variants(variants: Sequence[Any], instance: Any) -> list[Any]:
    """Return the *variants* holding *instance* by its class, exact ones before widened, ``Any`` last of each."""
    ordered = sorted(variants, key=_holds_anything)
    exact = [variant for variant in ordered if _variant_holds(variant, instance)]
    return exact + [variant for variant in ordered if variant not in exact and _holds_widened(variant, instance)]


def _holds_whole(tp: Any, instance: Any, above: frozenset[int] = frozenset()) -> bool:  # noqa: PLR0911  # one return per kind
    """True if *tp* holds *instance* and everything it contains, at every depth.

    *above* holds the id of each value being walked. A value inside itself or past
    ``MAX_DEPTH`` counts as held, for the dump to refuse by itself, and a one-shot iterator
    counts as held so that the walk leaves its items to the dump.

    Dev Notes:
        docs-dev/architecture/types/serialization.md#a-collection-variant-is-picked-by-what-it-holds
    """
    tp = _resolve_type(tp)
    kind = _type_kind(tp)
    if kind is _TypeKind.UNION and instance is not None:
        return any(_holds_whole(variant, instance, above) for variant in _union_branches(tp))
    if not _holds(tp, instance):
        return False
    if id(instance) in above or len(above) >= MAX_DEPTH:
        return True

    def whole(item_tp: Any, item: Any) -> bool:
        return _holds_whole(item_tp, item, above | {id(instance)})

    match kind:
        case _TypeKind.LIST | _TypeKind.SET | _TypeKind.FROZENSET:
            item_tp = _elem_type(tp)
            return not isinstance(instance, Collection) or all(whole(item_tp, item) for item in instance)
        case _TypeKind.TUPLE:
            fixed = _fixed_seq_types(tp)
            item_tps = repeat(_elem_type(tp)) if fixed is None else fixed
            return all(whole(item_tp, item) for item_tp, item in zip(item_tps, instance, strict=False))
        case _TypeKind.DICT:
            kt, vt = _dict_kv(tp)
            return all(whole(kt, k) and whole(vt, v) for k, v in instance.items())
        case _TypeKind.NAMEDTUPLE | _TypeKind.STRUCT:
            return _generic_origin(tp) is None or unheld_member(tp, instance, holds=whole) is None
        case _:
            return True


def _variant_holds(tp: Any, instance: Any) -> bool:  # noqa: C901, PLR0911  # one return per kind
    """True if *instance* is a value of union variant *tp*.

    Dispatches on :func:`_type_kind`, as :func:`_serialize_by_type` does, so the variant
    chosen here is the one that then serializes the value. A bare ``isinstance``
    cannot ask: a parameterized generic and a ``Literal`` both refuse to be its second
    argument, which left every union holding one undumpable. Each shape answers with the
    concrete class construction builds for it -- ``list`` for ``Sequence[X]``, ``dict`` for
    ``Mapping[K, V]`` -- and a ``Literal`` answers by membership, so ``True`` is not a value
    of ``Literal[1]``.

    Dev Notes:
        docs-dev/architecture/types/serialization.md#serialization
    """
    match _type_kind(tp):
        case _TypeKind.NAMEDTUPLE | _TypeKind.STRUCT:
            cls = _class_of(tp)
            return (
                _isinstance_answers(cls)
                and isinstance(instance, cls)
                and (_generic_origin(tp) is None or _holds_members(tp, instance))
            )
        case _TypeKind.LIST:
            return isinstance(instance, list)
        case _TypeKind.SET:
            return isinstance(instance, set)
        case _TypeKind.FROZENSET:
            return isinstance(instance, frozenset)
        case _TypeKind.TUPLE:
            fixed = _fixed_seq_types(tp)
            return isinstance(instance, tuple) and (fixed is None or len(instance) == len(fixed))
        case _TypeKind.DICT:
            return isinstance(instance, dict)
        case _TypeKind.LEAF if _is_literal(tp):
            # Every member, a bytes one too, so its value is refused by the Literal it belongs to.
            return _literal_holds(_literal_members(tp), instance)
        case _TypeKind.ANY:
            return True
        case _TypeKind.LEAF if _is_type_ref(tp):
            # Read back by the same bound, so a class it refuses is written as foreign (BUG-294).
            return isinstance(instance, type) and _type_ref_admits(tp, instance)
        case _TypeKind.UNION | _TypeKind.TAGGABLE_LEAF | _TypeKind.CALLABLE | _TypeKind.LEAF:
            # What is left is a class, or is parameterized over one (``type[X]``,
            # ``Callable[..., X]``).
            origin = _origin(tp)
            checkable = origin if isinstance(origin, type) else tp
            return isinstance(checkable, type) and isinstance(instance, checkable)


def _isinstance_answers(cls: type) -> bool:
    """Return whether ``isinstance`` answers for *cls*: anything but a Protocol class that is not runtime-checkable.

    ``isinstance`` raises for such a class, so it holds nothing here, construction refusing a
    value under it and the dump writing one as foreign, until its conformance answers (FEAT-57).

    Dev Notes:
        docs-dev/architecture/types/construction.md#a-built-instance-is-taken-as-it-is
    """
    return not is_protocol(cls) or bool(getattr(cls, "_is_runtime_protocol", False))


def _holds_members(tp: Any, instance: Any) -> bool:
    """True if every member of the parameterized struct *tp* that *instance* holds is a value of its bound type.

    The class alone does not tell ``Box[int]`` from ``Box[str]``: what it holds does.

    Dev Notes:
        docs-dev/architecture/types/introspection.md#a-generic-class-reads-its-parameters-bound
    """
    return unheld_member(tp, instance) is None


def unheld_member(
    tp: Any,
    instance: Any,
    *,
    holds: Callable[[Any, Any], bool] = _holds,
) -> tuple[str, Any, Any] | None:
    """Return the first member of the struct *tp* whose value *instance* holds is no value of its type, or None.

    Members are walked in declaration order, each as ``(name, type, value)``, its type
    resolved; one *instance* holds no value for is skipped. *holds* answers for each member.

    Dev Notes:
        docs-dev/architecture/types/introspection.md#a-generic-class-reads-its-parameters-bound
    """
    members = _namedtuple_fields(tp) if _type_kind(tp) is _TypeKind.NAMEDTUPLE else _struct_state_fields(tp)
    missing = object()
    for name, ft in members.items():
        value = getattr(instance, name, missing)
        if value is not missing and not holds(resolved := _resolve_type(ft), value):
            return name, resolved, value
    return None


def _holds_widened(tp: Any, instance: Any) -> bool:
    """True if *tp* holds *instance* as a type checker reads it, beyond what :func:`_variant_holds` says.

    An abstract collection holds an instance of its abstract class, a str or bytes apart for
    a sequence; a ``float`` holds an int (PEP 484's numeric tower).

    Dev Notes:
        docs-dev/architecture/types/serialization.md#a-value-its-type-does-not-hold-dumps-as-an-any-node-holds-it
    """
    match _type_kind(tp):
        case _TypeKind.LIST:
            return _abstractly_holds(tp, instance) and not isinstance(instance, (str, bytes))
        case _TypeKind.SET | _TypeKind.DICT:
            return _abstractly_holds(tp, instance)
        case _TypeKind.LEAF:
            return tp is float and isinstance(instance, int)
        case _:
            return False


def _abstractly_holds(tp: Any, instance: Any) -> bool:
    """True if *instance* is an instance of the class *tp* is spelled with: ``Sequence`` for ``Sequence[int]``."""
    spelled = _origin(tp) or tp
    return isinstance(spelled, type) and isinstance(instance, spelled)


def _holds_anything(variant: Any) -> bool:
    """Return whether union *variant* is ``Any``, the variant every value is held by.

    Dev Notes:
        docs-dev/architecture/types/construction.md#an-any-variant-is-tried-last
    """
    return _type_kind(_resolve_type(variant)) is _TypeKind.ANY


def _literal_holds(members: tuple[Any, ...], instance: Any) -> bool:
    """True if *instance* is one of the Literal *members*: equal and of the same type, so True is not 1."""
    return any(type(m) is type(instance) and m == instance for m in members)
