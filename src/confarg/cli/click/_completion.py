# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Dynamic completion hook for Click: extend a command with runtime-discovered flags."""

from __future__ import annotations

import logging
import os
import shlex
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import click

from confarg import _defaults
from confarg.cli.argparse._build import build_dynamic_flags
from confarg.cli.click._register import load_flags_into_command

_log = logging.getLogger(__name__)


def _partial_argv_from_env() -> list[str]:
    """Read the partial command line from bash/zsh completion env vars.

    Returns the words already typed (excluding the program name and the
    word currently being completed), or an empty list if the env vars are absent.
    """
    words_str = os.environ.get("COMP_WORDS", "")
    cword_str = os.environ.get("COMP_CWORD", "")
    if not words_str or not cword_str:
        return []
    try:
        cword = int(cword_str)
        words = shlex.split(words_str)
        # words[0] is the program name; words[cword] is the incomplete word
        return words[1:cword]
    except (ValueError, IndexError):
        return []


def setup_completion(
    command: click.Command,
    dc_type: type,
    *,
    union_tag: str = _defaults.UNION_TAG,
    config_flag: str = "config",
) -> None:
    """Extend *command* with dynamic flags before Click's completion lifecycle runs.

    Call this **before** ``command.main()`` (or the decorated function is invoked).
    It is a no-op when the process is not in shell-completion mode, so it is safe
    to call unconditionally.

    Dynamic flags are those whose existence depends on values already typed on the
    command line — for example, ``--db.bind.*`` flags that appear only after
    ``--db.class myapp.MyDB`` has been typed.  :func:`setup_completion` scans the
    partial command line (via ``COMP_WORDS`` / ``COMP_CWORD``) and registers the
    appropriate extra options on *command* so that Click can suggest them.

    Works with bash and zsh (which emulate bash completion env vars via
    click-provided shell integration scripts).  Fish support can be added later.

    Args:
        command: The :class:`click.Command` to extend.
        dc_type: The dataclass type whose fields define the available flags.
        union_tag: Discriminator field name (same as :func:`confarg.load`).
        config_flag: Name of the config-file option (must match :func:`populate_command`).
    """
    try:
        prog_name: Any = getattr(command, "name", None) or ""
        complete_var = f"_{prog_name.upper().replace('-', '_')}_COMPLETE"
        if not os.environ.get(complete_var):
            return

        partial_argv = _partial_argv_from_env()
        dynamic = build_dynamic_flags(dc_type, partial_argv, union_tag=union_tag, config_flag=config_flag)
        load_flags_into_command(dynamic, command)
    except Exception:  # noqa: BLE001
        # Completion must never crash; silently degrade.
        _log.debug("setup_completion failed", exc_info=True)
