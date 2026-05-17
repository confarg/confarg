# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Registration steps shared by the click and typer adapters.

Both frameworks model a command as an object carrying a ``params`` list and a
``callback``, so the whole of registration is framework-agnostic once the option
factory is supplied.

Dev Notes:
    docs-dev/architecture/cli-adapters/clicklike-seam.md#the-clicklike-seam
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from confarg.cli._spec import FlagSpec

from confarg.cli._build import bound_runs, build_dynamic_flags, build_static_flags
from confarg.cli._prefix import PREFIX_ATTR
from confarg.cli._sources import REGISTRATION_ATTR, Registration, registration_inputs


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


def populate_command(  # noqa: PLR0913, PLR0917  # mirrors the public populate_* signatures
    target: object,
    command: Any,
    option_factory: Callable[[FlagSpec], Any],
    option_cls: type,
    caller: str,
    opts: Mapping[str, Any],
    *,
    config_subkeys: bool = True,
) -> None:
    """Register the static and dynamic flags of ``target`` as options on ``command``.

    Args:
        target: The type whose fields to register.
        command: The framework command to populate.
        option_factory: Builds the framework's option object from one spec.
        option_cls: The framework's confarg option class, used to pick out the
            options the prefix and the registration are recorded on.
        caller: The public function's name, which an unknown keyword is refused by.
        opts: The sources and how to read them (:class:`~confarg.MergeOptions`).
        config_subkeys: Whether to register ``--<config_flag>.<path>`` options.
    """
    before_names = {p.name for p in command.params}
    options, below, sources = registration_inputs(target, caller, opts)
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
    load_flags_into_command(static, command, option_factory)
    dynamic = build_dynamic_flags(
        target,
        argv,
        cli_prefix=cli_prefix,
        union_tag=union_tag,
        config_flag=config_flag,
        below=below,
    )
    load_flags_into_command(dynamic, command, option_factory)
    registration = Registration(sources, bound_runs(static + dynamic, cli_prefix))
    # Recorded on the options, not on the command: both frameworks routinely copy
    # ``params`` onto another command (groups, decorators), and what registration read
    # must survive that so the merge step still finds it.
    for param in command.params:
        if isinstance(param, option_cls):
            setattr(param, REGISTRATION_ATTR, registration)
            if cli_prefix:
                setattr(param, PREFIX_ATTR, cli_prefix)
    # And on the command, for a target that registers no option at all (a scalar root
    # with no prefix), whose sources the merge still reads.
    setattr(command, REGISTRATION_ATTR, registration)

    confarg_names = {p.name for p in command.params} - before_names
    if command.callback is not None and confarg_names:
        _original = command.callback

        @functools.wraps(_original)
        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            filtered = {k: v for k, v in kwargs.items() if k not in confarg_names}
            return _original(*args, **filtered)

        command.callback = _wrapped
