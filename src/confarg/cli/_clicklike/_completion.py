# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Dynamic completion hook shared by the click and typer adapters.

Dev Notes:
    docs-dev/architecture/04-cli-adapters.md#the-clicklike-seam
"""

from __future__ import annotations

import logging
import os
import shlex
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from confarg.cli._spec import FlagSpec

from confarg import _defaults
from confarg.cli._build import build_dynamic_flags
from confarg.cli._clicklike._register import load_flags_into_command
from confarg.cli._prefix import PREFIX_ATTR

_log = logging.getLogger(__name__)


def partial_argv_from_env() -> list[str]:
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
    command: Any,
    target: type,
    option_factory: Callable[[FlagSpec], Any],
    *,
    union_tag: str = _defaults.UNION_TAG,
    config_flag: str = _defaults.CONFIG_FLAG,
) -> None:
    """Extend ``command`` with dynamic flags before the framework's completion runs.

    A no-op outside completion mode, and silent on any failure: completion must never
    crash the shell, so a failure degrades to fewer suggestions.

    Dev Notes:
        docs-dev/architecture/04-cli-adapters.md#completion
    """
    try:
        prog_name: Any = getattr(command, "name", None) or ""
        complete_var = f"_{prog_name.upper().replace('-', '_')}_COMPLETE"
        if not os.environ.get(complete_var):
            return

        argv = partial_argv_from_env()
        # The prefix populate_command registered with travels on the options themselves.
        cli_prefix = next(
            (p for p in (getattr(param, PREFIX_ATTR, None) for param in command.params) if p is not None),
            "",
        )
        dynamic = build_dynamic_flags(
            target,
            argv,
            cli_prefix=cli_prefix,
            union_tag=union_tag,
            config_flag=config_flag,
        )
        load_flags_into_command(dynamic, command, option_factory)
    except Exception:  # noqa: BLE001
        # Completion must never crash; silently degrade.
        _log.debug("setup_completion failed", exc_info=True)
