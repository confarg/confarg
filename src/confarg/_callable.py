# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Callable resolution and serialization for confarg."""

from __future__ import annotations

import contextlib
import functools
import importlib
import inspect
import sys
from dataclasses import dataclass
from typing import Any

from confarg._errors import ConfargError, SymbolImportError, TypeCoercionError
from confarg._types import (
    _callable_param_types,
    _callable_return_type,
    _is_callable,
    _resolve_type,
)


def _import_dotted(path: str) -> Any:
    """Import an object by dotted path, trying decreasing module prefixes.

    Tries importing the longest valid module prefix first, then chains
    getattr for the remaining parts.
    """
    parts = path.split(".")
    for i in range(len(parts), 0, -1):
        module_path = ".".join(parts[:i])
        try:
            obj = importlib.import_module(module_path)
        except ImportError:
            continue
        except Exception as e:
            msg = f"Cannot import {path!r}: error loading module '{module_path}': {e}"
            raise SymbolImportError(msg) from e
        try:
            for attr in parts[i:]:
                obj = getattr(obj, attr)
        except AttributeError as e:
            msg = f"Cannot import {path!r}: {e}"
            raise SymbolImportError(msg) from e
        else:
            return obj
    msg = f"Cannot import {path!r}: no importable module found in path"
    raise SymbolImportError(msg)


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


def _resolve_callable_spec(spec: Any, tp: Any, path: str, union_tag: str = "class") -> Any:
    """Resolve a Callable value from a raw spec (string or dict).

    Bare string:
      - If the import resolves to a class that is a subclass of the Callable
        return type → factory mode: return functools.partial(cls).
      - If the import resolves to a class (no return type match) → instantiate.
      - Otherwise (function) → use as-is.

    Dict with 'fn' key:
      - The referenced function or method is the callable.
      - If it is an instance method, the owning class is auto-instantiated
        (with sibling kwargs as constructor args, or no args if none are given).
      - 'bind' → functools.partial applied to the resulting callable.

    Dict with 'class' key where class is a subclass of the Callable return type:
      - Factory mode: return functools.partial(cls, **sibling_kwargs).

    Dict with 'class' key where class is NOT a subclass of the return type:
      - Callable-object mode: instantiate the class; the instance is the callable.
      - 'bind' → functools.partial applied to the resulting instance.

    Dict with no 'fn' or 'class' key and a concrete Callable return type:
      - Factory mode: use the return type as the implicit class.
    """
    if isinstance(spec, str):
        result = _resolve_bare_string(str(spec), path, tp)
    elif isinstance(spec, dict):
        result = _resolve_dict_spec(spec, tp, path, union_tag)
    elif callable(spec):
        result = spec
    else:
        msg = f"Cannot construct Callable at '{path}': expected str or dict, got {type(spec).__name__} {spec!r}"
        raise TypeCoercionError(msg)
    _check_callable_signature(result, tp, path)
    return result


def _resolve_bare_string(path_str: str, path: str, callable_tp: Any = None) -> Any:
    """Resolve a bare import-path string to a callable.

    If the object is a class that is a subclass of the Callable return type →
    factory mode: return functools.partial(cls) with no pre-bound kwargs.
    Otherwise, classes are auto-instantiated with no constructor args.
    """
    obj = _import_dotted(path_str)
    if isinstance(obj, type):
        if _is_factory_class(obj, callable_tp):
            return functools.partial(obj)
        try:
            return obj()
        except TypeError as e:
            msg = (
                f"Cannot instantiate {path_str!r} with no arguments at '{path}': {e}."
                f" Use the dict form with 'class: {path_str}' to provide"
                " constructor arguments."
            )
            raise TypeCoercionError(msg) from e
    return _maybe_bind_method(obj, path)


def _resolve_call_kwargs(func: Any, kwargs: dict, path: str, union_tag: str) -> dict:
    """Coerce and validate kwargs against func's signature using typed construction."""
    from confarg.typedload._construct import construct

    try:
        sig = inspect.signature(func)
    except (ValueError, TypeError):
        return dict(kwargs)

    try:
        from typing import get_type_hints

        hints = get_type_hints(func)
    except (NameError, AttributeError, TypeError):
        hints = {}

    params = sig.parameters
    has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
    if not has_var_keyword:
        valid = {
            n
            for n, p in params.items()
            if p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        }
        invalid = sorted(set(kwargs) - valid)
        if invalid:
            fn_name = getattr(func, "__qualname__", repr(func))
            msg = f"Unknown kwargs {invalid} for {fn_name!r} at '{path}'. Valid parameters: {sorted(valid)}"
            raise TypeCoercionError(msg)

    coerced: dict = {}
    for k, v in kwargs.items():
        ann = hints.get(k, inspect.Parameter.empty)
        if ann is inspect.Parameter.empty:
            coerced[k] = v
        else:
            from confarg._types import _resolve_type

            resolved_ann = _resolve_type(ann)
            coerced[k] = construct(resolved_ann, v, path=f"{path}.{k}", union_tag=union_tag)
    return coerced


def _resolve_call_spec(fn_path: str, call_kwargs: dict, original_spec: dict, path: str, union_tag: str) -> Any:
    """Resolve a 'call:' spec: import the function, call it with call_kwargs, use the return value."""
    func = _import_dotted(fn_path)
    coerced = _resolve_call_kwargs(func, call_kwargs, path, union_tag)
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


def _resolve_dict_spec(spec: dict, callable_tp: Any, path: str, union_tag: str) -> Any:
    """Resolve a dict callable spec (fn/class/call + sibling kwargs + bind)."""
    has_fn = "fn" in spec
    has_class = "class" in spec
    has_call = "call" in spec
    exclusive = [k for k in ("fn", "class", "call") if k in spec]
    if len(exclusive) > 1:
        msg = f"Callable dict at '{path}' must not specify more than one of 'fn', 'class', 'call' (got: {exclusive})"
        raise TypeCoercionError(msg)
    if not has_fn and not has_class and not has_call:
        # No fn/class key: factory mode if the return type is a concrete class.
        ret = _callable_return_type(callable_tp)
        if ret is not None and isinstance(ret, type) and not getattr(ret, "__abstractmethods__", frozenset()):
            init_kwargs = dict(spec)
            return _resolve_class_spec(
                _ClassSpec(f"{ret.__module__}.{ret.__qualname__}", init_kwargs, {}, spec),
                path,
                union_tag,
                callable_tp,
            )
        msg = f"Callable dict at '{path}' must have either a 'fn' or 'class' key"
        raise TypeCoercionError(msg)
    bind_raw = spec.get("bind", {})
    if not isinstance(bind_raw, dict):
        msg = f"'bind' in Callable dict at '{path}' must be a dict, got {type(bind_raw).__name__}"
        raise TypeCoercionError(msg)
    init_kwargs = {k: v for k, v in spec.items() if k not in ("fn", "class", "call", "bind")}

    if has_call:
        call_kwargs = {**init_kwargs, **bind_raw}
        return _resolve_call_spec(spec["call"], call_kwargs, spec, path, union_tag)
    if has_fn:
        return _resolve_fn_spec(spec["fn"], init_kwargs, bind_raw, path, union_tag)
    return _resolve_class_spec(_ClassSpec(spec["class"], init_kwargs, bind_raw, spec), path, union_tag, callable_tp)


def _coerce_bind_kwargs(callable_obj: Any, bind: dict) -> dict:
    """Coerce string bind values to the target parameter types via signature inspection.

    Only coerces to bool/int/float — everything else stays as-is.
    Silently skips parameters with uninspectable signatures (C extensions).
    """
    if not any(isinstance(v, str) for v in bind.values()):
        return bind
    try:
        sig = inspect.signature(callable_obj)
    except (ValueError, TypeError):
        return bind

    from typing import get_type_hints

    from confarg._types import _resolve_type, _unwrap_optional
    from confarg.typedload._coerce import _coerce_leaf

    try:
        hints = get_type_hints(callable_obj)
    except (NameError, AttributeError, TypeError):
        hints = {}

    result = {}
    for k, v in bind.items():
        if not isinstance(v, str) or k not in sig.parameters:
            result[k] = v
            continue
        ann = hints.get(k, inspect.Parameter.empty)
        if ann is inspect.Parameter.empty:
            result[k] = v
            continue
        tp = _resolve_type(ann)
        tp = _unwrap_optional(tp) or tp  # keep original union if multi-variant
        if tp in (bool, int, float):
            try:
                result[k] = _coerce_leaf(tp, v)
            except TypeCoercionError:
                result[k] = v
        else:
            result[k] = v
    return result


def _check_bind_params(callable_obj: Any, bind: dict, path: str) -> None:
    """Validate that all bind keys are valid parameter names of callable_obj.

    Skips validation for callables with **kwargs or uninspectable signatures
    (e.g. C extensions).
    """
    try:
        sig = inspect.signature(callable_obj)
    except (ValueError, TypeError):
        return

    params = sig.parameters
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return

    valid = {
        name
        for name, p in params.items()
        if p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    }
    invalid = sorted(set(bind) - valid)
    if invalid:
        msg = f"'bind' at '{path}' contains unknown parameter(s): {invalid}. Valid parameters: {sorted(valid)}"
        raise TypeCoercionError(msg)


def _resolve_fn_spec(fn_path: str, init_kwargs: dict, bind: dict, path: str, union_tag: str) -> Any:
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
        instance = _construct_class(cls, init_kwargs, path, union_tag)
        result: Any = getattr(instance, func.__name__)
    else:
        result = _maybe_bind_method(func, path)
    if bind:
        bind = _coerce_bind_kwargs(result, bind)
        _check_bind_params(result, bind, path)
        result = functools.partial(result, **bind)
    return result


def _is_factory_class(cls: type, callable_tp: Any) -> bool:
    """True if cls should be treated as a factory (partial constructor) rather than instantiated.

    Factory mode activates when cls is a subclass of the Callable annotation's return type.
    """
    from confarg._types import _callable_return_type

    ret = _callable_return_type(callable_tp)
    if ret is None or not isinstance(ret, type) or ret is type(None):
        return False
    try:
        return issubclass(cls, ret)
    except TypeError:
        return False


def _resolve_factory_kwargs(cls: type, kwargs: dict, path: str, union_tag: str) -> dict:
    """Coerce and validate factory kwargs against cls.__init__ signature."""
    from confarg.typedload._construct import construct

    try:
        sig = inspect.signature(cls.__init__)
    except (ValueError, TypeError):
        return dict(kwargs)  # Uninspectable (C extension etc.)

    try:
        from typing import get_type_hints

        hints = get_type_hints(cls.__init__)
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
            msg = (
                f"Unknown constructor kwargs {invalid} for {cls.__qualname__} at '{path}'."
                f" Valid parameters: {sorted(valid)}"
            )
            raise TypeCoercionError(msg)

    coerced: dict = {}
    for k, v in kwargs.items():
        ann = hints.get(k, inspect.Parameter.empty)
        if ann is inspect.Parameter.empty:
            coerced[k] = v
        else:
            from confarg._types import _resolve_type

            resolved_ann = _resolve_type(ann)
            coerced_v = construct(resolved_ann, v, path=f"{path}.{k}", union_tag=union_tag)
            coerced[k] = coerced_v
    return coerced


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
    callable_tp: Any = None,
) -> Any:
    """Resolve a 'class:' callable spec.

    Factory mode (cls is subclass of Callable return type):
      return functools.partial(cls, **init_kwargs).

    Callable-object mode (cls is not a subclass of return type):
      instantiate cls with init_kwargs; the instance must be callable.
      'bind' is then partially applied to the instance.
    """
    cls = _import_dotted(spec.cls_path)
    if not isinstance(cls, type):
        msg = f"'class' key at '{path}' must reference a class, got {type(cls).__name__} {spec.cls_path!r}"
        raise TypeCoercionError(msg)

    if _is_factory_class(cls, callable_tp):
        if spec.bind:
            msg = (
                f"'bind' is not valid in factory mode at '{path}'."
                f" Pass constructor kwargs as sibling keys alongside 'class:'."
            )
            raise TypeCoercionError(msg)
        coerced = _resolve_factory_kwargs(cls, spec.init_kwargs, path, union_tag)
        p = functools.partial(cls, **coerced)
        with contextlib.suppress(AttributeError, TypeError):
            p.__confarg_spec__ = spec.original
        return p

    # Callable-object mode
    instance = _construct_class(cls, spec.init_kwargs, path, union_tag)
    if not callable(instance):
        msg = (
            f"Instance of {spec.cls_path!r} at '{path}' is not callable."
            " The class must define __call__ to be used as a Callable."
        )
        raise TypeCoercionError(msg)
    result: Any
    if spec.bind:
        bind = _coerce_bind_kwargs(instance, spec.bind)
        _check_bind_params(instance, bind, path)
        result = functools.partial(instance, **bind)
    else:
        result = instance
    with contextlib.suppress(AttributeError, TypeError):
        result.__confarg_spec__ = spec.original
    return result


def _construct_class(cls: type, kwargs: dict, path: str, union_tag: str) -> Any:
    """Construct a class instance using the confarg struct construction pipeline."""
    from confarg.typedload._construct import _construct_struct

    return _construct_struct(cls, kwargs, path, union_tag)


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

    Factory partial (functools.partial wrapping a class)
      → {class: "module.qualname", **init_kwargs}
    Function partial → {fn: "module.qualname", bind: {k: v}}
    Class instance with __confarg_spec__ → stored spec dict
    Plain callable → "module.qualname" string
    """
    spec = getattr(value, "__confarg_spec__", None)
    if spec is not None:
        return spec

    if isinstance(value, functools.partial):
        func = value.func
        if isinstance(func, type):
            # Factory partial produced by factory mode
            cls_path = f"{func.__module__}.{func.__qualname__}"
            result: dict = {"class": cls_path}
            result.update(value.keywords)
            return result
        fn_path = f"{func.__module__}.{func.__qualname__}"
        result = {"fn": fn_path}
        if value.keywords:
            result["bind"] = dict(value.keywords)
        return result

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
