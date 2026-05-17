# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Argparse-specific flag loading: load_flags_into_parser and populate_parser."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Sequence

    from confarg.cli.argparse._spec import FlagSpec

from confarg import _defaults
from confarg.cli.argparse._build import (
    _build_callable_fn_specs,
    _build_leaf_spec,
    _build_union_tag_spec,
    _collect_callable_bind_specs,
    build_dynamic_flags,
    build_static_flags,
)


def _get_actions(target: argparse.ArgumentParser | argparse._ArgumentGroup) -> list[argparse.Action]:
    """Return the action list from a parser or argument group."""
    if hasattr(target, "_group_actions"):
        return cast("list[argparse.Action]", target._group_actions)
    return cast("list[argparse.Action]", target._actions)  # ty:ignore[redundant-cast]


def _register_spec(
    spec: FlagSpec,
    target: argparse.ArgumentParser | argparse._ArgumentGroup,
    existing_dests: set[str],
) -> None:
    """Add one FlagSpec to a specific argparse target (parser or group)."""
    if spec.name in existing_dests:
        return

    common: dict[str, Any] = {
        "dest": spec.name,
        "default": argparse.SUPPRESS,
        "help": spec.help,
    }
    if spec.choices is not None:
        common["choices"] = spec.choices
    if spec.metavar is not None:
        common["metavar"] = spec.metavar

    action = target.add_argument(f"--{spec.name}", type=str, nargs=spec.nargs, **common)

    if spec.completer is not None:
        _fn = spec.completer
        action.completer = lambda prefix, *_args, **_kw: _fn(prefix)  # ty: ignore[unresolved-attribute]  # argcomplete monkey-patches .completer onto actions at runtime

    existing_dests.add(spec.name)


def load_flags_into_parser(
    flags: list[FlagSpec],
    parser: argparse.ArgumentParser,
) -> None:
    """Load a list of :class:`~confarg.cli.argparse.FlagSpec` objects into an ArgumentParser.

    Creates argument groups lazily as needed (keyed by :attr:`FlagSpec.group`).
    Flags whose ``name`` is already registered as a ``dest`` are silently skipped.

    Args:
        flags: The specs to register, typically from :func:`build_static_flags`
            or :func:`build_dynamic_flags`.
        parser: The :class:`argparse.ArgumentParser` to populate.
    """
    groups: dict[str, argparse._ArgumentGroup] = {}
    existing_dests: set[str] = {a.dest for a in parser._actions}

    for spec in flags:
        if spec.group is not None:
            if spec.group not in groups:
                existing_group = next((g for g in parser._action_groups if g.title == spec.group), None)
                groups[spec.group] = existing_group or parser.add_argument_group(spec.group, spec.group_description)
            target: argparse.ArgumentParser | argparse._ArgumentGroup = groups[spec.group]
        else:
            target = parser

        _register_spec(spec, target, existing_dests)


def populate_parser(  # noqa: PLR0913
    target: type,
    parser: argparse.ArgumentParser,
    *,
    union_tag: str = _defaults.UNION_TAG,
    config_flag: str = "config",
    config_subkeys: bool = True,
    argv: Sequence[str] | None = None,
) -> None:
    """Register fields of a dataclass type as arguments on an ArgumentParser.

    Field types, defaults, and attribute docstrings are read automatically.
    For richer control, annotate individual fields with :class:`~confarg.cli.FieldMeta`::

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
        target: The dataclass type whose fields to register.
        parser: The :class:`argparse.ArgumentParser` to populate.
        union_tag: Name of the union discriminator field to skip (matches
            the ``union_tag`` parameter of :func:`from_namespace`).
        config_flag: Name of the config-file flag (default ``"config"``).
            Set to ``""`` to disable config-file argument registration.
        config_subkeys: Whether to register ``--<config_flag>.<field>`` flags for
            each direct struct field of the root dataclass (default ``True``).
            Set to ``False`` to expose only the root ``--<config_flag>`` flag.
        argv: CLI argument list used to pre-resolve ``--<field>.fn`` / ``--<field>.class``
            values so that callable ``--<field>.bind.*`` flags can be registered
            before :meth:`~argparse.ArgumentParser.parse_args` is called.
            Has no effect on which config-source flags are registered.
    """
    static = build_static_flags(target, union_tag=union_tag, config_flag=config_flag, config_subkeys=config_subkeys)
    load_flags_into_parser(static, parser)
    if argv is not None:
        dynamic = build_dynamic_flags(target, argv, union_tag=union_tag, config_flag=config_flag)
        load_flags_into_parser(dynamic, parser)


# ---------------------------------------------------------------------------
# Thin wrappers retained for _completion.py compatibility.
# These delegate to the spec-builder functions + _register_spec.
# A future refactoring of _completion.py can remove them.
# ---------------------------------------------------------------------------


def _add_leaf_argument(
    target: argparse.ArgumentParser | argparse._ArgumentGroup,
    flag: str,
    raw_type: Any,
    core: Any,
    help_text: str,
) -> None:
    """Register a single leaf field as an argparse argument."""
    spec = _build_leaf_spec(flag, raw_type, core, help_text, None, "")
    existing = {a.dest for a in _get_actions(target)}
    _register_spec(spec, target, existing)


def _add_callable_fn_flags(
    target: argparse.ArgumentParser | argparse._ArgumentGroup,
    flag: str,
) -> None:
    """Register --<flag>.fn, --<flag>.class, and --<flag>.call as discrete string flags."""
    existing = {a.dest for a in _get_actions(target)}
    for spec in _build_callable_fn_specs(flag, None, ""):
        _register_spec(spec, target, existing)


def _add_callable_bind_flags(
    parser: argparse.ArgumentParser,
    field_flag: str,
    fn_path: str,
    existing_dests: set[str] | None = None,
) -> None:
    """Register --<field_flag>.bind.<param> flags by inspecting the target's signature."""
    if existing_dests is None:
        existing_dests = {a.dest for a in parser._actions}
    specs = _collect_callable_bind_specs(field_flag, fn_path, existing_dests)
    load_flags_into_parser(specs, parser)


def _add_union_tag_argument(
    target: argparse.ArgumentParser | argparse._ArgumentGroup,
    flag: str,
    union_tag: str,
    variant_types: list[Any],
) -> None:
    """Register --<flag>.<union_tag> for dynamic class dispatch."""
    spec = _build_union_tag_spec(flag, union_tag, variant_types, None, "")
    existing = {a.dest for a in _get_actions(target)}
    _register_spec(spec, target, existing)
