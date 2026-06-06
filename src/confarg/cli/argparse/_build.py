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
from typing import TYPE_CHECKING, Any, get_type_hints

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

from confarg import _defaults
from confarg._callable import _detect_owning_class
from confarg._files import _load_file
from confarg._import import _import_dotted
from confarg._merge import _deep_merge
from confarg._types import (
    _callable_return_type,
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
    _resolve_type,
    _struct_defaults,
    _struct_fields,
    _tuple_types,
    _union_args_no_none,
    _unwrap_optional,
    _var_param_names,
)
from confarg.cli.argparse._spec import FlagSpec, _build_help, _get_field_docstrings, _get_field_meta
from confarg.exceptions import SymbolImportError
from confarg.typedload._coerce import _NONE_TOKENS, _enum_choices, _is_registered_leaf

_SCALAR_CAST_TYPES: frozenset[type] = frozenset({str, int, float, bool})


def _scalar_cast_types_in_union(resolved: Any) -> list[type]:
    """Return scalar types to offer as explicit cast flags for a multi-variant union.

    Returns non-empty only when the union has at least one enum variant and at least
    one scalar (str, int, float, bool) variant — the combination where stealing-rule
    disambiguation is non-obvious and an explicit cast escape-hatch is useful.
    """
    non_none = _union_args_no_none(resolved)
    types = [_resolve_type(v) for v in non_none]
    has_enum = any(_is_enum(t) for t in types)
    if not has_enum:
        return []
    return [t for t in types if t in _SCALAR_CAST_TYPES]


def _literal_cli_choices(vals: tuple[Any, ...]) -> list[str]:
    """Map Literal members to their accepted CLI strings."""
    choices: list[str] = []
    for v in vals:
        if v is None:
            choices.extend(sorted(_NONE_TOKENS))
        else:
            choices.append(str(v))
    return choices


def _resolve_struct(
    target: Any,
) -> tuple[Any, dict[str, Any], dict[str, Any]] | None:
    """Resolve a struct type to (tp, fields, hints), or None if not a struct."""
    tp = _resolve_type(target)
    if not _is_struct(tp):
        return None
    try:
        flds = _struct_fields(tp)
    except (ValueError, TypeError, NameError, AttributeError):
        return None
    try:
        hints = get_type_hints(tp, include_extras=True)
    except (NameError, AttributeError, TypeError):
        hints = {name: flds[name] for name in flds}
    return tp, flds, hints


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


def _build_callable_fn_specs(
    flag: str,
    group: str | None,
    group_description: str,
) -> list[FlagSpec]:
    """Build FlagSpecs for ``--<flag>.fn``, ``--<flag>.class``, ``--<flag>.call``."""
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


def _collect_callable_bind_specs(
    field_flag: str,
    fn_path: str,
    existing_names: set[str],
) -> list[FlagSpec]:
    """Build FlagSpecs for ``--<field_flag>.bind.<param>`` by inspecting the target's signature."""
    try:
        obj = _import_dotted(fn_path)
    except SymbolImportError:
        return []

    try:
        target_obj = obj.__init__ if isinstance(obj, type) else obj
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
        dest = f"{field_flag}.bind.{param_name}"
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
    existing_names: set[str],
) -> list[FlagSpec]:
    """Build bind/factory FlagSpecs for one callable field given its fn_path and mode."""
    if mode == "class":
        try:
            cls = _import_dotted(fn_path)
            if isinstance(cls, type):
                return _collect_callable_factory_specs(field_flag, cls, existing_names)
        except SymbolImportError:
            pass
    elif mode == "call":
        return _collect_callable_bind_specs(field_flag, fn_path, existing_names)
    else:  # mode == "fn"
        try:
            obj = _import_dotted(fn_path)
            if isinstance(obj, type):
                return _collect_callable_factory_specs(field_flag, obj, existing_names)
            owning_cls = _detect_owning_class(obj)
            if owning_cls is not None:
                return _collect_callable_factory_specs(field_flag, owning_cls, existing_names)
        except SymbolImportError:
            pass
    return _collect_callable_bind_specs(field_flag, fn_path, existing_names)


def _get_callable_field_return_type(target: Any, flag: str) -> Any | None:
    """Return the Callable return type for the field at the given dot-separated flag path."""
    parts = flag.split(".")
    tp = _resolve_type(target)
    for part in parts:
        if not _is_struct(tp):
            return None
        flds = _struct_fields(tp)
        if part not in flds:
            return None
        tp = _resolve_type(flds[part])
        unwrapped = _unwrap_optional(tp)
        if unwrapped is None:
            return None
        tp = unwrapped
    if not _is_callable(tp):
        return None
    return _callable_return_type(tp)


def _collect_fn_paths_from_argv(argv: Sequence[str]) -> dict[str, tuple[str, str]]:
    """Scan argv for --<field>.fn or --<field>.class tokens.

    Returns {field_flag: (fn_path, mode)} where mode is "fn", "class", or "call".
    CLI wins for duplicate keys.
    """
    result: dict[str, tuple[str, str]] = {}
    i = 0
    while i < len(argv):
        tok = argv[i]
        if not tok.startswith("--"):
            i += 1
            continue
        if "=" in tok:
            key, _, val = tok[2:].partition("=")
            for suffix in (".fn", ".class", ".call"):
                if key.endswith(suffix) and len(key) > len(suffix):
                    result[key[: -len(suffix)]] = (val, suffix[1:])
                    break
            i += 1
        else:
            key = tok[2:]
            for suffix in (".fn", ".class", ".call"):
                if key.endswith(suffix) and len(key) > len(suffix):
                    field_flag = key[: -len(suffix)]
                    if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                        result[field_flag] = (argv[i + 1], suffix[1:])
                        i += 2
                    else:
                        i += 1
                    break
            else:
                i += 1
    return result


def _callable_fn_path(sub: Any) -> tuple[str, str] | None:
    """Return (path, mode) from a callable's config sub-value, or None if not present.

    Checks string shorthand (implicit "fn") and dict keys "fn", "class", "call".
    """
    if isinstance(sub, str):
        return (sub, "fn")
    if isinstance(sub, dict):
        for key, mode in (("fn", "fn"), ("class", "class"), ("call", "call")):
            if isinstance(sub.get(key), str):
                return (sub[key], mode)
    return None


def _collect_fn_paths_from_config(
    config_dict: dict[str, Any],
    target: Any,
    prefix: str,
    union_tag: str,
) -> dict[str, tuple[str, str]]:
    """Walk target + config_dict to find fn/class values for Callable fields.

    Returns {field_flag: (fn_path, mode)} where mode is "fn", "class", or "call".
    """
    result: dict[str, tuple[str, str]] = {}
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
            return [_build_union_tag_spec(flag, union_tag, concrete, group, group_description)]
        cast_types = _scalar_cast_types_in_union(resolved)
        if cast_types:
            help_text = _build_help(name, raw_type, docstrings, defaults, flag=flag)
            result: list[FlagSpec] = [
                FlagSpec(name=flag, metavar="VALUE", help=help_text, group=group, group_description=group_description),
            ]
            for tp in cast_types:
                cast_name = tp.__name__
                result.append(
                    FlagSpec(
                        name=f"{flag}.{cast_name}",
                        metavar=cast_name.upper(),
                        help=f"Force {cast_name!r} type for '{flag}' (bypasses enum stealing).",
                        group=group,
                        group_description=group_description,
                    ),
                )
            return result
        return []

    if _is_final(core):
        core = _final_inner(core)

    if _is_callable(core):
        help_text = _build_help(name, raw_type, docstrings, defaults, flag=flag)
        specs: list[FlagSpec] = [_build_leaf_spec(flag, raw_type, core, help_text, group, group_description)]
        specs.extend(_build_callable_fn_specs(flag, group, group_description))
        ret = _callable_return_type(core)
        if ret is not None and isinstance(ret, type) and _is_struct(ret):
            existing: set[str] = {s.name for s in specs}
            specs.extend(_collect_callable_factory_specs(flag, ret, existing, group, group_description))
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
    for variant in variants:
        result.extend(
            _collect_struct_specs(
                variant,
                prefix,
                union_tag,
                group=variant.__name__,
                group_description=inspect.getdoc(variant) or "",
            ),
        )
    return result


def _collect_struct_specs(  # noqa: C901  # union-root branch added one more conditional
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
        existing_names: set[str] = {s.name for s in result}
        if tag_name not in existing_names:
            paths = [f"{v.__module__}.{v.__qualname__}" for v in all_subs]
            result.append(
                FlagSpec(
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
                ),
            )
            existing_names.add(tag_name)
        for sub in direct_subs:
            for spec in _collect_struct_specs(sub, prefix, union_tag, group, group_description):
                if spec.name not in existing_names:
                    result.append(spec)
                    existing_names.add(spec.name)

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
    target: type,
    *,
    union_tag: str = _defaults.UNION_TAG,
    config_flag: str = "config",
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


def build_dynamic_flags(
    target: type,
    argv: Sequence[str],
    *,
    union_tag: str = _defaults.UNION_TAG,
    config_flag: str = "config",
) -> list[FlagSpec]:
    """Build CLI flags discoverable only from argv (callable bind/factory args).

    Scans ``argv`` and any config files it references for ``--<field>.fn``,
    ``--<field>.class``, and ``--<field>.call`` tokens.  For each found path, imports
    the target and generates :class:`~confarg.cli.argparse.FlagSpec` objects for its
    parameters (bind kwargs or factory constructor args).

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
        result: list[FlagSpec] = []
        for field_flag, (fn_path, mode) in {**config_fns, **argv_fns}.items():
            result.extend(_collect_callable_field_specs(field_flag, fn_path, mode, existing_names))
    except Exception:  # noqa: BLE001 — best-effort; must not crash populate_parser
        return []
    else:
        return result
