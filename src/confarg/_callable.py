# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Callable resolution and serialization.

Dev Notes:
    docs-dev/architecture/callables.md
"""

from __future__ import annotations

import contextlib
import functools
import inspect
import types
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, cast, get_args, get_origin, get_type_hints

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

from confarg._import import _import_dotted, dotted_name
from confarg._types import (
    _callable_param_types,
    _is_callable,
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

    def instantiate(self, cls: type, kwargs: dict) -> Any:
        """Build exactly *cls* from *kwargs* at this context's path, whatever subclasses it has.

        Dev Notes:
            docs-dev/architecture/design-decisions/class-names-the-type-it-builds.md#class-names-the-type-it-builds
        """
        from confarg.typedload._construct import construct_named_class  # noqa: PLC0415  # import cycle

        return construct_named_class(cls, kwargs, path=self.path, union_tag=self.union_tag)


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
            "Under 'bind:' or 'call:', that spec is the target, and the keys beside it are the"
            " method's own arguments."
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
        of its own), with the sibling kwargs partially applied: functools.partial(target,
        **siblings). With no sibling, the target itself, so '{bind: T}' and 'T' are one spec.

    Dict with 'class' key:
      - Instantiate the class with the sibling kwargs; the instance is the callable
        (it must define __call__).

    Dict with 'call' key:
      - Call the target (a dotted path, or a callable spec of its own) with the sibling
        kwargs; its return value is the callable.

    Dict with 'classfn' key:
      - Build the owner of the instance method it names from the sibling kwargs; the
        bound method is the callable.

    Escaped mode (collision escape):
      - Each opener also has a single-underscore form ('_bind', '_class', '_call',
        '_classfn'). Using an escaped opener switches the whole spec to escaped mode, where
        every plain word — including 'bind', 'class', 'call', 'classfn' — is an ordinary
        kwarg of the target.
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
        f" The target's arguments are the spec's other keys: {{{opener}: <target>, <arg>: <value>}}."
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
    can be called invalid. The one canonical answer, shared by kwarg validation
    (:func:`_coerce_kwargs`) and the mixed-form check (:func:`_reject_mixed_form_kwargs`).
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
            msg = (
                f"Unknown {kind} {invalid} for {subject} at '{ctx.where}'."
                f" Valid parameters: {sorted(valid)}.{_mixed_form_hint(invalid)}"
            )
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


def _call_factory(target: Any, call_kwargs: dict, ctx: _SpecContext, opener: str) -> Any:
    """Call the target a ``call:`` *opener* names with ``call_kwargs`` and return its value, unchecked.

    The target resolves as a ``bind:`` target does (:func:`_resolve_target`), with no
    Callable to check a class against: calling a class builds the instance.
    """
    func = _resolve_target(target, None, ctx, opener)
    coerced = _resolve_call_kwargs(func, call_kwargs, ctx)
    try:
        return func(**coerced)
    except Exception as e:
        msg = f"Failed to call {target!r} at '{ctx.where}': {e}"
        raise TypeCoercionError(msg) from e


def _resolve_call_spec(target: Any, call_kwargs: dict, original_spec: dict, ctx: _SpecContext, opener: str) -> Any:
    """Resolve a 'call:' spec: call its target with call_kwargs, and use the return value as the callable."""
    result = _call_factory(target, call_kwargs, ctx, opener)
    if not callable(result):
        msg = (
            f"'call:' at '{ctx.where}': {target!r}(**{call_kwargs!r}) returned {type(result).__name__!r},"
            " which is not callable."
        )
        raise TypeCoercionError(msg)
    with contextlib.suppress(AttributeError, TypeError):
        result.__confarg_spec__ = original_spec
    return result


@dataclass(frozen=True)
class _Directives:
    """The directive key names active for a spec, in either plain or escaped mode.

    A callable dict names its target with exactly one *opener*: ``bind`` (a partial of
    the target), ``class`` (an instance), ``call`` (a return value) or ``classfn`` (an
    instance method, bound to an owner built from the other keys). Every other key is an
    argument of the target. The escaped mode uses the single-underscore forms
    (``_bind``/``_class``/``_call``/``_classfn``) and treats every plain word as an
    ordinary kwarg. The opener's form selects the mode for the whole spec.

    Dev Notes:
        docs-dev/architecture/callables.md#plain-and-escaped-directives
    """

    bind: str
    cls: str
    call: str
    classfn: str

    @property
    def openers(self) -> tuple[str, str, str, str]:
        return (self.bind, self.cls, self.call, self.classfn)

    @property
    def reserved(self) -> frozenset[str]:
        return frozenset(self.openers)

    @property
    def by_mode(self) -> dict[str, str]:
        """Return each opener's name in this form, keyed by its plain spelling (the mode)."""
        return dict(zip(_PLAIN_DIRECTIVES.openers, self.openers, strict=True))


_PLAIN_DIRECTIVES = _Directives(bind="bind", cls="class", call="call", classfn="classfn")
_ESCAPED_DIRECTIVES = _Directives(bind="_bind", cls="_class", call="_call", classfn="_classfn")


def active_directives(has_key: Callable[[str], bool]) -> _Directives:
    """Pick the active directive names by the opener's form, via a key-presence predicate.

    ``has_key(name)`` answers "is this directive key present?" — a spec dict passes
    ``spec.__contains__``; the CLI passes a probe over its flat ``{flag}.{name}``
    namespace. Use this everywhere plain-vs-escaped must be decided.

    Escaped mode is selected when an escaped opener (``_bind``/``_class``/``_call``/
    ``_classfn``) is present; otherwise plain mode. A directive word in the *other* form is ordinary
    data: beside an escaped opener, a plain ``bind`` is a kwarg.

    Dev Notes:
        docs-dev/architecture/callables.md#plain-and-escaped-directives
    """
    if any(has_key(opener) for opener in _ESCAPED_DIRECTIVES.openers):
        return _ESCAPED_DIRECTIVES
    return _PLAIN_DIRECTIVES


def names_an_opener(name: str) -> bool:
    """Return whether *name* is an opener key, in either the plain or the escaped form.

    An opener names the target; every other key refines it. A flag addressing one is
    therefore a replacement for a spec already in hand, not a refinement of it.
    """
    return name in _PLAIN_DIRECTIVES.openers or name in _ESCAPED_DIRECTIVES.openers


def names_a_call(name: str) -> bool:
    """Return whether *name* is the call key, in either the plain or the escaped form."""
    return name in (_PLAIN_DIRECTIVES.call, _ESCAPED_DIRECTIVES.call)


def names_a_target_opener(name: str) -> bool:
    """Return whether *name* is an opener whose value is a target, ``bind`` or ``call``, in either form.

    Such a value is a dotted path or a callable spec of its own (:func:`_resolve_target`).
    Both forms answer yes wherever a *path* is judged rather than a spec: a path does
    not see the opener, and which form is the directive and which is ordinary data is
    the opener's to decide, at construction.

    Dev Notes:
        docs-dev/architecture/callables.md#plain-and-escaped-directives
    """
    return names_a_call(name) or name in (_PLAIN_DIRECTIVES.bind, _ESCAPED_DIRECTIVES.bind)


def _mixed_form_hint(names: Iterable[str]) -> str:
    """Explain rejected kwargs that are plain opener words beside an escaped opener.

    Every directive is an opener, and any escaped opener selects the escaped mode
    (:func:`active_directives`), so only a *plain* word can be left as ordinary data: an
    escaped word always selects its own mode. The rejection is correct either way; the hint
    says why the word ended up a kwarg, which is what the likely typo needs to hear. Returns
    ``""`` when no name is a plain opener.

    Dev Notes:
        docs-dev/architecture/callables.md#plain-and-escaped-directives
    """
    return "".join(
        f" {name!r} is the plain spelling of the {escaped!r} opener, but this spec's opener is"
        f" escaped, so {name!r} is ordinary data here. A spec has one opener, and its form"
        f" selects how every other key reads."
        for name, escaped in zip(_PLAIN_DIRECTIVES.openers, _ESCAPED_DIRECTIVES.openers, strict=True)
        if name in set(names)
    )


def _reject_mixed_form_kwargs(target: Any, kwargs: dict, path: str) -> None:
    """Raise if a kwarg is a directive word in the inactive form that *target* cannot accept.

    The constructor rejects it anyway, through the shared struct construction that knows
    nothing of directives; catching it here is what lets the message name the mixed form.
    A name the target *does* accept is left alone — reaching a parameter that collides
    with a directive word is exactly what the escaped form exists for.
    """
    stray = set(kwargs) & _PLAIN_DIRECTIVES.reserved
    if not stray:
        return
    try:
        sig = inspect.signature(target)
    except (ValueError, TypeError):
        return  # uninspectable (C extension etc.): construction has the last word
    valid = _acceptable_kwarg_names(sig.parameters)
    if valid is None:
        return
    invalid = sorted(stray - valid)
    if invalid:
        msg = f"Unknown constructor kwarg(s) {invalid} for the Callable spec at {path!r}.{_mixed_form_hint(invalid)}"
        raise TypeCoercionError(msg)


def promote_bare_spec(spec: str) -> dict[str, Any]:
    """Return the dict spec that the bare-string shorthand *spec* is the shorthand for.

    ``"pkg.func"`` and ``{bind: "pkg.func"}`` are two spellings of one spec and resolve to
    the same object, so a bare string that a sibling key refines is opened into its dict
    form rather than discarded. The bare string is itself a *plain* opener — it has no
    escaped spelling — so the plain directive names are the active ones, and an escaped
    key sitting beside it is ordinary data, exactly as it is beside a plain ``bind:``.

    Dev Notes:
        docs-dev/architecture/callables.md#spec-grammar
    """
    return {_PLAIN_DIRECTIVES.bind: spec}


def _select_directives(spec: dict) -> _Directives:
    """Pick the active directives for a spec dict (see :func:`active_directives`)."""
    return active_directives(spec.__contains__)


def _single_opener(spec: dict, d: _Directives, where: str) -> str:
    """Return the one opener *spec* holds in the form *d* names, raising unless there is exactly one."""
    present = [k for k in d.openers if k in spec]
    if len(present) > 1:
        msg = f"Callable dict at '{where}' must not specify more than one of {list(d.openers)} (got: {present})"
        raise TypeCoercionError(msg)
    if not present:
        *head, last = (repr(o) for o in _PLAIN_DIRECTIVES.openers)
        msg = f"Callable dict at '{where}' must specify one of {', '.join(head)} or {last} (or their _-prefixed forms)"
        raise TypeCoercionError(msg)
    return present[0]


def _resolve_dict_spec(spec: dict, tp: Any, ctx: _SpecContext) -> Any:
    """Resolve a dict callable spec: one opener (bind/class/call/classfn) and its sibling keys.

    The siblings are the arguments of the target the opener names, and under ``classfn``
    those of the method's owner. Directive keys come in a plain and a
    single-underscore-escaped form; the opener selects which (see
    :func:`_select_directives`). *tp* is the Callable annotation, which a ``bind:`` target
    that is a class is checked against.
    """
    d = _select_directives(spec)
    opener = _single_opener(spec, d, ctx.where)
    kwargs = {k: v for k, v in spec.items() if k not in d.reserved}
    if opener == d.call:
        return _resolve_call_spec(spec[d.call], kwargs, spec, ctx, d.call)
    if opener == d.bind:
        return _resolve_bind_spec(spec[d.bind], kwargs, tp, ctx, d.bind)
    if opener == d.classfn:
        return _resolve_classfn_spec(spec[d.classfn], kwargs, spec, ctx, d.classfn)
    return _resolve_class_spec(_ClassSpec(spec[d.cls], kwargs, spec), ctx)


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

    The sibling keys are the function's arguments. A value the annotation already accepts is
    returned as it is; any other is built as ``tp`` from the raw value, so a wrong type fails the
    way a wrong literal does. A second opener beside ``call`` is refused, as in a Callable spec.

    Dev Notes:
        docs-dev/architecture/callables.md#call-in-a-typed-field
    """
    ctx = _SpecContext(path, union_tag, construct_fn)
    d = _select_directives(spec)
    _single_opener(spec, d, ctx.where)
    kwargs = {k: v for k, v in spec.items() if k not in d.reserved}
    value = _call_factory(spec[d.call], kwargs, ctx, d.call)
    if _accepts(tp, value):
        return value
    return ctx.construct(tp, value)


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
    """Validate and typed-construct a ``bind:`` spec's sibling kwargs against callable_obj's signature.

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


def _resolve_bind_spec(target: Any, kwargs: dict, tp: Any, ctx: _SpecContext, opener: str) -> Any:
    """Resolve a ``bind:`` spec: ``functools.partial(target, **kwargs)``.

    *target* is what the *opener* key holds, resolved by :func:`_resolve_target`. The
    sibling *kwargs* are built at *ctx*, the spec's own path, against the target's
    signature. With no sibling the target is the result, so ``{bind: T}`` and the bare
    ``"T"`` are one spec.

    Dev Notes:
        docs-dev/architecture/callables.md#spec-grammar
    """
    obj = _resolve_target(target, tp, ctx, opener)
    if not kwargs:
        return _as_callable(obj)
    return functools.partial(obj, **_resolve_bind_kwargs(obj, kwargs, ctx))


def _resolve_classfn_spec(method_path: Any, init_kwargs: dict, original: dict, ctx: _SpecContext, opener: str) -> Any:
    """Resolve a ``classfn:`` spec: build the method's owner from *init_kwargs*, and return the bound method.

    *method_path* must name an instance method (:func:`_instance_method_owner`). The
    sibling keys are the owner's constructor arguments, built as a ``class:`` spec's are;
    the method's own arguments sit beside a ``bind:`` or ``call:`` whose target this spec
    is. The owner is stamped with *original*, which is how the bound method dumps back.

    Dev Notes:
        docs-dev/architecture/callables.md#classfn-builds-the-owner
    """
    if not isinstance(method_path, str):
        msg = f"{opener!r} at '{ctx.where}' takes the dotted path of an instance method, got {_src_type(method_path)}."
        raise TypeCoercionError(msg)
    _import_dotted(method_path)
    owner = _instance_method_owner(method_path)
    if owner is None:
        msg = (
            f"{opener!r} at '{ctx.where}' names an instance method, and {method_path!r} is not one:"
            " a function, a class, a static or a class method needs no owner to be built."
            f" Name it with 'bind: {method_path}', its other keys its own arguments."
        )
        raise TypeCoercionError(msg)
    _reject_mixed_form_kwargs(owner, init_kwargs, ctx.where)
    instance = ctx.instantiate(owner, init_kwargs)
    with contextlib.suppress(AttributeError, TypeError):
        instance.__confarg_spec__ = original
    return getattr(instance, method_path.rpartition(".")[2])


@dataclass
class _ClassSpec:
    """Parsed 'class:' section of a callable dict spec."""

    cls_path: str
    init_kwargs: dict
    original: dict


def _resolve_class_spec(spec: _ClassSpec, ctx: _SpecContext) -> Any:
    """Resolve a 'class:' callable spec: instantiate the class; the instance is the callable.

    ``init_kwargs`` (sibling keys) are the constructor arguments; the instance must be
    callable (define ``__call__``). A partial over the instance is a ``bind:`` spec whose
    target is this one.

    To use a class as a *factory* (calling it constructs an instance), give its bare
    fully-qualified name, or ``bind: <class>`` with sibling keys for pre-applied constructor args.
    """
    cls = _import_dotted(spec.cls_path)
    if not isinstance(cls, type):
        msg = f"'class' key at '{ctx.where}' must reference a class, got {type(cls).__name__} {spec.cls_path!r}"
        raise TypeCoercionError(msg)

    _reject_mixed_form_kwargs(cls, spec.init_kwargs, ctx.where)
    instance = ctx.instantiate(cls, spec.init_kwargs)
    if not callable(instance):
        msg = (
            f"Instance of {spec.cls_path!r} at '{ctx.where}' is not callable: the class must define"
            f" __call__ to be used as a Callable via 'class:'. To use {spec.cls_path} as a"
            f" factory (calling it constructs an instance), give its bare name"
            f" '{spec.cls_path}', or 'bind: {spec.cls_path}' with its constructor args as sibling keys."
        )
        raise TypeCoercionError(msg)
    with contextlib.suppress(AttributeError, TypeError):
        cast("Any", instance).__confarg_spec__ = spec.original
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


def _serialize_callable(value: Any) -> str | dict:
    """Serialize a callable value back to its config representation.

    Class instance with __confarg_spec__ → stored spec dict (e.g. {class: ...}).
    Method bound to an owner a classfn: spec built → that spec, stamped on the owner.
    Partial with pre-bound kwargs → {bind: <its target, serialized>, k: v}, in the escaped
    form when a kwarg is spelled like a plain opener.
    Bare partial (a class used factory-like, no kwargs) → "module.qualname" string.
    Plain callable → "module.qualname" string.
    """
    spec = getattr(value, "__confarg_spec__", None)
    if spec is not None:
        return spec

    if inspect.ismethod(value):
        owner_spec = getattr(value.__self__, "__confarg_spec__", None)
        if isinstance(owner_spec, dict) and _select_directives(owner_spec).classfn in owner_spec:
            return owner_spec

    if isinstance(value, functools.partial):
        target = _serialize_callable(value.func)
        if value.keywords:
            d = _ESCAPED_DIRECTIVES if set(value.keywords) & _PLAIN_DIRECTIVES.reserved else _PLAIN_DIRECTIVES
            return {d.bind: target, **value.keywords}
        return target

    if getattr(value, "__module__", None) and getattr(value, "__qualname__", None):
        return dotted_name(value)

    msg = (
        f"Cannot serialize callable {value!r}: no __module__/__qualname__ available."
        " For class instances, ensure the instance was constructed via confarg"
        " (which stores the spec for round-trip serialization)."
    )
    raise ConfargError(msg)
