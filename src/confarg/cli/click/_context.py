# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Convert a Click Context into a nested dict for dataclass construction."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    import click

from click import ParameterSource

from confarg import _defaults
from confarg._files import _load_subpath_files
from confarg._merge import _deep_merge
from confarg._parse_env import _parse_env
from confarg._types import _resolve_type
from confarg.cli.argparse._namespace import _collect_ns_fields
from confarg.dictexpr import resolve_expressions
from confarg.typedload import construct


def _flat_from_ctx(ctx: click.Context) -> dict[str, Any]:
    """Return only the CLI-provided params from a Click Context.

    Uses :func:`click.Context.get_parameter_source` to distinguish values
    that the user typed on the command line (``ParameterSource.COMMANDLINE``)
    from those that came from defaults or other sources.  Non-empty tuples
    (from ``multiple=True`` options) are converted to lists.
    """
    result: dict[str, Any] = {}
    for k, v in ctx.params.items():
        if ctx.get_parameter_source(k) != ParameterSource.COMMANDLINE:
            continue
        result[k] = list(v) if isinstance(v, tuple) else v
    return result


def from_context(  # noqa: PLR0913
    ctx: click.Context,
    dc_type: type,
    *,
    union_tag: str = _defaults.UNION_TAG,
    config_flag: str = "config",
    files: Sequence[str | Path] = (),
    env: Mapping[str, str] | None = None,
    env_prefix: str | None = _defaults.ENV_PREFIX,
    env_separator: str = "__",
) -> Any:
    """Construct a dataclass instance from a Click :class:`~click.Context`.

    Merges three sources in ascending priority order: config files, environment
    variables, then CLI arguments from the Context.  This mirrors the behaviour
    of :func:`confarg.load`.

    Only options registered by :func:`populate_command` are consumed from ``ctx``.
    Options absent from the Context (i.e. not provided by the user) fall back to
    env vars, config files, or dataclass defaults; missing required fields raise
    :class:`~confarg.exceptions.MissingFieldError`.

    Args:
        ctx: The :class:`click.Context` returned by Click during command execution.
            Obtain it inside a command with :func:`click.get_current_context`.
        dc_type: The dataclass type to construct.
        union_tag: Discriminator field name (same as :func:`confarg.load`).
        config_flag: Name of the config-file option on ``ctx`` (default
            ``"config"``).  Must match the ``config_flag`` passed to
            :func:`populate_command`.  Set to ``""`` to ignore all config-file
            options.
        files: Additional root-level config file paths to load (lowest priority).
        env: Environment variable mapping.  Defaults to ``os.environ``.
            Pass ``{}`` to disable env-var reading.
        env_prefix: Prefix that env vars must start with. Defaults to ``None``,
            which disables environment variable parsing entirely.
        env_separator: Separator used to split env var names into nested keys.

    Returns:
        An instance of ``dc_type`` populated from all sources.
    """
    if env is None:
        env = os.environ

    flat = _flat_from_ctx(ctx)

    # 1. Collect CLI field values from the context
    cli_data: dict[str, Any] = {}
    _collect_ns_fields(flat, dc_type, prefix="", union_tag=union_tag, result=cli_data)

    # 2. Collect (subpath, path) pairs for all config files
    file_pairs: list[tuple[str, Path]] = [("", Path(f)) for f in files]
    if config_flag:
        file_pairs.extend(("", Path(f)) for f in flat.get(config_flag) or [])
        cfg_prefix = f"{config_flag}."
        for key, val in flat.items():
            if key.startswith(cfg_prefix):
                subpath = key[len(cfg_prefix) :]
                file_pairs.extend((subpath, Path(f)) for f in val or [])

    # 3. Load config files
    config_data = _load_subpath_files(file_pairs, union_tag)

    # 4. Parse env vars
    if env_prefix is None:
        env_data: dict[str, Any] = {}
        env_configs: list[tuple[str, Path]] = []
    else:
        env_data, env_configs = _parse_env(env, env_prefix, env_separator, dc_type)
    config_data = _deep_merge(config_data, _load_subpath_files(env_configs, union_tag), union_tag=union_tag)

    # 5. Merge: config < env < CLI
    merged = _deep_merge(config_data, env_data, union_tag=union_tag)
    merged = _deep_merge(merged, cli_data, union_tag=union_tag)

    # 6. Resolve expressions
    merged = resolve_expressions(merged)

    # 7. Construct
    return construct(_resolve_type(dc_type), merged, union_tag=union_tag)


__all__ = ["from_context"]
