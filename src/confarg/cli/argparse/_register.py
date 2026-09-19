# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Argparse-specific flag loading: load_flags_into_parser and populate_parser."""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

    from confarg.cli._spec import FlagSpec

from confarg import _defaults
from confarg.cli._build import (
    build_dynamic_flags,
    build_static_flags,
)
from confarg.cli._prefix import PREFIX_ATTR
from confarg.dictexpr import contains_expression


class _ExpressionTolerantChoices(list):
    """An argparse ``choices`` list that also admits unresolved ``${...}`` tokens.

    argparse gates a value with ``value not in action.choices`` and renders help
    by iterating the same object, so overriding ``__contains__`` widens the
    accepted domain while keeping the native ``{a,b}`` metavar and the native
    ``invalid choice`` error for real values.  ``build()`` validates the resolved
    expression.

    Dev Notes:
        docs-dev/architecture/04-cli-adapters.md#expression-tolerant-choice-gates
    """

    def __contains__(self, value: object) -> bool:
        """Accept a declared choice, or any token expression resolution will rewrite."""
        return contains_expression(value) or super().__contains__(value)


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
    if spec.nargs == 0:
        # Value-less flag (e.g. a list/dict delete --field.N-): argparse forbids
        # nargs=0 on a store action, so register it as a presence-only switch.
        action = target.add_argument(f"--{spec.name}", action="store_true", **common)
        existing_dests.add(spec.name)
        return

    if spec.choices is not None:
        common["choices"] = _ExpressionTolerantChoices(spec.choices)
    if spec.metavar is not None:
        common["metavar"] = spec.metavar

    # A fixed-arity flag that also takes one whole-value token registers greedily:
    # argparse fixes its token count at registration, so "*" is the only spelling that
    # accepts both `--pair 13 42` and `--pair '[13, 42]'`.  The arity is then confarg's
    # to enforce, in build() (docs-dev/architecture/04-cli-adapters.md#whole-value-flags).
    nargs = "*" if spec.whole_value else spec.nargs
    action = target.add_argument(f"--{spec.name}", type=str, nargs=nargs, **common)

    if spec.completer is not None:
        _fn = spec.completer
        action.completer = lambda prefix, *_args, **_kw: _fn(prefix)  # ty: ignore[unresolved-attribute]  # argcomplete monkey-patches .completer onto actions at runtime

    existing_dests.add(spec.name)


def load_flags_into_parser(
    flags: list[FlagSpec],
    parser: argparse.ArgumentParser,
) -> None:
    """Load a list of :class:`~confarg.cli.FlagSpec` objects into an ArgumentParser.

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
    target: object,
    parser: argparse.ArgumentParser,
    *,
    cli_prefix: str = "",
    union_tag: str = _defaults.UNION_TAG,
    config_flag: str = _defaults.CONFIG_FLAG,
    config_subkeys: bool = True,
    argv: Sequence[str] | None = None,
) -> None:
    """Register fields of a dataclass type as arguments on an ArgumentParser.

    Field types, defaults, and attribute docstrings are read automatically.
    For richer control, annotate individual fields with :class:`~confarg.cli.FieldMeta`::

        port: Annotated[int, FieldMeta(help="TCP port.", metavar="PORT")]

    All confarg arguments use ``default=argparse.SUPPRESS``, so fields absent
    from the command line do not appear in the resulting Namespace and never
    override config files or env vars in :func:`from_namespace`.

    A ``--<config_flag>`` argument (default ``--config``) is also registered so
    users can pass one or more config files on the command line.
    Pass ``config_flag=""`` to suppress it.

    A ``dict``-typed field gets only the bare ``--field JSON`` whole-value flag (its
    keys are unknown statically); each ``--field.key`` found in ``argv`` is registered
    alongside it.  Values are passed as strings: type coercion happens in
    :func:`from_namespace`, not in argparse.

    Args:
        target: The dataclass type whose fields to register.
        parser: The :class:`argparse.ArgumentParser` to populate.
        cli_prefix: Namespace every confarg flag lives under, so
            ``--<prefix>.<field>`` stays distinguishable from the host
            application's own flags.  Defaults to ``""`` (no prefix).  The value is
            recorded on the parser, so :func:`merge_namespace` / :func:`from_namespace`
            recover it and need not repeat it.  A non-struct (scalar) target is
            registered as the bare ``--<prefix>`` flag and has no CLI spelling
            without a prefix.
        union_tag: Name of the union discriminator field to skip (matches
            the ``union_tag`` parameter of :func:`from_namespace`).
        config_flag: Name of the config-file flag (default ``"config"``).
            Set to ``""`` to disable config-file argument registration.
        config_subkeys: Whether to register ``--<config_flag>.<field>`` flags for
            each direct struct field of the root dataclass (default ``True``).
            Set to ``False`` to expose only the root ``--<config_flag>`` flag.
        argv: CLI argument list scanned to register argv-derived dynamic flags:
            ``--<field>.bind.*`` for resolved ``--<field>.fn`` / ``--<field>.class``
            callables, ``--<config_flag>.<subpath>[+]`` scoped/append config files,
            and list-index / append / delete / dict-subkey patch flags — so the
            host parser accepts every flag ``from_namespace`` will later consume.
            Defaults to ``sys.argv[1:]`` (matching :func:`from_namespace`); pass an
            explicit list, or ``[]`` to register only the static, type-derived flags.

    Note:
        Prefer :func:`make_parser` for the common case — it sets
        ``allow_abbrev=False`` by default to prevent schema evolution from
        silently breaking abbreviated flag invocations.
    """
    if argv is None:
        argv = sys.argv[1:]
    static = build_static_flags(
        target,
        argv=argv,
        cli_prefix=cli_prefix,
        union_tag=union_tag,
        config_flag=config_flag,
        config_subkeys=config_subkeys,
    )
    load_flags_into_parser(static, parser)
    dynamic = build_dynamic_flags(target, argv, cli_prefix=cli_prefix, union_tag=union_tag, config_flag=config_flag)
    load_flags_into_parser(dynamic, parser)
    if cli_prefix:
        # argparse hands from_namespace only a Namespace, with no way back to this
        # parser, so the prefix rides along on every Namespace the parser produces.
        parser.set_defaults(**{PREFIX_ATTR: cli_prefix})


def make_parser(  # noqa: PLR0913  # thin pass-through: every parameter goes to populate_parser
    target: object,
    *,
    cli_prefix: str = "",
    union_tag: str = _defaults.UNION_TAG,
    config_flag: str = _defaults.CONFIG_FLAG,
    config_subkeys: bool = True,
    argv: Sequence[str] | None = None,
    **kwargs: Any,
) -> argparse.ArgumentParser:
    """Create an :class:`argparse.ArgumentParser` pre-populated with fields from *target*.

    Sets ``allow_abbrev=False`` unless overridden, preventing schema evolution
    from silently breaking abbreviated flag invocations.  All extra keyword
    arguments are forwarded to :class:`argparse.ArgumentParser` (e.g.
    ``description``, ``prog``).

    Example::

        parser = make_parser(Config, description="My app")
        namespace = parser.parse_args()
        config = from_namespace(Config, namespace)

    Args:
        target: The dataclass type whose fields to register.
        cli_prefix: Namespace every confarg flag lives under (forwarded to
            :func:`populate_parser`).
        union_tag: Name of the union discriminator field (forwarded to
            :func:`populate_parser`).
        config_flag: Name of the config-file flag (forwarded to
            :func:`populate_parser`).
        config_subkeys: Whether to register per-field config flags (forwarded
            to :func:`populate_parser`).
        argv: CLI argument list for registering argv-derived dynamic flags
            (forwarded to :func:`populate_parser`; defaults to ``sys.argv[1:]``,
            pass ``[]`` to register only static flags).
        **kwargs: Additional keyword arguments forwarded to
            :class:`argparse.ArgumentParser`.
    """
    kwargs.setdefault("allow_abbrev", False)
    parser = argparse.ArgumentParser(**kwargs)
    populate_parser(
        target,
        parser,
        cli_prefix=cli_prefix,
        union_tag=union_tag,
        config_flag=config_flag,
        config_subkeys=config_subkeys,
        argv=argv,
    )
    return parser
