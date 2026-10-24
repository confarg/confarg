# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Argparse-specific flag loading: load_flags_into_parser and populate_parser."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, Any, Unpack

if TYPE_CHECKING:
    from collections.abc import Sequence

    from confarg.cli._spec import FlagSpec

from confarg._defaults import MergeOptions
from confarg.cli._build import (
    bound_runs,
    build_dynamic_flags,
    build_static_flags,
)
from confarg.cli._markup import escape_percent
from confarg.cli._prefix import PREFIX_ATTR
from confarg.cli._sources import REGISTRATION_ATTR, Registration, registration_inputs
from confarg.dictexpr import contains_expression
from confarg.exceptions import ConfargError


class _ExpressionTolerantChoices(list):
    """An argparse ``choices`` list that also admits unresolved ``${...}`` tokens.

    argparse gates a value with ``value not in action.choices`` and renders help
    by iterating the same object, so overriding ``__contains__`` widens the
    accepted domain while keeping the native ``{a,b}`` metavar and the native
    ``invalid choice`` error for real values.  ``build()`` validates the resolved
    expression.

    Dev Notes:
        docs-dev/architecture/cli-adapters/parity.md#expression-tolerant-choice-gates
    """

    def __contains__(self, value: object) -> bool:
        """Accept a declared choice, or any token expression resolution will rewrite."""
        return contains_expression(value) or super().__contains__(value)


class _RefusingBareAction(argparse._StoreAction):
    """A store action raising :meth:`~confarg.cli.FlagSpec.bare_refusal` for an occurrence handed no value.

    Dev Notes:
        docs-dev/architecture/cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare
    """

    def __init__(self, *args: Any, bare_error: str, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.bare_error = bare_error

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        """Store *values*.

        Raises:
            ConfargError: If the occurrence carries no value.
        """
        if not values:
            raise ConfargError(self.bare_error)
        super().__call__(parser, namespace, values, option_string)


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
        # A hidden flag is accepted but kept out of --help (BUG-80).
        "help": argparse.SUPPRESS if spec.hidden else spec.rendered_help(escape_percent),
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
    if (bare_refusal := spec.bare_refusal()) is not None:
        common["action"] = _RefusingBareAction
        common["bare_error"] = bare_refusal

    # A fixed-arity flag that also takes one whole-value token registers greedily:
    # argparse fixes its token count at registration, so "*" is the only spelling that
    # accepts both `--pair 13 42` and `--pair '[13, 42]'`.  The arity is then confarg's
    # to enforce, in build() (docs-dev/architecture/cli-adapters/whole-value-flags.md#whole-value-flags).
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


def populate_parser(
    target: object,
    parser: argparse.ArgumentParser,
    *,
    config_subkeys: bool = True,
    **opts: Unpack[MergeOptions],
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
        config_subkeys: Whether to register ``--<config_flag>.<path>`` flags for
            every mount point of the target, at any depth (default ``True``).
            Set to ``False`` to expose only the root ``--<config_flag>`` flag.
        **opts: The sources the flags are typed by and how to read them, as for
            :func:`confarg.load`; see :class:`confarg.MergeOptions`. They are recorded on
            the parser, so :func:`merge_namespace` / :func:`from_namespace` reuse them,
            and refuse one passed to them that differs: argparse splits the command line
            by the types they give the flags. The classes ``files``, the environment and
            the ``--config`` files name type the flags below the nodes they name.
            ``argv`` is scanned to register the argv-derived dynamic flags --
            ``--<field>.<param>`` for a callable spec, ``--<config_flag>.<subpath>[+]``
            mounts, list-index / append / delete / dict-subkey patches -- so the parser
            accepts every flag ``from_namespace`` will consume; it defaults to
            ``sys.argv[1:]``, and ``[]`` registers only the static, type-derived flags.
            ``cli_prefix`` is the namespace every confarg flag lives under, so
            ``--<prefix>.<field>`` stays distinguishable from the host application's
            own; a non-struct (scalar) target is registered as the bare ``--<prefix>``
            flag, and has no CLI spelling without a prefix. ``config_flag`` names the
            config-file flag (``""`` registers none).

    Note:
        Prefer :func:`make_parser` for the common case — it sets
        ``allow_abbrev=False`` by default to prevent schema evolution from
        silently breaking abbreviated flag invocations.
    """
    options, below, sources = registration_inputs(target, "populate_parser", opts)
    cli_prefix, argv = options.cli_prefix or "", options.argv
    union_tag, config_flag = options.union_tag, options.config_flag
    static = build_static_flags(
        target,
        argv=argv,
        cli_prefix=cli_prefix,
        union_tag=union_tag,
        config_flag=config_flag,
        config_subkeys=config_subkeys,
        below=below,
    )
    load_flags_into_parser(static, parser)
    dynamic = build_dynamic_flags(
        target,
        argv,
        cli_prefix=cli_prefix,
        union_tag=union_tag,
        config_flag=config_flag,
        below=below,
    )
    load_flags_into_parser(dynamic, parser)
    # argparse hands the merge only a Namespace, so what registration read rides on it.
    parser.set_defaults(**{REGISTRATION_ATTR: Registration(sources, bound_runs(static + dynamic, cli_prefix))})
    if cli_prefix:
        # argparse hands from_namespace only a Namespace, with no way back to this
        # parser, so the prefix rides along on every Namespace the parser produces.
        parser.set_defaults(**{PREFIX_ATTR: cli_prefix})


def make_parser(
    target: object,
    *,
    config_subkeys: bool = True,
    **kwargs: Any,
) -> argparse.ArgumentParser:
    """Create an :class:`argparse.ArgumentParser` pre-populated with fields from *target*.

    Sets ``allow_abbrev=False`` unless overridden, preventing schema evolution
    from silently breaking abbreviated flag invocations.  A keyword
    :class:`confarg.MergeOptions` declares is forwarded to :func:`populate_parser`,
    every other one to :class:`argparse.ArgumentParser` (e.g. ``description``,
    ``prog``).

    Example::

        parser = make_parser(Config, description="My app", env_prefix="MYAPP_")
        namespace = parser.parse_args()
        config = from_namespace(Config, namespace)

    Args:
        target: The dataclass type whose fields to register.
        config_subkeys: Whether to register the mount-point config flags (forwarded
            to :func:`populate_parser`).
        **kwargs: The sources and how to read them (:class:`confarg.MergeOptions`,
            forwarded to :func:`populate_parser`), and the keyword arguments of
            :class:`argparse.ArgumentParser`.
    """
    opts: Any = {key: kwargs.pop(key) for key in list(kwargs) if key in MergeOptions.__annotations__}
    kwargs.setdefault("allow_abbrev", False)
    parser = argparse.ArgumentParser(**kwargs)
    populate_parser(target, parser, config_subkeys=config_subkeys, **opts)
    return parser
