# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Build lists of FlagSpec from dataclass type information, for every CLI adapter.

Must not import argparse (it is shared by all adapters) and imports ``_parse_cli``
inside functions only.

Dev Notes:
    docs-dev/architecture/04-cli-adapters.md#framework-neutral-flag-model
    docs-dev/architecture/04-cli-adapters.md#static-and-dynamic-flags
"""

from __future__ import annotations

import contextlib
import dataclasses
import inspect
import json
import warnings
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

from confarg import _defaults
from confarg._callable import _ESCAPED_DIRECTIVES, _PLAIN_DIRECTIVES, _detect_owning_class, active_directives
from confarg._cast import SCALAR_CAST_TYPES
from confarg._import import _import_dotted
from confarg._merge import _peek_nested, _set_nested
from confarg._tags import _partial_config_from_argv, import_tagged_classes
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
    _is_struct_like,
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
    _var_params,
)
from confarg.cli._prefix import apply_prefix, strip_argv_prefix
from confarg.cli._spec import FlagSpec, _build_help, _get_field_docstrings, _get_field_meta
from confarg.exceptions import ConfargWarning, SymbolImportError
from confarg.typedload._coerce import _NONE_TOKENS, _enum_choices, _is_registered_leaf


def _scalar_cast_types_in_union(resolved: Any) -> list[type]:
    """Return scalar types to offer as explicit cast flags for a multi-variant union.

    Returns non-empty when the union has (a) at least one enum variant, or (b) str
    alongside any other variant, scalar or not (``str | type``, ``str | Path``).

    Dev Notes:
        docs-dev/architecture/04-cli-adapters.md#union-inheritance-and-cast-flags
    """
    non_none = _union_args_no_none(resolved)
    types = [_resolve_type(v) for v in non_none]
    scalars = [t for t in types if t in SCALAR_CAST_TYPES.values()]
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

    Union variants can each contribute a ``FlagSpec`` for the same field (e.g.
    ``type: Literal["mariadb"]`` vs ``Literal["postgres"]``). When both the existing and
    new spec carry ``choices``, union them (order-preserving); otherwise keep the first
    spec unchanged.
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
    base = FlagSpec(name=flag, help=help_text, group=group, group_description=group_description)

    if _is_bool(core):
        return dataclasses.replace(base, metavar=metavar or "true|false")

    if _is_varlen_collection(core):
        et = _resolve_type(_elem_type(core))
        return dataclasses.replace(
            base,
            nargs="*",
            metavar=metavar or getattr(et, "__name__", "ITEM").upper(),
        )

    if _is_tuple(core):
        # _is_varlen_collection above absorbed tuple[X, ...], so a tuple
        # reaching here is fixed-length and tt is non-None. The guard narrows
        # the type; the None branch is unreachable.
        tt = _tuple_types(core)
        if tt is not None:
            return dataclasses.replace(
                base,
                nargs=len(tt),
                whole_value=True,
                metavar=metavar or "VALUE",
            )

    if _is_literal(core):
        return dataclasses.replace(base, choices=_literal_cli_choices(_literal_values(core)))

    if _is_enum(core):
        return dataclasses.replace(
            base,
            choices=_enum_choices(core),
            metavar=metavar or flag.rsplit(".", 1)[-1].upper(),
        )

    if _is_type_ref(core):
        return dataclasses.replace(base, metavar=metavar or "DOTTED.CLASS.PATH")

    # Generic scalar (str, int, float, Path, …)
    type_name = getattr(core, "__name__", "VALUE").upper()
    return dataclasses.replace(base, metavar=metavar or type_name)


# (opener_suffix, mode, bind_key) for both the plain and escaped directive forms.
# Escaped forms come first so the longer suffix (``._class``) is matched before the
# plain one (``.class``). Must agree with ``confarg._callable.active_directives``.
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

    Only openers present in argv are added. No group is set (cyclopts rejects two groups
    with the same name and different descriptions).

    Dev Notes:
        docs-dev/architecture/04-cli-adapters.md#static-and-dynamic-flags
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

    Only the plain openers; the escaped openers (``--<flag>._fn`` etc.) are registered
    by :func:`build_dynamic_flags` when they appear in argv.
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


def _path_is_callable_field(target: object, field_flag: str, union_tag: str) -> bool:
    """Return True if the dotted ``field_flag`` resolves to a callable-typed field.

    The argv opener scan pattern-matches ``--<path>.fn/.class/.call`` against argv, so a
    struct field literally named ``fn`` (or ``class``/``call``) would be misread as an
    opener for its parent.  Asking the target type — the same type-guided rule the
    config-file walk and the static flag builder use — keeps the scan from registering
    bind flags below a non-callable path (BUG-30).  The whole-value blob walk is already
    type-guided and reads the shorthand correctly; this brings the argv scan to the same
    answer.

    Dev Notes:
        docs-dev/architecture/04-cli-adapters.md#static-and-dynamic-flags
    """
    from confarg._parse_cli import _resolve_field_type  # noqa: PLC0415  # import cycle

    resolved = _resolve_field_type(target, field_flag.split("."), union_tag)
    if resolved is None:
        return False
    return _is_callable(_unwrap_optional(_resolve_type(resolved)))


def _collect_fn_paths_from_argv(
    argv: Sequence[str],
    target: object,
    union_tag: str,
) -> dict[str, tuple[str, str, str]]:
    """Scan argv for --<field>.fn/.class/.call and their escaped ._fn/._class/._call forms.

    Returns {field_flag: (fn_path, mode, bind_key)} where mode is "fn"/"class"/"call"
    and bind_key is "bind" (plain) or "_bind" (escaped). CLI wins for duplicate keys.

    A match is kept only when ``field_flag`` resolves to a callable-typed field in
    *target*, so a plain struct field named like an opener (``fn``/``class``/``call``)
    is a value, not an opener (BUG-30).  The whole-value blob walk already applies this
    type-guided rule; the scan now agrees with it.

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
                if _path_is_callable_field(target, field_flag, union_tag):
                    bucket = escaped if bind_key == _ESCAPED_DIRECTIVES.bind else plain
                    bucket[field_flag] = (val, mode, bind_key)
            i += 1
        else:
            matched = _match_opener_suffix(tok[2:])
            if matched is not None and i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                field_flag, mode, bind_key = matched
                if _path_is_callable_field(target, field_flag, union_tag):
                    bucket = escaped if bind_key == _ESCAPED_DIRECTIVES.bind else plain
                    bucket[field_flag] = (argv[i + 1], mode, bind_key)
                i += 2
            else:
                i += 1
    return {**plain, **escaped}  # escaped opener wins: a field's plain '.fn' is then data


def _blob_document_from_argv(argv: Sequence[str]) -> dict[str, Any]:
    """Nest every whole-value ``--<dotted.path> <value>`` token of argv into one document.

    The result is shaped like a config file, so :func:`_collect_fn_paths_from_config`
    reads the callable openers a whole value spells with the very walk it uses on
    ``--config`` files.  That walk is type-guided, which is what keeps a mapping field
    whose value happens to carry a ``class`` key from being read as a callable spec.

    Both whole-value shapes are collected, because a config file may spell a callable
    either way and the walk already reads both: a ``{``-prefixed blob, and a bare string,
    which is the shorthand for ``{fn: <string>}`` and must buy the same bind flags.  A
    malformed blob is skipped rather than raised on — registration is best-effort, and
    the real error belongs to the parse.  A key that would have to descend through a
    shorthand already collected is skipped too: it is the refinement, not a competitor.

    Dev Notes:
        docs-dev/architecture/04-cli-adapters.md#whole-value-flags
    """
    doc: dict[str, Any] = {}
    i = 0
    while i < len(argv):
        tok = argv[i]
        if not tok.startswith("--"):
            i += 1
            continue
        if "=" in tok:
            key, _, val = tok[2:].partition("=")
            i += 1
        elif i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            key, val = tok[2:], argv[i + 1]
            i += 2
        else:
            i += 1
            continue
        parts = key.split(".")
        if any(isinstance(_peek_nested(doc, parts[:n]), str) for n in range(1, len(parts))):
            continue
        if val.startswith("{"):
            with contextlib.suppress(json.JSONDecodeError):
                decoded = json.loads(val)
                if isinstance(decoded, dict):
                    _set_nested(doc, parts, decoded)
        else:
            _set_nested(doc, parts, val)
    return doc


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
            whole_value=True,
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


def _whole_value_spec(  # noqa: PLR0913
    flag: str,
    name: str,
    raw_type: Any,
    resolved: Any,
    group: str | None,
    group_description: str,
    docstrings: dict[str, str],
    defaults: dict[str, Any],
) -> FlagSpec:
    """Return the bare ``--<flag>`` spec assigning the whole field value in one token.

    ``nargs=None``: the vanilla parser consumes exactly one token here and rejects a
    second as a stray positional.  The metavar is ``JSON`` only where that token is
    actually decoded as an object, so a field the predicate declines does not advertise
    a syntax it will not honour.

    Dev Notes:
        docs-dev/architecture/04-cli-adapters.md#whole-value-flags
    """
    # Imported here: a module-level import would create an import cycle with _parse_cli.
    from confarg._parse_cli import _accepts_object_value  # noqa: PLC0415

    return FlagSpec(
        name=flag,
        metavar="JSON" if _accepts_object_value(resolved) else "VALUE",
        help=_build_help(name, raw_type, docstrings, defaults, flag=flag),
        group=group,
        group_description=group_description,
    )


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
            # The bare flag first: a whole variant object carries its own discriminator.
            whole = _whole_value_spec(flag, name, raw_type, resolved, group, group_description, docstrings, defaults)
            specs = [whole, _build_union_tag_spec(flag, union_tag, concrete, group, group_description)]
            by_name: dict[str, FlagSpec] = {s.name: s for s in specs}
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
        whole = _whole_value_spec(flag, name, raw_type, resolved, group, group_description, docstrings, defaults)
        return [whole, *_collect_struct_specs(core, flag, union_tag, flag, inspect.getdoc(core) or "")]

    if _is_dict(core):
        # A dict has no statically known keys, so the bare flag is its only static form;
        # each --<flag>.<key> found in argv is registered dynamically alongside it.
        return [_whole_value_spec(flag, name, raw_type, resolved, group, group_description, docstrings, defaults)]

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
    var_params = _var_params(tp).names
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
            # An empty completer would suppress the shell's own suggestions, so leave it unset.
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
                completer=_make_path_completer(paths) if paths else None,
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


def _scalar_root_spec(target: Any) -> FlagSpec:
    """Build the nameless FlagSpec for a non-struct (scalar) root target.

    :func:`~confarg.cli._prefix.apply_prefix` turns the empty name into the bare
    ``--<cli_prefix>`` flag -- the only CLI spelling a scalar root has -- and drops
    the spec entirely when no prefix is set.

    ``nargs`` is forced to a single token because vanilla's
    :func:`~confarg._parse_cli._handle_scalar_root` consumes exactly one: a
    ``list[int]`` root must not pick up the greedy ``nargs="*"`` that
    :func:`_build_leaf_spec` gives a collection *field*.

    Dev Notes:
        docs-dev/architecture/03-cli-parsing.md#cli_prefix
    """
    resolved = _resolve_type(target)
    core = _unwrap_optional(resolved)
    spec = _build_leaf_spec("", target, resolved if core is None else core, "The configuration value.", None, "")
    spec.nargs = None
    return spec


def build_static_flags(  # noqa: PLR0913 — one keyword per knob, mirroring confarg.load
    target: object,
    *,
    argv: Sequence[str] = (),
    cli_prefix: str = "",
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
        argv: The CLI argument list, read only to import the classes it names by
            ``union_tag`` before the type walk -- a subclass is invisible to the walk
            until its module has run.  It never adds a flag of its own: ``()`` (the
            default) and ``argv=[]`` still describe exactly the declared type.
        cli_prefix: Namespace every flag lives under, so ``--<prefix>.<field>``
            distinguishes configuration flags from the host framework's own.
            ``""`` (the default) registers bare field names.  A non-struct
            (scalar) target is registered as the bare ``--<prefix>`` flag, and has
            no CLI spelling at all without a prefix -- as in vanilla.
        union_tag: Discriminator field name (default ``"class"``).
        config_flag: Name of the config-file flag (default ``"config"``).
            Pass ``""`` to omit config-file flag specs.
        config_subkeys: Whether to register ``--<config_flag>.<field>`` flags for
            each direct struct field of the root dataclass (default ``True``).
            Set to ``False`` to expose only the root ``--<config_flag>`` flag.

    Returns:
        A list of :class:`~confarg.cli.argparse.FlagSpec` objects, one per CLI flag.
    """
    # Imported here: a module-level import would create an import cycle with _parse_cli.
    from confarg._parse_cli import _locals_keys  # noqa: PLC0415

    import_tagged_classes(argv, target, union_tag=union_tag, config_flag=config_flag)
    flags = _collect_struct_specs(target, prefix="", union_tag=union_tag)
    if not _is_struct_like(_resolve_type(target)):
        flags.insert(0, _scalar_root_spec(target))

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
            for key in _locals_keys(target, union_tag):
                # --config.<locals> FILE declares locals from the CLI; not a real field,
                # so _collect_subconfig_specs does not emit it.
                flags.append(
                    FlagSpec(
                        name=f"{config_flag}.{key}",
                        nargs="*",
                        metavar="FILE",
                        help=f"Config file(s) declaring local variables in the {key!r} namespace.",
                    ),
                )

    return apply_prefix(flags, cli_prefix)


def _collect_config_argv_specs(argv: Sequence[str], config_flag: str) -> list[FlagSpec]:
    """Build FlagSpecs for ``--<config_flag>.<subpath>[+]`` flags found in argv.

    Covers the deeper subpaths and ``+`` append flags that static registration does not.
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


def _collect_callable_key_argv_specs(
    target: object,
    argv: Sequence[str],
    union_tag: str,
    existing_names: set[str],
) -> list[FlagSpec]:
    """Build FlagSpecs for ``--<callable>.<key>`` flags found in argv but not in a signature.

    The signature-driven specs run first and win, so this pass only catches what no
    signature describes: a bind subkey in the spelling the opener left inactive (BUG-25),
    and a sibling kwarg the named target does not carry — or that names no target at all,
    the field having no opener anywhere (BUG-28).  The vanilla parser accepts any key
    below a callable field (:func:`~confarg._parse_cli._addresses_callable_key`), so
    registration follows the same rule and hands the token to the collector as a plain
    string; whether the kwarg is acceptable is construction's answer to give, identically
    in all four front-ends.

    Append and delete flags are skipped: they take no value, or a variable number of them,
    and :func:`_collect_patch_argv_specs` already registers every one of them in the shape
    its mode demands.  Claiming ``--f.bind.<key>-`` here made all three adapters ask for an
    argument the delete flag does not take (BUG-29).

    Dev Notes:
        docs-dev/architecture/04-cli-adapters.md#static-and-dynamic-flags
    """
    # Imported here: a module-level import would create an import cycle with _parse_cli.
    from confarg._parse_cli import (  # noqa: PLC0415
        _addresses_callable_key,
        _looks_like_flag,
        _normalize_eq_args,
        _parse_flag_mode,
    )

    specs: list[FlagSpec] = []
    for tok in _normalize_eq_args(list(argv)):
        if not _looks_like_flag(tok):
            continue
        key = tok[2:]
        _path, append_mode, delete_mode, _delete_idx, _is_list_delete = _parse_flag_mode(key)
        if append_mode or delete_mode:
            continue
        if key in existing_names or not _addresses_callable_key(target, key.split("."), union_tag):
            continue
        existing_names.add(key)
        specs.append(FlagSpec(name=key, metavar="VALUE", help=f"Value for '{key}' in the callable spec."))
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
    path the *target* type confirms reaches a list, tuple, set, or dict, plus ``.json``
    casts.  Their values are read later from argv by ``_parse_cli`` in ``patch_only``
    mode.  Delete flags register value-less (``nargs=0``).

    Dev Notes:
        docs-dev/architecture/04-cli-adapters.md#collection-patch-parity
    """
    # Imported here: a module-level import would create an import cycle with _parse_cli.
    from confarg._parse_cli import (  # noqa: PLC0415
        _addresses_key,
        _is_collection_patch_path,
        _locals_keys,
        _looks_like_flag,
        _normalize_eq_args,
        _parse_flag_mode,
        _walk_target,
        detect_force_cast,
    )

    # Same graft the vanilla parser uses, so `--<key>.<name>` registers through
    # the identical path as any other dict subkey.
    target = _walk_target(target, _locals_keys(target, union_tag))

    specs: list[FlagSpec] = []
    seen: set[str] = set()
    args = _normalize_eq_args(list(argv))
    for tok in args:
        if not _looks_like_flag(tok):
            continue
        key = tok[2:]
        if _addresses_key(key, config_flag):
            continue  # config files are registered by _collect_config_argv_specs
        if key in seen:
            continue
        path, append_mode, delete_mode, _delete_idx, _is_list_delete = _parse_flag_mode(key)
        if not (append_mode or delete_mode):
            path, force_cast = detect_force_cast(path, target, union_tag)
            if force_cast == "json":
                # .json is registered only when typed. An empty path is the root `--json` cast.
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


def build_dynamic_flags(  # one branch per argv-scanned flag family (config/locals/callable/patch)
    target: object,
    argv: Sequence[str],
    *,
    cli_prefix: str = "",
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

    Also registers the collection-patch flags (``--field.N``, ``--field+``,
    ``--field.N-``, ``--field.key``) and ``.json`` casts found in ``argv``.

    Registration is best-effort: no exception escapes into ``populate_*``.  A failure
    returns no dynamic flag and emits a :class:`~confarg.exceptions.ConfargWarning`
    naming it, since otherwise the only symptom is the host framework later rejecting a
    flag that should exist.  Turn it into an error with
    ``warnings.filterwarnings("error", ConfargWarning)``.

    Args:
        target: The top-level dataclass type.
        argv: The CLI argument list seen so far (e.g. ``sys.argv[1:]`` at
            completion time, or the full argv at parse time).
        cli_prefix: Namespace the flags live under.  argv is stripped of it before
            the scan, so the dotted paths resolve against *target*, and the specs
            are renamed back into the namespace on the way out.
        union_tag: Discriminator field name.
        config_flag: Name of the config-file flag.

    Returns:
        A list of additional :class:`~confarg.cli.argparse.FlagSpec` objects.

    Dev Notes:
        docs-dev/architecture/04-cli-adapters.md#static-and-dynamic-flags
    """
    try:
        # Strip first: the scans below resolve dotted paths against *target*, which
        # knows nothing of the prefix (docs-dev/architecture/03-cli-parsing.md#cli_prefix).
        argv_list = strip_argv_prefix(argv, cli_prefix)
        config_dict = _partial_config_from_argv(argv_list, config_flag) if config_flag else {}

        config_fns = _collect_fn_paths_from_config(config_dict, target, "", union_tag)
        blob_fns = _collect_fn_paths_from_config(_blob_document_from_argv(argv_list), target, "", union_tag)
        argv_fns = _collect_fn_paths_from_argv(argv_list, target, union_tag)
        existing_names: set[str] = set()
        result: list[FlagSpec] = _escaped_opener_specs(argv_fns, existing_names)
        # Opener flags beat the blob they refine, as the collector's deep merge does.
        for field_flag, (fn_path, mode, bind_key) in {**config_fns, **blob_fns, **argv_fns}.items():
            result.extend(_collect_callable_field_specs(field_flag, fn_path, mode, bind_key, existing_names))
        result.extend(_collect_callable_key_argv_specs(target, argv_list, union_tag, existing_names))
        if config_flag:
            result.extend(_collect_config_argv_specs(argv_list, config_flag))
        result.extend(_collect_patch_argv_specs(target, argv_list, union_tag, config_flag))
    except Exception as exc:  # noqa: BLE001 — best-effort; must not crash populate_parser
        warnings.warn(
            f"Dynamic CLI flag registration failed ({type(exc).__name__}: {exc});"
            " no dynamic flags were registered, so flags discoverable only from argv"
            " (collection patches, '.json' casts, callable bind parameters, scoped"
            f" --{config_flag} flags) may be rejected as unknown.",
            ConfargWarning,
            stacklevel=2,
        )
        return []
    else:
        return apply_prefix(result, cli_prefix)
