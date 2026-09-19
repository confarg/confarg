# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Dynamic tab-completion support for argparse integration."""

from __future__ import annotations

import inspect
import logging
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import argparse

from confarg import _defaults
from confarg._import import _import_dotted
from confarg._tags import _partial_config_from_argv, _tags_from_argv, _tags_from_config
from confarg._types import (
    _final_inner,
    _is_callable,
    _is_dict,
    _is_final,
    _is_singleton_literal,
    _is_struct,
    _resolve_struct,
    _resolve_type,
    _struct_defaults,
    _union_args_no_none,
    _unwrap_optional,
    _var_params,
)
from confarg.cli._build import (
    _build_callable_fn_specs,
    _build_leaf_spec,
    _build_union_tag_spec,
    _collect_callable_bind_specs,
    _collect_fn_paths_from_argv,
    _collect_fn_paths_from_config,
    _whole_value_spec,
)
from confarg.cli._prefix import PREFIX_ATTR, strip_argv_prefix
from confarg.cli._spec import FlagSpec, _build_help, _get_field_docstrings
from confarg.cli.argparse._register import load_flags_into_parser

_log = logging.getLogger(__name__)


@dataclass
class _WalkCtx:
    """Shared state threaded through recursive completion-walk calls."""

    parser: argparse.ArgumentParser
    union_tag: str
    existing_dests: set[str] = field(default_factory=set)


def _extend_walk_field(  # noqa: PLR0913, C901
    name: str,
    raw_type: Any,
    flag: str,
    core: Any,
    ctx: _WalkCtx,
    docstrings: dict[str, str],
    defaults: dict[str, Any],
    *,
    concrete: bool,
    group: str | None,
    group_description: str,
) -> list[FlagSpec]:
    """Build FlagSpecs for one field of a struct type during the completion walk.

    Mirrors :func:`confarg.cli._build._specs_for_field` but produces only the
    flags completion needs for a concrete union variant: the whole-value flag,
    the union tag (without recursing into sibling variants), callable openers,
    and plain leaves.  Singleton literal fields are skipped when *concrete* is
    set — the class is already selected, so their value is determined.
    """
    specs: list[FlagSpec] = []

    if core is None:
        dest = f"{flag}.{ctx.union_tag}"
        if dest not in ctx.existing_dests:
            non_none = _union_args_no_none(_resolve_type(raw_type))
            concrete_variants = [_resolve_type(v) for v in non_none if _is_struct(_resolve_type(v))]
            if flag not in ctx.existing_dests:
                specs.append(
                    _whole_value_spec(
                        flag,
                        name,
                        raw_type,
                        _resolve_type(raw_type),
                        group,
                        group_description,
                        docstrings,
                        defaults,
                    ),
                )
                ctx.existing_dests.add(flag)
            specs.append(_build_union_tag_spec(flag, ctx.union_tag, concrete_variants, group, group_description))
            ctx.existing_dests.add(dest)
        return specs

    if _is_final(core):
        core = _final_inner(core)

    if concrete and _is_singleton_literal(core):
        return specs  # class already selected — singleton value is determined by the class

    if _is_callable(core):
        if flag not in ctx.existing_dests:
            help_text = _build_help(name, raw_type, docstrings, defaults, flag=flag)
            specs.append(_build_leaf_spec(flag, raw_type, core, help_text, group, group_description))
            ctx.existing_dests.add(flag)
        specs.extend(_build_callable_fn_specs(flag, group, group_description))
        ctx.existing_dests.update({f"{flag}.fn", f"{flag}.class"})
        return specs

    if _is_struct(core):
        if flag not in ctx.existing_dests:
            specs.append(
                _whole_value_spec(
                    flag,
                    name,
                    raw_type,
                    _resolve_type(raw_type),
                    group,
                    group_description,
                    docstrings,
                    defaults,
                ),
            )
            ctx.existing_dests.add(flag)
        specs.extend(
            _extend_walk_specs(
                core,
                ctx,
                flag,
                concrete=concrete,
                group=flag,
                group_description=inspect.getdoc(core) or "",
            ),
        )
        return specs

    if _is_dict(core):
        # No statically known keys, so the bare whole-value flag is all completion can offer.
        if flag not in ctx.existing_dests:
            specs.append(
                _whole_value_spec(
                    flag,
                    name,
                    raw_type,
                    _resolve_type(raw_type),
                    group,
                    group_description,
                    docstrings,
                    defaults,
                ),
            )
            ctx.existing_dests.add(flag)
        return specs

    if flag not in ctx.existing_dests:
        help_text = _build_help(name, raw_type, docstrings, defaults, flag=flag)
        specs.append(_build_leaf_spec(flag, raw_type, core, help_text, group, group_description))
        ctx.existing_dests.add(flag)
    return specs


def _extend_walk_specs(  # noqa: PLR0913
    target: Any,
    ctx: _WalkCtx,
    prefix: str,
    *,
    concrete: bool = False,
    group: str | None = None,
    group_description: str = "",
) -> list[FlagSpec]:
    """Build FlagSpecs for all fields of a struct type during the completion walk."""
    setup = _resolve_struct(target)
    if setup is None:
        return []
    tp, flds, hints = setup

    var_params = _var_params(tp).names
    docstrings = _get_field_docstrings(tp)
    defaults = _struct_defaults(tp)

    specs: list[FlagSpec] = []
    for name in flds:
        if name == ctx.union_tag or name in var_params:
            continue
        raw_type = hints.get(name, Any)
        flag = f"{prefix}.{name}" if prefix else name
        core = _unwrap_optional(_resolve_type(raw_type))
        specs.extend(
            _extend_walk_field(
                name,
                raw_type,
                flag,
                core,
                ctx,
                docstrings,
                defaults,
                concrete=concrete,
                group=group,
                group_description=group_description,
            ),
        )
    return specs


def _extend_walk(
    target: Any,
    ctx: _WalkCtx,
    group_target: argparse.ArgumentParser | argparse._ArgumentGroup,  # noqa: ARG001  # kept for callers
    prefix: str,
    *,
    concrete: bool = False,
) -> None:
    """Build FlagSpecs for the fields of *target* and register them on the parser.

    Group placement is driven by ``spec.group`` (consumed by
    :func:`load_flags_into_parser`), not by *group_target*, which is kept only
    for callers that predate the FlagSpec refactor.
    """
    specs = _extend_walk_specs(target, ctx, prefix, concrete=concrete)
    load_flags_into_parser(specs, ctx.parser)


def _in_prefix(flag: str, cli_prefix: str) -> str:
    """Put a field path back under *cli_prefix*, after the scans resolved it without one."""
    return f"{cli_prefix}.{flag}" if cli_prefix else flag


def _pre_extend_parser_for_completion(
    parser: argparse.ArgumentParser,
    target: Any,
    union_tag: str,
    config_flag: str,
    argv: list[str],
) -> None:
    """Extend parser with variant-specific flags for any union fields whose class tag is known.

    Reads class tags from config files listed in argv and from explicit --<field>.class argv
    tokens, then imports each resolved class and registers its fields onto the parser.
    All errors are silently swallowed — this must never crash a completion invocation.

    A ``cli_prefix`` recorded by :func:`~confarg.cli.argparse.populate_parser` is stripped
    from argv before the scans (whose dotted paths resolve against *target*) and put back
    on the field paths, so the flags land under the same namespace as the static ones.
    """
    try:
        cli_prefix = parser.get_default(PREFIX_ATTR) or ""
        argv = strip_argv_prefix(argv, cli_prefix)
        config_dict = _partial_config_from_argv(argv, config_flag)
        cli_tags = _tags_from_argv(argv, union_tag)
        config_tags = _tags_from_config(config_dict, target, prefix="", union_tag=union_tag)

        # CLI wins over config
        all_tags = {_in_prefix(flag, cli_prefix): tag for flag, tag in {**config_tags, **cli_tags}.items()}

        walk_ctx = _WalkCtx(parser=parser, union_tag=union_tag, existing_dests={a.dest for a in parser._actions})

        for field_prefix, class_path in all_tags.items():
            try:
                cls = _import_dotted(class_path)
                if not isinstance(cls, type) or not _is_struct(_resolve_type(cls)):
                    continue
                _extend_walk(cls, walk_ctx, parser, field_prefix, concrete=True)
            except Exception:  # noqa: BLE001 — completion must never crash; any import/argparse failure is non-fatal
                _log.debug("dynamic union flags: skipping %r", class_path, exc_info=True)
                continue

        config_fns = _collect_fn_paths_from_config(config_dict, target, "", union_tag)
        argv_fns = _collect_fn_paths_from_argv(argv, target, union_tag)
        for field_flag, (fn_path, _mode, bind_key) in {**config_fns, **argv_fns}.items():
            try:
                bind_specs = _collect_callable_bind_specs(
                    _in_prefix(field_flag, cli_prefix),
                    fn_path,
                    bind_key,
                    walk_ctx.existing_dests,
                )
                load_flags_into_parser(bind_specs, parser)
            except Exception:  # noqa: BLE001 — completion must never crash
                _log.debug("callable bind flags: skipping %r", fn_path, exc_info=True)
                continue

    except Exception:  # noqa: BLE001 — completion must never crash; failure here silently degrades suggestions
        _log.debug("extend_completion_parser failed", exc_info=True)


def setup_completion(
    parser: argparse.ArgumentParser,
    target: Any,
    *,
    union_tag: str = _defaults.UNION_TAG,
    config_flag: str = _defaults.CONFIG_FLAG,
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
        target: The top-level dataclass type (same as passed to
            :func:`~confarg.cli.argparse.populate_parser`).
        union_tag: Discriminator field name (default ``"class"``).
        config_flag: Config file flag name (default ``"config"``).
        argv: CLI argument list.  Defaults to ``sys.argv[1:]``.

    Raises:
        ImportError: If ``argcomplete`` is not installed.
    """
    try:
        import argcomplete  # noqa: PLC0415
    except ImportError:
        msg = "Tab-completion requires 'argcomplete'. Install with: pip install confarg[completion]"
        raise ImportError(msg) from None

    if argv is None:
        argv = sys.argv[1:]

    _pre_extend_parser_for_completion(parser, target, union_tag, config_flag, argv)
    argcomplete.autocomplete(parser)
