# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Convert a Typer Context into a nested dict for dataclass construction."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    import typer

from confarg import _defaults
from confarg.cli import _clicklike


def merge_context(  # noqa: PLR0913
    target: object,
    ctx: typer.Context,
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

    Same as :func:`from_context` but returns the raw merged dict instead of a
    constructed dataclass.  ``${...}`` expression strings are preserved — call
    :func:`confarg.resolve` to resolve them, then :func:`confarg.build` or
    :func:`confarg.from_dict` to construct the dataclass.

    Args:
        target: The dataclass type to construct.
        ctx: The :class:`typer.Context` Typer passes to the command function.
            Declare it as a parameter of the command to receive it.
        argv: CLI argument list used to determine config-file loading order.
            Defaults to ``sys.argv[1:]``.  Pass an explicit list when the
            command was invoked with a custom argv (e.g. in tests).
        env: Environment variable mapping.  Defaults to ``os.environ``.
            Pass ``{}`` to disable env-var reading.
        env_prefix: Prefix that env vars must start with. Defaults to ``None``,
            which disables environment variable parsing entirely.
        env_separator: Separator used to split env var names into nested keys.
        cli_prefix: Namespace the confarg flags live under.  Omit it (the
            default) to reuse the value passed to :func:`populate_command`, which
            is the normal case; passing one that disagrees with what was
            registered raises :class:`~confarg.exceptions.ConfargError`
            rather than silently matching no flags.
        config_flag: Name of the config-file option on ``ctx`` (default
            ``"config"``).  Must match the ``config_flag`` passed to
            :func:`populate_command`.  Set to ``""`` to ignore all config-file
            options.
        files: Additional root-level config file paths to load (lowest priority).
        env_config: Name of an env var whose value is a config file path to load.
            Loaded after ``files`` but before CLI ``--config`` files.
        union_tag: Discriminator field name (same as :func:`confarg.load`).

    Returns:
        A plain dict of the merged configuration, with expression strings intact.

    Config file loading order:
        Same as :func:`confarg.merge`.
    """
    return _clicklike.merge_from_ctx(
        target,
        ctx,
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


def from_context(  # noqa: PLR0913
    target: object,
    ctx: typer.Context,
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
    """Construct a dataclass instance from a :class:`typer.Context`.

    Merges three sources in ascending priority order: config files, environment
    variables, then CLI arguments from the Context.  This mirrors the behaviour
    of :func:`confarg.load`.

    Only options registered by :func:`populate_command` are consumed from ``ctx``.
    Options absent from the Context (i.e. not provided by the user) fall back to
    env vars, config files, or dataclass defaults; missing required fields raise
    :class:`~confarg.exceptions.MissingFieldError`.

    Args:
        target: The dataclass type to construct.
        ctx: The :class:`typer.Context` Typer passes to the command function.
            Declare it as a parameter of the command to receive it.
        argv: CLI argument list used to determine config-file loading order.
            Defaults to ``sys.argv[1:]``.  Pass an explicit list when the
            command was invoked with a custom argv (e.g. in tests).
        env: Environment variable mapping.  Defaults to ``os.environ``.
            Pass ``{}`` to disable env-var reading.
        env_prefix: Prefix that env vars must start with. Defaults to ``None``,
            which disables environment variable parsing entirely.
        env_separator: Separator used to split env var names into nested keys.
        cli_prefix: Namespace the confarg flags live under.  Omit it (the
            default) to reuse the value passed to :func:`populate_command`, which
            is the normal case; passing one that disagrees with what was
            registered raises :class:`~confarg.exceptions.ConfargError`
            rather than silently matching no flags.
        config_flag: Name of the config-file option on ``ctx`` (default
            ``"config"``).  Must match the ``config_flag`` passed to
            :func:`populate_command`.  Set to ``""`` to ignore all config-file
            options.
        files: Additional root-level config file paths to load (lowest priority).
        env_config: Name of an env var whose value is a config file path to load.
            Loaded after ``files`` but before CLI ``--config`` files.
        union_tag: Discriminator field name (same as :func:`confarg.load`).

    Returns:
        An instance of ``target`` populated from all sources.
    """
    return _clicklike.construct_from_ctx(
        target,
        ctx,
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


__all__ = ["from_context", "merge_context"]
