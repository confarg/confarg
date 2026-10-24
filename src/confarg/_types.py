# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Type introspection utilities."""

from __future__ import annotations

import dataclasses
import enum
import functools
import inspect
import itertools
import types
import typing
import weakref
from collections import Counter, deque
from collections.abc import (
    Callable,
    Collection,
    Iterable,
    Mapping,
    MutableMapping,
    MutableSequence,
    MutableSet,
    Sequence,
    Set,
)
from pathlib import PurePath
from struct import calcsize
from typing import (
    Annotated,
    Any,
    Final,
    Literal,
    NewType,
    ParamSpec,
    TypeVar,
    TypeVarTuple,
    Union,
    Unpack,
    get_args,
    get_origin,
    get_type_hints,
    is_typeddict,
)

from confarg._registry import LEAF_COERCIONS
from confarg.dictexpr._expressions import _list_index

type TagPolicy = Literal["auto", "always"]

_MISSING = object()


class _StrToken(str):
    """Untyped text from CLI args, env vars or CSV cells — eligible for coercion to the target type.

    Dev Notes:
        docs-dev/architecture/types/token-model.md#token-model
    """

    __slots__ = ()


class _UnionSeqToken(_StrToken):
    """A lone CLI token for a union that has both scalar and sequence variants.

    Union construction tries the scalar variants first and, only if they all fail,
    fills the sequence variant as a one-element list (``--input hello`` for
    ``bool | list[str]`` → ``['hello']``). A plain ``_StrToken`` gets no such fallback.

    Dev Notes:
        docs-dev/architecture/cli-parsing/token-consumption.md#unions-with-sequence-variants
    """

    __slots__ = ()


@dataclasses.dataclass(frozen=True)
class _Pinned:
    """Carries an explicitly-typed value through the merge dict, bypassing union stealing."""

    tp: type
    value: Any


def _src_type(value: Any) -> str:
    """Return the user-visible type name of a value, collapsing _StrToken to 'str'.

    Dev Notes:
        docs-dev/architecture/types/token-model.md#token-model
    """
    return "str" if isinstance(value, _StrToken) else type(value).__name__


def _per_class_cache[R](fn: Callable[[Any], R]) -> Callable[[Any], R]:
    """Cache *fn*'s answer per class, for as long as the class lives.

    The class is held weakly, so a class nothing else references is collected, its answer
    with it. A call that raises stores nothing, so the next call asks again.

    Dev Notes:
        docs-dev/architecture/types/introspection.md#introspection-is-cached-per-class
    """
    answers: weakref.WeakKeyDictionary[Any, R] = weakref.WeakKeyDictionary()

    @functools.wraps(fn)
    def cached(cls: Any) -> R:
        try:
            return answers[cls]
        except KeyError:
            answer = answers[cls] = fn(cls)
            return answer

    return cached


def _resolve_type(tp: Any) -> Any:
    """Unwrap the TypeAliasType, Annotated, Final and NewType wrappers, nested in any order.

    ``Final[T]`` is ``T`` to every walk, and a bare ``Final`` is ``Any``: the qualifier says
    the attribute is not reassigned, which no channel, merge or construction step reads. A
    ``NewType`` is its supertype: at runtime its values are the supertype's.

    Args:
        tp: The type to resolve.

    Returns:
        The unwrapped underlying type.

    Dev Notes:
        docs-dev/architecture/types/introspection.md#wrappers-are-transparent
    """
    if isinstance(tp, type):
        return tp  # a class is never one of the wrappers
    while True:
        if type(tp).__name__ == "TypeAliasType":
            tp = tp.__value__
        elif get_origin(tp) is Annotated or get_origin(tp) is Final:
            tp = get_args(tp)[0]
        elif isinstance(tp, NewType):
            tp = tp.__supertype__
        elif tp is Final:
            return Any
        else:
            return tp


def _is_struct_like(tp: Any) -> bool:
    """True if tp is a struct (dataclass or plain class), or a union with at least one struct variant."""
    tp = _resolve_type(tp)
    if _is_struct(tp):
        return True
    if _is_union(tp):
        return any(_is_struct(_resolve_type(v)) for v in _union_args_no_none(tp))
    return False


def _is_dc(tp: Any) -> bool:
    """Check whether a type is a dataclass class (not an instance).

    Args:
        tp: The type to check.

    Returns:
        True if tp is a dataclass type.
    """
    tp = _class_of(_resolve_type(tp))
    return dataclasses.is_dataclass(tp) and isinstance(tp, type)


@_per_class_cache
def _dc_fields(tp: Any) -> Mapping[str, Any]:
    """Return the fields a dataclass instance stores, mapped to their resolved types.

    ``dataclasses.fields()``: an ``init=False`` field included, an ``InitVar`` never. This
    is the state :func:`_struct_state_fields` dumps, not what a channel sets
    (:func:`_struct_fields`). Cached per class, so the mapping is shared and read-only.

    Args:
        tp: A dataclass type.

    Returns:
        A read-only mapping of field names to their resolved type annotations.

    Raises:
        NameError: If an annotation does not resolve; nothing is cached, so a later call retries.

    Dev Notes:
        docs-dev/architecture/design-decisions/the-object-dump-writes-state.md#a-dataclass-dumps-the-fields-it-stores
    """
    cls = _class_of(tp)
    hints = get_type_hints(cls)
    stored = _bind_hints(tp, {f.name: hints[f.name] for f in dataclasses.fields(cls)})
    return types.MappingProxyType({name: _resolve_type(_as_state(h)) for name, h in stored.items()})


def _dataclass_factory_default() -> Any:
    """Return the default a generated dataclass ``__init__`` shows for a ``default_factory`` field.

    Read off a generated signature rather than imported: the sentinel is private to
    ``dataclasses``, which documents no name for it.
    """
    probe = dataclasses.make_dataclass("_FactoryProbe", [("x", list, dataclasses.field(default_factory=list))])
    return inspect.signature(probe).parameters["x"].default


_DATACLASS_FACTORY_DEFAULT = _dataclass_factory_default()


def _dc_member_hints(tp: Any, names: Iterable[str], *, include_extras: bool = False) -> dict[str, Any]:
    """Return the class's own annotation of each of *names* that is a field of dataclass *tp*.

    An ``InitVar`` reads as the type it wraps. *include_extras* keeps ``Annotated`` metadata.

    Raises:
        NameError: If an annotation of the class does not resolve, as for :func:`_dc_fields`.
    """
    cls = _class_of(tp)
    declared = cls.__dataclass_fields__
    own = get_type_hints(cls, include_extras=include_extras)
    hints = {name: own[name] for name in names if name in declared and name in own}
    bound = _bind_hints(tp, {name: h.type if isinstance(h, dataclasses.InitVar) else h for name, h in hints.items()})
    return {name: _as_member(h) for name, h in bound.items()}


def _is_none_type(tp: Any) -> bool:
    """Check whether a type is NoneType.

    Args:
        tp: The type to check.

    Returns:
        True if tp is NoneType.
    """
    return _resolve_type(tp) is types.NoneType


def _is_union(tp: Any) -> bool:
    """Check whether a type is a Union (including X | Y syntax).

    Args:
        tp: The type to check.

    Returns:
        True if tp is a Union type.
    """
    o = get_origin(_resolve_type(tp))
    return o is Union or o is types.UnionType


def _union_args(tp: Any) -> list[Any]:
    """Return all type arguments of a Union type.

    Args:
        tp: A Union type.

    Returns:
        A list of the Union's type arguments.
    """
    return list(get_args(_resolve_type(tp)))


def _union_args_no_none(tp: Any) -> list[Any]:
    """Return Union type arguments excluding NoneType.

    Args:
        tp: A Union type.

    Returns:
        A list of the Union's type arguments with NoneType filtered out.
    """
    return [a for a in get_args(_resolve_type(tp)) if a is not types.NoneType]


def _allows_none(tp: Any) -> bool:
    """Check whether a type accepts None values.

    Args:
        tp: The type to check.

    Returns:
        True if tp is NoneType or an Optional/Union that includes NoneType.
    """
    tp = _resolve_type(tp)
    if _is_none_type(tp):
        return True
    if _is_union(tp):
        return types.NoneType in _union_args(tp)
    return False


def _unwrap_optional(tp: Any) -> Any | None:
    """Unwrap Optional[T] / Union[T, None] to T.

    Returns:
        - T (resolved) if tp is Optional[T] — exactly one non-None union variant.
        - tp (resolved) if tp is not a union at all.
        - None if tp is a multi-variant union (two or more non-None variants).
          This sentinel is Python None, never NoneType; it signals the caller
          must handle the multi-variant case separately.
    """
    tp = _resolve_type(tp)
    if not _is_union(tp):
        return tp
    non_none = _union_args_no_none(tp)
    if len(non_none) == 1:
        return _resolve_type(non_none[0])
    return None  # multi-variant — caller handles


def _is_bool(tp: Any) -> bool:
    """Check whether a type is bool.

    Args:
        tp: The type to check.

    Returns:
        True if tp is bool.
    """
    return _resolve_type(tp) is bool


def _origin(tp: Any) -> Any:
    """Return the generic origin of a type.

    Args:
        tp: The type to inspect.

    Returns:
        The origin type (e.g. list for list[int]), or None.
    """
    return get_origin(_resolve_type(tp))


#: The builtins a subclass of one reads as, in the order a class is tested against them.
_BUILTIN_BASES: tuple[type, ...] = (dict, list, set, frozenset, tuple, str, int, float)


def _subclassed_builtin(cls: Any) -> type | None:
    """Return the builtin the class *cls* subclasses and reads as, None for any other class or type.

    A subclass of dict, list, set, frozenset, tuple, str, int or float, but not the builtin
    itself, and not a class that reads otherwise: a dataclass by its fields, a namedtuple by
    its, an ``Enum`` (``StrEnum``, ``IntEnum``) by its members, and a ``TypedDict``, a dict
    whose keys are typed one by one. Reads no registry, so a cached struct test may ask it.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-builtins-subclass-is-that-builtin.md#a-builtins-subclass-is-that-builtin
    """
    if not isinstance(cls, type) or cls in _BUILTIN_BASES or cls is bool:
        return None
    if dataclasses.is_dataclass(cls) or _is_namedtuple(cls) or is_typeddict(cls) or issubclass(cls, enum.Enum):
        return None
    return next((base for base in _BUILTIN_BASES if issubclass(cls, base)), None)


def _builtin_read_as(tp: Any) -> type | None:
    """Return the builtin the subclass *tp*, bare or parameterized, reads as; None if it reads otherwise.

    The one answer to "is this a builtin's subclass, read as the builtin?". A registered
    subclass is a leaf, read through its registration in both directions, so it is none.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-builtins-subclass-is-that-builtin.md#a-builtins-subclass-is-that-builtin
    """
    tp = _resolve_type(tp)
    cls = tp if isinstance(tp, type) else get_origin(tp)
    if cls in LEAF_COERCIONS:
        return None
    return _subclassed_builtin(cls)


def _builtin_args(tp: Any) -> tuple[Any, ...]:
    """Return the type arguments of the builtin *tp* reads as, () where it gives none.

    A builtin or an abstract collection gives its own; a subclass gives its arguments
    (``OrderedDict[str, int]``), else the ones its parameterized base declares
    (``class Scores(dict[str, int])``), its own arguments substituted for the base's
    TypeVars and an unbound TypeVar read as its default, else ``Any``. A ``Counter`` counts in ints, as
    typeshed declares it: ``Counter[K]`` is ``dict[K, int]``.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-builtins-subclass-is-that-builtin.md#a-subclass-is-typed-as-a-type-checker-types-it
    """
    tp = _resolve_type(tp)
    cls = tp if isinstance(tp, type) else get_origin(tp)
    args = () if isinstance(tp, type) else get_args(tp)
    builtin = _subclassed_builtin(cls)
    return args if builtin is None or cls is None else _subclass_args(cls, args, builtin)


def _subclass_args(cls: type, args: tuple[Any, ...], builtin: type) -> tuple[Any, ...]:
    """Return the arguments of *builtin* that the subclass *cls*, given *args*, reads with."""
    if cls is Counter:
        return ((_resolve_type(args[0]) if args else Any), int)
    bases = cls.__dict__.get("__orig_bases__")
    if bases is None:
        # No parameterized base: the class's own arguments are the builtin's (an OrderedDict
        # is subscripted as a dict is), or the class it subclasses answers.
        parent = next(b for b in cls.__bases__ if issubclass(b, builtin))
        return args if args or parent is builtin else _subclass_args(parent, args, builtin)
    bound = dict(zip(getattr(cls, "__parameters__", ()), args, strict=False))
    base = next((b for b in bases if isinstance(o := get_origin(b) or b, type) and issubclass(o, builtin)), None)
    if base is None:  # the builtin is reached through an unparameterized base
        parent = next(b for b in cls.__bases__ if issubclass(b, builtin))
        return args if parent is builtin else _subclass_args(parent, args, builtin)
    if params := getattr(base, "__parameters__", ()):
        base = base[tuple(bound.get(p, _param_default(p)) if isinstance(p, TypeVar) else p for p in params)]
    origin = get_origin(base) or base
    return get_args(base) if origin is builtin else _subclass_args(origin, get_args(base), builtin)


# --- Generic classes: a parameterized class's members, its type parameters bound -------------


def _type_params(cls: Any) -> tuple[Any, ...]:
    """Return the type parameters the class *cls* declares, () for one that declares none."""
    params = getattr(cls, "__parameters__", ()) if isinstance(cls, type) else ()
    return params if isinstance(params, tuple) else ()


def _generic_origin(tp: Any) -> type | None:
    """Return the class the parameterized generic *tp* subscripts, ``Box`` for ``Box[int]``; None for any other type.

    Only a class declaring type parameters of its own: ``list[int]``, ``Sequence[int]`` and
    ``type[int]`` subscript none.

    Dev Notes:
        docs-dev/architecture/types/introspection.md#a-generic-class-reads-its-parameters-bound
    """
    origin = get_origin(tp)
    return origin if _type_params(origin) else None


def _class_of(tp: Any) -> Any:
    """Return the class *tp* builds: the class a parameterized generic subscripts, else *tp* itself."""
    return _generic_origin(tp) or tp


def _param_default(param: Any) -> Any:
    """Return what the type parameter *param* reads as when nothing binds it, as a type checker reads a bare generic.

    Its PEP 696 default where it declares one, else ``Any``: the arguments ``tuple[Any, ...]``
    unpacks to for a TypeVarTuple, ``...`` for a ParamSpec. A TypeVarTuple's is a tuple of
    arguments, spliced where it is substituted.

    Dev Notes:
        docs-dev/architecture/types/introspection.md#a-generic-class-reads-its-parameters-bound
    """
    if getattr(param, "has_default", lambda: False)():
        default = param.__default__
        return (default,) if isinstance(param, TypeVarTuple) else default
    if isinstance(param, TypeVarTuple):
        return (Unpack[tuple[Any, ...]],)
    return ... if isinstance(param, ParamSpec) else Any


def _param_binding(params: tuple[Any, ...], args: tuple[Any, ...]) -> dict[Any, Any]:
    """Bind each of *params* to its argument in *args*, positionally, or to its default when *args* gives none.

    A TypeVarTuple takes, as a tuple, the arguments the parameters around it leave.

    Dev Notes:
        docs-dev/architecture/types/introspection.md#a-generic-class-reads-its-parameters-bound
    """
    if not args:
        return {p: _param_default(p) for p in params}
    star = next((i for i, p in enumerate(params) if isinstance(p, TypeVarTuple)), None)
    if star is None:
        return {p: args[i] if i < len(args) else _param_default(p) for i, p in enumerate(params)}
    after = len(params) - star - 1
    binding = dict(zip(params[:star], args, strict=False))
    binding[params[star]] = tuple(args[star : len(args) - after])
    binding.update(zip(params[star + 1 :], args[len(args) - after :], strict=False))
    return binding


def _substitute(tp: Any, binding: Mapping[Any, Any]) -> Any:
    """Return the annotation *tp* with each type parameter *binding* names replaced by what it binds.

    Python's own substitution does it (``list[T][int]``), so a TypeVarTuple splices its
    arguments and a ParamSpec takes its list; ``tuple[*Ts]`` with *Ts* unbound reads as
    ``tuple[Any, ...]``. A class is never subscripted: a bare generic is read as its defaults
    where it is used.

    Dev Notes:
        docs-dev/architecture/types/introspection.md#a-generic-class-reads-its-parameters-bound
    """
    if not binding:
        return tp
    if isinstance(tp, (TypeVar, ParamSpec)):
        return binding.get(tp, tp)
    params = getattr(tp, "__parameters__", ())
    if isinstance(tp, type) or not isinstance(params, tuple) or not any(p in binding for p in params):
        return tp
    args: list[Any] = []
    for p in params:
        value = binding.get(p, p)
        if isinstance(p, TypeVarTuple):
            args.extend(value if isinstance(value, tuple) else (Unpack[p],))
        else:
            args.append(list(value) if isinstance(p, ParamSpec) and isinstance(value, tuple) else value)
    return _unpacked_whole(tp[tuple(args)])


def _unpacked_whole(tp: Any) -> Any:
    """Return ``tuple[X, ...]`` for ``tuple[*tuple[X, ...]]``, which a TypeVarTuple default leaves; else *tp*.

    The unpacked tuple is spelled ``Unpack[tuple[X, ...]]`` or ``*tuple[X, ...]``.
    """
    args = get_args(tp)
    if get_origin(tp) is not tuple or len(args) != 1:
        return tp
    if get_origin(args[0]) is Unpack:
        return get_args(args[0])[0]
    return types.GenericAlias(tuple, get_args(args[0])) if getattr(args[0], "__unpacked__", False) else tp


@_per_class_cache
def _ancestor_args(tp: Any) -> Mapping[type, tuple[Any, ...]]:
    """Return the type arguments each class in the MRO of *tp*, a class or a parameterized generic, reads with.

    *tp*'s own class takes *tp*'s arguments; a base a class subscripts in its bases
    (``class IntBox(Box[int])``) takes those, the class's own parameters substituted; any
    other class none, so it reads its defaults (:func:`_param_binding`). The first subscript
    the MRO meets wins, as for a type checker.

    Dev Notes:
        docs-dev/architecture/types/introspection.md#a-generic-class-reads-its-parameters-bound
    """
    cls = _class_of(tp)
    out: dict[type, tuple[Any, ...]] = {cls: () if isinstance(tp, type) else get_args(tp)}
    for c in cls.__mro__:
        binding = _param_binding(_type_params(c), out.setdefault(c, ()))
        for base in c.__dict__.get("__orig_bases__", ()):
            origin = get_origin(base)
            if isinstance(origin, type) and origin not in out:
                out[origin] = tuple(_substitute(a, binding) for a in get_args(base))
    return types.MappingProxyType(out)


def _class_binding(tp: Any, cls: type) -> dict[Any, Any]:
    """Return how *tp*, a class or a parameterized generic, binds the type parameters of *cls*, a class in its MRO."""
    return _param_binding(_type_params(cls), _ancestor_args(tp).get(cls, ()))


def _is_generic_somewhere(tp: Any) -> bool:
    """True if a class in the MRO of *tp*'s class declares type parameters, so a member may name one."""
    cls = _class_of(tp)
    return isinstance(cls, type) and any(_type_params(c) for c in cls.__mro__)


def _bind_hints(tp: Any, hints: Mapping[str, Any], *, owner: type | None = None) -> dict[str, Any]:
    """Return *hints*, annotations of *tp*'s class, each declaring class's type parameters bound as *tp* binds them.

    The declaring class is *owner* for every hint when given (the class defining a
    constructor), else the first class in the MRO annotating the name, as for a dataclass
    field.

    Dev Notes:
        docs-dev/architecture/types/introspection.md#a-generic-class-reads-its-parameters-bound
    """
    if not _is_generic_somewhere(tp):
        return dict(hints)
    cls = _class_of(tp)
    return {
        name: _substitute(h, _class_binding(tp, owner or _annotating_class(cls, name))) for name, h in hints.items()
    }


def _annotating_class(cls: type, name: str) -> type:
    """Return the first class in *cls*'s MRO that annotates *name*, *cls* when none does."""
    return next((c for c in cls.__mro__ if name in inspect.get_annotations(c)), cls)


def _constructor_owner(cls: type, constructor: Any) -> type | None:
    """Return the class in *cls*'s MRO whose namespace defines *constructor*, None when none does."""
    return next(
        (c for c in cls.__mro__ if any(c.__dict__.get(n) is constructor for n in ("__init__", "__new__"))),
        None,
    )


def _tagged_struct(cls: Any, declared: Any) -> Any:
    """Return the struct a class tag naming *cls* builds where *declared* is expected, None when it builds none there.

    *cls* must be a subclass of the class *declared* builds, and one *declared*'s arguments
    can bind. Its type parameters are bound through its bases to those arguments, as a type
    checker infers ``Labeled(...)`` where a ``Box[int]`` is expected: ``Labeled[int]``; one its
    bases do not reach reads its default. A class whose bases fix another argument
    (``class IntBox(Box[int])`` where a ``Box[str]`` is expected) builds none.

    Dev Notes:
        docs-dev/architecture/types/introspection.md#a-tag-binds-the-class-it-names-through-its-bases
    """
    target = _class_of(_resolve_type(declared))
    if not (isinstance(cls, type) and isinstance(target, type) and issubclass(cls, target)):
        return None
    if target is declared:
        return cls
    params = _type_params(cls)
    own = cls[tuple(Unpack[p] if isinstance(p, TypeVarTuple) else p for p in params)] if params else cls
    solved: dict[Any, Any] = {}
    pairs = zip(_ancestor_args(own).get(target, ()), _ancestor_args(declared)[target], strict=False)
    if not all(_unify(pattern, actual, solved) for pattern, actual in pairs):
        return None
    if not params:
        return cls
    bound = _param_binding(params, ())
    bound.update((p, solved[p]) for p in params if p in solved)
    args: list[Any] = []
    for p in params:
        args.extend(bound[p]) if isinstance(p, TypeVarTuple) else args.append(bound[p])
    return cls[tuple(args)]


def _unify(pattern: Any, actual: Any, solved: dict[Any, Any]) -> bool:
    """Record in *solved* what each TypeVar in *pattern* stands for, *actual* being *pattern* with them bound.

    Return whether *actual* can be *pattern* bound: ``list[T]`` can be ``list[int]``, never
    ``int``. ``Any`` on either side, and a parameter no TypeVar matches, can be anything.
    """
    if pattern is Any or actual is Any or isinstance(pattern, (TypeVarTuple, ParamSpec)):
        return True
    if isinstance(pattern, TypeVar):
        return solved.setdefault(pattern, actual) == actual
    origin, args = get_origin(pattern), get_args(pattern)
    if origin is None or not args:
        return pattern == actual
    actual_args = get_args(actual)
    return (
        origin is get_origin(actual)
        and len(args) == len(actual_args)
        and all(_unify(p, a, solved) for p, a in zip(args, actual_args, strict=True))
    )


# --- Descriptor-typed fields: what __set__ takes, what __get__ gives ---------------------------


def _descriptor_class(tp: Any) -> type | None:
    """Return the data descriptor class the annotation *tp* names, bare or parameterized; None for any other.

    A class whose instances define ``__set__``: a dataclass field annotated by one is set
    through it, as a type checker reads it.

    Dev Notes:
        docs-dev/architecture/types/introspection.md#a-descriptor-typed-field-takes-what-its-__set__-takes
    """
    cls = _class_of(_resolve_type(tp))
    return cls if isinstance(cls, type) and _defining_class(cls, "__set__") is not None else None


def _defining_class(cls: type, method: str) -> type | None:
    """Return the class of *cls*'s MRO defining *method*, where the descriptor protocol looks it up; None for none."""
    return next((c for c in cls.__mro__ if method in c.__dict__), None)


# The descriptor protocol calls __set__(self, instance, value) and __get__(self, instance, owner).
_INSTANCE, _VALUE = 1, 2


def _descriptor_input(tp: Any) -> Any:
    """Return the type the descriptor annotation *tp*'s ``__set__`` takes as its value, its parameters bound.

    The union of an overloaded ``__set__``'s values, an unannotated one joining as ``Any``,
    as a type checker joins them; ``Any`` where no value is annotated, or the hints cannot be read.

    Dev Notes:
        docs-dev/architecture/types/introspection.md#a-descriptor-typed-field-takes-what-its-__set__-takes
    """

    def the_value(hints: Mapping[str, Any], params: list[str]) -> Any:
        return hints.get(params[_VALUE], Any) if len(params) > _VALUE else Any

    return _descriptor_hint(tp, "__set__", the_value)


def _descriptor_held(tp: Any) -> Any:
    """Return the type the descriptor annotation *tp*'s ``__get__`` gives on an instance, its parameters bound.

    The union of the overloads of ``__get__`` an instance reaches, one whose instance
    parameter is ``None`` being class access; ``Any`` where it is not annotated, the hints
    cannot be read, or the class defines no ``__get__``.

    Dev Notes:
        docs-dev/architecture/types/introspection.md#a-descriptor-typed-field-takes-what-its-__set__-takes
    """

    def on_an_instance(hints: Mapping[str, Any], params: list[str]) -> Any:
        if len(params) > _INSTANCE and hints.get(params[_INSTANCE], Any) in (None, types.NoneType):
            return None  # the overload for class access
        return hints.get("return", Any)

    return _descriptor_hint(tp, "__get__", on_an_instance)


def _descriptor_hint(tp: Any, method: str, pick: Callable[[Mapping[str, Any], list[str]], Any]) -> Any:
    """Return what *pick* reads off the descriptor *tp*'s *method*'s hints, each overload's joined, bound by *tp*.

    ``Any`` where they cannot be read: a method in C, as ``property``'s, has neither hints
    nor the module :func:`typing.get_overloads` keys on.
    """
    resolved = _resolve_type(tp)
    owner = _defining_class(_class_of(resolved), method)
    if owner is None or not callable(fn := owner.__dict__[method]):
        return Any
    picked: list[Any] = []
    try:
        for variant in typing.get_overloads(fn) or [fn]:
            hints = _type_hints(variant, owner=owner)
            if (hint := pick(hints, list(inspect.signature(variant).parameters))) is not None:
                picked.append(hint)
    except (_UnresolvedHintsError, AttributeError, ValueError, TypeError):
        return Any
    if not picked:
        return Any
    # Union[(x,)] would respell an `X | Y` hint as Union[X, Y], which messages print.
    joined = picked[0] if len(picked) == 1 else Union[tuple(picked)]  # noqa: UP007  # a runtime union of hints
    return _bind_hints(resolved, {method: joined}, owner=owner)[method]


def _as_member(hint: Any) -> Any:
    """Return the dataclass field annotation *hint* as a member a channel sets: a descriptor's as ``__set__`` takes.

    ``Annotated`` metadata stays on the type it is read as.

    Dev Notes:
        docs-dev/architecture/types/introspection.md#a-descriptor-typed-field-takes-what-its-__set__-takes
    """
    return _through_descriptor(hint, _descriptor_input)


def _as_state(hint: Any) -> Any:
    """Return the dataclass field annotation *hint* as the state ``dump()`` reads: a descriptor's as ``__get__`` gives.

    Dev Notes:
        docs-dev/architecture/types/introspection.md#a-descriptor-typed-field-takes-what-its-__set__-takes
    """
    return _through_descriptor(hint, _descriptor_held)


def _through_descriptor(hint: Any, read: Callable[[Any], Any]) -> Any:
    """Return *hint* with the descriptor it names replaced by *read* of it.

    The wrappers :func:`_resolve_type` sees through are walked alike: ``Final`` and
    ``Annotated`` are kept, their metadata on the type read; an alias gives its value.
    """
    if _descriptor_class(hint) is None:
        return hint
    if type(hint).__name__ == "TypeAliasType":
        return _through_descriptor(hint.__value__, read)
    if get_origin(hint) is Annotated:
        inner, *metadata = get_args(hint)
        return Annotated[(_through_descriptor(inner, read), *metadata)]
    if get_origin(hint) is Final:
        return Final[_through_descriptor(get_args(hint)[0], read)]
    return read(hint)


def _self_defaulting_descriptor(tp: Any, name: str) -> str:
    """Return the name of the data descriptor the dataclass *tp*'s field *name* defaults to, ``""`` for none.

    Dev Notes:
        docs-dev/architecture/types/introspection.md#a-descriptor-returning-itself-on-class-access-is-no-default
    """
    cls = _class_of(_resolve_type(tp))
    field = getattr(cls, "__dataclass_fields__", {}).get(name)
    if field is None or not _defaults_to_its_descriptor(cls, name, field.default):
        return ""
    return type(field.default).__name__


def _defaults_to_its_descriptor(cls: type, name: str, default: Any) -> bool:
    """True if the dataclass *cls*'s field *name* defaults to the data descriptor installed for it.

    A descriptor whose ``__get__`` returns itself on class access hands it to ``dataclasses``
    as the field's default, which is no value of the field: the field reads as required.

    Dev Notes:
        docs-dev/architecture/types/introspection.md#a-descriptor-returning-itself-on-class-access-is-no-default
    """
    return (
        dataclasses.is_dataclass(cls)
        and default is inspect.getattr_static(cls, name, None)
        and hasattr(type(default), "__set__")
    )


def _scalar_read_as(tp: Any) -> type | None:
    """Return str, int or float for a subclass of one, which *tp* reads as; None for anything else.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-builtins-subclass-is-that-builtin.md#a-builtins-subclass-is-that-builtin
    """
    builtin = _builtin_read_as(tp)
    return builtin if builtin in (str, int, float) else None


_LIST_ORIGINS = frozenset({list, Sequence, MutableSequence, Iterable, Collection})
_SET_ORIGINS = frozenset({set, Set, MutableSet})
_DICT_ORIGINS = frozenset({dict, Mapping, MutableMapping})


def _is_list(tp: Any) -> bool:
    """Check whether a type is a list: list[...], a bare list, or Sequence, MutableSequence, Iterable or Collection.

    Args:
        tp: The type to check.

    Returns:
        True if tp is a list or sequence type.
    """
    tp = _resolve_type(tp)
    return tp in _LIST_ORIGINS or _origin(tp) in _LIST_ORIGINS or _builtin_read_as(tp) is list


def _is_set(tp: Any) -> bool:
    """Check whether a type is set[...], a bare set, or an abstract set type (AbstractSet, MutableSet).

    Args:
        tp: The type to check.

    Returns:
        True if tp is a set type.
    """
    tp = _resolve_type(tp)
    return tp in _SET_ORIGINS or _origin(tp) in _SET_ORIGINS or _builtin_read_as(tp) is set


def _is_frozenset(tp: Any) -> bool:
    """Check whether a type is frozenset[...] or a bare frozenset.

    Args:
        tp: The type to check.

    Returns:
        True if tp is a frozenset type.
    """
    tp = _resolve_type(tp)
    return tp is frozenset or _origin(tp) is frozenset or _builtin_read_as(tp) is frozenset


def _is_tuple(tp: Any) -> bool:
    """Check whether a type is tuple[...] or a bare tuple.

    Args:
        tp: The type to check.

    Returns:
        True if tp is a tuple type.
    """
    tp = _resolve_type(tp)
    return tp is tuple or _origin(tp) is tuple or _builtin_read_as(tp) is tuple


def _is_namedtuple(tp: Any) -> bool:
    """True if tp is a namedtuple class (collections.namedtuple or typing.NamedTuple), or a parameterized one."""
    tp = _class_of(tp)
    return isinstance(tp, type) and issubclass(tp, tuple) and hasattr(tp, "_fields") and hasattr(tp, "_make")


class _UnresolvedHintsError(Exception):
    """``get_type_hints`` failed: raised through a cached function so the fallback is not cached."""


def _type_hints(obj: Any, *, include_extras: bool = False, owner: Any = None) -> dict[str, Any]:
    """Return ``get_type_hints(obj)``, raising _UnresolvedHintsError when an annotation does not resolve.

    *owner* is the class defining the function *obj*: its PEP 695 type parameters resolve a
    postponed annotation naming them, which ``get_type_hints`` finds in no namespace it reads.
    """
    localns = {p.__name__: p for p in getattr(owner, "__type_params__", ())}
    try:
        return get_type_hints(obj, localns=localns or None, include_extras=include_extras)
    except (NameError, AttributeError, TypeError) as e:
        raise _UnresolvedHintsError from e


def _namedtuple_fields(tp: Any) -> Mapping[str, Any]:
    """Return {field_name: resolved_type} for a namedtuple class.

    A field whose annotation does not resolve reads as Any. Cached per class once every
    annotation resolves, so the mapping is shared and read-only.

    Dev Notes:
        docs-dev/architecture/types/introspection.md#introspection-is-cached-per-class
    """
    try:
        return _annotated_namedtuple_fields(tp)
    except _UnresolvedHintsError:
        return _typed_namedtuple_fields(tp, {})


@_per_class_cache
def _annotated_namedtuple_fields(tp: Any) -> Mapping[str, Any]:
    """Return :func:`_namedtuple_fields` when every annotation resolves, cached per class."""
    return _typed_namedtuple_fields(tp, _bind_hints(tp, _type_hints(_class_of(tp))))


def _typed_namedtuple_fields(tp: Any, hints: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return {field_name: resolved_type} for a namedtuple class, reading types from *hints*."""
    return types.MappingProxyType({f: _resolve_type(hints.get(f, Any)) for f in tp._fields})


def _namedtuple_defaults(tp: Any) -> dict[str, Any]:
    """Return {field_name: default_value} for fields that have defaults."""
    return dict(tp._field_defaults)


def _is_dict(tp: Any) -> bool:
    """Check whether a type is dict[...], a bare dict, or an abstract mapping type (Mapping, MutableMapping).

    Args:
        tp: The type to check.

    Returns:
        True if tp is a dict or mapping type.
    """
    tp = _resolve_type(tp)
    return tp in _DICT_ORIGINS or _origin(tp) in _DICT_ORIGINS or _builtin_read_as(tp) is dict


def _is_varlen_collection(tp: Any) -> bool:
    """Check whether a type is a variable-length collection.

    Matches list, set, frozenset, or tuple[X, ...].

    Args:
        tp: The type to check.

    Returns:
        True if tp is a variable-length collection type.
    """
    tp = _resolve_type(tp)
    if _is_list(tp) or _is_set(tp) or _is_frozenset(tp):
        return True
    if _is_tuple(tp):
        a = get_args(tp)
        _variable_length_tuple_args = 2
        return not a or (len(a) == _variable_length_tuple_args and a[1] is Ellipsis)
    return False


def _is_seq_variant(tp: Any) -> bool:
    """True if tp is a sequence-shaped type: any tuple, a namedtuple, or a list/set/frozenset.

    A namedtuple counts: it is a fixed-length sequence with names attached, so it takes
    the CLI and file spellings a same-arity ``tuple`` takes.

    Dev Notes:
        docs-dev/architecture/cli-parsing/token-consumption.md#token-consumption
    """
    tp = _resolve_type(tp)
    return _is_tuple(tp) or _is_namedtuple(tp) or _is_varlen_collection(tp)


def _fixed_seq_types(tp: Any) -> list[Any] | None:
    """Return the element types a fixed-length sequence consumes, or None if it has none.

    The one answer to "how many positional tokens does this field take, and of which
    types?", for both spellings of a fixed-length sequence: ``tuple[X, Y]`` and a
    namedtuple class.  ``None`` means the question does not apply -- a variable-length
    collection, or no sequence at all.

    Dev Notes:
        docs-dev/architecture/cli-parsing/token-consumption.md#token-consumption
    """
    tp = _resolve_type(tp)
    if _is_namedtuple(tp):
        return list(_namedtuple_fields(tp).values())
    if _is_tuple(tp):
        return _tuple_types(tp)
    return None


def _spelled_position(key: Any) -> int | None:
    """Return the index *key* spells as a key of a fixed-length sequence, None when it spells none.

    An integer, which a YAML file parses a bare ``-1:`` key as (never a ``bool``), or a string
    spelling one as ``str()`` writes it (:func:`~confarg.dictexpr._expressions._list_index`):
    ``0`` and ``-1``, never ``01``, ``+1``, ``-0`` or a non-ASCII digit. The range is not checked.
    """
    if isinstance(key, bool):
        return None
    if isinstance(key, int):
        return key
    return _list_index(key) if isinstance(key, str) else None


def _fixed_position(tp: Any, key: Any) -> int | None:
    """Return the position *key* names in the fixed-length sequence *tp*, None when it names none.

    The one reader of a fixed tuple's and a namedtuple's position, for the type walk, the merge
    and construction alike: a namedtuple field's name, or an index :func:`_spelled_position`
    reads within the arity, a negative one counting from the end. None too for a *tp* that is
    no fixed-length sequence (:func:`_fixed_seq_types`).

    Dev Notes:
        docs-dev/architecture/design-decisions/namedtuple-is-a-fixed-length-sequence.md#a-namedtuple-is-a-fixed-length-sequence
    """
    tp = _resolve_type(tp)
    if _is_namedtuple(tp) and isinstance(key, str) and key in (names := _namedtuple_fields(tp)):
        return list(names).index(key)
    positions = _fixed_seq_types(tp)
    index = _spelled_position(key)
    if positions is None or index is None or not -len(positions) <= index < len(positions):
        return None
    return index % len(positions)


def _union_has_seq_variant(tp: Any) -> bool:
    """True if tp is a union with at least one sequence-shaped variant.

    Such a field (e.g. ``str | tuple[str, str]`` or ``str | list[str]``) accepts
    multiple CLI tokens; the front-ends consume greedily and defer
    tuple/list/set vs scalar disambiguation to ``construct``.
    """
    tp = _resolve_type(tp)
    return _is_union(tp) and any(_is_seq_variant(v) for v in _union_args_no_none(tp))


def _union_has_varlen_variant(tp: Any) -> bool:
    """True if tp is a union with at least one varlen-collection variant.

    Such a union (e.g. ``int | list[int]``) legitimately accepts an empty CLI
    flag: the front-end builds the empty list and defers to ``construct``. A
    union whose only sequence variant is a fixed-length tuple is excluded, since
    an empty list can build nothing valid for it.
    """
    tp = _resolve_type(tp)
    return _is_union(tp) and any(_is_varlen_collection(_resolve_type(v)) for v in _union_args_no_none(tp))


def _union_has_scalar_variant(tp: Any) -> bool:
    """True if tp is a union with at least one non-sequence (scalar) variant.

    Used as the single-token unwrap trigger: when a union mixes a scalar with a
    sequence variant, a lone CLI token is stored as that bare scalar (so
    ``--input foo`` stays ``'foo'``), while two-or-more tokens form the sequence.
    For an all-sequence union this is False, so a lone token stays a 1-element
    list and still builds e.g. ``tuple[str]``.
    """
    tp = _resolve_type(tp)
    return _is_union(tp) and any(not _is_seq_variant(v) for v in _union_args_no_none(tp))


def _elem_type(tp: Any) -> Any:
    """Return the element type of a generic collection.

    Args:
        tp: A generic collection type (e.g. list[int]).

    Returns:
        The element type, or Any if not parameterized.
    """
    a = _builtin_args(tp)
    return _resolve_type(a[0]) if a else Any


def _tuple_types(tp: Any) -> list[Any] | None:
    """Return fixed-length element types for a tuple, or None for tuple[X, ...] or a bare tuple.

    Args:
        tp: A tuple type.

    Returns:
        A list of element types for fixed-length tuples, or None for variable-length.
    """
    a = _builtin_args(tp)
    _variable_length_tuple_args = 2
    if not a or (len(a) == _variable_length_tuple_args and a[1] is Ellipsis):
        return None
    return [_resolve_type(x) for x in a]


def _dict_kv(tp: Any) -> tuple[Any, Any]:
    """Return the key and value types of a dict type.

    Args:
        tp: A dict type.

    Returns:
        A (key_type, value_type) tuple, defaulting to (Any, Any) for the unparameterized form.
    """
    a = _builtin_args(tp)
    return (_resolve_type(a[0]), _resolve_type(a[1])) if a else (Any, Any)


def _is_literal(tp: Any) -> bool:
    """Check whether a type is a Literal type.

    Args:
        tp: The type to check.

    Returns:
        True if tp is a Literal type.
    """
    return get_origin(_resolve_type(tp)) is Literal


def _literal_members(tp: Any) -> tuple[Any, ...]:
    """Return every member of the Literal type *tp*, as written: the ones confarg reads and the others."""
    return get_args(_resolve_type(tp))


def _is_readable_literal_member(member: Any) -> bool:
    """True if *member* is a Literal member confarg reads: an int, str, bool, Enum member or None.

    PEP 586 also allows a bytes member, which confarg reads nowhere, as it reads no ``bytes`` field.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-literal-member-is-what-pep-586-allows.md#a-literal-member-is-what-pep-586-allows
    """
    return member is None or isinstance(member, int | str | enum.Enum)


def _literal_values(tp: Any) -> tuple[Any, ...]:
    """Return the members of a Literal type that confarg reads, a bytes member left out.

    Args:
        tp: A Literal type.

    Returns:
        A tuple of the Literal's members that a value can read as.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-literal-member-is-what-pep-586-allows.md#a-literal-member-is-what-pep-586-allows
    """
    return tuple(m for m in _literal_members(tp) if _is_readable_literal_member(m))


def _forbidden_literal_member(tp: Any) -> tuple[Any, Any] | None:
    """Return ``(literal, member)`` for the first Literal member PEP 586 forbids reachable from *tp*, None if none.

    The one answer to "is this annotation an invalid ``Literal``?". The walk descends into a
    union's branches and a collection's item types, where a refused branch would otherwise
    let another take the value, and stops at a struct, whose fields are reached as fields.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-literal-member-is-what-pep-586-allows.md#a-forbidden-member-makes-the-annotation-invalid
    """
    tp = _resolve_type(tp)
    if _is_literal(tp):
        member = next((m for m in _literal_members(tp) if not _is_pep_586_member(m)), _NO_MEMBER)
        return None if member is _NO_MEMBER else (tp, member)
    if not (_is_union(tp) or _is_dict(tp) or _is_list(tp) or _is_set(tp) or _is_frozenset(tp) or _is_tuple(tp)):
        return None
    return next((found for arg in get_args(tp) if (found := _forbidden_literal_member(arg)) is not None), None)


_NO_MEMBER = object()


def _is_pep_586_member(member: Any) -> bool:
    """True if PEP 586 allows *member* in a Literal: one confarg reads, or a bytes value."""
    return _is_readable_literal_member(member) or isinstance(member, bytes)


def _is_singleton_literal(tp: Any) -> bool:
    """Check whether a type is a Literal with exactly one allowed value.

    Args:
        tp: The type to check.

    Returns:
        True if tp is Literal[X] for a single value X.
    """
    return _is_literal(tp) and len(_literal_values(tp)) == 1


def _is_enum(tp: Any) -> bool:
    """Check whether a type is an Enum subclass.

    Args:
        tp: The type to check.

    Returns:
        True if tp is an Enum type.
    """
    tp = _resolve_type(tp)
    return isinstance(tp, type) and issubclass(tp, enum.Enum)


def _all_have_defaults(tp: Any) -> bool:
    """Check whether every field in a struct type has a default value."""
    tp = _resolve_type(tp)
    return _is_struct(tp) and not _struct_required(tp)


_PLAIN_CLASS_BUILTINS = frozenset(
    {str, int, float, bool, bytes, bytearray, types.NoneType, list, dict, set, frozenset, tuple, Callable},
)


def _is_plain_class(tp: Any) -> bool:
    """True if tp is a non-dataclass, non-primitive class whose constructor signature reads.

    One that takes nothing is a plain class too, a struct with no fields, unless its instances
    hold C storage (:func:`_holds_c_storage`), as a lock does.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-structs-members-are-its-constructors-parameters.md#a-class-taking-nothing-is-a-struct-with-no-fields
    """
    tp = _class_of(_resolve_type(tp))
    # Since Python 3.11 ``typing.Any`` is a subclassable class in module "typing", so it passes
    # ``isinstance(tp, type)`` and the signature check below and would masquerade as a plain class.
    # It is not a struct; _type_kind names it ANY before asking any shape.
    if tp is Any or not isinstance(tp, type):
        return False
    if _is_dc(tp):
        return False
    if tp in _PLAIN_CLASS_BUILTINS or tp.__module__ == "builtins":
        return False
    # A builtin's subclass reads as the builtin, and a bare abstract collection as the concrete one.
    reads_as_a_collection = tp in _LIST_ORIGINS or tp in _SET_ORIGINS or tp in _DICT_ORIGINS
    if issubclass(tp, (enum.Enum, PurePath, tuple)) or _subclassed_builtin(tp) is not None or reads_as_a_collection:
        return False
    try:
        params = _init_params(tp)
    except (ValueError, TypeError):
        return False
    return bool(params.names) or not _holds_c_storage(tp)


_POINTER_SIZE = calcsize("P")


def _holds_c_storage(cls: type) -> bool:
    """True if an instance of *cls* holds storage beyond its ``__dict__``, ``__weakref__`` and slots.

    The layout test ``object.__reduce_ex__`` refuses to pickle a value by: a C type's own
    fields, a lock's or an exception's, which no ``__getstate__`` exempts here.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-structs-members-are-its-constructors-parameters.md#a-class-taking-nothing-that-holds-c-storage-is-no-struct
    """
    reached = object.__basicsize__
    # A managed __dict__ or __weakref__ (a negative offset) lives outside the instance's basic size.
    if cls.__dictoffset__ > 0:
        reached += _POINTER_SIZE
    if cls.__weakrefoffset__ > 0:
        reached += _POINTER_SIZE
    reached += _POINTER_SIZE * sum(_declared_slot_count(c) for c in cls.__mro__)
    return cls.__basicsize__ > reached or cls.__itemsize__ > 0


def _declared_slot_count(cls: type) -> int:
    """Return how many slots *cls*'s own body declares, ``__dict__`` and ``__weakref__`` left out.

    The count ``copyreg._slotnames`` gives, which is not called: it is private, and it caches
    its answer onto the class as ``__slotnames__``.
    """
    slots = cls.__dict__.get("__slots__", ())
    names = (slots,) if isinstance(slots, str) else tuple(slots)
    return sum(n not in {"__dict__", "__weakref__"} for n in names)


@dataclasses.dataclass(frozen=True)
class _VarParams:
    """The *args and **kwargs parameter names of a struct's __init__, None when absent."""

    positional: str | None = None
    keyword: str | None = None

    @property
    def names(self) -> frozenset[str]:
        """The names that are present, for membership tests against declared fields."""
        return frozenset(name for name in (self.positional, self.keyword) if name is not None)


class _PositionalGapError(TypeError):
    """A positional-only parameter is unset, with no default, before one a call sets.

    Attributes:
        unset: The parameter no value reaches.
        later: The set parameter past it.
    """

    def __init__(self, unset: str, later: str) -> None:
        super().__init__(f"positional-only parameter {unset!r} is unset before {later!r}")
        self.unset = unset
        self.later = later


#: The parameter kinds a positional argument fills.
_POSITIONAL_KINDS = (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)


@dataclasses.dataclass(frozen=True)
class _PositionalParams:
    """The parameters of a signature that a positional argument fills.

    Attributes:
        names: The positional-only parameters, then the positional-or-keyword ones, in
            order; all of them precede ``*args``.
        positional_only: How many of *names*, from the first, take no keyword.
        defaults: The declared default of each of *names* that has one.
    """

    names: tuple[str, ...]
    positional_only: int
    defaults: Mapping[str, Any]

    @classmethod
    def of(cls, params: Iterable[inspect.Parameter]) -> _PositionalParams:
        """Return the positional parameters among *params*, a signature's parameters in order."""
        positional = [p for p in params if p.kind in _POSITIONAL_KINDS]
        return cls(
            names=tuple(p.name for p in positional),
            positional_only=sum(p.kind is inspect.Parameter.POSITIONAL_ONLY for p in positional),
            defaults=types.MappingProxyType(
                {p.name: p.default for p in positional if p.default is not inspect.Parameter.empty},
            ),
        )

    def split(self, values: Mapping[str, Any]) -> tuple[list[Any], dict[str, Any]]:
        """Return *values*, keyed by parameter name, as the arguments a call passes by position and by keyword.

        The one answer to "which arguments go by position". A positional-only parameter left
        unset before a set one takes its declared default, since no keyword reaches the later
        one past it. Then the longest run of set names from the first goes by position, and
        every other value by keyword. A partial built from the split therefore names its
        positional arguments back to the same values, which split the same way.

        Raises:
            _PositionalGapError: If a positional-only parameter before a set one has no default.

        Dev Notes:
            docs-dev/architecture/callables.md#arguments-go-by-position-where-they-can
        """
        by_keyword = dict(values)
        only = self.names[: self.positional_only]
        last_set = max((i for i, name in enumerate(only) if name in by_keyword), default=-1)
        for name in only[:last_set]:
            if name not in by_keyword:
                if name not in self.defaults:
                    raise _PositionalGapError(name, only[last_set])
                by_keyword[name] = self.defaults[name]
        filled = list(itertools.takewhile(by_keyword.__contains__, self.names))
        return [by_keyword.pop(name) for name in filled], by_keyword


@dataclasses.dataclass(frozen=True)
class _InitParams:
    """What a struct's constructor signature declares, ``self`` or ``cls`` excluded.

    Attributes:
        names: Every parameter name, in signature order.
        defaults: The declared default of each parameter that has one; ``*args`` and
            ``**kwargs`` have none here. A dataclass ``default_factory`` field shows
            ``_DATACLASS_FACTORY_DEFAULT``, which :func:`_init_defaults` replaces by a call.
        var: The ``*args`` and ``**kwargs`` names.
        positional: The parameters a positional argument fills.
        constructor: The function whose annotations type the parameters, None when the
            class takes nothing.
    """

    names: tuple[str, ...]
    defaults: Mapping[str, Any]
    var: _VarParams
    positional: _PositionalParams
    constructor: Any

    @property
    def required(self) -> frozenset[str]:
        """The names a call must supply: no declared default, and neither ``*args`` nor ``**kwargs``."""
        return frozenset(n for n in self.names if n not in self.defaults and n not in self.var.names)


def _constructor_parameters(tp: type) -> tuple[list[inspect.Parameter], Any]:
    """Return the parameters calling class *tp* takes, and the function that declares them.

    ``__init__``'s when the class does not inherit it from ``object``, else ``__new__``'s
    when it does not inherit that one, else none: a class taking nothing.

    Raises:
        ValueError: If the signature cannot be read.
        TypeError: If the signature cannot be read.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-structs-members-are-its-constructors-parameters.md#which-signature-is-read
    """
    if tp.__init__ is not object.__init__:
        params = list(inspect.signature(tp.__init__).parameters.values())
        takes_self = bool(params) and params[0].kind in _POSITIONAL_KINDS
        return (params[1:] if takes_self else params), tp.__init__
    if tp.__new__ is not object.__new__:
        # The class's own signature, not __new__'s: a builtin __new__ reads as (*args, **kwargs),
        # where the class's text signature names its parameters (Decimal, Fraction).
        return list(inspect.signature(tp).parameters.values()), tp.__new__
    return [], None


@_per_class_cache
def _init_params(tp: Any) -> _InitParams:
    """Return the one walk of *tp*'s constructor signature every struct question reads.

    The members a channel sets, a dataclass's included (:func:`_constructor_parameters`).
    Cached per class; it reads no annotation, so its answer holds however they resolve. Beyond
    the signature, it reads a dataclass's fields and class attributes, a default that is the
    field's own descriptor being none (:func:`_defaults_to_its_descriptor`).

    Raises:
        ValueError: If the signature cannot be read (nothing is cached).
        TypeError: If the signature cannot be read (nothing is cached).

    Dev Notes:
        docs-dev/architecture/types/introspection.md#introspection-is-cached-per-class
    """
    cls = _class_of(tp)
    params, constructor = _constructor_parameters(cls)
    var_kinds = (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    variadic = {p.kind: p.name for p in params if p.kind in var_kinds}
    return _InitParams(
        names=tuple(p.name for p in params),
        defaults=types.MappingProxyType(
            {
                p.name: p.default
                for p in params
                if p.default is not inspect.Parameter.empty and not _defaults_to_its_descriptor(cls, p.name, p.default)
            },
        ),
        var=_VarParams(variadic.get(inspect.Parameter.VAR_POSITIONAL), variadic.get(inspect.Parameter.VAR_KEYWORD)),
        positional=_PositionalParams.of(params),
        constructor=constructor,
    )


def _init_fields(tp: Any) -> Mapping[str, Any]:
    """Return {name: resolved_type} for the constructor parameters of a struct.

    VAR_POSITIONAL (*args) becomes List[T] and VAR_KEYWORD (**kwargs) becomes
    Dict[str, T], where T is the annotation on the parameter (Any if absent). A dataclass
    field's type is the class's annotation, an ``InitVar`` read as the type it wraps.
    Constructor annotations that do not resolve all read as Any. Cached per class once
    every annotation resolves, so the mapping is shared and read-only.

    Raises:
        NameError: If a dataclass's own annotation does not resolve, as for :func:`_dc_fields`.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-structs-members-are-its-constructors-parameters.md#a-structs-members-are-its-constructors-parameters
    """
    try:
        return _annotated_init_fields(tp)
    except _UnresolvedHintsError:
        return _typed_init_fields(tp, _dc_member_hints(tp, _init_params(tp).names) if _is_dc(tp) else {})


@_per_class_cache
def _annotated_init_fields(tp: Any) -> Mapping[str, Any]:
    """Return :func:`_init_fields` when every annotation resolves, cached per class."""
    return _typed_init_fields(tp, _member_hints(tp))


def _member_hints(tp: Any, *, include_extras: bool = False) -> dict[str, Any]:
    """Return the annotation of each constructor parameter of struct *tp* that has one.

    A dataclass field's, an ``InitVar``'s included, is the class's own annotation; any other
    parameter's is its constructor's. *include_extras* keeps ``Annotated`` metadata.

    Raises:
        NameError: If a dataclass's own annotation does not resolve.
        _UnresolvedHintsError: If a constructor annotation does not resolve.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-structs-members-are-its-constructors-parameters.md#a-structs-members-are-its-constructors-parameters
    """
    params = _init_params(tp)
    if not _is_dc(tp):
        return _bound_constructor_hints(tp, params.constructor, include_extras=include_extras)
    hints = _dc_member_hints(tp, params.names, include_extras=include_extras)
    if any(name not in hints for name in params.names):
        # A handwritten __init__, or an undecorated subclass's own: the constructor's annotations
        # type what the fields do not name.
        hints = {**_bound_constructor_hints(tp, params.constructor, include_extras=include_extras), **hints}
    return hints


def _bound_constructor_hints(tp: Any, constructor: Any, *, include_extras: bool = False) -> dict[str, Any]:
    """Return :func:`_constructor_hints`, the parameters of the class defining *constructor* bound by *tp*."""
    cls = _class_of(tp)
    owner = _constructor_owner(cls, constructor) or cls
    hints = _constructor_hints(constructor, include_extras=include_extras, owner=owner)
    return _bind_hints(tp, hints, owner=owner) if hints else hints


def _constructor_hints(constructor: Any, *, include_extras: bool = False, owner: Any = None) -> dict[str, Any]:
    """Return the resolved annotations of *constructor*, which *owner* defines; none for a builtin or no constructor.

    Raises:
        _UnresolvedHintsError: If an annotation does not resolve.
    """
    if getattr(constructor, "__annotations__", None) is None:
        return {}
    return _type_hints(constructor, include_extras=include_extras, owner=owner)


def _typed_init_fields(tp: Any, hints: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return {name: resolved_type} for the constructor parameters of a struct, reading types from *hints*."""
    params = _init_params(tp)
    out: dict[str, Any] = {}
    for name in params.names:
        ann = _resolve_type(hints.get(name, Any))
        if name == params.var.positional:
            out[name] = list[ann]
        elif name == params.var.keyword:
            out[name] = dict[str, ann]
        else:
            out[name] = ann
    return types.MappingProxyType(out)


def _init_defaults(tp: Any) -> dict[str, Any]:
    """Return {name: default} for the constructor parameters of a struct that have defaults.

    VAR_POSITIONAL and VAR_KEYWORD params always get implicit defaults of [] and {}, and a
    dataclass ``default_factory`` field the factory's value, fresh on every call.

    Dev Notes:
        docs-dev/architecture/types/introspection.md#introspection-is-cached-per-class
    """
    # Never cache this: its [] and {}, and a factory's value, would be shared by every constructed instance.
    params = _init_params(tp)
    out: dict[str, Any] = {}
    for name in params.names:
        if name == params.var.positional:
            out[name] = []
        elif name == params.var.keyword:
            out[name] = {}
        elif name in params.defaults:
            default = params.defaults[name]
            factory = default is _DATACLASS_FACTORY_DEFAULT
            out[name] = _class_of(tp).__dataclass_fields__[name].default_factory() if factory else default
    return out


def _var_params(tp: Any) -> _VarParams:
    """Return the *args and **kwargs parameter names of tp's constructor.

    An uninspectable constructor tells us nothing, so it short-circuits to an empty result.

    Args:
        tp: The struct type to inspect.

    Returns:
        A _VarParams holding the two names, each None when the parameter is absent.
    """
    try:
        return _init_params(tp).var
    except (ValueError, TypeError):
        return _VarParams()


def _is_struct(tp: Any) -> bool:
    """True if tp is a dataclass or a plain class, one taking nothing included, or a parameterized generic one."""
    tp = _class_of(_resolve_type(tp))
    return isinstance(tp, type) and _is_struct_class(tp)


@_per_class_cache
def _is_struct_class(cls: type) -> bool:
    """Return :func:`_is_struct` for a class, cached per class.

    Dev Notes:
        docs-dev/architecture/types/introspection.md#introspection-is-cached-per-class
    """
    return _is_dc(cls) or _is_plain_class(cls)


def _struct_subclasses(tp: Any) -> list[Any]:
    """Return all struct subclasses of tp, recursively (BFS order), each bound as a tag naming it binds it.

    *tp* may be a parameterized generic: each subclass then reads with the type parameters
    *tp*'s arguments bind (:func:`_tagged_struct`), and one whose bases fix other arguments
    is left out. Read afresh on every call, so a subclass defined since the last one is found.

    Dev Notes:
        docs-dev/architecture/types/introspection.md#introspection-is-cached-per-class
    """
    found: list[Any] = []
    seen: set[type] = set()
    queue: deque[type] = deque(_class_of(tp).__subclasses__())
    while queue:
        sub = queue.popleft()
        if sub in seen:
            continue
        seen.add(sub)
        queue.extend(sub.__subclasses__())
        if _is_struct_class(sub) and (bound := _tagged_struct(sub, tp)) is not None:
            found.append(bound)
    return found


def _direct_struct_subclasses(tp: Any) -> list[Any]:
    """Return the direct struct subclasses of the class *tp* builds, bound as :func:`_struct_subclasses` binds them."""
    subs = (_tagged_struct(s, tp) for s in _class_of(tp).__subclasses__() if _is_struct(s))
    return [s for s in subs if s is not None]


def _struct_fields(tp: Any) -> Mapping[str, Any]:
    """Return {name: type} for the members every channel sets on a struct: its constructor's parameters, read-only.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-structs-members-are-its-constructors-parameters.md#a-structs-members-are-its-constructors-parameters
    """
    return _init_fields(tp)


def _struct_state_fields(tp: Any) -> Mapping[str, Any]:
    """Return {name: type} for what ``dump()`` reads off an instance of struct *tp*, read-only.

    A dataclass's stored fields (:func:`_dc_fields`); a plain class declares no state but
    its constructor's parameters (:func:`_struct_fields`), a ``*args`` one as the tuple Python
    hands the constructor, where it is a list as a member.

    Dev Notes:
        docs-dev/architecture/design-decisions/the-object-dump-writes-state.md#a-dataclass-dumps-the-fields-it-stores
    """
    if _is_dc(tp):
        return _dc_fields(tp)
    members = _init_fields(tp)
    star = _init_params(tp).var.positional
    if star is None:
        return members
    item = _elem_type(members[star])
    return types.MappingProxyType({**members, star: tuple[item, ...]})


def _answered_by_subclasses(tp: Any, field: str) -> bool:
    """Return whether the type walk answers struct ``tp``'s member *field* from its subclasses.

    Only a name ``tp`` does not declare itself is: a declared field is answered by ``tp``'s
    own annotation however a subclass overrides it, so the subclasses own nothing at ``tp``
    but their subclass-only names (BUG-86).

    Dev Notes:
        docs-dev/architecture/cli-adapters/union-inheritance-and-cast-flags.md#union-inheritance-and-cast-flags
    """
    return field not in _struct_fields(tp)


def _base_declares_path(tp: Any, prefix: str, path: str) -> bool:
    """Return whether dotted *path* lies under *prefix* through a member struct ``tp`` declares.

    The path form of :func:`_answered_by_subclasses`, for registration's subclass recursion,
    which sees flag paths rather than segments: such a path is the base's to answer, never a
    subclass's, so ``cli/_build._collect_struct_specs`` drops a subclass's spec under it
    (BUG-86).
    """
    head = f"{prefix}." if prefix else ""
    return path.startswith(head) and not _answered_by_subclasses(tp, path.removeprefix(head).split(".", maxsplit=1)[0])


def _subclass_field_type(tp: type, field: str) -> Any | None:
    """Search all struct subclasses of tp for a field, returning its type.

    Returns the common type if all subclasses agree, str if they disagree, None if absent.

    Dev Notes:
        docs-dev/architecture/cli-parsing/casts-and-reserved-words.md#real-field-wins
    """
    found: list[Any] = []
    for sub in _struct_subclasses(tp):
        flds = _struct_fields(sub)
        if field in flds:
            found.append(flds[field])
    if not found:
        return None
    first = found[0]
    return first if all(f == first for f in found[1:]) else str


def _struct_member_type(tp: Any, name: str) -> Any | None:
    """Return the type struct ``tp`` answers for member *name*, None when nothing declares it.

    The walk's one member rule: ``tp``'s own annotation for a name it declares, however a
    subclass overrides it, and the subclasses' common type or ``str`` for a subclass-only
    name. The type walk asks it for the type; the member predicates ask whether it is None,
    so "is it a member?" and "what type is it?" cannot drift apart (BUG-86, BUG-103).

    Dev Notes:
        docs-dev/architecture/cli-adapters/union-inheritance-and-cast-flags.md#union-inheritance-and-cast-flags
    """
    return _subclass_field_type(tp, name) if _answered_by_subclasses(tp, name) else _struct_fields(tp)[name]


def _struct_member_names(tp: Any) -> list[str]:
    """Return every name :func:`_struct_member_type` answers for struct ``tp``, its own first.

    The listing view of the same member rule, for a caller that matches a spelling against
    the members rather than looks one up: ``tp``'s declared fields, then each subclass-only
    name in the order :func:`_struct_subclasses` meets it.
    """
    inherited = (n for sub in _struct_subclasses(tp) for n in _struct_fields(sub) if _answered_by_subclasses(tp, n))
    return list(dict.fromkeys([*_struct_fields(tp), *inherited]))


def _union_branches(tp: Any) -> list[Any]:
    """Return the resolved, non-union types a node of type *tp* is walked as, in variant order.

    *tp* itself when it is no union; otherwise each non-None variant, a variant that is a
    union in turn spread into its own.
    """
    tp = _resolve_type(tp)
    if not _is_union(tp):
        return [tp]
    return [node for v in _union_args_no_none(tp) for node in _union_branches(v)]


def _union_tag_shadowed(tp: Any, union_tag: str) -> bool:
    """Return True if a struct-shaped ``tp`` owns a member spelled exactly like the tag.

    Answers "is this tag-shaped key a field's value instead?" wherever only the type and
    the key are at hand. A union is shadowed by any struct variant that owns the name;
    a struct by its own fields or by a subclass-only field — the walk's member answer,
    so a subclass-only field spelled exactly like the tag wins the tag's spelling
    (BUG-103).

    Dev Notes:
        docs-dev/architecture/cli-parsing/casts-and-reserved-words.md#real-field-wins
    """
    tp = _resolve_type(tp)
    if _is_union(tp):
        return any(_union_tag_shadowed(v, union_tag) for v in _union_args_no_none(tp))
    if not _is_struct(tp):
        return False
    return _struct_member_type(tp, union_tag) is not None


def _struct_defaults(tp: Any) -> dict[str, Any]:
    """Return {name: default} for the members that have defaults, built afresh on every call."""
    return _init_defaults(tp)


def _struct_required(tp: Any) -> frozenset[str]:
    """Return the names of a struct's members that have no default, building none of the defaults.

    The members :func:`_struct_defaults` leaves out, without calling a ``default_factory``.
    """
    return _init_params(tp).required


def _struct_declared_defaults(tp: Any) -> dict[str, Any]:
    """Return the defaults a struct declares as values for its members, calling nothing to get them.

    The constructor's parameter defaults, a dataclass ``default_factory`` field's left out.
    A fresh dict per call, never cached: the values are the class's own objects.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-field-default-is-the-base-layer.md#tier-1-defaults-read-without-running-code
    """
    return {n: d for n, d in _init_params(tp).defaults.items() if d is not _DATACLASS_FACTORY_DEFAULT}


def _resolve_struct(
    target: Any,
) -> tuple[Any, Mapping[str, Any], dict[str, Any]] | None:
    """Resolve a struct type to (tp, members, hints), or None if not a struct.

    *hints* holds each member's annotation as written, ``Annotated`` metadata kept, or its
    resolved type where none resolves.

    Dev Notes:
        docs-dev/architecture/design-decisions/a-structs-members-are-its-constructors-parameters.md#a-structs-members-are-its-constructors-parameters
    """
    tp = _resolve_type(target)
    if not _is_struct(tp):
        return None
    try:
        flds = _struct_fields(tp)
    except (ValueError, TypeError, NameError, AttributeError):
        return None
    try:
        written = _member_hints(tp, include_extras=True)
    except (NameError, AttributeError, TypeError, _UnresolvedHintsError):
        written = {}
    return tp, flds, {name: written.get(name, ft) for name, ft in flds.items()}


def _is_type_ref(tp: Any) -> bool:
    """True for `type`, `type[X]`, or `Type[X]`."""
    tp = _resolve_type(tp)
    return tp is type or get_origin(tp) is type


def _type_ref_constraint(tp: Any) -> type:
    """Upper-bound class from `type[X]`; `object` for bare `type`."""
    tp = _resolve_type(tp)
    args = get_args(tp)
    if args:
        c = _resolve_type(args[0])
        return c if isinstance(c, type) else object
    return object


def _is_callable(tp: Any) -> bool:
    """Check whether a type is Callable[...] or bare Callable."""
    tp = _resolve_type(tp)
    return get_origin(tp) is Callable or tp is Callable


def _callable_param_types(tp: Any) -> list[Any] | None:
    """Return the declared parameter types for Callable[[T1, T2], R], or None.

    Returns None for bare Callable or Callable[..., R] (no param constraint).
    """
    args = get_args(_resolve_type(tp))
    if not args:
        return None
    params = args[0]
    if params is Ellipsis:
        return None
    return [_resolve_type(p) for p in params]
