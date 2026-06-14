# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Convert an argparse Namespace into a nested dict for dataclass construction."""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import argparse
    from collections.abc import Mapping, Sequence
    from pathlib import Path

from confarg import _defaults
from confarg._api import build
from confarg._parse_cli import _collect_config_file_pairs
from confarg._pipeline import _merge_sources
from confarg.cli._collect import _collect_ns_fields


def merge_namespace(  # noqa: PLR0913
    target: object,
    ns: argparse.Namespace,
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

    Same as :func:`from_namespace` but returns the raw merged dict instead of a
    constructed dataclass.  ``${...}`` expression strings are preserved — call
    :func:`confarg.resolve` to resolve them, then :func:`confarg.build` or
    :func:`confarg.from_dict` to construct the dataclass.

    Args:
        target: The dataclass type to construct.
        ns: The Namespace returned by ``ArgumentParser.parse_args()``.
        argv: CLI argument list used to determine config-file loading order.
            Defaults to ``sys.argv[1:]``.  Pass an explicit list when
            ``parse_args()`` was called with a custom argv.
        env: Environment variable mapping.  Defaults to ``os.environ``.
            Pass ``{}`` to disable env-var reading.
        env_prefix: Prefix that env vars must start with. Defaults to ``None``,
            which disables environment variable parsing entirely. Set to ``""``
            to read all env vars without filtering, or to e.g. ``"MYAPP_"`` to
            read only vars with that prefix.
        env_separator: Separator used to split env var names into nested keys.
        config_flag: Name of the config-file attribute on ``ns`` (default
            ``"config"``).  Must match the ``config_flag`` passed to
            :func:`populate_parser`.  Subkey flags ``--config.<subpath>``
            (registered automatically by :func:`populate_parser`) are also
            consumed.  Set to ``""`` to ignore all config-file attributes.
        files: Additional root-level config file paths to load (lowest priority).
        env_config: Name of an env var whose value is a config file path to load.
            Loaded after ``files`` but before CLI ``--config`` files.
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

    cli_data: dict[str, Any] = {}
    _collect_ns_fields(vars(ns), target, prefix="", union_tag=union_tag, result=cli_data)

    # Scanning argv (not the namespace) preserves interleaved --config[.subpath]
    # ordering, so later CLI config files win on conflict.
    argv_ = sys.argv[1:] if argv is None else list(argv)
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


def from_namespace(  # noqa: PLR0913
    target: object,
    ns: argparse.Namespace,
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
    """Construct a dataclass instance from an argparse :class:`~argparse.Namespace`.

    Merges three sources in ascending priority order: config files, environment
    variables, then CLI arguments from the Namespace.  This mirrors the
    behaviour of :func:`confarg.load`.

    Only fields registered by :func:`populate_parser` are consumed from ``ns``.
    Fields absent from the Namespace fall back to env vars, config files, or
    dataclass defaults; missing required fields raise
    :class:`~confarg.exceptions.MissingFieldError`.

    Args:
        target: The dataclass type to construct.
        ns: The Namespace returned by ``ArgumentParser.parse_args()``.
        argv: CLI argument list used to determine config-file loading order.
            Defaults to ``sys.argv[1:]``.  Pass an explicit list when
            ``parse_args()`` was called with a custom argv.
        env: Environment variable mapping.  Defaults to ``os.environ``.
            Pass ``{}`` to disable env-var reading.
        env_prefix: Prefix that env vars must start with. Defaults to ``None``,
            which disables environment variable parsing entirely. Set to ``""``
            to read all env vars without filtering, or to e.g. ``"MYAPP_"`` to
            read only vars with that prefix.
        env_separator: Separator used to split env var names into nested keys.
        config_flag: Name of the config-file attribute on ``ns`` (default
            ``"config"``).  Must match the ``config_flag`` passed to
            :func:`populate_parser`.  Subkey flags ``--config.<subpath>``
            (registered automatically by :func:`populate_parser`) are also
            consumed.  Set to ``""`` to ignore all config-file attributes.
        files: Additional root-level config file paths to load (lowest priority).
        env_config: Name of an env var whose value is a config file path to load.
            Loaded after ``files`` but before CLI ``--config`` files.
        union_tag: Discriminator field name (same as :func:`confarg.load`).

    Returns:
        An instance of ``target`` populated from all sources.
    """
    merged = merge_namespace(
        target,
        ns,
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
