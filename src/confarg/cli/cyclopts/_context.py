# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Parse a cyclopts App invocation and construct a dataclass from all sources."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    import cyclopts

from confarg import _defaults
from confarg._parse_cli import _collect_config_file_pairs
from confarg.cli._argv import drop_bare_occurrences, refuse_bare_occurrences
from confarg.cli._collect import _construct_from_merged, _merge_from_flat
from confarg.cli._prefix import PREFIX_ATTR, resolve_prefix, strip_argv_prefix
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
    cli_prefix: str | None = None,
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
        cli_prefix: Namespace the confarg flags live under.  Omit it (the
            default) to reuse the value passed to :func:`populate_app`, which
            is the normal case; passing one that disagrees with what was
            registered raises :class:`~confarg.exceptions.ConfargError`
            rather than silently matching no flags.
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
        Same as :func:`confarg.merge`.
    """
    meta = _app_meta.get(id(app))

    # Parse CLI tokens; exits on errors (exit_on_error=True by default).  cyclopts is
    # handed the argv without the bare occurrences of a flag that takes zero *or* more
    # items: it reads one as an implicit empty container and then asserts when that
    # meets a real token.  A fixed-arity flag cannot drop its bare occurrence -- the
    # occurrence is a missing value, not a no-op -- so it is refused instead, before
    # cyclopts parses, with confarg's own error.  Both scans read the argv the user
    # typed (docs-dev/architecture/cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare).
    prefix = resolve_prefix(meta.get(PREFIX_ATTR) if meta else None, cli_prefix)
    tokens = sys.argv[1:] if argv is None else list(argv)
    if config_flag:
        # A bare --config[.subpath] must be refused before cyclopts parses it, with
        # confarg's own error rather than the framework's implicit-token assertion.
        _collect_config_file_pairs(strip_argv_prefix(tokens, prefix), config_flag, target, union_tag)
    refuse_bare_occurrences(tokens, meta["refuses_bare"] if meta else ())
    command, bound, _ = app.parse_args(
        drop_bare_occurrences(tokens, meta["stands_bare"] if meta else ()),
    )

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

    return _merge_from_flat(
        flat,
        target,
        argv=argv,
        cli_prefix=prefix,
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
    cli_prefix: str | None = None,
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
        cli_prefix: Namespace the confarg flags live under.  Omit it (the
            default) to reuse the value passed to :func:`populate_app`, which
            is the normal case; passing one that disagrees with what was
            registered raises :class:`~confarg.exceptions.ConfargError`
            rather than silently matching no flags.
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
        cli_prefix=cli_prefix,
        config_flag=config_flag,
        files=files,
        env_config=env_config,
        union_tag=union_tag,
    )
    return _construct_from_merged(target, merged, union_tag)


__all__ = ["from_app", "merge_app"]
