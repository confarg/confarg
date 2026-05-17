# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Parse a cyclopts App invocation and construct a dataclass from all sources."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    import cyclopts

from confarg import _defaults
from confarg._files import _load_subpath_files
from confarg._merge import _deep_merge
from confarg._parse_env import _parse_env
from confarg._types import _resolve_type
from confarg.cli.argparse._namespace import _collect_ns_fields
from confarg.cli.cyclopts._register import _app_meta
from confarg.dictexpr import resolve_expressions
from confarg.typedload import construct


def _run_command(command: Any, bound: Any) -> Any:
    """Call *command* with its bound arguments; return the result."""
    return command(*bound.args, **bound.kwargs) if bound is not None else command()


def merge_app(  # noqa: PLR0913
    target: object,
    app: cyclopts.App,
    *,
    union_tag: str = _defaults.UNION_TAG,
    config_flag: str = "config",
    argv: Sequence[str] | None = None,
    files: Sequence[str | Path] = (),
    env: Mapping[str, str] | None = None,
    env_prefix: str | None = _defaults.ENV_PREFIX,
    env_separator: str = "__",
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
        union_tag: Discriminator field name (same as :func:`confarg.load`).
        config_flag: Name of the config-file option (must match
            :func:`populate_app`).
        argv: CLI token list.  ``None`` (default) reads ``sys.argv[1:]``.
        files: Additional root-level config file paths (lowest priority).
        env: Environment variable mapping.  Defaults to :data:`os.environ`.
            Pass ``{}`` to disable env-var reading.
        env_prefix: Prefix for env vars.  ``None`` (default) disables env
            parsing entirely.
        env_separator: Separator used to split env var names into nested
            keys.

    Returns:
        A plain dict of the merged configuration, with expression strings intact.
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

    # 1. Collect CLI field values
    cli_data: dict[str, Any] = {}
    _collect_ns_fields(flat, target, prefix="", union_tag=union_tag, result=cli_data)

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
        env_data, env_configs = _parse_env(env, env_prefix, env_separator, target)
    config_data = _deep_merge(config_data, _load_subpath_files(env_configs, union_tag), union_tag=union_tag)

    # 5. Merge: config < env < CLI
    merged = _deep_merge(config_data, env_data, union_tag=union_tag)
    return _deep_merge(merged, cli_data, union_tag=union_tag)


def from_app(  # noqa: PLR0913
    target: object,
    app: cyclopts.App,
    *,
    union_tag: str = _defaults.UNION_TAG,
    config_flag: str = "config",
    argv: Sequence[str] | None = None,
    files: Sequence[str | Path] = (),
    env: Mapping[str, str] | None = None,
    env_prefix: str | None = _defaults.ENV_PREFIX,
    env_separator: str = "__",
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
        union_tag: Discriminator field name (same as :func:`confarg.load`).
        config_flag: Name of the config-file option (must match
            :func:`populate_app`).
        argv: CLI token list.  ``None`` (default) reads ``sys.argv[1:]``.
        files: Additional root-level config file paths (lowest priority).
        env: Environment variable mapping.  Defaults to :data:`os.environ`.
            Pass ``{}`` to disable env-var reading.
        env_prefix: Prefix for env vars.  ``None`` (default) disables env
            parsing entirely.
        env_separator: Separator used to split env var names into nested
            keys.

    Returns:
        An instance of *target* populated from all sources.
    """
    merged = merge_app(
        target,
        app,
        union_tag=union_tag,
        config_flag=config_flag,
        argv=argv,
        files=files,
        env=env,
        env_prefix=env_prefix,
        env_separator=env_separator,
    )
    merged = resolve_expressions(merged)
    return construct(_resolve_type(target), merged, union_tag=union_tag)


__all__ = ["from_app", "merge_app"]
