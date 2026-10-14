# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Callable resolution and serialization.

Dev Notes:
    docs-dev/architecture/callables.md
"""

from __future__ import annotations

import functools
import inspect
import types
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, NoReturn, get_args, get_origin, get_type_hints

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

from confarg import _defaults
from confarg._import import _import_dotted, dotted_name, imports_back
from confarg._types import (
    _callable_param_types,
    _is_callable,
    _is_struct,
    _is_union,
    _resolve_type,
    _src_type,
)
from confarg.exceptions import ConfargError, FieldPath, SymbolImportError, TypeCoercionError, _spell_field_path


@dataclass(frozen=True)
class _SpecContext:
    """Where a callable spec sits, and how the arguments it names are built.

    Attributes:
        path: The spec's construction path, which messages name and its arguments are built below.
        union_tag: The union tag the arguments are built with.
        construct_fn: The typed construction the arguments go through.
    """

    path: FieldPath
    union_tag: str
    construct_fn: Any

    @property
    def where(self) -> str:
        """Return the spec's path as messages spell it."""
        return _spell_field_path(self.path)

    def at(self, key: str) -> _SpecContext:
        """Return this context one *key* deeper."""
        return replace(self, path=(*self.path, key))

    def construct(self, tp: Any, value: Any) -> Any:
        """Build *value* as *tp* at this context's path."""
        return self.construct_fn(tp, value, path=self.path, union_tag=self.union_tag)

    def instantiate(self, cls: type, kwargs: dict, name: str, opener: str) -> Any:
        """Build exactly *cls* from *kwargs* at this context's path, whatever subclasses it has.

        *name* is the class as the spec wrote it, and *opener* the key that named it.

        Dev Notes:
            docs-dev/architecture/design-decisions/class-names-the-type-it-builds.md#class-names-the-type-it-builds
        """
        from confarg.typedload._construct import construct_named_class  # noqa: PLC0415  # import cycle

        return construct_named_class(cls, kwargs, path=self.path, union_tag=self.union_tag, name=name, opener=opener)


def _instance_method_owner(path_str: str) -> type | None:
    """Return the class whose instance method the dotted *path_str* names, or None.

    The owner is the class the path names before its last segment, so a method a base
    defines is owned by the subclass the path names. The last segment must be a function
    that class holds, its own or a base's: a static or class method needs no instance, and
    ``__init__`` is read as a plain function. A path whose parent is a module or an instance
    names no instance method.

    Dev Notes:
        docs-dev/architecture/callables.md#auto-binding
    """
    owner_path, _, name = path_str.rpartition(".")
    if not owner_path or name == "__init__":
        return None
    try:
        owner = _import_dotted(owner_path)
    except SymbolImportError:
        return None
    if not isinstance(owner, type):
        return None
    attr = inspect.getattr_static(owner, name, None)
    return owner if isinstance(attr, types.FunctionType) else None


def _reads_back_from(path_str: str, value: Any) -> bool:
    """Check that the dotted *path_str*, read as a callable spec, yields *value* again.

    Imports the path rather than resolving it, so nothing is built: an instance method
    (:func:`_instance_method_owner`) reads back bound to a new owner, so *value* must be that
    method's function bound to an instance of exactly that owner. What the owner holds is not
    checked: :func:`_serialize_callable` writes it beside the path. Anything else reads back as
    what the path imports (:func:`imports_back`).

    Dev Notes:
        docs-dev/architecture/callables.md#a-path-is-written-only-when-it-reads-back
    """
    owner = _instance_method_owner(path_str)
    if owner is None:
        return imports_back(path_str, value)
    return inspect.ismethod(value) and type(value.__self__) is owner and imports_back(path_str, value.__func__)


def _target_signature(path_str: str) -> inspect.Signature:
    """Return the signature of the callable a dotted ``bind:`` or ``call:`` target yields, building nothing.

    The callable :func:`_import_target` resolves: a class is called as it is, so its
    signature has no receiver, and an instance method is bound to its owner first
    (:func:`_instance_method_owner`), so its receiver goes, whatever it is named. Any other
    function keeps every parameter it declares, a ``self`` included. The owner is not built:
    the method is bound to a stand-in, which only the receiver's position depends on.

    Raises:
        SymbolImportError: If *path_str* does not import.
        ValueError: If the callable cannot be inspected.
        TypeError: If what *path_str* names is not callable.

    Dev Notes:
        docs-dev/architecture/callables.md#one-coercion-route
    """
    obj = _import_dotted(path_str)
    if _instance_method_owner(path_str) is not None:
        obj = types.MethodType(obj, object())
    return inspect.signature(obj)


def target_parameter_types(path_str: str) -> dict[str, Any]:
    """Return the annotation of each parameter a dotted ``bind:`` or ``call:`` target takes, building nothing.

    The parameters :func:`_target_signature` lists, read from the object :func:`_hints_source`
    names, as :func:`_coerce_kwargs` reads them to build the arguments under ``args``. A
    parameter with no annotation is left out: its argument is kept as written.

    Raises:
        SymbolImportError: If *path_str* does not import.
        ValueError: If the callable cannot be inspected.
        TypeError: If what *path_str* names is not callable.
        NameError: If an annotation names nothing.
    """
    params = _target_signature(path_str).parameters
    hints = get_type_hints(_hints_source(_import_dotted(path_str)))
    return {p.name: hints[p.name] for p in _fillable_params(params) if p.name in hints}


def _maybe_bind_method(func: Any, path_str: str, where: str) -> Any:
    """Bind *func* to an owner built with no arguments when *path_str* names an instance method.

    Returns func unchanged when it is no instance method (:func:`_instance_method_owner`).
    Raises when the owner requires constructor arguments: the message gives the ``classfn:``
    spec that builds the owner with them, the constructor's parameters listed in it.
    """
    owner = _instance_method_owner(path_str)
    if owner is None:
        return func
    try:
        instance = owner()
    except TypeError as e:
        spec = "\n".join(filter(None, [f"  classfn: {path_str}", _format_constructor_params(owner)]))
        msg = (
            f"Cannot instantiate {owner.__qualname__!r} with no arguments at '{where}': {e}.\n"
            f"{path_str} is an instance method, so its owner is built with no arguments. To build"
            f" {owner.__qualname__} with arguments, name the method with 'classfn:', its other keys"
            f" the constructor's arguments:\n{spec}\n"
            "Under 'bind:' or 'call:', that spec is the target, and the mapping under 'args' holds"
            " the method's own arguments."
        )
        raise TypeCoercionError(msg) from e
    return getattr(instance, path_str.rpartition(".")[2])


def _fillable_params(
    params: Mapping[str, inspect.Parameter],
    *,
    required: bool | None = None,
) -> list[inspect.Parameter]:
    """Return the parameters a caller fills one argument each: all but ``*args`` and ``**kwargs``.

    *required* keeps only those without a default when true, only those with one when
    false, and every one when None. *params* is a signature's ``parameters``, so a receiver
    is in it only when the callable really declares one (an unbound function's ``self``).
    """
    return [
        p
        for p in params.values()
        if p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        and (required is None or required is (p.default is inspect.Parameter.empty))
    ]


def _format_constructor_params(cls: type) -> str:
    """Return a YAML-like listing of *cls*'s constructor parameters, the required ones first."""
    try:
        sig = inspect.signature(cls)
    except (ValueError, TypeError):
        return "  # (constructor parameters cannot be inspected)"

    lines = []
    for p in _fillable_params(sig.parameters, required=True):
        type_hint = f"  # {p.annotation.__name__}" if isinstance(p.annotation, type) else ""
        lines.append(f"  {p.name}: <value>{type_hint}")
    for p in _fillable_params(sig.parameters, required=False):
        type_hint = f"  # {p.annotation.__name__}, optional" if isinstance(p.annotation, type) else "  # optional"
        lines.append(f"  # {p.name}: {p.default!r}{type_hint}")
    return "\n".join(lines)


def _resolve_callable_spec(spec: Any, tp: Any, path: FieldPath, union_tag: str, construct_fn: Any) -> Any:
    """Resolve a Callable value from a raw spec (string or dict).

    Bare string:
      - If the import resolves to a class → the class itself is the callable
        (factory-like): return functools.partial(cls). Calling it constructs an
        instance. To use an *instance* as the callable, use the 'class:' dict form.
        When the Callable declares a concrete return type the class cannot produce,
        this raises and points at the 'class:' form.
      - Otherwise (function/method) → use as-is.

    Dict with 'bind' key:
      - The target, resolved as a bare string is (or, when it is a dict, as a callable spec
        of its own), with the kwargs under 'args' partially applied: functools.partial(target,
        **args). With no argument, the target itself, so '{bind: T}' and 'T' are one spec.

    Dict with 'class' key:
      - Instantiate the class with the other keys as its fields; the instance is the
        callable (it must define __call__).

    Dict with 'call' key:
      - Call the target (a dotted path, or a callable spec of its own) with the kwargs
        under 'args'; its return value is the callable.

    Dict with 'classfn' key:
      - Build the owner of the instance method it names from the other keys; the bound
        method is the callable.
    """
    where = _spell_field_path(path)
    if isinstance(spec, str):
        result = _resolve_bare_string(str(spec), where, tp)
    elif isinstance(spec, dict):
        result = _resolve_dict_spec(spec, tp, _SpecContext(path, union_tag, construct_fn))
    elif callable(spec):
        result = spec
    else:
        msg = f"Cannot construct Callable at '{where}': expected str or dict, got {type(spec).__name__} {spec!r}"
        raise TypeCoercionError(msg)
    if not callable(result):
        msg = f"Callable at '{where}': {spec!r} resolved to {result!r}, which is not callable."
        raise TypeCoercionError(msg)
    _check_callable_signature(result, tp, where)
    return result


def _import_target(path_str: str, path: str, callable_tp: Any) -> Any:
    """Import the target a bare string, a ``bind:`` or a ``call:`` spec names: a class, or a function.

    A class is returned as it is, to be used factory-like. Raises ``TypeCoercionError``
    pointing at the 'class:' form when *callable_tp* declares a concrete return type
    (including ``None``) that the class cannot produce; a bare or abstractly-typed
    Callable, or no Callable at all (None, as for a ``call:``), is not checked. An instance
    method is bound to an owner built with no arguments (:func:`_maybe_bind_method`); any
    other function is returned as it is.
    """
    obj = _import_dotted(path_str)
    if isinstance(obj, type):
        required = _unproducible_return(obj, callable_tp)
        if required is not None:
            msg = (
                f"Callable at '{path}': class {path_str!r} would be used as a factory,"
                f" but its instances are not {required} (the Callable's declared return type)."
                f" To use an instance of {path_str} as the callable, use the dict form:"
                f" 'class: {path_str}'."
            )
            raise TypeCoercionError(msg)
        return obj
    return _maybe_bind_method(obj, path_str, path)


def _resolve_target(target: Any, tp: Any, ctx: _SpecContext, opener: str) -> Any:
    """Return the callable that the ``bind:`` or ``call:`` *opener* of a spec at *ctx* names.

    *target* is a dotted path, imported by :func:`_import_target` and checked against the
    Callable *tp* (None checks nothing), or a callable spec of its own, resolved one key
    below the spec. Anything else is refused.

    Dev Notes:
        docs-dev/architecture/callables.md#spec-grammar
    """
    if isinstance(target, str):
        return _import_target(target, ctx.where, tp)
    if isinstance(target, dict):
        target_ctx = ctx.at(opener)
        obj = _resolve_dict_spec(target, tp, target_ctx)
        if not callable(obj):
            msg = f"{opener!r} target at '{target_ctx.where}': {target!r} resolved to {obj!r}, which is not callable."
            raise TypeCoercionError(msg)
        return obj
    msg = (
        f"{opener!r} at '{ctx.where}' takes a dotted path or a callable spec, got {_src_type(target)}."
        f" The target's arguments go under 'args': {{{opener}: <target>, args: {{<name>: <value>}}}}."
    )
    raise TypeCoercionError(msg)


def _as_callable(target: Any) -> Any:
    """Return *target* as the callable a spec with nothing to apply yields: a class as a bare factory."""
    return functools.partial(target) if isinstance(target, type) else target


def _resolve_bare_string(path_str: str, path: str, callable_tp: Any = None) -> Any:
    """Resolve a bare import-path string to a callable.

    A class resolves to the class itself, used factory-like: return
    functools.partial(cls) with no pre-bound kwargs, so calling it constructs an
    instance. To use an instance as the callable, use the 'class:' dict form.
    Functions and methods are used as-is (see :func:`_import_target`).
    """
    return _as_callable(_import_target(path_str, path, callable_tp))


def _issubclass_safe(cls: type, other: type) -> bool:
    """Issubclass that returns False instead of raising for non-class operands."""
    try:
        return issubclass(cls, other)
    except TypeError:
        return False


def _unproducible_return(cls: type, callable_tp: Any) -> str | None:
    """Describe the Callable's declared return type when a bare ``cls`` factory can't produce it.

    Returns a short human description (e.g. ``'_Optimizer'``, ``'None'``) when ``cls``
    used factory-like would yield the wrong type, or ``None`` when it is a valid factory
    — including when the Callable declares no concrete return type (bare ``Callable``,
    ``Callable[..., TypeVar]``), in which case the user is trusted.

    Note: ``get_args`` reports the return of ``Callable[..., None]`` as the object
    ``None`` (not ``NoneType``), so a lookup answering ``None`` for a bare ``Callable``
    could not tell the two apart; the raw args are inspected here instead.
    """
    if callable_tp is None:
        return None
    _callable_min_args = 2
    args = get_args(_resolve_type(callable_tp))
    if len(args) < _callable_min_args:
        return None  # bare Callable: nothing to check against
    ret = args[1]
    if ret is None:
        return "None"  # Callable[..., None]: a constructed instance is never None
    ret = _resolve_type(ret)
    if not isinstance(ret, type) or ret is type(None):
        return None  # TypeVar / special form: trust the user
    if _issubclass_safe(cls, ret):
        return None  # valid factory
    return ret.__qualname__


def _acceptable_kwarg_names(params: Mapping[str, inspect.Parameter]) -> set[str] | None:
    """Return the names *params* can be filled by keyword, or None when anything goes.

    None means "unanswerable": a ``**kwargs`` parameter accepts every name, so no name
    can be called invalid.
    """
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return None
    return {p.name for p in _fillable_params(params)}


def _coerce_kwargs(  # noqa: PLR0913  # kind and subject only word the refusal
    sig_obj: Any,
    hints_obj: Any,
    kwargs: dict,
    ctx: _SpecContext,
    *,
    kind: str,
    subject: str,
) -> dict:
    """Validate and typed-construct kwargs against a callable's signature.

    Shared by 'call', 'class' (factory), and 'bind' kwargs: unknown keys raise, and
    each value is built through *ctx*, one key below its path.

    ``sig_obj`` and ``hints_obj`` are passed separately because for a class they
    differ: ``inspect.signature(cls)`` yields the constructor params (self excluded),
    but the annotations live on ``cls.__init__``.

    Dev Notes:
        docs-dev/architecture/callables.md#one-coercion-route
    """
    try:
        sig = inspect.signature(sig_obj)
    except (ValueError, TypeError):
        return dict(kwargs)  # uninspectable (C extension etc.)

    try:
        hints = get_type_hints(hints_obj)
    except (NameError, AttributeError, TypeError):
        hints = {}

    valid = _acceptable_kwarg_names(sig.parameters)
    if valid is not None:
        invalid = sorted(set(kwargs) - valid)
        if invalid:
            msg = f"Unknown {kind} {invalid} for {subject} at '{ctx.where}'. Valid parameters: {sorted(valid)}."
            raise TypeCoercionError(msg)

    coerced: dict = {}
    for k, v in kwargs.items():
        ann = hints.get(k, inspect.Parameter.empty)
        if ann is inspect.Parameter.empty:
            coerced[k] = v
        else:
            coerced[k] = ctx.at(k).construct(_resolve_type(ann), v)
    return coerced


def _resolve_call_kwargs(func: Any, kwargs: dict, ctx: _SpecContext) -> dict:
    """Coerce and validate kwargs against func's signature using typed construction."""
    subject = repr(getattr(func, "__qualname__", repr(func)))
    return _coerce_kwargs(func, _hints_source(func), kwargs, ctx, kind="kwargs", subject=subject)


def _call_factory(target: Any, call_kwargs: dict, ctx: _SpecContext) -> Any:
    """Call the target a ``call:`` spec at *ctx* names with ``call_kwargs`` and return its value, unchecked.

    The target resolves as a ``bind:`` target does (:func:`_resolve_target`), with no
    Callable to check a class against: calling a class builds the instance. The arguments
    are built below ``args``, where the spec holds them.
    """
    func = _resolve_target(target, None, ctx, _defaults.CALL_KEY)
    coerced = _resolve_call_kwargs(func, call_kwargs, ctx.at(_defaults.ARGS_KEY))
    try:
        return func(**coerced)
    except Exception as e:
        msg = f"Failed to call {target!r} at '{ctx.where}': {e}"
        raise TypeCoercionError(msg) from e


def _resolve_call_spec(target: Any, call_kwargs: dict, ctx: _SpecContext) -> Any:
    """Resolve a 'call:' spec: call its target with call_kwargs, and use the return value as the callable.

    The result keeps no trace of the spec: it dumps as what it is, never as the call.

    Dev Notes:
        docs-dev/architecture/design-decisions/the-object-dump-writes-state.md#the-object-dump-writes-state
    """
    result = _call_factory(target, call_kwargs, ctx)
    if not callable(result):
        msg = (
            f"'call:' at '{ctx.where}': {target!r}(**{call_kwargs!r}) returned {type(result).__name__!r},"
            " which is not callable."
        )
        raise TypeCoercionError(msg)
    return result


_OPENERS = (_defaults.BIND_KEY, _defaults.CLASS_KEY, _defaults.CALL_KEY, _defaults.CLASSFN_KEY)
#: The openers that build an object: every other key of their spec is one of its fields.
_OBJECT_OPENERS = (_defaults.CLASS_KEY, _defaults.CLASSFN_KEY)
#: The openers that compute over a target: its arguments are the mapping under ``args``.
_COMPUTATION_OPENERS = (_defaults.BIND_KEY, _defaults.CALL_KEY)


def names_an_opener(name: str) -> bool:
    """Return whether *name* is an opener key: ``bind``, ``class``, ``call`` or ``classfn``.

    An opener names the target; every other key refines it. A flag addressing one is
    therefore a replacement for a spec already in hand, not a refinement of it.
    """
    return name in _OPENERS


def opens_a_subtree(name: str) -> bool:
    """Return whether the key *name* of a computation's spec holds a subtree rather than a value.

    A ``bind`` or ``call`` target is a dotted path or a callable spec of its own, and
    ``args`` holds the target's arguments by name, so a path reaches below all three.

    Dev Notes:
        docs-dev/architecture/callables.md#spec-grammar
    """
    return name in (*_COMPUTATION_OPENERS, _defaults.ARGS_KEY)


def promote_bare_spec(spec: str) -> dict[str, Any]:
    """Return the dict spec that the bare-string shorthand *spec* is the shorthand for.

    ``"pkg.func"`` and ``{bind: "pkg.func"}`` are two spellings of one spec and resolve to
    the same object, so a bare string that a deeper key refines is opened into its dict
    form rather than discarded.

    Dev Notes:
        docs-dev/architecture/callables.md#spec-grammar
    """
    return {_defaults.BIND_KEY: spec}


def _refuse_openers(present: list[str], where: str) -> NoReturn:
    """Refuse a spec holding *present*, which is not exactly one opener."""
    if present:
        msg = f"Callable dict at '{where}' must not specify more than one of {list(_OPENERS)} (got: {present})"
    else:
        *head, last = (repr(o) for o in _OPENERS)
        msg = f"Callable dict at '{where}' must specify one of {', '.join(head)} or {last}"
    raise TypeCoercionError(msg)


def _spec_parts(spec: dict, where: str) -> tuple[str, dict]:
    """Return the one opener of *spec* and the arguments of what it builds.

    ``class`` and ``classfn`` build an object, so every other key is one of its fields, a
    field named like another opener included. ``bind`` and ``call`` compute over a target
    (:func:`_computation_parts`).

    Raises:
        TypeCoercionError: on two openers of one kind, on none, and as
            :func:`_computation_parts` does.

    Dev Notes:
        docs-dev/architecture/callables.md#spec-grammar
    """
    present = _competing_openers(spec)
    if len(present) != 1:
        _refuse_openers(present, where)
    opener = present[0]
    if opener in _OBJECT_OPENERS:
        return opener, {k: v for k, v in spec.items() if k != opener}
    return _computation_parts(spec, where)


def _competing_openers(spec: dict) -> list[str]:
    """Return the openers *spec* holds that compete to open it: its object openers, else its computation ones.

    An object opener takes every other key as a field, so beside one, a ``bind`` or ``call``
    word is a field and competes for nothing.
    """
    objects = [k for k in _OBJECT_OPENERS if k in spec]
    return objects or [k for k in _COMPUTATION_OPENERS if k in spec]


def holds_an_opener(data: dict) -> bool:
    """Return whether the dict *data* holds an opener key, so that an ``Any`` node reads it as a spec.

    Dev Notes:
        docs-dev/architecture/callables.md#an-any-node-reads-every-opener
    """
    return any(k in data for k in _OPENERS)


def spec_opener(spec: dict) -> str | None:
    """Return the opener construction reads *spec* by (:func:`_spec_parts`), None when it holds no single one."""
    present = _competing_openers(spec)
    return present[0] if len(present) == 1 else None


def _computation_parts(spec: dict, where: str) -> tuple[str, dict]:
    """Return the ``bind`` or ``call`` opener of *spec* and the target's arguments, the mapping under ``args``.

    Raises:
        TypeCoercionError: on both openers or neither, on a key beside them other than
            ``args``, and on an ``args`` that is no mapping.

    Dev Notes:
        docs-dev/architecture/callables.md#spec-grammar
    """
    present = [k for k in _COMPUTATION_OPENERS if k in spec]
    if len(present) != 1:
        _refuse_openers(present, where)
    opener = present[0]
    stray = sorted(str(k) for k in spec if k not in (opener, _defaults.ARGS_KEY))
    if stray:
        msg = (
            f"Callable dict at '{where}' holds {stray} beside {opener!r}: the target's arguments"
            f" go under 'args', {{{opener}: <target>, args: {{<name>: <value>}}}}."
        )
        raise TypeCoercionError(msg)
    args = spec.get(_defaults.ARGS_KEY, {})
    if not isinstance(args, dict):
        msg = f"'args' at '{where}' takes the target's arguments by name, got {_src_type(args)}."
        raise TypeCoercionError(msg)
    return opener, args


def _resolve_dict_spec(spec: dict, tp: Any, ctx: _SpecContext) -> Any:
    """Resolve a dict callable spec: one opener (bind/class/call/classfn) and the arguments of what it builds.

    The arguments are the mapping under ``args`` for ``bind`` and ``call``, and the other
    keys for ``class`` and for ``classfn``, whose owner they build (:func:`_spec_parts`).
    *tp* is the Callable annotation, which a ``bind:`` target that is a class is checked
    against.
    """
    opener, args = _spec_parts(spec, ctx.where)
    if opener == _defaults.CALL_KEY:
        return _resolve_call_spec(spec[opener], args, ctx)
    if opener == _defaults.BIND_KEY:
        return _resolve_bind_spec(spec[opener], args, tp, ctx)
    if opener == _defaults.CLASSFN_KEY:
        return _resolve_classfn_spec(spec[opener], args, ctx)
    return _resolve_class_spec(_ClassSpec(spec[opener], args), ctx)


def _accepts(tp: Any, value: Any) -> bool:
    """True if ``value`` already is a ``tp``, so it needs no construction to be one.

    A plain class or a parametrized one (by its origin) is an ``isinstance`` test; a union
    accepts what any of its members accepts. Anything else answers no, and the caller
    constructs the value, which is what coerces or refuses it.
    """
    if tp is Any:
        return True
    if _is_union(tp):
        return any(_accepts(_resolve_type(arg), value) for arg in get_args(tp))
    base = get_origin(tp) or tp
    return isinstance(base, type) and isinstance(value, base)


def resolve_typed_call(spec: dict, tp: Any, path: FieldPath, union_tag: str, construct_fn: Any) -> Any:
    """Build a non-Callable value from a ``call:`` spec: call the function and take its value as the field's.

    The mapping under ``args`` holds the function's arguments. A value the annotation already
    accepts is returned as it is; any other is built as ``tp`` from the raw value, so a wrong
    type fails the way a wrong literal does. A ``bind`` beside ``call`` is a second opener,
    and any other key beside it is refused, as in a Callable spec (:func:`_computation_parts`).

    Dev Notes:
        docs-dev/architecture/callables.md#call-in-a-typed-field
    """
    ctx = _SpecContext(path, union_tag, construct_fn)
    _opener, kwargs = _computation_parts(spec, ctx.where)
    value = _call_factory(spec[_defaults.CALL_KEY], kwargs, ctx)
    if _accepts(tp, value):
        return value
    return ctx.construct(tp, value)


def resolve_held_spec(spec: dict, path: FieldPath, union_tag: str, construct_fn: Any) -> Any:
    """Build what a spec an ``Any`` node holds yields: an instance, a bound method, a partial or a value.

    Every opener is read, as on a Callable field (:func:`_spec_parts`), with no Callable to
    check the result against: ``class:`` builds any class, callable or not, and ``call:``
    takes its target's value as it is.

    Dev Notes:
        docs-dev/architecture/callables.md#an-any-node-reads-every-opener
    """
    ctx = _SpecContext(path, union_tag, construct_fn)
    opener, args = _spec_parts(spec, ctx.where)
    if opener == _defaults.CALL_KEY:
        return _call_factory(spec[opener], args, ctx)
    if opener == _defaults.CLASS_KEY:
        return _instantiate_class_spec(_ClassSpec(spec[opener], args), ctx)
    return _resolve_dict_spec(spec, None, ctx)


def _hints_source(callable_obj: Any) -> Any:
    """Return the object whose type hints describe callable_obj's parameters.

    ``inspect.signature`` already yields the user-facing params for every callable
    shape (function, bound method, class, callable instance), but ``get_type_hints``
    needs the object that actually carries the parameter annotations: ``__init__``
    for a class, ``__call__`` for a callable instance, the object itself otherwise.
    """
    if inspect.isclass(callable_obj):
        return callable_obj.__init__
    if inspect.isfunction(callable_obj) or inspect.ismethod(callable_obj):
        return callable_obj
    call = getattr(type(callable_obj), "__call__", None)  # noqa: B004  # want __call__ object for hints, not a bool
    return call if call is not None else callable_obj


def _resolve_bind_kwargs(callable_obj: Any, bind: dict, ctx: _SpecContext) -> dict:
    """Validate and typed-construct a ``bind:`` spec's arguments against callable_obj's signature.

    Values go through :func:`_coerce_kwargs`, so bound arguments get full typed
    construction (enums, dataclasses, lists, unions) and bad values raise.
    """
    subject = getattr(callable_obj, "__qualname__", None) or getattr(
        type(callable_obj),
        "__qualname__",
        repr(callable_obj),
    )
    return _coerce_kwargs(
        callable_obj,
        _hints_source(callable_obj),
        bind,
        ctx,
        kind="bind parameter(s)",
        subject=subject,
    )


def _resolve_bind_spec(target: Any, kwargs: dict, tp: Any, ctx: _SpecContext) -> Any:
    """Resolve a ``bind:`` spec: ``functools.partial(target, **kwargs)``.

    *target* is what the ``bind`` key holds, resolved by :func:`_resolve_target`. The
    *kwargs*, the mapping under ``args``, are built below it against the target's
    signature. With no argument the target is the result, so ``{bind: T}`` and the bare
    ``"T"`` are one spec.

    Dev Notes:
        docs-dev/architecture/callables.md#spec-grammar
    """
    obj = _resolve_target(target, tp, ctx, _defaults.BIND_KEY)
    if not kwargs:
        return _as_callable(obj)
    return functools.partial(obj, **_resolve_bind_kwargs(obj, kwargs, ctx.at(_defaults.ARGS_KEY)))


def _resolve_classfn_spec(method_path: Any, init_kwargs: dict, ctx: _SpecContext) -> Any:
    """Resolve a ``classfn:`` spec: build the method's owner from *init_kwargs*, and return the bound method.

    *method_path* must name an instance method (:func:`_instance_method_owner`). The
    other keys are the owner's fields, built as a ``class:`` spec's are; the method's own
    arguments sit under the ``args`` of a ``bind:`` or ``call:`` whose target this spec
    is. The bound method dumps back from the fields its owner holds (:func:`_serialize_callable`).

    Dev Notes:
        docs-dev/architecture/callables.md#classfn-builds-the-owner
    """
    opener = _defaults.CLASSFN_KEY
    if not isinstance(method_path, str):
        msg = f"{opener!r} at '{ctx.where}' takes the dotted path of an instance method, got {_src_type(method_path)}."
        raise TypeCoercionError(msg)
    _import_dotted(method_path)
    owner = _instance_method_owner(method_path)
    if owner is None:
        msg = (
            f"{opener!r} at '{ctx.where}' names an instance method, and {method_path!r} is not one:"
            " a function, a class, a static or a class method needs no owner to be built."
            f" Name it with 'bind: {method_path}', its own arguments under 'args'."
        )
        raise TypeCoercionError(msg)
    instance = ctx.instantiate(owner, init_kwargs, method_path.rpartition(".")[0], opener)
    return getattr(instance, method_path.rpartition(".")[2])


@dataclass
class _ClassSpec:
    """Parsed 'class:' section of a callable dict spec."""

    cls_path: str
    init_kwargs: dict


def _instantiate_class_spec(spec: _ClassSpec, ctx: _SpecContext) -> Any:
    """Build the instance a 'class:' spec names, from the other keys as its constructor arguments.

    Raises:
        TypeCoercionError: If the path names no class.
    """
    cls = _import_dotted(spec.cls_path)
    if not isinstance(cls, type):
        msg = f"'class' key at '{ctx.where}' must reference a class, got {type(cls).__name__} {spec.cls_path!r}"
        raise TypeCoercionError(msg)
    return ctx.instantiate(cls, spec.init_kwargs, spec.cls_path, _defaults.CLASS_KEY)


def _resolve_class_spec(spec: _ClassSpec, ctx: _SpecContext) -> Any:
    """Resolve a 'class:' callable spec: instantiate the class; the instance is the callable.

    ``init_kwargs`` (the other keys) are the constructor arguments; the instance must be
    callable (define ``__call__``). A partial over the instance is a ``bind:`` spec whose
    target is this one. The instance dumps back from the fields it holds (:func:`_serialize_callable`).

    To use a class as a *factory* (calling it constructs an instance), give its bare
    fully-qualified name, or ``bind: <class>`` with pre-applied constructor args under ``args``.
    """
    instance = _instantiate_class_spec(spec, ctx)
    if not callable(instance):
        msg = (
            f"Instance of {spec.cls_path!r} at '{ctx.where}' is not callable: the class must define"
            f" __call__ to be used as a Callable via 'class:'. To use {spec.cls_path} as a"
            f" factory (calling it constructs an instance), give its bare name"
            f" '{spec.cls_path}', or 'bind: {spec.cls_path}' with its constructor args under 'args'."
        )
        raise TypeCoercionError(msg)
    return instance


def _check_callable_signature(obj: Any, tp: Any, path: str) -> None:
    """Validate obj's signature against the Callable[[T1, T2], R] annotation.

    Checks that the number of required positional/keyword parameters (after
    accounting for already-bound args in a functools.partial) matches the
    declared parameter count. Skips check for bare Callable, Callable[..., R],
    and callables with uninspectable signatures (builtins, C extensions).
    """
    if not _is_callable(tp):
        return
    param_types = _callable_param_types(tp)
    if param_types is None:
        return

    try:
        sig = inspect.signature(obj)
    except (ValueError, TypeError):
        return

    has_var_positional = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in sig.parameters.values())
    if has_var_positional:
        return

    required = _fillable_params(sig.parameters, required=True)
    if len(required) != len(param_types):
        type_names = [getattr(_resolve_type(t), "__name__", repr(t)) for t in param_types]
        msg = (
            f"Callable at '{path}': annotation expects {len(param_types)} parameter(s)"
            f" {type_names}, but {obj!r} has {len(required)} required"
            f" parameter(s) {[p.name for p in required]}"
        )
        raise TypeCoercionError(msg)


def _serialize_callable(value: Any, owner_fields: Callable[[Any], dict[str, Any]]) -> str | dict:
    """Serialize a callable value back to its config representation.

    Partial with pre-bound kwargs → {bind: <its target, serialized>, args: {k: v}}.
    Bare partial (a class used factory-like, no kwargs) → "module.qualname" string.
    Plain callable → "module.qualname" string, when that path reads back as it
    (:func:`_reads_back_from`); a closure, a lambda or a shadowed name is refused.
    Instance method → that path, beside its owner's fields when the owner has any
    (:func:`_bound_method_spec`).
    Callable instance → a ``class:`` spec beside the fields it holds (:func:`_object_spec`).
    *owner_fields* reads the fields off an owner or an instance.

    Dev Notes:
        docs-dev/architecture/callables.md#round-trip
    """
    if isinstance(value, functools.partial):
        target = _serialize_callable(value.func, owner_fields)
        if value.keywords:
            return {_defaults.BIND_KEY: target, _defaults.ARGS_KEY: dict(value.keywords)}
        return target

    if not getattr(value, "__qualname__", None):
        return _instance_spec(value, owner_fields)

    if getattr(value, "__module__", None):
        path = dotted_name(value)
        if _reads_back_from(path, value):
            if _instance_method_owner(path) is None:
                return path
            return _bound_method_spec(path, value, owner_fields)
        reason = (
            f"{path!r} does not read back as this callable, as for a closure, a lambda, or a function"
            " its module no longer holds under that name"
        )
        raise ConfargError.callable_not_spelled(value, reason)

    raise ConfargError.callable_not_spelled(value, "it has no dotted path")


def _instance_spec(instance: Any, owner_fields: Callable[[Any], dict[str, Any]]) -> dict:
    """Return the ``class:`` spec that builds a callable instance with the state it holds.

    Raises:
        ConfargError: If the instance's class does not import back from its dotted path, or if
            :func:`_object_spec` refuses it.

    Dev Notes:
        docs-dev/architecture/callables.md#an-object-dumps-the-state-it-holds
    """
    cls = type(instance)
    path_str = dotted_name(cls)
    if not imports_back(path_str, cls):
        reason = (
            f"it has no dotted path of its own, and {path_str!r}, the path of its class, does not import back"
            " as that class, as for a class defined in a function"
        )
        raise ConfargError.callable_not_spelled(instance, reason)
    return _object_spec(_defaults.CLASS_KEY, path_str, instance, instance, owner_fields)


def _bound_method_spec(path_str: str, method: Any, owner_fields: Callable[[Any], dict[str, Any]]) -> str | dict:
    """Return the spec that builds the owner *method* is bound to with the state it holds, and binds *method* to it.

    *path_str* names *method* as an instance method, and reads back bound to an owner built
    with no arguments. An owner whose constructor takes none holds nothing that one lacks, so
    the path is the spec. Any other owner dumps as a ``classfn:`` spec beside its fields
    (:func:`_object_spec`).

    Dev Notes:
        docs-dev/architecture/callables.md#an-object-dumps-the-state-it-holds
    """
    spec = _object_spec(_defaults.CLASSFN_KEY, path_str, method.__self__, method, owner_fields)
    return path_str if spec.keys() == {_defaults.CLASSFN_KEY} else spec


def _object_spec(
    opener: str, path_str: str, obj: Any, value: Any, owner_fields: Callable[[Any], dict[str, Any]]
) -> dict:
    """Return the *opener* spec naming *path_str* that builds *obj* with the state it holds.

    *obj* is a ``class:`` instance or a ``classfn:`` owner, and *value* the callable being
    dumped, which messages name. An object whose constructor takes no argument holds nothing a
    no-argument build lacks, so the opener stands alone. Any other is a struct, read through
    *owner_fields* as a struct field is.

    Raises:
        ConfargError: If the constructor takes arguments and the class is no struct, or if the
            object has a field named like the ``classfn`` opener, which no object spec can hold
            beside its own.

    Dev Notes:
        docs-dev/architecture/callables.md#an-object-dumps-the-state-it-holds
    """
    cls = type(obj)
    whose = "its" if obj is value else "its owner's"
    try:
        takes_arguments = bool(inspect.signature(cls).parameters)
    except (ValueError, TypeError):
        takes_arguments = True
    if not takes_arguments:
        return {opener: path_str}
    if not _is_struct(cls):
        reason = (
            f"{whose} class, {cls.__qualname__}, takes constructor arguments, and has no fields a"
            f" '{opener}:' spec could set"
        )
        raise ConfargError.callable_not_spelled(value, reason)
    fields = owner_fields(obj)
    if _defaults.CLASSFN_KEY in fields:
        reason = (
            f"{whose} class, {cls.__qualname__}, has a field named {_defaults.CLASSFN_KEY!r},"
            f" which a '{opener}:' spec cannot hold beside its opener"
        )
        raise ConfargError.callable_not_spelled(value, reason)
    return {opener: path_str, **fields}
