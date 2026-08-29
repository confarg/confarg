# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Callable resolution and serialization."""

from __future__ import annotations

import contextlib
import functools
import inspect
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast, get_args, get_type_hints

if TYPE_CHECKING:
    from collections.abc import Callable

from confarg._import import _import_dotted
from confarg._types import (
    _callable_param_types,
    _is_callable,
    _resolve_type,
)
from confarg.exceptions import ConfargError, TypeCoercionError


def _detect_owning_class(func: Any) -> type | None:
    """Return the class that owns func as an instance method, or None.

    Uses __qualname__ (e.g. 'MyClass.method') and __module__ to find the
    class. Returns None for module-level functions, lambdas, and nested
    scopes that cannot be resolved.
    """
    qualname = getattr(func, "__qualname__", "")
    if "." not in qualname or "<" in qualname:
        return None
    cls_qualname = qualname.rsplit(".", 1)[0]
    module = sys.modules.get(getattr(func, "__module__", ""))
    if module is None:
        return None
    cls: Any = module
    for part in cls_qualname.split("."):
        cls = getattr(cls, part, None)
        if cls is None:
            return None
    return cls if isinstance(cls, type) else None


def _maybe_bind_method(func: Any, path: str) -> Any:
    """If func is an unbound instance method, auto-instantiate its owning class (no args) and return the bound method.

    Returns func unchanged when it is not an instance method or the class
    requires constructor arguments.
    """
    if getattr(func, "__name__", None) == "__init__":
        return func
    cls = _detect_owning_class(func)
    if cls is None:
        return func
    try:
        instance = cls()
    except TypeError as e:
        fn_path = f"{func.__module__}.{func.__qualname__}"
        msg = (
            f"Cannot instantiate {cls.__qualname__!r} with no arguments at '{path}': {e}.\n"
            f"Use the dict form and supply {cls.__qualname__}'s constructor arguments as sibling keys:\n"
            f"{_format_fn_dict_example(fn_path, cls)}"
        )
        raise TypeCoercionError(msg) from e
    return getattr(instance, func.__name__)


def _format_fn_dict_example(fn_path: str, cls: type) -> str:
    """Return a YAML-like snippet showing the fn: dict form with required constructor kwargs."""
    try:
        sig = inspect.signature(cls.__init__)
    except (ValueError, TypeError):
        return f"  fn: {fn_path}\n  # (add constructor arguments here)"

    params = [
        (name, p)
        for name, p in sig.parameters.items()
        if name != "self"
        and p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        and p.default is inspect.Parameter.empty
    ]
    optional_params = [
        (name, p)
        for name, p in sig.parameters.items()
        if name != "self"
        and p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        and p.default is not inspect.Parameter.empty
    ]

    lines = [f"  fn: {fn_path}"]
    for name, p in params:
        ann = p.annotation
        type_hint = f"  # {ann.__name__}" if isinstance(ann, type) else ""
        lines.append(f"  {name}: <value>{type_hint}")
    for name, p in optional_params:
        ann = p.annotation
        type_hint = f"  # {ann.__name__}, optional" if isinstance(ann, type) else "  # optional"
        lines.append(f"  # {name}: {p.default!r}{type_hint}")
    return "\n".join(lines)


def _resolve_callable_spec(spec: Any, tp: Any, path: str, union_tag: str, construct_fn: Any) -> Any:
    """Resolve a Callable value from a raw spec (string or dict).

    Bare string:
      - If the import resolves to a class → the class itself is the callable
        (factory-like): return functools.partial(cls). Calling it constructs an
        instance. To use an *instance* as the callable, use the 'class:' dict form.
        When the Callable declares a concrete return type the class cannot produce,
        this raises and points at the 'class:' form.
      - Otherwise (function/method) → use as-is.

    Dict with 'fn' key:
      - The referenced function or method (or class, used factory-like) is the callable.
      - If it is an instance method, the owning class is auto-instantiated
        (with sibling kwargs as constructor args, or no args if none are given).
      - 'bind' → functools.partial applied to the resulting callable (e.g. 'fn: SomeClass'
        + 'bind: {lr: 0.1}' is a factory with pre-applied constructor args).

    Dict with 'class' key:
      - Instantiate the class with the sibling kwargs; the instance is the callable
        (it must define __call__). 'bind' → functools.partial applied to the instance.

    Dict with 'call' key:
      - Call the referenced factory function; its return value is the callable.

    Escaped mode (collision escape):
      - Each directive also has a single-underscore form ('_fn', '_class', '_call',
        '_bind'). Using an escaped *opener* ('_fn'/'_class'/'_call') switches the whole
        spec to escaped mode, where the underscore forms are the directives and every
        plain word — including 'bind', 'fn', 'call' — is an ordinary constructor kwarg.
        This lets a callable whose own parameter is named like a directive still be
        configured (e.g. '_class: H' with a plain 'bind:' init arg and '_bind:' to
        partial-apply __call__). Do not mix forms within one spec: the opener alone
        selects the mode, so a stray '_bind' under a plain opener is treated as data.
    """
    if isinstance(spec, str):
        result = _resolve_bare_string(str(spec), path, tp)
    elif isinstance(spec, dict):
        result = _resolve_dict_spec(spec, path, union_tag, construct_fn)
    elif callable(spec):
        result = spec
    else:
        msg = f"Cannot construct Callable at '{path}': expected str or dict, got {type(spec).__name__} {spec!r}"
        raise TypeCoercionError(msg)
    if not callable(result):
        msg = f"Callable at '{path}': {spec!r} resolved to {result!r}, which is not callable."
        raise TypeCoercionError(msg)
    _check_callable_signature(result, tp, path)
    return result


def _resolve_bare_string(path_str: str, path: str, callable_tp: Any = None) -> Any:
    """Resolve a bare import-path string to a callable.

    A class resolves to the class itself, used factory-like: return
    functools.partial(cls) with no pre-bound kwargs, so calling it constructs an
    instance. To use an instance as the callable, use the 'class:' dict form.

    When the Callable declares a concrete return type (including ``None``) that the
    class cannot produce, raise and point at the 'class:' form rather than silently
    building a factory of the wrong type. A bare or abstractly-typed Callable has no
    return type to check against, so the class is trusted as a factory.

    Functions and methods are used as-is.
    """
    obj = _import_dotted(path_str)
    if isinstance(obj, type):
        required = _unproducible_return(obj, callable_tp)
        if required is not None:
            msg = (
                f"Callable at '{path}': bare class {path_str!r} would be used as a factory,"
                f" but its instances are not {required} (the Callable's declared return type)."
                f" To use an instance of {path_str} as the callable, use the dict form:"
                f" 'class: {path_str}'."
            )
            raise TypeCoercionError(msg)
        return functools.partial(obj)
    return _maybe_bind_method(obj, path)


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
    ``None`` (not ``NoneType``), so ``_callable_return_type`` cannot distinguish it from
    a bare ``Callable``; the raw args are inspected here instead.
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


def _coerce_kwargs(  # noqa: PLR0913
    sig_obj: Any,
    hints_obj: Any,
    kwargs: dict,
    base_path: str,
    union_tag: str,
    construct_fn: Any,
    *,
    kind: str,
    subject: str,
) -> dict:
    """Validate and typed-construct kwargs against a callable's signature.

    The single canonical coercion route shared by 'call', 'class' (factory), and
    'bind' kwargs: unknown keys raise, and each value is built via construct_fn
    (the same route as every other configuration element).

    ``sig_obj`` and ``hints_obj`` are passed separately because for a class they
    differ: ``inspect.signature(cls)`` yields the constructor params (self excluded),
    but the annotations live on ``cls.__init__``.
    """
    try:
        sig = inspect.signature(sig_obj)
    except (ValueError, TypeError):
        return dict(kwargs)  # uninspectable (C extension etc.)

    try:
        hints = get_type_hints(hints_obj)
    except (NameError, AttributeError, TypeError):
        hints = {}

    params = sig.parameters
    has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
    if not has_var_keyword:
        valid = {
            n
            for n, p in params.items()
            if n != "self" and p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        }
        invalid = sorted(set(kwargs) - valid)
        if invalid:
            msg = f"Unknown {kind} {invalid} for {subject} at '{base_path}'. Valid parameters: {sorted(valid)}"
            raise TypeCoercionError(msg)

    coerced: dict = {}
    for k, v in kwargs.items():
        ann = hints.get(k, inspect.Parameter.empty)
        if ann is inspect.Parameter.empty:
            coerced[k] = v
        else:
            resolved_ann = _resolve_type(ann)
            coerced[k] = construct_fn(resolved_ann, v, path=f"{base_path}.{k}", union_tag=union_tag)
    return coerced


def _resolve_call_kwargs(func: Any, kwargs: dict, path: str, union_tag: str, construct_fn: Any) -> dict:
    """Coerce and validate kwargs against func's signature using typed construction."""
    subject = repr(getattr(func, "__qualname__", repr(func)))
    return _coerce_kwargs(func, func, kwargs, path, union_tag, construct_fn, kind="kwargs", subject=subject)


def _resolve_call_spec(  # noqa: PLR0913
    fn_path: str,
    call_kwargs: dict,
    original_spec: dict,
    path: str,
    union_tag: str,
    construct_fn: Any,
) -> Any:
    """Resolve a 'call:' spec: import the function, call it with call_kwargs, use the return value."""
    func = _import_dotted(fn_path)
    coerced = _resolve_call_kwargs(func, call_kwargs, path, union_tag, construct_fn)
    try:
        result = func(**coerced)
    except Exception as e:
        msg = f"Failed to call {fn_path!r} at '{path}': {e}"
        raise TypeCoercionError(msg) from e
    if not callable(result):
        msg = (
            f"'call:' at '{path}': {fn_path!r}(**{call_kwargs!r}) returned {type(result).__name__!r},"
            " which is not callable."
        )
        raise TypeCoercionError(msg)
    with contextlib.suppress(AttributeError, TypeError):
        result.__confarg_spec__ = original_spec
    return result


@dataclass(frozen=True)
class _Directives:
    """The directive key names active for a spec, in either plain or escaped mode.

    A callable dict names its target with an *opener* (``fn``/``class``/``call``)
    and may partially apply the result with ``bind``. Because these words sit as
    siblings of the target's own kwargs, a parameter named ``fn``/``call``/``bind``
    would collide. The escaped mode swaps every directive for its single-underscore
    form (``_fn``/``_class``/``_call``/``_bind``), freeing every plain word to be an
    ordinary kwarg. The opener's form selects the mode for the whole spec.
    """

    fn: str
    cls: str
    call: str
    bind: str

    @property
    def openers(self) -> tuple[str, str, str]:
        return (self.fn, self.cls, self.call)

    @property
    def reserved(self) -> frozenset[str]:
        return frozenset({self.fn, self.cls, self.call, self.bind})


_PLAIN_DIRECTIVES = _Directives(fn="fn", cls="class", call="call", bind="bind")
_ESCAPED_DIRECTIVES = _Directives(fn="_fn", cls="_class", call="_call", bind="_bind")


def active_directives(has_key: Callable[[str], bool]) -> _Directives:
    """Pick the active directive names by the opener's form, via a key-presence predicate.

    The single canonical mode selector, shared by the vanilla construct path and the
    CLI collection/registration paths so every channel agrees on plain-vs-escaped
    without duplicating the tables. ``has_key(name)`` answers "is this directive key
    present?" — a spec dict passes ``spec.__contains__``; the CLI passes a probe over
    its flat ``{flag}.{name}`` namespace.

    Escaped mode is selected when an escaped *opener* (``_fn``/``_class``/``_call``) is
    present; otherwise plain mode. Deliberately lenient: the opener alone decides, and a
    directive word in the *other* form is treated as ordinary data. Do not mix forms
    within one spec — a plain opener with a stray ``_bind`` leaves that ``_bind`` a
    kwarg, not the directive.
    """
    if any(has_key(opener) for opener in _ESCAPED_DIRECTIVES.openers):
        return _ESCAPED_DIRECTIVES
    return _PLAIN_DIRECTIVES


def _select_directives(spec: dict) -> _Directives:
    """Pick the active directives for a spec dict (see :func:`active_directives`)."""
    return active_directives(spec.__contains__)


def _resolve_dict_spec(spec: dict, path: str, union_tag: str, construct_fn: Any) -> Any:
    """Resolve a dict callable spec (fn/class/call + sibling kwargs + bind).

    Directive keys come in a plain and a single-underscore-escaped form; the opener
    selects which (see :func:`_select_directives`).
    """
    d = _select_directives(spec)
    has_fn = d.fn in spec
    has_class = d.cls in spec
    has_call = d.call in spec
    exclusive = [k for k in d.openers if k in spec]
    if len(exclusive) > 1:
        msg = f"Callable dict at '{path}' must not specify more than one of {list(d.openers)} (got: {exclusive})"
        raise TypeCoercionError(msg)
    if not has_fn and not has_class and not has_call:
        msg = f"Callable dict at '{path}' must specify one of 'fn', 'class', or 'call' (or their _-prefixed forms)"
        raise TypeCoercionError(msg)
    bind_raw = spec.get(d.bind, {})
    if not isinstance(bind_raw, dict):
        msg = f"{d.bind!r} in Callable dict at '{path}' must be a dict, got {type(bind_raw).__name__}"
        raise TypeCoercionError(msg)
    init_kwargs = {k: v for k, v in spec.items() if k not in d.reserved}

    if has_call:
        call_kwargs = {**init_kwargs, **bind_raw}
        return _resolve_call_spec(spec[d.call], call_kwargs, spec, path, union_tag, construct_fn)
    if has_fn:
        return _resolve_fn_spec(spec[d.fn], init_kwargs, bind_raw, path, union_tag, construct_fn)
    return _resolve_class_spec(
        _ClassSpec(spec[d.cls], init_kwargs, bind_raw, spec),
        path,
        union_tag,
        construct_fn,
    )


def _bind_hints_source(callable_obj: Any) -> Any:
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


def _resolve_bind_kwargs(callable_obj: Any, bind: dict, path: str, union_tag: str, construct_fn: Any) -> dict:
    """Validate and typed-construct 'bind' kwargs against callable_obj's signature.

    Routes bind values through the same canonical construction path as every other
    configuration element (see _coerce_kwargs), so bound arguments gain full typed
    construction (enums, dataclasses, lists, unions) and fail-fast on bad values.
    """
    subject = getattr(callable_obj, "__qualname__", None) or getattr(
        type(callable_obj),
        "__qualname__",
        repr(callable_obj),
    )
    return _coerce_kwargs(
        callable_obj,
        _bind_hints_source(callable_obj),
        bind,
        f"{path}.bind",
        union_tag,
        construct_fn,
        kind="bind parameter(s)",
        subject=subject,
    )


def _resolve_fn_spec(fn_path: str, init_kwargs: dict, bind: dict, path: str, union_tag: str, construct_fn: Any) -> Any:  # noqa: PLR0913
    """Resolve a 'fn:' callable spec.

    If init_kwargs are provided, detect the owning class via __qualname__,
    construct the instance, then retrieve the method. Otherwise use the
    imported object directly.
    """
    func = _import_dotted(fn_path)
    if init_kwargs and getattr(func, "__name__", None) == "__init__":
        msg = (
            f"Constructor kwargs {sorted(init_kwargs)} are not valid for '__init__' at '{path}':"
            " '__init__' is treated as a plain function. Use 'bind:' to partially apply arguments."
        )
        raise TypeCoercionError(msg)
    if init_kwargs:
        cls = _detect_owning_class(func)
        if cls is None:
            msg = (
                f"Constructor kwargs {sorted(init_kwargs)} provided for {fn_path!r} at '{path}',"
                " but it does not appear to be an instance method."
                " Use 'bind' to partially apply arguments to a plain function or class."
            )
            raise TypeCoercionError(msg)
        instance = _construct_class(cls, init_kwargs, path, union_tag, construct_fn)
        result: Any = getattr(instance, func.__name__)
    else:
        result = _maybe_bind_method(func, path)
    if bind:
        bind = _resolve_bind_kwargs(result, bind, path, union_tag, construct_fn)
        result = functools.partial(result, **bind)
    return result


@dataclass
class _ClassSpec:
    """Parsed 'class:' section of a callable dict spec."""

    cls_path: str
    init_kwargs: dict
    bind: dict
    original: dict


def _resolve_class_spec(
    spec: _ClassSpec,
    path: str,
    union_tag: str,
    construct_fn: Any,
) -> Any:
    """Resolve a 'class:' callable spec: instantiate the class; the instance is the callable.

    ``init_kwargs`` (sibling keys) are the constructor arguments; the instance must be
    callable (define ``__call__``). ``bind`` is then partially applied to the instance.

    To use a class as a *factory* (calling it constructs an instance), give its bare
    fully-qualified name, or ``fn: <class>`` with ``bind:`` for pre-applied constructor args.
    """
    cls = _import_dotted(spec.cls_path)
    if not isinstance(cls, type):
        msg = f"'class' key at '{path}' must reference a class, got {type(cls).__name__} {spec.cls_path!r}"
        raise TypeCoercionError(msg)

    instance = _construct_class(cls, spec.init_kwargs, path, union_tag, construct_fn)
    if not callable(instance):
        msg = (
            f"Instance of {spec.cls_path!r} at '{path}' is not callable: the class must define"
            f" __call__ to be used as a Callable via 'class:'. To use {spec.cls_path} as a"
            f" factory (calling it constructs an instance), give its bare name"
            f" '{spec.cls_path}', or 'fn: {spec.cls_path}' with 'bind:' for constructor args."
        )
        raise TypeCoercionError(msg)
    result: Any
    if spec.bind:
        bind = _resolve_bind_kwargs(instance, spec.bind, path, union_tag, construct_fn)
        result = functools.partial(instance, **bind)
    else:
        result = instance
    with contextlib.suppress(AttributeError, TypeError):
        cast("Any", result).__confarg_spec__ = spec.original
    return result


def _construct_class(cls: type, kwargs: dict, path: str, union_tag: str, construct_fn: Any) -> Any:
    """Construct a class instance using the confarg struct construction pipeline."""
    return construct_fn(cls, kwargs, path=path, union_tag=union_tag)


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

    required = [
        p
        for p in sig.parameters.values()
        if p.default is inspect.Parameter.empty
        and p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    ]
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
    Partial with pre-bound kwargs (factory or bound function) → {fn: "module.qualname", bind: {k: v}}.
    Bare partial (a class used factory-like, no kwargs) → "module.qualname" string.
    Plain callable → "module.qualname" string.
    """
    spec = getattr(value, "__confarg_spec__", None)
    if spec is not None:
        return spec

    if isinstance(value, functools.partial):
        func = value.func
        path = f"{func.__module__}.{func.__qualname__}"
        if value.keywords:
            return {"fn": path, "bind": dict(value.keywords)}
        return path

    module = getattr(value, "__module__", None)
    qualname = getattr(value, "__qualname__", None)
    if module and qualname:
        return f"{module}.{qualname}"

    msg = (
        f"Cannot serialize callable {value!r}: no __module__/__qualname__ available."
        " For class instances, ensure the instance was constructed via confarg"
        " (which stores the spec for round-trip serialization)."
    )
    raise ConfargError(msg)
