# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The single source-merging pipeline shared by ``confarg.merge()`` and all CLI adapters.

Every entry point — vanilla :func:`confarg.merge` and the argparse/click/cyclopts
``merge_*`` functions — first extracts CLI-provided values and ``--config`` file
pairs in its own way, then delegates here.  Fix merge-order or file-loading
behavior in this module only; it lands in all integrations at once.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

from confarg._files import _load_file, _load_file_item, _load_subpath_files
from confarg._merge import LIST_APPEND_KEY as _LIST_APPEND_KEY
from confarg._merge import _deep_merge
from confarg._parse_env import _parse_env
from confarg.exceptions import ConfargError


def _load_cli_config(fpath: Path, subpath: str, config_flag: str) -> dict[str, Any]:
    """Load one CLI config file (--config[.subpath][+] fpath) into a nested dict."""
    if subpath.endswith("+"):
        real_subpath = subpath[:-1].rstrip(".")
        if not real_subpath:
            msg = f"--{config_flag}+ requires a field path. Use --{config_flag}.fieldname+ /path/to/file."
            raise ConfargError(msg)
        last_key = real_subpath.rsplit(".", 1)[-1]
        fitem = _load_file_item(fpath)
        if isinstance(fitem, list):
            append_items: list[Any] = [fitem]
        elif isinstance(fitem, dict) and len(fitem) == 1 and last_key in fitem and isinstance(fitem[last_key], list):
            append_items = fitem[last_key]
        else:
            append_items = [fitem]
        fdata: dict[str, Any] = {_LIST_APPEND_KEY: append_items}
        for part in reversed(real_subpath.split(".")):
            fdata = {part: fdata}
        return fdata

    fdata = _load_file(fpath)
    if subpath:
        for part in reversed(subpath.split(".")):
            fdata = {part: fdata}
    return fdata


def _merge_sources(  # noqa: PLR0913  # internal pipeline; mirrors merge()'s parameter surface
    target: Any,
    cli_data: dict[str, Any],
    cli_configs: Sequence[tuple[str, Path]],
    *,
    env: Mapping[str, str],
    env_prefix: str | None,
    env_separator: str,
    config_flag: str,
    files: Sequence[str | Path],
    env_config: str | None,
    union_tag: str,
) -> dict[str, Any]:
    """Merge pre-collected CLI data with env vars and config files in priority order.

    Args:
        target: The target type, guiding env-var parsing.
        cli_data: Nested dict of CLI-provided field values (highest priority).
        cli_configs: (subpath, path) pairs from ``--config[.subpath][+]`` flags,
            in left-to-right CLI order.
        env: Environment variable mapping to scan.
        env_prefix: Prefix that env vars must start with; ``None`` disables
            env-var parsing entirely.
        env_separator: Separator used to split env var names into nested keys.
        config_flag: Name of the config-file flag; the env segment with this name
            marks a sub-config file pointer. ``""`` disables env config pointers.
        files: Paths of config files to load first (lowest priority).
        env_config: Name of an env var whose value is a config file path to load
            after ``files`` but before env- and CLI-specified config files.
        union_tag: Field name used as a discriminator tag in union types.

    Returns:
        A plain dict of the merged configuration, with expression strings intact.

    Config file loading order (all at the same priority level, below inline
    env vars and CLI args; later files win on conflict):
        1. ``files`` — in the order given.
        2. ``env_config`` — the single global path named by that env var (if set).
        3. ``<config_flag>__*`` env vars — sorted lexicographically, i.e. by
           subpath depth (shallower paths first).
        4. ``cli_configs`` — in left-to-right CLI order.
    """
    # 1. Parse env vars (done here so env-specified config files are loaded in order)
    if env_prefix is None:
        env_data: dict[str, Any] = {}
        env_configs: list[tuple[str, Path]] = []
    else:
        # Exclude the env_config key so it is not mistakenly treated as a field.
        env_for_fields = {k: v for k, v in env.items() if k != env_config} if env_config else env
        env_data, env_configs = _parse_env(env_for_fields, env_prefix, env_separator, target, config_flag)

    # 2. Load config files in priority order (all become config-level, below inline env/CLI)
    file_entries: list[tuple[str, Path]] = [("", Path(f)) for f in files]
    if env_config and (env_config_path := env.get(env_config)):
        file_entries.append(("", Path(env_config_path)))
    env_configs.sort(key=lambda ec: ec[0])
    config_data = _load_subpath_files(file_entries + env_configs, union_tag)
    for subpath, fpath in cli_configs:
        fdata = _load_cli_config(fpath, subpath, config_flag)
        config_data = _deep_merge(config_data, fdata, union_tag=union_tag)

    # 3. Merge: config (lowest) → env → CLI (highest)
    merged = _deep_merge(config_data, env_data, union_tag=union_tag)
    return _deep_merge(merged, cli_data, union_tag=union_tag)
