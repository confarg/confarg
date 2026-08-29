# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Build lists of FlagSpec from dataclass type information.

No argparse import — this module is usable by any CLI adapter.
"""

from __future__ import annotations

import contextlib
import inspect
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

from confarg import _defaults
from confarg._callable import _ESCAPED_DIRECTIVES, _PLAIN_DIRECTIVES, _detect_owning_class, active_directives
from confarg._files import _load_file
from confarg._import import _import_dotted
from confarg._merge import _deep_merge
from confarg._types import (
    _dataclass_subclasses,
    _elem_type,
    _final_inner,
    _init_defaults,
    _init_fields,
    _is_bool,
    _is_callable,
    _is_dict,
    _is_enum,
    _is_final,
    _is_literal,
    _is_namedtuple,
    _is_struct,
    _is_tuple,
    _is_type_ref,
    _is_union,
    _is_varlen_collection,
    _literal_values,
    _namedtuple_fields,
    _resolve_struct,
    _resolve_type,
    _struct_defaults,
    _struct_fields,
    _tuple_types,
    _union_args_no_none,
    _union_has_seq_variant,
    _unwrap_optional,
    _var_param_names,
)
from confarg.cli.argparse._spec import FlagSpec, _build_help, _get_field_docstrings, _get_field_meta
from confarg.exceptions import SymbolImportError
from confarg.typedload._coerce import _NONE_TOKENS, _enum_choices, _is_registered_leaf

_SCALAR_CAST_TYPES: frozenset[type] = frozenset({str, int, float, bool})


def _scalar_cast_types_in_union(resolved: Any) -> list[type]:
    """Return scalar types to offer as explicit cast flags for a multi-variant union.

    Returns non-empty when the union has (a) at least one enum variant, or (b) str
    alongside any other variant — both are combinations where the stealing rule is
    non-obvious and an explicit cast escape-hatch is useful. Case (b) covers str
    sharing the union with a non-scalar variant too (``str | type``, ``str | Path``),
    so ``--field.str`` is always available to bypass a stolen str, whatever the other
    variant is.
    """
    non_none = _union_args_no_none(resolved)
    types = [_resolve_type(v) for v in non_none]
    scalars = [t for t in types if t in _SCALAR_CAST_TYPES]
    has_enum = any(_is_enum(t) for t in types)
    # In this branch the union always has >= 2 non-None variants, so a bare `str in
    # scalars` already means "str shares the union with at least one other variant".
    has_str_with_other = str in scalars
    if not has_enum and not has_str_with_other:
        return []
    return scalars


def _literal_cli_choices(vals: tuple[Any, ...]) -> list[str]:
    """Map Literal members to their accepted CLI strings."""
    choices: list[str] = []
    for v in vals:
        if v is None:
            choices.extend(sorted(_NONE_TOKENS))
        else:
            choices.append(str(v))
    return choices


def _merge_or_append_spec(result: list[FlagSpec], by_name: dict[str, FlagSpec], spec: FlagSpec) -> None:
    """Append ``spec`` to ``result``, or merge its ``choices`` into a same-named earlier spec.

    Union variants can each contribute a ``FlagSpec`` for the same discriminator field
    (e.g. ``type: Literal["mariadb"]`` vs ``Literal["postgres"]``). First-wins dedup would
    drop all but the first variant's choices, so a merged single flag must accept every
    variant's value. When both the existing and new spec carry ``choices``, union them
    (order-preserving); otherwise keep the first spec unchanged.
    """
    existing = by_name.get(spec.name)
    if existing is None:
        result.append(spec)
        by_name[spec.name] = spec
        return
    if existing.choices is not None and spec.choices is not None:
        existing.choices.extend(c for c in spec.choices if c not in existing.choices)


def _build_leaf_spec(  # noqa: PLR0911 PLR0913
    flag: str,
    raw_type: Any,
    core: Any,
    help_text: str,
    group: str | None,
    group_description: str,
) -> FlagSpec:
    """Build a FlagSpec for a single leaf field."""
    meta = _get_field_meta(raw_type)
    metavar: str | None = meta.metavar if meta is not None else None

    if _is_bool(core):
        return FlagSpec(
            name=flag,
            metavar=metavar or "true|false",
            help=help_text,
            group=group,
            group_description=group_description,
        )

    if _is_varlen_collection(core):
        et = _resolve_type(_elem_type(core))
        return FlagSpec(
            name=flag,
            nargs="*",
            metavar=metavar or getattr(et, "__name__", "ITEM").upper(),
            help=help_text,
            group=group,
            group_description=group_description,
        )

    if _is_tuple(core):
        tt = _tuple_types(core)
        if tt is not None:
            return FlagSpec(
                name=flag,
                nargs=len(tt),
                metavar=metavar or "VALUE",
                help=help_text,
                group=group,
                group_description=group_description,
            )
        # tuple[X, ...] — variable length (unreachable: caught by _is_varlen_collection)
        et = _resolve_type(_elem_type(core))  # pragma: no cover
        return FlagSpec(
            name=flag,
            nargs="*",
            metavar=metavar or getattr(et, "__name__", "ITEM").upper(),
            help=help_text,
            group=group,
            group_description=group_description,
        )

    if _is_literal(core):
        return FlagSpec(
            name=flag,
            choices=_literal_cli_choices(_literal_values(core)),
            help=help_text,
            group=group,
            group_description=group_description,
        )

    if _is_enum(core):
        return FlagSpec(
            name=flag,
            choices=_enum_choices(core),
            metavar=metavar or flag.rsplit(".", 1)[-1].upper(),
            help=help_text,
            group=group,
            group_description=group_description,
        )

    if _is_type_ref(core):
        return FlagSpec(
            name=flag,
            metavar=metavar or "DOTTED.CLASS.PATH",
            help=help_text,
            group=group,
            group_description=group_description,
        )

    # Generic scalar (str, int, float, Path, …)
    type_name = getattr(core, "__name__", "VALUE").upper()
    return FlagSpec(
        name=flag,
        metavar=metavar or type_name,
        help=help_text,
        group=group,
        group_description=group_description,
    )


# (opener_suffix, mode, bind_key) for both the plain and escaped directive forms.
# Escaped forms come first so the longer suffix (``._class``) is matched before the
# plain one (``.class``). The single source of truth for how an argv opener flag maps
# to a mode + bind-flag namespace, mirroring ``confarg._callable.active_directives`` on
# the construction side so registration and collection agree.
_OPENER_SPECS: tuple[tuple[str, str, str], ...] = tuple(
    (f".{opener}", mode, directives.bind)
    for directives in (_ESCAPED_DIRECTIVES, _PLAIN_DIRECTIVES)
    for opener, mode in ((directives.fn, "fn"), (directives.cls, "class"), (directives.call, "call"))
)


def _escaped_opener_name(mode: str) -> str:
    """Return the escaped opener flag name (``_fn``/``_class``/``_call``) for a mode."""
    return {
        "fn": _ESCAPED_DIRECTIVES.fn,
        "class": _ESCAPED_DIRECTIVES.cls,
        "call": _ESCAPED_DIRECTIVES.call,
    }[mode]


def _escaped_opener_specs(
    argv_fns: dict[str, tuple[str, str, str]],
    existing_names: set[str],
) -> list[FlagSpec]:
    """Register the escaped opener flags (``--<field>._class`` etc.) actually typed on the CLI.

    Escaped openers are not registered statically; only those present in argv are added, so
    the host framework accepts them while ``--help`` stays uncluttered. No group is set:
    sharing the field's group name with a different description trips cyclopts' "2 distinct
    Group objects with same name" check.
    """
    result: list[FlagSpec] = []
    for field_flag, (_fn_path, mode, bind_key) in argv_fns.items():
        if bind_key != _ESCAPED_DIRECTIVES.bind:
            continue
        opener_flag = f"{field_flag}.{_escaped_opener_name(mode)}"
        if opener_flag in existing_names:
            continue
        result.append(
            FlagSpec(
                name=opener_flag,
                metavar="DOTTED.PATH",
                help=f"Escaped-mode opener for the '{field_flag}' callable.",
            ),
        )
        existing_names.add(opener_flag)
    return result


def _build_callable_fn_specs(
    flag: str,
    group: str | None,
    group_description: str,
) -> list[FlagSpec]:
    """Build FlagSpecs for ``--<flag>.fn``, ``--<flag>.class``, ``--<flag>.call``.

    Only the plain openers are registered statically; the escaped openers
    (``--<flag>._fn`` etc.) are registered on demand by :func:`build_dynamic_flags`
    when they actually appear in argv, keeping the static ``--help`` uncluttered.
    """
    return [
        FlagSpec(
            name=f"{flag}.{sub}",
            metavar="DOTTED.PATH",
            help=f"Dotted import path for the '{flag}' callable ({desc}).",
            group=group,
            group_description=group_description,
        )
        for sub, desc in (
            ("fn", "function or class; classes get functools.partial with bind kwargs"),
            ("class", "class to instantiate; the resulting instance is the callable"),
            ("call", "factory function to call; result is used as the callable field value"),
        )
    ]


def _make_path_completer(paths: list[str]) -> Callable[[str], list[str]]:
    return lambda prefix: [p for p in paths if p.startswith(prefix)]


def _build_union_tag_spec(
    flag: str,
    union_tag: str,
    variant_types: list[Any],
    group: str | None,
    group_description: str,
) -> FlagSpec:
    """Build a FlagSpec for ``--<flag>.<union_tag>`` with an optional path completer."""
    completer = None
    if variant_types:
        paths = [f"{v.__module__}.{v.__qualname__}" for v in variant_types]
        completer = _make_path_completer(paths)
    return FlagSpec(
        name=f"{flag}.{union_tag}",
        metavar="DOTTED.CLASS.PATH",
        help=(
            f"Fully-qualified class path selecting the variant for '{flag}' "
            f"(e.g. mypackage.MyClass). "
            f"Once set, use --{flag}.<field> flags for that class's fields."
        ),
        group=group,
        group_description=group_description,
        completer=completer,
    )


def _bind_specs_from_signature(
    field_flag: str,
    target_obj: Any,
    bind_key: str,
    existing_names: set[str],
) -> list[FlagSpec]:
    """Build ``--<field_flag>.<bind_key>.<param>`` FlagSpecs from a callable's signature.

    ``bind_key`` is ``bind`` in plain mode and ``_bind`` in escaped mode, so the
    registered flags match the active directive namespace.
    """
    try:
        sig = inspect.signature(target_obj)
    except (ValueError, TypeError):
        return []

    bind_group_desc = f"Bind arguments for callable '{field_flag}'"
    result: list[FlagSpec] = []
    for param_name, param in sig.parameters.items():
        if param_name == "self":
            continue
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        dest = f"{field_flag}.{bind_key}.{param_name}"
        if dest in existing_names:
            continue
        help_parts = []
        ann = param.annotation
        if ann is not inspect.Parameter.empty:
            help_parts.append(getattr(ann, "__name__", repr(ann)))
        if param.default is not inspect.Parameter.empty:
            help_parts.append(f"default: {param.default!r}")
        with contextlib.suppress(Exception):
            result.append(
                FlagSpec(
                    name=dest,
                    metavar=param_name.upper(),
                    help=", ".join(help_parts),
                    group=field_flag,
                    group_description=bind_group_desc,
                ),
            )
        existing_names.add(dest)

    return result


def _collect_callable_bind_specs(
    field_flag: str,
    fn_path: str,
    bind_key: str,
    existing_names: set[str],
) -> list[FlagSpec]:
    """Build FlagSpecs for ``--<field_flag>.<bind_key>.<param>`` by inspecting the target's signature."""
    try:
        obj = _import_dotted(fn_path)
    except SymbolImportError:
        return []
    target_obj = obj.__init__ if isinstance(obj, type) else obj
    return _bind_specs_from_signature(field_flag, target_obj, bind_key, existing_names)


def _collect_callable_call_bind_specs(
    field_flag: str,
    cls: type,
    bind_key: str,
    existing_names: set[str],
) -> list[FlagSpec]:
    """Build ``--<field_flag>.<bind_key>.<param>`` FlagSpecs from a class's ``__call__`` parameters.

    In ``--<field>.class`` mode the constructor parameters become factory kwargs
    (``--<field>.<param>``), while the *instance's* ``__call__`` parameters are
    what ``bind`` targets — so they register here rather than via the
    constructor-signature path.
    """
    # Look up __call__ in the class's own MRO rather than via getattr, which
    # would fall back to the metaclass type.__call__ when instances are not
    # themselves callable (yielding bogus bind params).
    call = next((c.__dict__["__call__"] for c in cls.__mro__ if "__call__" in c.__dict__), None)
    if call is None:
        return []
    return _bind_specs_from_signature(field_flag, call, bind_key, existing_names)


def _collect_callable_factory_specs(
    flag: str,
    cls: type,
    existing_names: set[str],
    group: str | None = None,
    group_description: str = "",
) -> list[FlagSpec]:
    """Build FlagSpecs for factory-mode constructor kwargs of ``cls``."""
    try:
        fields = _init_fields(cls)
        defaults = _init_defaults(cls)
    except (ValueError, TypeError, NameError, AttributeError):
        return []

    result: list[FlagSpec] = []
    for param_name, ft in fields.items():
        dest = f"{flag}.{param_name}"
        if dest in existing_names:
            continue
        core_ft = _resolve_type(ft)
        help_parts: list[str] = []
        type_name = getattr(core_ft, "__name__", repr(core_ft))
        if type_name and type_name != "Any":
            help_parts.append(type_name)
        if param_name in defaults:
            help_parts.append(f"default: {defaults[param_name]!r}")
        with contextlib.suppress(Exception):
            result.append(_build_leaf_spec(dest, ft, core_ft, ", ".join(help_parts), group, group_description))
        existing_names.add(dest)

    return result


def _collect_callable_field_specs(
    field_flag: str,
    fn_path: str,
    mode: str,
    bind_key: str,
    existing_names: set[str],
) -> list[FlagSpec]:
    """Build bind/factory FlagSpecs for one callable field given its fn_path, mode and bind_key.

    ``bind_key`` (``bind`` or ``_bind``) names the active bind-flag namespace; factory
    kwargs stay plain (``--<field>.<param>``) in both modes.
    """
    if mode == "class":
        try:
            cls = _import_dotted(fn_path)
            if isinstance(cls, type):
                # Constructor params → factory kwargs; __call__ params → bind kwargs.
                specs = _collect_callable_factory_specs(field_flag, cls, existing_names)
                specs.extend(_collect_callable_call_bind_specs(field_flag, cls, bind_key, existing_names))
                return specs
        except SymbolImportError:
            pass
    elif mode == "call":
        return _collect_callable_bind_specs(field_flag, fn_path, bind_key, existing_names)
    else:  # mode == "fn"
        try:
            obj = _import_dotted(fn_path)
            if isinstance(obj, type):
                # 'fn: SomeClass' is a factory; its constructor params are bind targets
                # (--<field>.bind.<param>), applied via functools.partial.
                return _collect_callable_bind_specs(field_flag, fn_path, bind_key, existing_names)
            owning_cls = _detect_owning_class(obj)
            if owning_cls is not None:
                # Bound-method path (e.g. Class.method): the owning class's
                # constructor params become factory kwargs, while the method's
                # own params are what bind targets.
                specs = _collect_callable_factory_specs(field_flag, owning_cls, existing_names)
                specs.extend(_collect_callable_bind_specs(field_flag, fn_path, bind_key, existing_names))
                return specs
        except SymbolImportError:
            pass
    return _collect_callable_bind_specs(field_flag, fn_path, bind_key, existing_names)


def _match_opener_suffix(key: str) -> tuple[str, str, str] | None:
    """Return (field_flag, mode, bind_key) if ``key`` ends with a plain or escaped opener suffix."""
    for suffix, mode, bind_key in _OPENER_SPECS:
        if key.endswith(suffix) and len(key) > len(suffix):
            return key[: -len(suffix)], mode, bind_key
    return None


def _collect_fn_paths_from_argv(argv: Sequence[str]) -> dict[str, tuple[str, str, str]]:
    """Scan argv for --<field>.fn/.class/.call and their escaped ._fn/._class/._call forms.

    Returns {field_flag: (fn_path, mode, bind_key)} where mode is "fn"/"class"/"call"
    and bind_key is "bind" (plain) or "_bind" (escaped). CLI wins for duplicate keys.

    A field's escaped opener takes precedence over any plain-opener match for the same
    field: once ``--<field>._fn`` is present, a sibling ``--<field>.fn`` is a factory
    kwarg named ``fn``, not a second opener. This mirrors
    :func:`~confarg._callable.active_directives`, where the opener's form alone selects
    the mode.
    """
    escaped: dict[str, tuple[str, str, str]] = {}
    plain: dict[str, tuple[str, str, str]] = {}
    i = 0
    while i < len(argv):
        tok = argv[i]
        if not tok.startswith("--"):
            i += 1
            continue
        if "=" in tok:
            key, _, val = tok[2:].partition("=")
            matched = _match_opener_suffix(key)
            if matched is not None:
                field_flag, mode, bind_key = matched
                bucket = escaped if bind_key == _ESCAPED_DIRECTIVES.bind else plain
                bucket[field_flag] = (val, mode, bind_key)
            i += 1
        else:
            matched = _match_opener_suffix(tok[2:])
            if matched is not None and i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                field_flag, mode, bind_key = matched
                bucket = escaped if bind_key == _ESCAPED_DIRECTIVES.bind else plain
                bucket[field_flag] = (argv[i + 1], mode, bind_key)
                i += 2
            else:
                i += 1
    return {**plain, **escaped}  # escaped opener wins: a field's plain '.fn' is then data


def _callable_fn_path(sub: Any) -> tuple[str, str, str] | None:
    """Return (path, mode, bind_key) from a callable's config sub-value, or None if not present.

    Checks string shorthand (implicit "fn") and the opener keys of the active directive
    form (plain ``fn``/``class``/``call`` or escaped ``_fn``/``_class``/``_call``),
    selected canonically via :func:`~confarg._callable.active_directives`.
    """
    if isinstance(sub, str):
        return (sub, "fn", _PLAIN_DIRECTIVES.bind)
    if isinstance(sub, dict):
        d = active_directives(sub.__contains__)
        for key, mode in ((d.fn, "fn"), (d.cls, "class"), (d.call, "call")):
            if isinstance(sub.get(key), str):
                return (sub[key], mode, d.bind)
    return None


def _collect_fn_paths_from_config(
    config_dict: dict[str, Any],
    target: Any,
    prefix: str,
    union_tag: str,
) -> dict[str, tuple[str, str, str]]:
    """Walk target + config_dict to find fn/class values for Callable fields.

    Returns {field_flag: (fn_path, mode, bind_key)} where mode is "fn"/"class"/"call"
    and bind_key is "bind" (plain) or "_bind" (escaped).
    """
    result: dict[str, tuple[str, str, str]] = {}
    tp = _resolve_type(target)
    if not _is_struct(tp):
        return result
    try:
        flds = _struct_fields(tp)
    except (ValueError, TypeError, NameError, AttributeError):
        return result

    for name, ft in flds.items():
        flag = f"{prefix}.{name}" if prefix else name
        resolved = _unwrap_optional(_resolve_type(ft))
        if resolved is None:
            continue
        if _is_callable(resolved):
            fn_path = _callable_fn_path(config_dict.get(name))
            if fn_path is not None:
                result[flag] = fn_path
        elif _is_struct(resolved):
            sub = config_dict.get(name, {})
            if isinstance(sub, dict):
                result.update(_collect_fn_paths_from_config(sub, resolved, flag, union_tag))
    return result


def _collect_namedtuple_specs(
    core: Any,
    flag: str,
    group: str | None,
    group_description: str,
) -> list[FlagSpec]:
    """Build FlagSpecs for a namedtuple field: nargs leaf + per-field-name + per-index flags."""
    flds = _namedtuple_fields(core)
    n = len(flds)
    result: list[FlagSpec] = []
    # Combined nargs flag (like a regular tuple)
    result.append(
        FlagSpec(
            name=flag,
            nargs=n,
            metavar="VALUE",
            help=f"Set all {n} field(s) of {core.__name__} at once (positional order: {', '.join(flds)})",
            group=group,
            group_description=group_description,
        ),
    )
    # Individual flags by field name and by index
    for i, (fname, ft) in enumerate(flds.items()):
        field_help = f"Field {fname!r} of {core.__name__} (index {i})"
        # By field name
        result.append(
            FlagSpec(
                name=f"{flag}.{fname}",
                metavar=getattr(ft, "__name__", "VALUE").upper(),
                help=field_help,
                group=group,
                group_description=group_description,
            ),
        )
        # By index
        result.append(
            FlagSpec(
                name=f"{flag}.{i}",
                metavar=getattr(ft, "__name__", "VALUE").upper(),
                help=field_help,
                group=group,
                group_description=group_description,
            ),
        )
    return result


def _union_cast_flag_specs(
    flag: str,
    cast_types: list[type],
    group: str | None,
    group_description: str,
) -> list[FlagSpec]:
    """Build ``--<flag>.<scalar>`` force-cast FlagSpecs for a multi-variant union."""
    return [
        FlagSpec(
            name=f"{flag}.{tp.__name__}",
            metavar=tp.__name__.upper(),
            help=f"Force {tp.__name__!r} type for '{flag}' (bypasses the stealing rule).",
            group=group,
            group_description=group_description,
        )
        for tp in cast_types
    ]


def _specs_for_field(  # noqa: C901, PLR0911, PLR0913
    flag: str,
    name: str,
    raw_type: Any,
    resolved: Any,
    union_tag: str,
    group: str | None,
    group_description: str,
    docstrings: dict[str, str],
    defaults: dict[str, Any],
) -> list[FlagSpec]:
    """Return FlagSpecs for one field of a struct type."""
    core = _unwrap_optional(resolved)
    if core is None:
        non_none = _union_args_no_none(resolved)
        concrete = [_resolve_type(v) for v in non_none if _is_struct(_resolve_type(v))]
        if concrete:
            specs = [_build_union_tag_spec(flag, union_tag, concrete, group, group_description)]
            by_name: dict[str, FlagSpec] = {specs[0].name: specs[0]}
            for variant in concrete:
                for spec in _collect_struct_specs(
                    variant,
                    flag,
                    union_tag,
                    group=variant.__name__,
                    group_description=inspect.getdoc(variant) or "",
                ):
                    _merge_or_append_spec(specs, by_name, spec)
            return specs
        # Union with a sequence variant (str | tuple[...], str | list[str]) →
        # a multi-token flag; vanilla consumes greedily, so register nargs="*".
        if _union_has_seq_variant(resolved):
            help_text = _build_help(name, raw_type, docstrings, defaults, flag=flag)
            seq_specs: list[FlagSpec] = [
                FlagSpec(
                    name=flag,
                    nargs="*",
                    metavar="VALUE",
                    help=help_text,
                    group=group,
                    group_description=group_description,
                ),
            ]
            seq_specs.extend(
                _union_cast_flag_specs(flag, _scalar_cast_types_in_union(resolved), group, group_description),
            )
            return seq_specs
        # Any other multi-variant leaf union (str | type, int | float, str | Path, …)
        # is a single scalar flag. Register it unconditionally so the field is
        # accepted; add force-cast escape hatches when the stealing rule is
        # non-obvious (str-with-scalar or enum unions).
        help_text = _build_help(name, raw_type, docstrings, defaults, flag=flag)
        return [
            FlagSpec(name=flag, metavar="VALUE", help=help_text, group=group, group_description=group_description),
            *_union_cast_flag_specs(flag, _scalar_cast_types_in_union(resolved), group, group_description),
        ]

    if _is_final(core):
        core = _final_inner(core)

    if _is_callable(core):
        help_text = _build_help(name, raw_type, docstrings, defaults, flag=flag)
        specs: list[FlagSpec] = [_build_leaf_spec(flag, raw_type, core, help_text, group, group_description)]
        specs.extend(_build_callable_fn_specs(flag, group, group_description))
        return specs

    if _is_namedtuple(core):
        return _collect_namedtuple_specs(core, flag, group, group_description)

    if _is_registered_leaf(core):
        help_text = _build_help(name, raw_type, docstrings, defaults, flag=flag)
        return [_build_leaf_spec(flag, raw_type, core, help_text, group, group_description)]

    if _is_struct(core):
        return _collect_struct_specs(core, flag, union_tag, flag, inspect.getdoc(core) or "")

    if _is_dict(core):
        return []

    help_text = _build_help(name, raw_type, docstrings, defaults, flag=flag)
    return [_build_leaf_spec(flag, raw_type, core, help_text, group, group_description)]


def _collect_union_root_specs(
    variants: list[Any],
    prefix: str,
    union_tag: str,
) -> list[FlagSpec]:
    """Build FlagSpecs for a union target (variants are the concrete struct types)."""
    tag_name = f"{prefix}.{union_tag}" if prefix else union_tag
    paths = [f"{v.__module__}.{v.__qualname__}" for v in variants]
    result: list[FlagSpec] = [
        FlagSpec(
            name=tag_name,
            metavar="DOTTED.CLASS.PATH",
            help=(
                "Fully-qualified class path selecting the union variant "
                f"(e.g. {paths[0] if paths else 'mypackage.MyClass'}). "
                "Once set, use the variant's field flags."
            ),
            completer=_make_path_completer(paths),
        ),
    ]
    by_name: dict[str, FlagSpec] = {result[0].name: result[0]}
    for variant in variants:
        for spec in _collect_struct_specs(
            variant,
            prefix,
            union_tag,
            group=variant.__name__,
            group_description=inspect.getdoc(variant) or "",
        ):
            _merge_or_append_spec(result, by_name, spec)
    return result


def _collect_struct_specs(  # union-root branch added one more conditional
    target: Any,
    prefix: str,
    union_tag: str,
    group: str | None = None,
    group_description: str = "",
) -> list[FlagSpec]:
    """Recursively build FlagSpecs for all fields of a struct type."""
    setup = _resolve_struct(target)
    if setup is None:
        tp = _resolve_type(target)
        if _is_union(tp):
            non_none = _union_args_no_none(tp)
            concrete = [_resolve_type(v) for v in non_none if _is_struct(_resolve_type(v))]
            if concrete:
                return _collect_union_root_specs(concrete, prefix, union_tag)
        return []
    tp, flds, hints = setup
    var_params = _var_param_names(tp)
    docstrings = _get_field_docstrings(tp)
    defaults = _struct_defaults(tp)

    result: list[FlagSpec] = []
    for name in flds:
        if name == union_tag or name in var_params:
            continue
        raw_type = hints.get(name, Any)
        resolved = _resolve_type(raw_type)
        flag = f"{prefix}.{name}" if prefix else name
        result.extend(
            _specs_for_field(flag, name, raw_type, resolved, union_tag, group, group_description, docstrings, defaults),
        )

    # Handle inheritance-based dispatch: if this struct has subclasses, register
    # a --<union_tag> selector and the union of all subclass fields.
    direct_subs = [s for s in tp.__subclasses__() if _is_struct(s)]
    if direct_subs:
        all_subs = _dataclass_subclasses(tp)  # recursive, for tab-completion paths
        tag_name = f"{prefix}.{union_tag}" if prefix else union_tag
        by_name: dict[str, FlagSpec] = {s.name: s for s in result}
        if tag_name not in by_name:
            paths = [f"{v.__module__}.{v.__qualname__}" for v in all_subs]
            tag_spec = FlagSpec(
                name=tag_name,
                metavar="DOTTED.CLASS.PATH",
                help=(
                    f"Fully-qualified class path selecting the {tp.__name__!r} subclass "
                    f"(e.g. mypackage.SubClass). "
                    f"Once set, use the subclass's field flags."
                ),
                group=group,
                group_description=group_description,
                completer=_make_path_completer(paths),
            )
            result.append(tag_spec)
            by_name[tag_name] = tag_spec
        for sub in direct_subs:
            for spec in _collect_struct_specs(sub, prefix, union_tag, group, group_description):
                _merge_or_append_spec(result, by_name, spec)

    return result


def _collect_subconfig_specs(
    target: Any,
    config_flag: str,
    prefix: str,
    union_tag: str,
) -> list[FlagSpec]:
    """Build FlagSpecs for ``--<config_flag>.<subpath>`` scoped config-file flags."""
    setup = _resolve_struct(target)
    if setup is None:
        return []
    _tp, flds, hints = setup

    result: list[FlagSpec] = []
    for name in flds:
        if name == union_tag:
            continue

        resolved = _resolve_type(hints.get(name, Any))
        subpath = f"{prefix}.{name}" if prefix else name

        core = _unwrap_optional(resolved)
        if core is None:
            continue

        if not _is_struct(core):
            continue

        result.append(
            FlagSpec(
                name=f"{config_flag}.{subpath}",
                nargs="*",
                metavar="FILE",
                help=(
                    f"Config file(s) whose contents are merged under the '{subpath}' field. "
                    f"Equivalent to a root config file with a top-level '{subpath}' key. "
                    "Supports TOML, YAML, and JSON."
                ),
            ),
        )

    return result


def build_static_flags(
    target: object,
    *,
    union_tag: str = _defaults.UNION_TAG,
    config_flag: str = _defaults.CONFIG_FLAG,
    config_subkeys: bool = True,
) -> list[FlagSpec]:
    """Build the collection of static CLI flags for a dataclass type.

    Walks the type structure to produce :class:`~confarg.cli.argparse.FlagSpec` objects
    for every field that can be represented as a CLI flag.  The result is
    framework-agnostic and can be loaded into any CLI adapter.

    Args:
        target: The dataclass type whose fields to describe.
        union_tag: Discriminator field name (default ``"class"``).
        config_flag: Name of the config-file flag (default ``"config"``).
            Pass ``""`` to omit config-file flag specs.
        config_subkeys: Whether to register ``--<config_flag>.<field>`` flags for
            each direct struct field of the root dataclass (default ``True``).
            Set to ``False`` to expose only the root ``--<config_flag>`` flag.

    Returns:
        A list of :class:`~confarg.cli.argparse.FlagSpec` objects, one per CLI flag.
    """
    flags = _collect_struct_specs(target, prefix="", union_tag=union_tag)

    if config_flag:
        flags.append(
            FlagSpec(
                name=config_flag,
                nargs="*",
                metavar="FILE",
                help=(
                    "Config file(s) to merge at lowest priority (below env vars and CLI flags). "
                    "Multiple files are merged left-to-right; later files override earlier ones. "
                    "Supports TOML, YAML, and JSON. "
                    f"Use --{config_flag}.<field> FILE to scope a file's contents under a specific field "
                    f"(e.g. --{config_flag}.db db.toml merges db.toml as if its keys were nested under 'db')."
                ),
            ),
        )
        if config_subkeys:
            flags.extend(_collect_subconfig_specs(target, config_flag, prefix="", union_tag=union_tag))

    return flags


def _collect_config_argv_specs(argv: Sequence[str], config_flag: str) -> list[FlagSpec]:
    """Build FlagSpecs for ``--<config_flag>.<subpath>[+]`` flags found in argv.

    Static registration only covers direct struct fields; scanning argv lets any
    subpath the user actually typed — deeper paths and ``+`` append flags — be
    accepted by the host CLI framework, matching what ``confarg.load()`` parses.
    """
    specs: list[FlagSpec] = []
    seen: set[str] = set()
    prefix = f"--{config_flag}."
    for tok in argv:
        if not tok.startswith(prefix):
            continue
        name = tok.split("=", 1)[0][2:]
        if name in seen:
            continue
        seen.add(name)
        subpath = name[len(config_flag) + 1 :]
        action = "appended to" if subpath.endswith("+") else "merged under"
        specs.append(
            FlagSpec(
                name=name,
                nargs="*",
                metavar="FILE",
                help=f"Config file(s) whose contents are {action} the '{subpath.rstrip('+')}' field path.",
            ),
        )
    return specs


def _collect_patch_argv_specs(  # noqa: C901  # one branch per dynamic flag kind (delete/append/collection/json cast)
    target: object,
    argv: Sequence[str],
    union_tag: str,
    config_flag: str,
) -> list[FlagSpec]:
    """Build FlagSpecs for collection-patch flags found in argv.

    Scans for list index/append/delete and dict-subkey flags
    (``--field.N``, ``--field+``, ``--field.N-``, ``--field.key``) whose dotted
    path the *target* type confirms reaches a list, tuple, set, or dict.  These
    are not derivable from the static type walk, so registering exactly the
    ones the user typed lets the host framework accept them; the merge-side
    patch scan (``_parse_cli`` in ``patch_only`` mode) reads their values from
    argv in command order.  Delete flags register value-less (``nargs=0``).
    """
    # Imported here to keep the framework-agnostic _build module free of an
    # import cycle with the argv parser at module load time.
    from confarg._parse_cli import (  # noqa: PLC0415
        _is_collection_patch_path,
        _looks_like_flag,
        _normalize_eq_args,
        _parse_flag_mode,
        detect_force_cast,
    )

    specs: list[FlagSpec] = []
    seen: set[str] = set()
    args = _normalize_eq_args(list(argv))
    for tok in args:
        if not _looks_like_flag(tok):
            continue
        key = tok[2:]
        if config_flag and (key == config_flag or key.startswith(config_flag + ".")):
            continue  # config files are registered by _collect_config_argv_specs
        if key in seen:
            continue
        path, append_mode, delete_mode, _delete_idx, _is_list_delete = _parse_flag_mode(key)
        if not (append_mode or delete_mode):
            path, force_cast = detect_force_cast(path, target, union_tag)
            if force_cast == "json":
                # .json is broadly applicable, so it is registered dynamically (only when
                # typed) rather than statically like the scalar-union casts (--field.int).
                # An empty path is the root `--json` cast (inject the whole config).
                seen.add(key)
                target_desc = f"'{'.'.join(path)}'" if path else "the whole config"
                specs.append(
                    FlagSpec(name=key, metavar="JSON", help=f"Parse the value as JSON for {target_desc}."),
                )
                continue
            if force_cast and not _is_collection_patch_path(target, path, union_tag):
                continue  # scalar-union cast on a plain field (--field.int): registered statically
            # else: cast on a collection element (--field.N.str) falls through to
            # dynamic collection-patch registration below.
        if not (delete_mode or append_mode or _is_collection_patch_path(target, path, union_tag)):
            continue
        seen.add(key)
        target_path = ".".join(path)
        if delete_mode:
            specs.append(FlagSpec(name=key, nargs=0, help=f"Delete the element or key at '{target_path}'."))
        elif append_mode:
            specs.append(
                FlagSpec(
                    name=key,
                    nargs="*",
                    metavar="ITEM",
                    help=f"Append element(s) to the list at '{target_path}'.",
                ),
            )
        else:
            specs.append(
                FlagSpec(name=key, nargs="*", metavar="VALUE", help=f"Set the collection element at '{target_path}'."),
            )
    return specs


def build_dynamic_flags(
    target: object,
    argv: Sequence[str],
    *,
    union_tag: str = _defaults.UNION_TAG,
    config_flag: str = _defaults.CONFIG_FLAG,
) -> list[FlagSpec]:
    """Build CLI flags discoverable only from argv.

    Scans ``argv`` and any config files it references for ``--<field>.fn``,
    ``--<field>.class``, and ``--<field>.call`` tokens.  For each found path, imports
    the target and generates :class:`~confarg.cli.argparse.FlagSpec` objects for its
    parameters (bind kwargs or factory constructor args).

    Also registers a spec for every ``--<config_flag>.<subpath>[+]`` token found
    in ``argv``, so scoped and append config-file flags at any depth are accepted
    by the host framework (duplicates of static flags are skipped at load time).

    Errors are silently ignored — this is a best-effort enhancement.

    Args:
        target: The top-level dataclass type.
        argv: The CLI argument list seen so far (e.g. ``sys.argv[1:]`` at
            completion time, or the full argv at parse time).
        union_tag: Discriminator field name.
        config_flag: Name of the config-file flag.

    Returns:
        A list of additional :class:`~confarg.cli.argparse.FlagSpec` objects.
    """
    try:
        config_dict: dict[str, Any] = {}
        argv_list = list(argv)
        flag_prefix = f"--{config_flag}"
        i = 0
        while i < len(argv_list):
            tok = argv_list[i]
            if tok == flag_prefix:
                i += 1
                while i < len(argv_list) and not argv_list[i].startswith("--"):
                    with contextlib.suppress(Exception):
                        config_dict = _deep_merge(config_dict, _load_file(Path(argv_list[i])))
                    i += 1
            elif tok.startswith(f"{flag_prefix}="):
                path_str = tok[len(flag_prefix) + 1 :]
                if path_str:
                    with contextlib.suppress(Exception):
                        config_dict = _deep_merge(config_dict, _load_file(Path(path_str)))
                i += 1
            else:
                i += 1

        config_fns = _collect_fn_paths_from_config(config_dict, target, "", union_tag)
        argv_fns = _collect_fn_paths_from_argv(argv_list)
        existing_names: set[str] = set()
        result: list[FlagSpec] = _escaped_opener_specs(argv_fns, existing_names)
        for field_flag, (fn_path, mode, bind_key) in {**config_fns, **argv_fns}.items():
            result.extend(_collect_callable_field_specs(field_flag, fn_path, mode, bind_key, existing_names))
        if config_flag:
            result.extend(_collect_config_argv_specs(argv_list, config_flag))
        result.extend(_collect_patch_argv_specs(target, argv_list, union_tag, config_flag))
    except Exception:  # noqa: BLE001 — best-effort; must not crash populate_parser
        return []
    else:
        return result
