# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Type introspection utilities for confarg."""

from __future__ import annotations

import dataclasses
import enum
import inspect
import types
from collections.abc import (
    Callable as CallableABC,
)
from collections.abc import (
    Collection as CollectionABC,
)
from collections.abc import (
    Iterable as IterableABC,
)
from collections.abc import (
    Mapping as MappingABC,
)
from collections.abc import (
    MutableMapping as MutableMappingABC,
)
from collections.abc import (
    MutableSequence as MutableSequenceABC,
)
from collections.abc import (
    MutableSet as MutableSetABC,
)
from collections.abc import (
    Sequence as SequenceABC,
)
from collections.abc import (
    Set as SetABC,
)
from pathlib import Path, PurePath
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

type TagPolicy = Literal["auto", "always"]

_MISSING = object()


class _StrToken(str):
    """String value from CLI args or env vars — eligible for coercion to target type."""

    __slots__ = ()


def _resolve_type(tp: Any) -> Any:
    """Unwrap TypeAliasType and Annotated wrappers.

    Args:
        tp: The type to resolve.

    Returns:
        The unwrapped underlying type.
    """
    while type(tp).__name__ == "TypeAliasType":
        tp = tp.__value__
    from typing import Annotated

    if get_origin(tp) is Annotated:
        tp = get_args(tp)[0]
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
    tp = _resolve_type(tp)
    return dataclasses.is_dataclass(tp) and isinstance(tp, type)


def _dc_fields(tp: Any) -> dict[str, Any]:
    """Return field names mapped to their resolved types for a dataclass.

    Args:
        tp: A dataclass type.

    Returns:
        A dict mapping field names to their resolved type annotations.
    """
    hints = get_type_hints(tp)
    return {f.name: _resolve_type(hints[f.name]) for f in dataclasses.fields(tp)}


def _dc_defaults(tp: Any) -> dict[str, Any]:
    """Return field names mapped to their default values.

    Args:
        tp: A dataclass type.

    Returns:
        A dict mapping field names to default values for fields that have them.
    """
    out: dict[str, Any] = {}
    for f in dataclasses.fields(tp):
        if f.default is not dataclasses.MISSING:
            out[f.name] = f.default
        elif f.default_factory is not dataclasses.MISSING:
            out[f.name] = f.default_factory()
    return out


def _is_none_type(tp: Any) -> bool:
    """Check whether a type is NoneType.

    Args:
        tp: The type to check.

    Returns:
        True if tp is NoneType.
    """
    return _resolve_type(tp) is type(None)


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
    return [a for a in get_args(_resolve_type(tp)) if a is not type(None)]


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
        return type(None) in _union_args(tp)
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


_LIST_ORIGINS = frozenset({list, SequenceABC, MutableSequenceABC, IterableABC, CollectionABC})
_SET_ORIGINS = frozenset({set, SetABC, MutableSetABC})
_DICT_ORIGINS = frozenset({dict, MappingABC, MutableMappingABC})


def _is_list(tp: Any) -> bool:
    """Check whether a type is list[...] or an abstract sequence type (Sequence, MutableSequence, Iterable, Collection).

    Args:
        tp: The type to check.

    Returns:
        True if tp is a list or sequence type.
    """
    return _origin(tp) in _LIST_ORIGINS


def _is_set(tp: Any) -> bool:
    """Check whether a type is set[...] or an abstract set type (AbstractSet, MutableSet).

    Args:
        tp: The type to check.

    Returns:
        True if tp is a set type.
    """
    return _origin(tp) in _SET_ORIGINS


def _is_frozenset(tp: Any) -> bool:
    """Check whether a type is frozenset[...].

    Args:
        tp: The type to check.

    Returns:
        True if tp is a frozenset type.
    """
    return _origin(tp) is frozenset


def _is_tuple(tp: Any) -> bool:
    """Check whether a type is tuple[...].

    Args:
        tp: The type to check.

    Returns:
        True if tp is a tuple type.
    """
    return _origin(tp) is tuple


def _is_dict(tp: Any) -> bool:
    """Check whether a type is dict[...] or an abstract mapping type (Mapping, MutableMapping).

    Args:
        tp: The type to check.

    Returns:
        True if tp is a dict or mapping type.
    """
    return _origin(tp) in _DICT_ORIGINS


def _is_collection(tp: Any) -> bool:
    """Check whether a type is a list, set, frozenset, or tuple.

    Args:
        tp: The type to check.

    Returns:
        True if tp is a list, set, frozenset, or tuple type.
    """
    return _is_list(tp) or _is_set(tp) or _is_frozenset(tp) or _is_tuple(tp)


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
        return len(a) == _variable_length_tuple_args and a[1] is Ellipsis
    return False


def _elem_type(tp: Any) -> Any:
    """Return the element type of a generic collection.

    Args:
        tp: A generic collection type (e.g. list[int]).

    Returns:
        The element type, or Any if not parameterized.
    """
    a = get_args(_resolve_type(tp))
    return _resolve_type(a[0]) if a else Any


def _tuple_types(tp: Any) -> list[Any] | None:
    """Return fixed-length element types for a tuple, or None for tuple[X, ...].

    Args:
        tp: A tuple type.

    Returns:
        A list of element types for fixed-length tuples, or None for variable-length.
    """
    a = get_args(_resolve_type(tp))
    _variable_length_tuple_args = 2
    if len(a) == _variable_length_tuple_args and a[1] is Ellipsis:
        return None
    return [_resolve_type(x) for x in a]


def _dict_kv(tp: Any) -> tuple[Any, Any]:
    """Return the key and value types of a dict type.

    Args:
        tp: A dict type.

    Returns:
        A (key_type, value_type) tuple, defaulting to (str, Any).
    """
    a = get_args(_resolve_type(tp))
    return (_resolve_type(a[0]), _resolve_type(a[1])) if a else (str, Any)


def _is_literal(tp: Any) -> bool:
    """Check whether a type is a Literal type.

    Args:
        tp: The type to check.

    Returns:
        True if tp is a Literal type.
    """
    from typing import Literal

    return get_origin(_resolve_type(tp)) is Literal


def _literal_values(tp: Any) -> tuple[Any, ...]:
    """Return the allowed values of a Literal type.

    Args:
        tp: A Literal type.

    Returns:
        A tuple of the Literal's allowed values.
    """
    return get_args(_resolve_type(tp))


def _is_singleton_literal(tp: Any) -> bool:
    """Check whether a type is a Literal with exactly one allowed value.

    Args:
        tp: The type to check.

    Returns:
        True if tp is Literal[X] for a single value X.
    """
    return _is_literal(tp) and len(_literal_values(tp)) == 1


def _is_final(tp: Any) -> bool:
    """Check whether a type is a Final annotation.

    Args:
        tp: The type to check.

    Returns:
        True if tp is Final[X] for some X.
    """
    from typing import Final

    return get_origin(tp) is Final


def _final_inner(tp: Any) -> Any:
    """Return the inner type of a Final annotation.

    Args:
        tp: A Final[X] type.

    Returns:
        X, or Any if Final has no argument.
    """
    args = get_args(tp)
    return args[0] if args else Any


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
    if not _is_struct(tp):
        return False
    defs = _struct_defaults(tp)
    return all(name in defs for name in _struct_fields(tp))


_PLAIN_CLASS_BUILTINS = frozenset(
    {str, int, float, bool, bytes, bytearray, type(None), list, dict, set, frozenset, tuple, CallableABC}
)


def _is_plain_class(tp: Any) -> bool:
    """True if tp is a non-dataclass, non-primitive class with __init__ parameters."""
    tp = _resolve_type(tp)
    if not isinstance(tp, type):
        return False
    if _is_dc(tp):
        return False
    if tp in _PLAIN_CLASS_BUILTINS or tp.__module__ == "builtins":
        return False
    if issubclass(tp, enum.Enum) or issubclass(tp, PurePath):
        return False
    try:
        sig = inspect.signature(tp.__init__)
        return any(p.name != "self" for p in sig.parameters.values())
    except (ValueError, TypeError):
        return False


def _init_fields(tp: Any) -> dict[str, Any]:
    """Return {name: resolved_type} for __init__ parameters of a plain class.

    VAR_POSITIONAL (*args) becomes List[T] and VAR_KEYWORD (**kwargs) becomes
    Dict[str, T], where T is the annotation on the parameter (Any if absent).
    """
    try:
        hints = get_type_hints(tp.__init__)
    except (NameError, AttributeError, TypeError):
        hints = {}
    sig = inspect.signature(tp.__init__)
    result: dict[str, Any] = {}
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        if param.kind == inspect.Parameter.VAR_POSITIONAL:
            elem = _resolve_type(hints.get(name, Any))
            result[name] = list[elem]
        elif param.kind == inspect.Parameter.VAR_KEYWORD:
            val = _resolve_type(hints.get(name, Any))
            result[name] = dict[str, val]
        else:
            result[name] = _resolve_type(hints.get(name, Any))
    return result


def _init_defaults(tp: Any) -> dict[str, Any]:
    """Return {name: default} for __init__ parameters that have defaults.

    VAR_POSITIONAL and VAR_KEYWORD params always get implicit defaults of [] and {}.
    """
    sig = inspect.signature(tp.__init__)
    result: dict[str, Any] = {}
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        if param.kind == inspect.Parameter.VAR_POSITIONAL:
            result[name] = []
        elif param.kind == inspect.Parameter.VAR_KEYWORD:
            result[name] = {}
        elif param.default is not inspect.Parameter.empty:
            result[name] = param.default
    return result


def _var_param_names(tp: Any) -> frozenset[str]:
    """Return names of all *args and **kwargs parameters of tp.__init__."""
    if _is_dc(tp):
        return frozenset()
    try:
        sig = inspect.signature(tp.__init__)
        return frozenset(
            name
            for name, param in sig.parameters.items()
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        )
    except (ValueError, TypeError):
        return frozenset()


def _var_positional_name(tp: Any) -> str | None:
    """Return the name of the *args parameter of tp.__init__, or None."""
    if _is_dc(tp):
        return None
    try:
        sig = inspect.signature(tp.__init__)
        for name, param in sig.parameters.items():
            if param.kind == inspect.Parameter.VAR_POSITIONAL:
                return name
    except (ValueError, TypeError):
        pass
    return None


def _var_keyword_name(tp: Any) -> str | None:
    """Return the name of the **kwargs parameter of tp.__init__, or None."""
    if _is_dc(tp):
        return None
    try:
        sig = inspect.signature(tp.__init__)
        for name, param in sig.parameters.items():
            if param.kind == inspect.Parameter.VAR_KEYWORD:
                return name
    except (ValueError, TypeError):
        pass
    return None


def _is_struct(tp: Any) -> bool:
    """True if tp is a dataclass or a plain class with __init__ parameters."""
    return _is_dc(tp) or _is_plain_class(tp)


def _struct_fields(tp: Any) -> dict[str, Any]:
    """Return {name: type} for all fields/parameters of a struct or plain class."""
    return _dc_fields(tp) if _is_dc(tp) else _init_fields(tp)


def _struct_defaults(tp: Any) -> dict[str, Any]:
    """Return {name: default} for fields/parameters that have defaults."""
    return _dc_defaults(tp) if _is_dc(tp) else _init_defaults(tp)


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
    return get_origin(tp) is CallableABC or tp is CallableABC


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


def _callable_return_type(tp: Any) -> Any | None:
    """Return the declared return type for Callable[..., R], or None for bare Callable."""
    _callable_min_args = 2
    args = get_args(_resolve_type(tp))
    if len(args) < _callable_min_args:
        return None
    return _resolve_type(args[1])


def _try_coerce(ft: Any, token: _StrToken) -> Any:
    """Coerce a string token to the target type if unambiguous.

    Coerces immediately for concrete leaf types (bool, int, float, Path,
    Literal, Enum) so the merged dict has consistent types regardless of source.
    str tokens are returned unchanged — _StrToken is already a str subclass.
    For multi-variant unions, returns token unchanged for construct() to handle.
    """
    from confarg._errors import TypeCoercionError
    from confarg.typedload._coerce import _coerce_leaf  # lazy — avoids circular import

    if ft is None:
        return token
    ft = _resolve_type(ft)
    if _is_union(ft):
        non_none = _union_args_no_none(ft)
        if len(non_none) != 1:
            return token
        ft = _resolve_type(non_none[0])
    if not (_is_literal(ft) or _is_enum(ft) or ft in (bool, int, float, Path)):
        return token
    try:
        return _coerce_leaf(ft, token)
    except TypeCoercionError:
        return token
