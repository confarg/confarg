# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Registration steps shared by the click and typer adapters.

Both frameworks model a command as an object carrying a ``params`` list and a
``callback``, so the whole of registration is framework-agnostic once the option
factory is supplied.

Dev Notes:
    docs-dev/architecture/04-cli-adapters.md#the-clicklike-seam
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from confarg.cli._spec import FlagSpec

from confarg import _defaults
from confarg.cli._build import build_dynamic_flags, build_static_flags
from confarg.cli._prefix import PREFIX_ATTR


def load_flags_into_command(
    flags: list[FlagSpec],
    command: Any,
    option_factory: Callable[[FlagSpec], Any],
) -> None:
    """Append one option per spec to ``command.params``, skipping known names.

    Args:
        flags: The specs to register.
        command: The framework command to populate.
        option_factory: Builds the framework's option object from one spec.
    """
    existing = {p.name for p in command.params}
    for spec in flags:
        if spec.name in existing:
            continue
        command.params.append(option_factory(spec))
        existing.add(spec.name)


def populate_command(  # noqa: PLR0913  # mirrors the public populate_* signatures
    target: object,
    command: Any,
    option_factory: Callable[[FlagSpec], Any],
    option_cls: type,
    *,
    cli_prefix: str = "",
    union_tag: str = _defaults.UNION_TAG,
    config_flag: str = _defaults.CONFIG_FLAG,
    config_subkeys: bool = True,
    argv: Sequence[str],
) -> None:
    """Register the static and dynamic flags of ``target`` as options on ``command``.

    Args:
        target: The type whose fields to register.
        command: The framework command to populate.
        option_factory: Builds the framework's option object from one spec.
        option_cls: The framework's confarg option class, used to pick out the
            options the prefix may be recorded on.
        cli_prefix: Namespace every confarg option lives under.
        union_tag: Name of the union discriminator field.
        config_flag: Name of the config-file option; ``""`` suppresses it.
        config_subkeys: Whether to register ``--<config_flag>.<field>`` options.
        argv: CLI argument list scanned for argv-derived dynamic options.
    """
    before_names = {p.name for p in command.params}

    static = build_static_flags(
        target,
        argv=argv,
        cli_prefix=cli_prefix,
        union_tag=union_tag,
        config_flag=config_flag,
        config_subkeys=config_subkeys,
    )
    load_flags_into_command(static, command, option_factory)
    dynamic = build_dynamic_flags(target, argv, cli_prefix=cli_prefix, union_tag=union_tag, config_flag=config_flag)
    load_flags_into_command(dynamic, command, option_factory)
    if cli_prefix:
        # Recorded on the options, not on the command: both frameworks routinely copy
        # ``params`` onto another command (groups, decorators), and the prefix must
        # survive that so the merge step still finds it.
        for param in command.params:
            if isinstance(param, option_cls):
                setattr(param, PREFIX_ATTR, cli_prefix)

    confarg_names = {p.name for p in command.params} - before_names
    if command.callback is not None and confarg_names:
        _original = command.callback

        @functools.wraps(_original)
        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            filtered = {k: v for k, v in kwargs.items() if k not in confarg_names}
            return _original(*args, **filtered)

        command.callback = _wrapped
