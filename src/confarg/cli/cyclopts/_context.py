# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Parse a cyclopts App invocation and construct a dataclass from all sources."""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    import cyclopts

from confarg import _defaults
from confarg._api import build
from confarg._merge import _deep_merge
from confarg._parse_cli import _collect_cli_patch_ops, _collect_config_file_pairs
from confarg._pipeline import _merge_sources
from confarg.cli._collect import _collect_ns_fields
from confarg.cli.cyclopts._register import _app_meta


def _run_command(command: Any, bound: Any) -> Any:
    """Call *command* with its bound arguments; return the result."""
    return command(*bound.args, **bound.kwargs) if bound is not None else command()


def merge_app(  # noqa: PLR0913
    target: object,
    app: cyclopts.App,
    *,
    argv: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
    env_prefix: str | None = _defaults.ENV_PREFIX,
    env_separator: str = _defaults.ENV_SEPARATOR,
    config_flag: str = _defaults.CONFIG_FLAG,
    files: Sequence[str | Path] = (),
    env_config: str | None = None,
    union_tag: str = _defaults.UNION_TAG,
) -> dict[str, Any]:
    """Collect and merge configuration from all sources into a raw dict.

    Same as :func:`from_app` but returns the raw merged dict instead of a
    constructed dataclass.  ``${...}`` expression strings are preserved — call
    :func:`confarg.resolve` to resolve them, then :func:`confarg.build` or
    :func:`confarg.from_dict` to construct the dataclass.

    Like :func:`from_app`, this function calls :meth:`~cyclopts.App.parse_args`
    and will call :func:`sys.exit` if ``--help`` or ``--version`` was requested.

    :func:`populate_app` must have been called on *app* before calling this
    function.

    Args:
        target: The dataclass type to construct.
        app: The cyclopts :class:`~cyclopts.App` populated by
            :func:`populate_app`.
        argv: CLI token list.  ``None`` (default) reads ``sys.argv[1:]``.
        env: Environment variable mapping.  Defaults to :data:`os.environ`.
            Pass ``{}`` to disable env-var reading.
        env_prefix: Prefix for env vars.  ``None`` (default) disables env
            parsing entirely.
        env_separator: Separator used to split env var names into nested
            keys.
        config_flag: Name of the config-file option (must match
            :func:`populate_app`).  Set to ``""`` to ignore all config-file
            options.
        files: Additional root-level config file paths (lowest priority).
        env_config: Name of an env var whose value is a config file path to
            load.  Loaded after ``files`` but before CLI ``--config`` files.
        union_tag: Discriminator field name (same as :func:`confarg.load`).

    Returns:
        A plain dict of the merged configuration, with expression strings intact.

    Config file loading order:
        All config files share the same priority level (below inline env vars and
        CLI args).  Within that level they are loaded left-to-right so that later
        sources win on conflict: ``files`` first, then ``env_config``, then
        ``<config_flag>`` env vars (shallower subpaths first), then CLI
        ``--config`` / ``--config.subpath`` flags in left-to-right order.
    """
    if env is None:
        env = os.environ

    # Parse CLI tokens; exits on errors (exit_on_error=True by default).
    command, bound, _ = app.parse_args(argv)

    meta = _app_meta.get(id(app))
    confarg_fn = meta["command"] if meta else None
    if command is not confarg_fn:
        # --help, --version, or another special command: execute and exit.
        result = _run_command(command, bound)
        sys.exit(result if isinstance(result, int) else 0)

    # Extract CLI-provided values from the bound arguments.
    # Filter out None (= not provided by user) just as the synthetic fn would.
    name_map: dict[str, str] = meta["name_map"] if meta else {}
    raw: dict[str, Any] = {k: v for k, v in bound.arguments.items() if v is not None}
    flat: dict[str, Any] = {name_map.get(k, k): v for k, v in raw.items()}

    cli_data: dict[str, Any] = {}
    _collect_ns_fields(flat, target, prefix="", union_tag=union_tag, result=cli_data)

    # Scanning argv (not the bound arguments) preserves interleaved
    # --config[.subpath] ordering, so later CLI config files win on conflict, and
    # lets the patch scan apply list-index / append / delete / dict-subkey ops in
    # command order.
    argv_ = sys.argv[1:] if argv is None else list(argv)
    cli_data = _deep_merge(cli_data, _collect_cli_patch_ops(argv_, target, config_flag, union_tag))
    cli_configs = _collect_config_file_pairs(argv_, config_flag) if config_flag else []

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


def from_app(  # noqa: PLR0913
    target: object,
    app: cyclopts.App,
    *,
    argv: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
    env_prefix: str | None = _defaults.ENV_PREFIX,
    env_separator: str = _defaults.ENV_SEPARATOR,
    config_flag: str = _defaults.CONFIG_FLAG,
    files: Sequence[str | Path] = (),
    env_config: str | None = None,
    union_tag: str = _defaults.UNION_TAG,
) -> Any:
    """Parse CLI arguments and construct a dataclass from all sources.

    Calls :meth:`~cyclopts.App.parse_args` on *app* to parse *argv*, then
    merges CLI values with config files and environment variables — in the
    same priority order as :func:`confarg.load` — and returns the
    constructed dataclass.

    If ``--help`` or ``--version`` was requested, this function handles the
    output and calls :func:`sys.exit` as expected; the caller never receives
    a return value in that case.

    :func:`populate_app` must have been called on *app* before calling this
    function.

    Args:
        target: The dataclass type to construct.
        app: The cyclopts :class:`~cyclopts.App` populated by
            :func:`populate_app`.
        argv: CLI token list.  ``None`` (default) reads ``sys.argv[1:]``.
        env: Environment variable mapping.  Defaults to :data:`os.environ`.
            Pass ``{}`` to disable env-var reading.
        env_prefix: Prefix for env vars.  ``None`` (default) disables env
            parsing entirely.
        env_separator: Separator used to split env var names into nested
            keys.
        config_flag: Name of the config-file option (must match
            :func:`populate_app`).  Set to ``""`` to ignore all config-file
            options.
        files: Additional root-level config file paths (lowest priority).
        env_config: Name of an env var whose value is a config file path to
            load.  Loaded after ``files`` but before CLI ``--config`` files.
        union_tag: Discriminator field name (same as :func:`confarg.load`).

    Returns:
        An instance of *target* populated from all sources.
    """
    merged = merge_app(
        target,
        app,
        argv=argv,
        env=env,
        env_prefix=env_prefix,
        env_separator=env_separator,
        config_flag=config_flag,
        files=files,
        env_config=env_config,
        union_tag=union_tag,
    )
    return build(target, merged, union_tag=union_tag)


__all__ = ["from_app", "merge_app"]
