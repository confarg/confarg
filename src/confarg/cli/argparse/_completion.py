# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Dynamic tab-completion support for confarg's argparse integration."""

from __future__ import annotations

import contextlib
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import argparse

from confarg import _defaults


def _collect_partial_config(argv: list[str], config_flag: str) -> dict[str, Any]:
    """Scan argv for --<config_flag> FILE tokens and return a merged dict.

    Errors (missing files, parse failures) are silently ignored — this runs
    at shell-completion time and must never crash.
    """
    from confarg._files import _load_file
    from confarg._merge import _deep_merge

    merged: dict[str, Any] = {}
    flag_prefix = f"--{config_flag}"
    i = 0
    while i < len(argv):
        tok = argv[i]
        # Only handle root --config / --config=FILE, not --config.subpath variants
        if tok == flag_prefix:
            # Space-separated form: --config file1 file2 ...
            i += 1
            while i < len(argv) and not argv[i].startswith("--"):
                with contextlib.suppress(Exception):
                    merged = _deep_merge(merged, _load_file(Path(argv[i])))
                i += 1
        elif tok.startswith(f"{flag_prefix}="):
            # Equals form: --config=file
            path_str = tok[len(flag_prefix) + 1 :]
            if path_str:
                with contextlib.suppress(Exception):
                    merged = _deep_merge(merged, _load_file(Path(path_str)))
            i += 1
        else:
            i += 1
    return merged


def _collect_partial_cli_tags(argv: list[str], union_tag: str) -> dict[str, str]:
    """Scan argv for --<prefix>.<union_tag> VALUE tokens.

    Returns {field_prefix: class_path_string}.
    """
    tags: dict[str, str] = {}
    suffix = f".{union_tag}"
    i = 0
    while i < len(argv):
        tok = argv[i]
        if not tok.startswith("--"):
            i += 1
            continue
        if "=" in tok:
            flag, _, val = tok.partition("=")
            flag = flag[2:]  # strip leading --
            if flag.endswith(suffix):
                prefix = flag[: -len(suffix)]
                tags[prefix] = val
        elif tok[2:].endswith(suffix):
            flag = tok[2:]
            prefix = flag[: -len(suffix)]
            if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                tags[prefix] = argv[i + 1]
                i += 2
                continue
        i += 1
    return tags


def _resolve_tags_from_config(
    merged: dict[str, Any],
    dc_type: Any,
    prefix: str,
    union_tag: str,
) -> dict[str, str]:
    """Walk merged config in parallel with dc_type; return {prefix: class_path} for resolved unions."""
    from confarg._types import _is_struct, _is_union, _resolve_type, _struct_fields, _union_args_no_none

    tags: dict[str, str] = {}
    tp = _resolve_type(dc_type)
    if not _is_struct(tp):
        return tags

    try:
        flds = _struct_fields(tp)
    except (ValueError, TypeError, NameError, AttributeError):
        return tags

    for name, ft in flds.items():
        flag = f"{prefix}.{name}" if prefix else name
        resolved = _resolve_type(ft)

        if _is_union(resolved):
            non_none = _union_args_no_none(resolved)
            if len(non_none) > 1:
                sub = merged.get(name)
                if isinstance(sub, dict) and union_tag in sub:
                    val = sub[union_tag]
                    if isinstance(val, str):
                        tags[flag] = val
            elif len(non_none) == 1:
                sub = merged.get(name, {})
                if isinstance(sub, dict):
                    tags.update(_resolve_tags_from_config(sub, _resolve_type(non_none[0]), flag, union_tag))
        elif _is_struct(resolved):
            sub = merged.get(name, {})
            if isinstance(sub, dict):
                tags.update(_resolve_tags_from_config(sub, resolved, flag, union_tag))

    return tags


@dataclass
class _WalkCtx:
    """Shared state threaded through recursive completion-walk calls."""

    parser: argparse.ArgumentParser
    union_tag: str
    existing_dests: set[str] = field(default_factory=set)


def _extend_walk(  # noqa: PLR0912 PLR0915
    dc_type: Any,
    ctx: _WalkCtx,
    group_target: argparse.ArgumentParser | argparse._ArgumentGroup,
    prefix: str,
    *,
    concrete: bool = False,
) -> None:
    """Register fields of dc_type under prefix, skipping already-registered dests."""
    from confarg._types import (
        _final_inner,
        _is_callable,
        _is_dict,
        _is_final,
        _is_struct,
        _resolve_type,
        _struct_defaults,
        _union_args_no_none,
        _unwrap_optional,
        _var_param_names,
    )
    from confarg.cli.argparse._build import _resolve_struct
    from confarg.cli.argparse._register import _add_leaf_argument, _add_union_tag_argument
    from confarg.cli.argparse._spec import _build_help, _get_field_docstrings

    setup = _resolve_struct(dc_type)
    if setup is None:
        return
    tp, flds, hints = setup

    var_params = _var_param_names(tp)
    docstrings = _get_field_docstrings(tp)
    defaults = _struct_defaults(tp)

    for name in flds:
        if name == ctx.union_tag or name in var_params:
            continue

        raw_type = hints.get(name, Any)
        resolved = _resolve_type(raw_type)
        flag = f"{prefix}.{name}" if prefix else name

        core = _unwrap_optional(resolved)
        if core is None:
            # Multi-variant union: register its class-tag flag if not already present
            non_none = _union_args_no_none(resolved)
            dest = f"{flag}.{ctx.union_tag}"
            if dest not in ctx.existing_dests:
                concrete_variants = [_resolve_type(v) for v in non_none if _is_struct(_resolve_type(v))]
                _add_union_tag_argument(group_target, flag, ctx.union_tag, concrete_variants)
                ctx.existing_dests.add(dest)
            continue

        if _is_final(core):
            if concrete:
                continue  # class already selected — Final value is determined by the class
            core = _final_inner(core)

        if _is_callable(core):
            if flag not in ctx.existing_dests:
                help_text = _build_help(name, raw_type, docstrings, defaults, flag=flag)
                _add_leaf_argument(group_target, flag, raw_type, core, help_text)
                ctx.existing_dests.add(flag)
            from confarg.cli.argparse._register import _add_callable_fn_flags

            _add_callable_fn_flags(group_target, flag)
            ctx.existing_dests.update({f"{flag}.fn", f"{flag}.class"})
            continue

        if _is_struct(core):
            # Find or create argument group
            existing_titles = {g.title for g in ctx.parser._action_groups}
            if flag not in existing_titles:
                import inspect as _inspect

                new_group = ctx.parser.add_argument_group(flag, _inspect.getdoc(core) or "")
            else:
                new_group = next(g for g in ctx.parser._action_groups if g.title == flag)
            _extend_walk(core, ctx, new_group, flag, concrete=concrete)
            continue

        if _is_dict(core):
            continue

        if flag not in ctx.existing_dests:
            help_text = _build_help(name, raw_type, docstrings, defaults, flag=flag)
            _add_leaf_argument(group_target, flag, raw_type, core, help_text)
            ctx.existing_dests.add(flag)


def _pre_extend_parser_for_completion(
    parser: argparse.ArgumentParser,
    dc_type: Any,
    union_tag: str,
    config_flag: str,
    argv: list[str],
) -> None:
    """Extend parser with variant-specific flags for any union fields whose class tag is known.

    Reads class tags from config files listed in argv and from explicit --<field>.class argv
    tokens, then imports each resolved class and registers its fields onto the parser.
    All errors are silently swallowed — this must never crash a completion invocation.
    """
    from confarg._callable import _import_dotted
    from confarg._types import _is_struct, _resolve_type

    try:
        config_dict = _collect_partial_config(argv, config_flag)
        cli_tags = _collect_partial_cli_tags(argv, union_tag)
        config_tags = _resolve_tags_from_config(config_dict, dc_type, prefix="", union_tag=union_tag)

        # CLI wins over config
        all_tags = {**config_tags, **cli_tags}

        walk_ctx = _WalkCtx(parser=parser, union_tag=union_tag, existing_dests={a.dest for a in parser._actions})

        for field_prefix, class_path in all_tags.items():
            try:
                cls = _import_dotted(class_path)
                if not isinstance(cls, type) or not _is_struct(_resolve_type(cls)):
                    continue
                _extend_walk(cls, walk_ctx, parser, field_prefix, concrete=True)
            except Exception:  # noqa: BLE001 — completion must never crash; any import/argparse failure is non-fatal
                continue

        from confarg.cli.argparse._build import _collect_fn_paths_from_argv, _collect_fn_paths_from_config
        from confarg.cli.argparse._register import _add_callable_bind_flags

        config_fns = _collect_fn_paths_from_config(config_dict, dc_type, "", union_tag)
        argv_fns = _collect_fn_paths_from_argv(argv)
        for field_flag, fn_path in {**config_fns, **argv_fns}.items():
            try:
                _add_callable_bind_flags(parser, field_flag, fn_path, walk_ctx.existing_dests)
            except Exception:  # noqa: BLE001 — completion must never crash
                continue

    except Exception:  # noqa: BLE001 — completion must never crash; failure here silently degrades suggestions
        pass


def setup_completion(
    parser: argparse.ArgumentParser,
    dc_type: Any,
    *,
    union_tag: str = _defaults.UNION_TAG,
    config_flag: str = "config",
    argv: list[str] | None = None,
) -> None:
    """Enable tab-completion for the parser.

    Must be called after :func:`~confarg.cli.argparse.populate_parser` and before
    ``parser.parse_args()``.  Requires the ``argcomplete`` package::

        pip install confarg[completion]

    Also requires one-time shell setup::

        eval "$(register-python-argcomplete <your-script>)"

    When a union field's concrete class is determinable — either from a
    ``--config`` file listed in the current command line or from a
    ``--<field>.class`` flag — this function extends the parser with that
    class's fields so the shell can offer them as completions.

    In a normal (non-completion) run ``argcomplete.autocomplete`` returns
    immediately, making this call a no-op with negligible overhead.

    Args:
        parser: The :class:`~argparse.ArgumentParser` previously populated by
            :func:`~confarg.cli.argparse.populate_parser`.
        dc_type: The top-level dataclass type (same as passed to
            :func:`~confarg.cli.argparse.populate_parser`).
        union_tag: Discriminator field name (default ``"class"``).
        config_flag: Config file flag name (default ``"config"``).
        argv: CLI argument list.  Defaults to ``sys.argv[1:]``.

    Raises:
        ImportError: If ``argcomplete`` is not installed.
    """
    try:
        import argcomplete
    except ImportError:
        msg = "Tab-completion requires 'argcomplete'. Install with: pip install confarg[completion]"
        raise ImportError(msg) from None

    if argv is None:
        argv = sys.argv[1:]

    _pre_extend_parser_for_completion(parser, dc_type, union_tag, config_flag, argv)
    argcomplete.autocomplete(parser)
