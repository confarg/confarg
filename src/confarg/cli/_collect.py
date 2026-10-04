# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The adapters' shared merge tail: the CLI channel written from argv by vanilla's own loop.

Backend-neutral: every CLI adapter (argparse, click, typer, cyclopts) lets its framework
parse argv -- validation, ``--help``, completion -- then hands the parse result and the
argv here.  The CLI channel is written by :func:`~confarg._parse_cli._parse_cli` over that
argv, the loop vanilla runs, so the merged dict equals vanilla's by construction: values,
patches, tags and key order alike.  The parse result is only checked against the argv.

Dev Notes:
    docs-dev/architecture/cli-adapters/model.md#argv-is-the-only-writer
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

from confarg._api import build
from confarg._import import _import_dotted
from confarg._parse_cli import _parse_cli, _path_unknown
from confarg._pipeline import _merge_sources
from confarg._types import _is_struct, _resolve_type
from confarg.cli._argv import spelled_flag_names
from confarg.cli._build import _binds_a_run
from confarg.cli._prefix import strip_argv_prefix, strip_flat_prefix
from confarg.exceptions import ConfargError, SymbolImportError


def _tag_named_struct(class_tag: Any) -> Any:
    """Return the struct type a class tag names, or ``None`` when it names none.

    ``None`` covers both failure modes -- the import fails, or the class is not a struct
    -- because every caller's response is the same: leave the tag where its channel put
    it and move on.  Vanilla stores the raw string and lets ``construct()`` raise the
    import error, so no caller reports the failure itself.
    """
    try:
        cls = _import_dotted(str(class_tag))
    except (SymbolImportError, TypeError, ValueError, NameError, AttributeError):
        return None
    return cls if isinstance(cls, type) and _is_struct(_resolve_type(cls)) else None


def _require_argv_spells(
    flat: Mapping[str, Any],
    argv: Sequence[str],
    cli_prefix: str,
    target: object,
    union_tag: str,
) -> None:
    """Raise unless *argv* spells every confarg flag the framework's parse result holds.

    The CLI channel is written from *argv* alone, so a parse result that holds a flag
    *argv* never spells means the two are not the same command line -- typically
    ``parse_args(custom)`` merged with *argv* left to default to ``sys.argv[1:]``.  The
    values would be lost without a word, so the mismatch is refused instead.  A key the
    target does not resolve is the host's own parameter and is not confarg's to judge.

    Dev Notes:
        docs-dev/architecture/cli-adapters/model.md#argv-is-the-only-writer
    """
    spelled = spelled_flag_names(strip_argv_prefix(argv, cli_prefix))
    for key, value in strip_flat_prefix(dict(flat), cli_prefix).items():
        if value is None or key in spelled or _path_unknown(target, key.split("."), union_tag):
            continue
        msg = (
            f"The parse result holds '--{key}', which argv does not spell: pass argv= the "
            "list the framework parsed (it defaults to sys.argv[1:])"
        )
        raise ConfargError(msg)


def _merge_from_flat(  # noqa: PLR0913  # mirrors confarg.merge's keyword-only signature
    flat: dict[str, Any],
    target: object,
    *,
    argv: Sequence[str] | None,
    env: Mapping[str, str] | None,
    env_prefix: str | None,
    env_separator: str,
    cli_prefix: str,
    config_flag: str,
    files: Sequence[str | Path],
    env_config: str | None,
    union_tag: str,
    binds_runs: bool,
) -> dict[str, Any]:
    """Merge every source into a raw dict, the CLI channel written from *argv*.

    The shared tail of ``merge_namespace`` / ``merge_context`` / ``merge_app``, so the
    four cannot drift.  The CLI channel and its ``--config`` files are what vanilla's
    loop (:func:`~confarg._parse_cli._parse_cli`) reads off *argv*, in the mode that
    leaves the host's own tokens to the host; the framework's parse result *flat* only
    has to agree with *argv* (:func:`_require_argv_spells`).

    Args:
        flat: The adapter's parse result as ``{dotted.flag: value}``.
        target: The target type, used to guide the type walk.
        argv: The CLI arguments the framework parsed; ``None`` means ``sys.argv[1:]``.
        env: Environment variable mapping; ``None`` means ``os.environ``.
        env_prefix: Prefix that env vars must start with.
        env_separator: Separator splitting env var names into nested keys.
        cli_prefix: Namespace the flags were registered under.
        config_flag: Flag name used to specify config files.
        files: Config file paths to load at lowest priority.
        env_config: Name of an env var holding a config file path.
        union_tag: Field name used as a discriminator tag in unions.
        binds_runs: The framework binds every token up to the next flag to a
            multi-token or fixed-arity flag (argparse, cyclopts), so a token after
            the run vanilla consumes is a stray rather than a positional of the host's.

    Returns:
        A plain dict of the merged configuration, with expression strings intact.

    Raises:
        ConfargError: If *flat* holds a confarg flag *argv* does not spell.

    Dev Notes:
        docs-dev/architecture/cli-adapters/model.md#argv-is-the-only-writer
    """
    if env is None:
        env = os.environ

    raw_argv = sys.argv[1:] if argv is None else list(argv)
    _require_argv_spells(flat, raw_argv, cli_prefix, target, union_tag)
    cli_data, cli_configs = _parse_cli(
        raw_argv,
        target,
        cli_prefix,
        config_flag,
        union_tag,
        host_parsed=True,
        host_binds_run=_binds_a_run if binds_runs else None,
    )

    return _merge_sources(
        target,
        cli_data,
        cli_configs,
        env=env,
        env_prefix=env_prefix,
        env_separator=env_separator,
        config_flag=config_flag,
        files=files,
        env_config=env_config,
        union_tag=union_tag,
    )


def _construct_from_merged(target: object, merged: dict[str, Any], union_tag: str) -> Any:
    """Construct *target* from an already-merged dict; the shared tail of every ``from_*``."""
    return build(target, merged, union_tag=union_tag)
