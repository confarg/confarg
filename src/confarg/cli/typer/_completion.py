# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Dynamic completion hook for Typer: extend a command with runtime-discovered flags."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typer._click import Command

from confarg import _defaults
from confarg.cli import _clicklike
from confarg.cli.typer._register import _spec_to_option


def setup_completion(
    command: Command,
    target: type,
    *,
    union_tag: str = _defaults.UNION_TAG,
    config_flag: str = _defaults.CONFIG_FLAG,
) -> None:
    """Extend *command* with dynamic flags before Typer's completion lifecycle runs.

    Call this **before** invoking the command.  It is a no-op when the process is
    not in shell-completion mode, so it is safe to call unconditionally.

    Dynamic flags are those whose existence depends on values already typed on the
    command line — for example, ``--db.bind.*`` flags that appear only after
    ``--db.class myapp.MyDB`` has been typed.  :func:`setup_completion` scans the
    partial command line (via ``COMP_WORDS`` / ``COMP_CWORD``) and registers the
    appropriate extra options on *command* so that Typer can suggest them.

    Works with bash and zsh (which emulate bash completion env vars via the shell
    integration scripts Typer installs); fish is not supported.

    Args:
        command: The command from :func:`typer.main.get_command` to extend.
        target: The dataclass type whose fields define the available flags.
        union_tag: Discriminator field name (same as :func:`confarg.load`).
        config_flag: Name of the config-file option (must match :func:`populate_command`).
    """
    _clicklike.setup_completion(
        command,
        target,
        _spec_to_option,
        union_tag=union_tag,
        config_flag=config_flag,
    )
