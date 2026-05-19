# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Argparse integration for confarg."""

from __future__ import annotations

import argparse
import ast
import contextlib
import dataclasses
import inspect
import os
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any, get_type_hints

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

from confarg import _defaults
from confarg._errors import SymbolImportError
from confarg._files import _load_file
from confarg._merge import _deep_merge, _set_nested
from confarg._parse_env import _parse_env
from confarg._types import (
    _allows_none,
    _callable_return_type,
    _elem_type,
    _is_bool,
    _is_callable,
    _is_dict,
    _is_enum,
    _is_literal,
    _is_struct,
    _is_tuple,
    _is_type_ref,
    _is_varlen_collection,
    _literal_values,
    _resolve_type,
    _StrToken,
    _struct_defaults,
    _struct_fields,
    _tuple_types,
    _union_args_no_none,
    _unwrap_optional,
    _var_param_names,
)
from confarg.dictexpr import resolve_expressions
from confarg.typedload import construct


@dataclasses.dataclass
class FieldMeta:
    """Optional per-field metadata for argparse integration.

    Attach via ``Annotated``::

        from typing import Annotated
        from confarg import FieldMeta

        @dataclass
        class Config:
            port: Annotated[int, FieldMeta(help="TCP port.", metavar="PORT")]
            \"\"\"Fallback docstring (FieldMeta.help takes precedence).\"\"\"
    """

    help: str | None = None
    metavar: str | None = None


def _get_field_meta(raw_type: Any) -> FieldMeta | None:
    """Return FieldMeta from Annotated[T, FieldMeta(...)] annotation, or None."""
    from typing import Annotated, get_args, get_origin

    if get_origin(raw_type) is Annotated:
        for arg in get_args(raw_type)[1:]:
            if isinstance(arg, FieldMeta):
                return arg
    return None


def _get_field_docstrings(dc_type: type) -> dict[str, str]:
    """Extract attribute docstrings (string literals after field defs) via AST.

    For each annotated field in the class body, if the immediately following
    statement is a string constant, that string is treated as the field's
    docstring.  Returns an empty dict when source is unavailable (e.g.
    dynamically created classes).
    """
    try:
        source = inspect.getsource(dc_type)
        source = textwrap.dedent(source)
        tree = ast.parse(source)
    except (OSError, TypeError, IndentationError, SyntaxError):
        return {}

    for node in ast.walk(tree):
        if not (isinstance(node, ast.ClassDef) and node.name == dc_type.__name__):
            continue
        result: dict[str, str] = {}
        stmts = node.body
        for i, stmt in enumerate(stmts):
            if not (isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)):
                continue
            if i + 1 >= len(stmts):
                continue
            next_stmt = stmts[i + 1]
            if (
                isinstance(next_stmt, ast.Expr)
                and isinstance(next_stmt.value, ast.Constant)
                and isinstance(next_stmt.value.value, str)
            ):
                result[stmt.target.id] = inspect.cleandoc(next_stmt.value.value)
        return result
    return {}


def _build_help(
    field_name: str,
    raw_type: Any,
    docstrings: dict[str, str],
    defaults: dict[str, Any],
    flag: str = "",
) -> str:
    """Compose the argparse help string for one field.

    Priority: FieldMeta.help > attribute docstring > empty string.
    If the field has a dataclass default, appends ``(default: <repr>)``.
    If the field is Optional, appends a hint about the None sentinel.
    """
    meta = _get_field_meta(raw_type)
    base = meta.help if meta is not None and meta.help is not None else docstrings.get(field_name, "")

    if field_name in defaults:
        suffix = f"(default: {defaults[field_name]!r})"
        base = f"{base} {suffix}".strip() if base else suffix

    if flag and _allows_none(_resolve_type(raw_type)) and _union_args_no_none(_resolve_type(raw_type)):
        none_hint = "(pass 'none' or 'null' to set to None)"
        base = f"{base} {none_hint}".strip() if base else none_hint

    return base


def _add_leaf_argument(
    target: argparse.ArgumentParser | argparse._ArgumentGroup,
    flag: str,
    raw_type: Any,
    core: Any,
    help_text: str,
) -> None:
    """Register a single leaf field as an argparse argument."""
    meta = _get_field_meta(raw_type)
    metavar: str | None = meta.metavar if meta is not None else None

    common: dict[str, Any] = {
        "dest": flag,
        "default": argparse.SUPPRESS,
        "help": help_text,
    }

    if _is_bool(core):
        target.add_argument(f"--{flag}", type=str, metavar="true|false", **common)
        return

    if _is_varlen_collection(core):
        et = _resolve_type(_elem_type(core))
        target.add_argument(
            f"--{flag}",
            nargs="*",
            type=str,
            metavar=metavar or getattr(et, "__name__", "ITEM").upper(),
            **common,
        )
        return

    if _is_tuple(core):
        tt = _tuple_types(core)
        if tt is not None:
            target.add_argument(
                f"--{flag}",
                nargs=len(tt),
                type=str,
                metavar=metavar or "VALUE",
                **common,
            )
        else:  # pragma: no cover
            # tuple[X, ...] — variable length (unreachable: caught by _is_varlen_collection above)
            et = _resolve_type(_elem_type(core))
            target.add_argument(
                f"--{flag}",
                nargs="*",
                type=str,
                metavar=metavar or getattr(et, "__name__", "ITEM").upper(),
                **common,
            )
        return

    if _is_literal(core):
        target.add_argument(
            f"--{flag}",
            choices=[str(v) for v in _literal_values(core)],
            type=str,
            **common,
        )
        return

    if _is_enum(core):
        target.add_argument(
            f"--{flag}",
            choices=[e.name for e in core],
            type=str,
            metavar=metavar or flag.rsplit(".", 1)[-1].upper(),
            **common,
        )
        return

    if _is_type_ref(core):
        target.add_argument(
            f"--{flag}",
            type=str,
            metavar=metavar or "DOTTED.CLASS.PATH",
            **common,
        )
        return

    # Generic scalar (str, int, float, Path, …)
    type_name = getattr(core, "__name__", "VALUE").upper()
    target.add_argument(
        f"--{flag}",
        type=str,
        metavar=metavar or type_name,
        **common,
    )


def _add_callable_fn_flags(
    target: argparse.ArgumentParser | argparse._ArgumentGroup,
    flag: str,
) -> None:
    """Register --<flag>.fn, --<flag>.class, and --<flag>.call as discrete string flags."""
    for sub, desc in (
        ("fn", "function or class; classes get functools.partial with bind kwargs"),
        ("class", "class to instantiate; the resulting instance is the callable"),
        ("call", "factory function to call; result is used as the callable field value"),
    ):
        target.add_argument(
            f"--{flag}.{sub}",
            dest=f"{flag}.{sub}",
            type=str,
            default=argparse.SUPPRESS,
            metavar="DOTTED.PATH",
            help=f"Dotted import path for the '{flag}' callable ({desc}).",
        )


def _add_callable_bind_flags(
    parser: argparse.ArgumentParser,
    flag: str,
    fn_path: str,
    existing_dests: set[str] | None = None,
) -> None:
    """Register --<flag>.bind.<param> flags by inspecting the target's signature.

    Silently does nothing when the signature is uninspectable (C extensions).
    """
    from confarg._callable import _import_dotted

    try:
        obj = _import_dotted(fn_path)
    except SymbolImportError:
        return

    try:
        target_obj = obj.__init__ if isinstance(obj, type) else obj
        sig = inspect.signature(target_obj)
    except (ValueError, TypeError):
        return

    if existing_dests is None:
        existing_dests = {a.dest for a in parser._actions}

    existing_titles = {g.title for g in parser._action_groups}
    if flag in existing_titles:
        group: argparse.ArgumentParser | argparse._ArgumentGroup = next(
            g for g in parser._action_groups if g.title == flag
        )
    else:
        group = parser.add_argument_group(flag, f"Bind arguments for callable '{flag}'")

    for param_name, param in sig.parameters.items():
        if param_name == "self":
            continue
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        dest = f"{flag}.bind.{param_name}"
        if dest in existing_dests:
            continue
        help_parts = []
        ann = param.annotation
        if ann is not inspect.Parameter.empty:
            help_parts.append(getattr(ann, "__name__", repr(ann)))
        if param.default is not inspect.Parameter.empty:
            help_parts.append(f"default: {param.default!r}")
        with contextlib.suppress(Exception):
            group.add_argument(
                f"--{dest}",
                dest=dest,
                type=str,
                default=argparse.SUPPRESS,
                metavar=param_name.upper(),
                help=", ".join(help_parts),
            )
        existing_dests.add(dest)


def _add_callable_factory_flags(
    target: argparse.ArgumentParser | argparse._ArgumentGroup,
    flag: str,
    cls: type,
    existing_dests: set[str] | None = None,
) -> None:
    """Register --<flag>.<param> flags for factory-mode constructor kwargs."""
    from confarg._types import _init_defaults, _init_fields

    try:
        fields = _init_fields(cls)
        defaults = _init_defaults(cls)
    except (ValueError, TypeError, NameError, AttributeError):
        return

    if existing_dests is None:
        existing_dests = set()

    for param_name, ft in fields.items():
        dest = f"{flag}.{param_name}"
        if dest in existing_dests:
            continue
        core_ft = _resolve_type(ft)
        help_parts: list[str] = []
        type_name = getattr(core_ft, "__name__", repr(core_ft))
        if type_name and type_name != "Any":
            help_parts.append(type_name)
        if param_name in defaults:
            help_parts.append(f"default: {defaults[param_name]!r}")
        with contextlib.suppress(Exception):
            _add_leaf_argument(target, dest, ft, core_ft, ", ".join(help_parts))
        existing_dests.add(dest)


def _get_callable_field_return_type(dc_type: Any, flag: str) -> Any | None:
    """Return the Callable return type for the field at the given dot-separated flag path."""
    parts = flag.split(".")
    tp = _resolve_type(dc_type)
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

    Returns {field_flag: (fn_path, mode)} where mode is "fn" or "class".
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


def _collect_fn_paths_from_config(
    config_dict: dict[str, Any],
    dc_type: Any,
    prefix: str,
    union_tag: str,
) -> dict[str, tuple[str, str]]:
    """Walk dc_type + config_dict to find fn/class values for Callable fields.

    Returns {field_flag: (fn_path, mode)} where mode is "fn" or "class".
    """
    result: dict[str, tuple[str, str]] = {}
    tp = _resolve_type(dc_type)
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
            sub = config_dict.get(name)
            if isinstance(sub, dict):
                fn_val = sub.get("fn")
                cls_val = sub.get("class")
                call_val = sub.get("call")
                if isinstance(fn_val, str):
                    result[flag] = (fn_val, "fn")
                elif isinstance(cls_val, str):
                    result[flag] = (cls_val, "class")
                elif isinstance(call_val, str):
                    result[flag] = (call_val, "call")
            elif isinstance(sub, str):
                result[flag] = (sub, "fn")
        elif _is_struct(resolved):
            sub = config_dict.get(name, {})
            if isinstance(sub, dict):
                result.update(_collect_fn_paths_from_config(sub, resolved, flag, union_tag))
    return result


def _register_callable_flags_for_field(
    parser: argparse.ArgumentParser,
    field_flag: str,
    fn_path: str,
    mode: str,
    existing_dests: set[str],
) -> None:
    """Register bind/factory flags for one callable field given its fn_path and mode."""
    if mode == "class":
        try:
            from confarg._callable import _import_dotted

            cls = _import_dotted(fn_path)
            if isinstance(cls, type):
                _add_callable_factory_flags(parser, field_flag, cls, existing_dests)
                return
        except SymbolImportError:
            pass
    elif mode == "call":
        _add_callable_bind_flags(parser, field_flag, fn_path, existing_dests)
        return
    else:  # mode == "fn"
        try:
            from confarg._callable import _detect_owning_class, _import_dotted

            obj = _import_dotted(fn_path)
            if isinstance(obj, type):
                _add_callable_factory_flags(parser, field_flag, obj, existing_dests)
                return
            owning_cls = _detect_owning_class(obj)
            if owning_cls is not None:
                _add_callable_factory_flags(parser, field_flag, owning_cls, existing_dests)
                return
        except SymbolImportError:
            pass
    _add_callable_bind_flags(parser, field_flag, fn_path, existing_dests)


def _extend_callable_flags(
    parser: argparse.ArgumentParser,
    dc_type: Any,
    argv: Sequence[str],
    config_flag: str,
    union_tag: str,
) -> None:
    """Pre-parse argv/config to find Callable fn paths, then register bind flags.

    Errors are silently ignored — this is a best-effort enhancement.
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

        config_fns = _collect_fn_paths_from_config(config_dict, dc_type, "", union_tag)
        argv_fns = _collect_fn_paths_from_argv(argv_list)
        existing_dests = {a.dest for a in parser._actions}
        for field_flag, (fn_path, mode) in {**config_fns, **argv_fns}.items():
            _register_callable_flags_for_field(parser, field_flag, fn_path, mode, existing_dests)
    except Exception:  # noqa: BLE001 — best-effort enhancement, must not crash populate_parser
        pass


def _add_union_tag_argument(
    target: argparse.ArgumentParser | argparse._ArgumentGroup,
    flag: str,
    union_tag: str,
    variant_types: list[Any],
) -> None:
    """Register --<flag>.<union_tag> for dynamic class dispatch.

    Attaches a .completer attribute listing known variant class paths so that
    argcomplete (if installed) can suggest them without requiring an import here.
    """
    dest = f"{flag}.{union_tag}"
    action = target.add_argument(
        f"--{dest}",
        type=str,
        dest=dest,
        default=argparse.SUPPRESS,
        metavar="DOTTED.CLASS.PATH",
        help=(
            f"Fully-qualified class path selecting the variant for '{flag}' "
            f"(e.g. mypackage.MyClass). "
            f"Once set, use --{flag}.<field> flags for that class's fields."
        ),
    )
    if variant_types:
        paths = [f"{v.__module__}.{v.__qualname__}" for v in variant_types]
        action.completer = lambda prefix, parsed_args, **kw: [p for p in paths if p.startswith(prefix)]


def _resolve_struct(
    dc_type: Any,
) -> tuple[Any, dict[str, Any], dict[str, Any]] | None:
    """Resolve a struct type to (tp, fields, hints_with_extras), or None if not a struct."""
    tp = _resolve_type(dc_type)
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


def _walk_struct(
    dc_type: Any,
    parser: argparse.ArgumentParser,
    group_target: argparse.ArgumentParser | argparse._ArgumentGroup,
    prefix: str,
    union_tag: str,
) -> None:
    """Recursively register dataclass fields onto parser / argument groups.

    Each nested dataclass creates its own named group (for --help grouping).
    Leaf fields are registered on ``group_target``.  Dict-typed fields and
    multi-variant union fields are silently skipped.
    """
    setup = _resolve_struct(dc_type)
    if setup is None:
        return
    tp, flds, hints = setup
    var_params = _var_param_names(tp)
    docstrings = _get_field_docstrings(tp)
    defaults = _struct_defaults(tp)

    for name in flds:
        if name == union_tag or name in var_params:
            continue

        raw_type = hints.get(name, Any)
        resolved = _resolve_type(raw_type)
        flag = f"{prefix}.{name}" if prefix else name

        core = _unwrap_optional(resolved)
        if core is None:
            # Multi-variant union: register class-tag flag only when struct variants exist
            non_none = _union_args_no_none(resolved)
            concrete = [_resolve_type(v) for v in non_none if _is_struct(_resolve_type(v))]
            if concrete:
                _add_union_tag_argument(group_target, flag, union_tag, concrete)
            continue

        if _is_callable(core):
            help_text = _build_help(name, raw_type, docstrings, defaults, flag=flag)
            _add_leaf_argument(group_target, flag, raw_type, core, help_text)
            _add_callable_fn_flags(group_target, flag)
            ret = _callable_return_type(core)
            if ret is not None and isinstance(ret, type) and _is_struct(ret):
                existing = (
                    {a.dest for a in group_target._group_actions} if hasattr(group_target, "_group_actions") else set()
                )
                _add_callable_factory_flags(group_target, flag, ret, existing)
            continue

        if _is_struct(core):
            group_desc = inspect.getdoc(core) or ""
            new_group = parser.add_argument_group(flag, group_desc)
            _walk_struct(core, parser, new_group, flag, union_tag)
            continue

        if _is_dict(core):
            # Keys unknown at registration time; skip
            continue

        help_text = _build_help(name, raw_type, docstrings, defaults, flag=flag)
        _add_leaf_argument(group_target, flag, raw_type, core, help_text)


def _register_subconfig_flags(
    dc_type: Any,
    parser: argparse.ArgumentParser,
    config_flag: str,
    prefix: str,
    union_tag: str,
) -> None:
    """Recursively register --<config_flag>.<subpath> flags for nested structs."""
    setup = _resolve_struct(dc_type)
    if setup is None:
        return
    _tp, flds, hints = setup

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

        parser.add_argument(
            f"--{config_flag}.{subpath}",
            nargs="*",
            metavar="FILE",
            dest=f"{config_flag}.{subpath}",
            default=argparse.SUPPRESS,
            help=(
                f"Config file(s) whose contents are merged under the '{subpath}' field. "
                f"Equivalent to a root config file with a top-level '{subpath}' key. "
                "Supports TOML, YAML, and JSON."
            ),
        )
        _register_subconfig_flags(core, parser, config_flag, subpath, union_tag)


def populate_parser(
    dc_type: type,
    parser: argparse.ArgumentParser,
    *,
    union_tag: str = _defaults.UNION_TAG,
    config_flag: str = "config",
    argv: Sequence[str] | None = None,
) -> None:
    """Register fields of a dataclass type as arguments on an ArgumentParser.

    Field types, defaults, and attribute docstrings are read automatically.
    For richer control, annotate individual fields with :class:`FieldMeta`::

        port: Annotated[int, FieldMeta(help="TCP port.", metavar="PORT")]

    All confarg arguments use ``default=argparse.SUPPRESS``, so fields absent
    from the command line do not appear in the resulting Namespace.  This makes
    it straightforward to compose with :func:`from_namespace` for config-file
    and env-var sources.

    A ``--<config_flag>`` argument (default ``--config``) is also registered so
    users can pass one or more TOML/YAML config files on the command line.
    Pass ``config_flag=""`` to suppress it.

    **Skipped fields:**

    - ``dict``-typed fields (keys are unknown at registration time).
    - Multi-variant union fields (ambiguous argparse type mapping).

    Args:
        dc_type: The dataclass type whose fields to register.
        parser: The :class:`argparse.ArgumentParser` to populate.
        union_tag: Name of the union discriminator field to skip (matches
            the ``union_tag`` parameter of :func:`from_namespace`).
        config_flag: Name of the config-file flag (default ``"config"``).
            Set to ``""`` to disable config-file argument registration.
        argv: CLI argument list used to pre-resolve ``--<field>.fn`` / ``--<field>.class``
            values so that callable ``--<field>.bind.*`` flags can be registered
            before :meth:`~argparse.ArgumentParser.parse_args` is called.
            Has no effect on which config-source flags are registered.
    """
    _walk_struct(dc_type, parser, parser, prefix="", union_tag=union_tag)
    if config_flag:
        parser.add_argument(
            f"--{config_flag}",
            nargs="*",
            metavar="FILE",
            dest=config_flag,
            default=argparse.SUPPRESS,
            help=(
                "Config file(s) to merge at lowest priority (below env vars and CLI flags). "
                "Multiple files are merged left-to-right; later files override earlier ones. "
                "Supports TOML, YAML, and JSON. "
                f"Use --{config_flag}.<field> FILE to scope a file's contents under a specific field "
                f"(e.g. --{config_flag}.db db.toml merges db.toml as if its keys were nested under 'db')."
            ),
        )
        _register_subconfig_flags(dc_type, parser, config_flag, prefix="", union_tag=union_tag)
    if argv is not None:
        _extend_callable_flags(parser, dc_type, argv, config_flag, union_tag)


def _str_token(v: Any) -> Any:
    """Wrap str in _StrToken; pass through non-str unchanged."""
    return _StrToken(v) if isinstance(v, str) else v


def _merge_blob_into_spec(blob: dict[str, Any], spec: dict[str, Any], bind: dict[str, Any]) -> dict[str, Any]:
    """Merge a pre-existing blob dict with the newly assembled spec, combining bind entries."""
    merged = {**blob, **{k: v for k, v in spec.items() if k != "bind"}}
    blob_bind = blob.get("bind", {})
    if isinstance(blob_bind, dict) and bind:
        merged["bind"] = {**blob_bind, **bind}
    elif bind:
        merged["bind"] = bind
    return merged


def _collect_callable_spec(
    flat: dict[str, Any],
    flag: str,
    core: Any,
    result: dict[str, Any],
) -> None:
    """Build and store the callable spec dict from flat namespace entries for flag."""
    fn_key = f"{flag}.fn"
    cls_key = f"{flag}.class"
    call_key = f"{flag}.call"
    bind_prefix = f"{flag}.bind."
    flag_prefix = f"{flag}."
    reserved = {fn_key, cls_key, call_key}

    spec: dict[str, Any] = {}
    for src_key, dest_name in ((fn_key, "fn"), (cls_key, "class"), (call_key, "call")):
        if src_key in flat:
            spec[dest_name] = _str_token(flat[src_key])

    bind: dict[str, Any] = {k[len(bind_prefix) :]: _str_token(v) for k, v in flat.items() if k.startswith(bind_prefix)}
    if bind:
        spec["bind"] = bind

    ret = _callable_return_type(core)
    if ret is not None and isinstance(ret, type) and ret is not type(None) or cls_key in flat or fn_key in flat:
        for k, v in flat.items():
            if k.startswith(flag_prefix) and k not in reserved and not k.startswith(bind_prefix):
                tail = k[len(flag_prefix) :]
                if "." not in tail:
                    spec[tail] = _str_token(v)

    if flag in flat:
        blob = flat[flag]
        if isinstance(blob, str) and not spec:
            _set_nested(result, flag.split("."), _StrToken(blob))
            return
        if isinstance(blob, dict):
            spec = _merge_blob_into_spec(blob, spec, bind)

    if spec:
        _set_nested(result, flag.split("."), spec)


def _collect_ns_union_field(
    flat: dict[str, Any],
    flag: str,
    resolved: Any,
    union_tag: str,
    result: dict[str, Any],
) -> None:
    """Handle a multi-variant union field: pick up the class-tag and recurse into the resolved variant."""
    non_none = _union_args_no_none(resolved)
    if not any(_is_struct(_resolve_type(v)) for v in non_none):
        return
    tag_key = f"{flag}.{union_tag}"
    if tag_key not in flat:
        return
    class_tag = flat[tag_key]
    _set_nested(result, [*flag.split("."), union_tag], _str_token(class_tag))
    try:
        from confarg._callable import _import_dotted

        cls = _import_dotted(str(class_tag))
        if isinstance(cls, type) and _is_struct(_resolve_type(cls)):
            _collect_ns_fields(flat, cls, flag, union_tag, result)
    except (SymbolImportError, TypeError, ValueError, NameError, AttributeError):
        pass


def _collect_ns_fields(
    flat: dict[str, Any],
    dc_type: Any,
    prefix: str,
    union_tag: str,
    result: dict[str, Any],
) -> None:
    """Walk dc_type and copy matching flat-namespace entries into nested dict."""
    setup = _resolve_struct(dc_type)
    if setup is None:
        return
    _tp, flds, hints = setup

    for name in flds:
        if name == union_tag:
            continue

        raw_type = hints.get(name, Any)
        resolved = _resolve_type(raw_type)
        flag = f"{prefix}.{name}" if prefix else name

        core = _unwrap_optional(resolved)
        if core is None:
            _collect_ns_union_field(flat, flag, resolved, union_tag, result)
            continue

        if _is_struct(core):
            _collect_ns_fields(flat, core, flag, union_tag, result)
            continue

        if _is_dict(core):
            continue

        if _is_callable(core):
            _collect_callable_spec(flat, flag, core, result)
            continue

        if flag in flat:
            v = flat[flag]
            v = [_str_token(item) for item in v] if isinstance(v, list) else _str_token(v)
            _set_nested(result, flag.split("."), v)


def from_namespace[T](  # noqa: PLR0913
    ns: argparse.Namespace,
    dc_type: type[T],
    *,
    union_tag: str = _defaults.UNION_TAG,
    config_flag: str = "config",
    files: Sequence[str | Path] = (),
    env: Mapping[str, str] | None = None,
    env_prefix: str | None = _defaults.ENV_PREFIX,
    env_separator: str = "__",
) -> T:
    """Construct a dataclass instance from an argparse :class:`~argparse.Namespace`.

    Merges three sources in ascending priority order: config files, environment
    variables, then CLI arguments from the Namespace.  This mirrors the
    behaviour of :func:`confarg.load`.

    Only fields registered by :func:`populate_parser` are consumed from ``ns``.
    Fields absent from the Namespace fall back to env vars, config files, or
    dataclass defaults; missing required fields raise
    :class:`~confarg.MissingFieldError`.

    Args:
        ns: The Namespace returned by ``ArgumentParser.parse_args()``.
        dc_type: The dataclass type to construct.
        union_tag: Discriminator field name (same as :func:`confarg.load`).
        config_flag: Name of the config-file attribute on ``ns`` (default
            ``"config"``).  Must match the ``config_flag`` passed to
            :func:`populate_parser`.  Subkey flags ``--config.<subpath>``
            (registered automatically by :func:`populate_parser`) are also
            consumed.  Set to ``""`` to ignore all config-file attributes.
        files: Additional root-level config file paths to load (lowest priority).
        env: Environment variable mapping.  Defaults to ``os.environ``.
            Pass ``{}`` to disable env-var reading.
        env_prefix: Prefix that env vars must start with. Defaults to ``None``,
            which disables environment variable parsing entirely. Set to ``""``
            to read all env vars without filtering, or to e.g. ``"MYAPP_"`` to
            read only vars with that prefix.
        env_separator: Separator used to split env var names into nested keys.

    Returns:
        An instance of ``dc_type`` populated from all sources.
    """
    if env is None:
        env = os.environ

    # 1. Collect CLI field values from the namespace
    cli_data: dict[str, Any] = {}
    _collect_ns_fields(vars(ns), dc_type, prefix="", union_tag=union_tag, result=cli_data)

    # 2. Collect (subpath, path) pairs for all config files
    #    - explicit files= param → root (subpath "")
    #    - --config file.toml → root
    #    - --config.server file.toml → subpath "server"
    file_pairs: list[tuple[str, Path]] = [("", Path(f)) for f in files]
    if config_flag:
        file_pairs.extend(("", Path(f)) for f in getattr(ns, config_flag, None) or [])
        cfg_prefix = f"{config_flag}."
        for key, val in vars(ns).items():
            if key.startswith(cfg_prefix):
                subpath = key[len(cfg_prefix) :]
                file_pairs.extend((subpath, Path(f)) for f in val or [])

    # 3. Load config files, nesting subpath files under their key
    config_data: dict[str, Any] = {}
    for subpath, fpath in file_pairs:
        fdata = _load_file(fpath)
        if subpath:
            for part in reversed(subpath.split(".")):
                fdata = {part: fdata}
        config_data = _deep_merge(config_data, fdata, union_tag=union_tag)

    # 4. Parse env vars
    if env_prefix is None:
        env_data: dict[str, Any] = {}
        env_configs: list[tuple[str, Path]] = []
    else:
        env_data, env_configs = _parse_env(env, env_prefix, env_separator, dc_type)
    for subpath, fpath in env_configs:
        fdata = _load_file(fpath)
        if subpath:
            for part in reversed(subpath.split(".")):
                fdata = {part: fdata}
        config_data = _deep_merge(config_data, fdata, union_tag=union_tag)

    # 5. Merge: config < env < CLI
    merged = _deep_merge(config_data, env_data, union_tag=union_tag)
    merged = _deep_merge(merged, cli_data, union_tag=union_tag)

    # 6. Resolve expressions
    merged = resolve_expressions(merged)

    # 7. Construct
    return construct(_resolve_type(dc_type), merged, union_tag=union_tag)  # type: ignore[return-value]
