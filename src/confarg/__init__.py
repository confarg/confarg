# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""confarg — read configuration from CLI args, env vars, and config files into dataclasses."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

from confarg import _defaults
from confarg._errors import (
    AmbiguousUnionError,
    CircularReferenceError,
    ConfargError,
    ConfargWarning,
    ExpressionEvalError,
    InvalidConfigFileError,
    MissingFieldError,
    MissingReferenceError,
    SymbolImportError,
    TypeCoercionError,
    UnknownArgumentError,
    UnsafeExpressionError,
)
from confarg._files import INCLUDE_KEY, _dump_file, _load_file, _load_file_item
from confarg._merge import LIST_APPEND_KEY, _deep_merge
from confarg._parse_cli import _parse_cli
from confarg._parse_env import _parse_env
from confarg._serialize import _serialize
from confarg._types import _MISSING, TagPolicy, _is_dc, _is_struct, _is_struct_like, _resolve_type
from confarg.dictexpr import resolve_expressions
from confarg.typedload import construct as _tc


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
        fdata: dict[str, Any] = {LIST_APPEND_KEY: append_items}
        for part in reversed(real_subpath.split(".")):
            fdata = {part: fdata}
        return fdata

    fdata = _load_file(fpath)
    if subpath:
        for part in reversed(subpath.split(".")):
            fdata = {part: fdata}
    return fdata


def merge(  # noqa: PLR0913
    target: type,
    *,
    args: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
    env_prefix: str | None = _defaults.ENV_PREFIX,
    env_separator: str = "__",
    cli_prefix: str = "",
    config_flag: str = "config",
    files: Sequence[str | Path] = (),
    env_config: str | None = None,
    union_tag: str = _defaults.UNION_TAG,
) -> dict[str, Any]:
    """Collect and merge configuration from all sources into a raw dict.

    Sources are merged in priority order: config files (lowest), then
    environment variables, then CLI arguments (highest). No expression
    resolution and no dataclass construction are performed — the returned
    dict reflects the config input exactly as written, with ${...}
    expression strings preserved.

    Args:
        target: The dataclass type (or scalar type) used to guide CLI parsing.
        args: CLI arguments to parse. Defaults to sys.argv[1:].
        env: Environment variable mapping to scan. Defaults to os.environ.
        env_prefix: Prefix that env vars must start with. Defaults to ``None``,
            which disables environment variable parsing entirely. Set to ``""``
            to read all env vars without filtering, or to e.g. ``"MYAPP_"`` to
            read only vars with that prefix.
        env_separator: Separator used to split env var names into nested keys.
            Defaults to ``"__"`` (double underscore).
        cli_prefix: Required prefix for all CLI flags. Defaults to ``""``,
            which means no prefix is required.
        config_flag: Flag name used to specify config files on the CLI
            (``--config path/to/file.yaml``). Set to ``""`` to disable.
            Defaults to ``"config"``.
        files: Paths to config files to load.
        env_config: Name of an env var whose value is a config file path to load.
            Loaded after ``files`` but before CLI ``--config`` files.
        union_tag: Field name used as a discriminator tag in union types.
            Defaults to ``"class"`` — a Python keyword that can never clash
            with a dataclass field name.

    Returns:
        A plain dict of the merged configuration, with expression strings intact.

    Config file loading order:
        All config files share the same priority level (below inline env vars and
        CLI args).  Within that level they are loaded left-to-right so that later
        sources win on conflict.  The full sequence is:

        1. ``files`` — in the order given.
        2. ``env_config`` — the single global path named by that env var (if set).
        3. ``CONFIG__*`` env vars — sorted lexicographically by their env var name,
           which is equivalent to sorting by subpath depth (shallower paths first).
           A global ``CONFIG=file`` therefore loads before ``CONFIG__DB=db.yaml``,
           which loads before ``CONFIG__DB__HOST=host.yaml``.
        4. CLI ``--config`` / ``--config.subpath`` flags — in left-to-right order.

    Raises:
        InvalidConfigFileError: If a config file cannot be loaded.
        UnknownArgumentError: If an unrecognized CLI argument is encountered.
    """
    if args is None:
        args = sys.argv[1:]
    if env is None:
        env = os.environ

    # 1. Parse CLI
    cli_data, cli_configs = _parse_cli(args, target, cli_prefix, config_flag, union_tag)

    # 2. Parse env vars (done here so env-specified config files are loaded in order)
    if env_prefix is None:
        env_data: dict[str, Any] = {}
        env_configs: list[tuple[str, Path]] = []
    else:
        # Exclude the env_config key so it is not mistakenly treated as a field.
        env_for_fields = {k: v for k, v in env.items() if k != env_config} if env_config else env
        env_data, env_configs = _parse_env(env_for_fields, env_prefix, env_separator, target, config_flag)

    # 3. Load config files in priority order (all become config-level, below inline env/CLI)
    config_data: dict[str, Any] = {}
    for f in files:
        config_data = _deep_merge(config_data, _load_file(Path(f)), union_tag=union_tag)
    if env_config is not None:
        env_config_path = env.get(env_config)
        if env_config_path:
            config_data = _deep_merge(config_data, _load_file(Path(env_config_path)), union_tag=union_tag)
    env_configs.sort(key=lambda ec: ec[0])
    for subpath, fpath in env_configs:
        fdata: dict[str, Any] = _load_file(fpath)
        if subpath:
            for part in reversed(subpath.split(".")):
                fdata = {part: fdata}
        config_data = _deep_merge(config_data, fdata, union_tag=union_tag)
    for subpath, fpath in cli_configs:
        fdata = _load_cli_config(fpath, subpath, config_flag)
        config_data = _deep_merge(config_data, fdata, union_tag=union_tag)

    # 4. Merge: config (lowest) → env → CLI (highest)
    merged = _deep_merge(config_data, env_data, union_tag=union_tag)
    return _deep_merge(merged, cli_data, union_tag=union_tag)


def build[T](
    target: type[T],
    data: dict[str, Any],
    *,
    union_tag: str = "class",
) -> T:
    """Resolve ``${...}`` expressions and construct the target type from a merged config dict.

    Use this as the second step after ``merge()``, or to load configuration
    from a dict you have assembled yourself.

    Args:
        target: The dataclass type (or scalar type) to construct.
        data: The raw config dict (e.g. the output of ``merge()``).
        union_tag: The field name used as a discriminator tag in unions.

    Returns:
        An instance of the target type.

    Raises:
        MissingFieldError: If a required field is not provided.
        TypeCoercionError: If a value cannot be coerced to the target type.
        AmbiguousUnionError: If a Union cannot be disambiguated.
        CircularReferenceError: If expression references form a cycle.
        UnsafeExpressionError: If an expression contains disallowed constructs.
        MissingReferenceError: If an expression references a field that does not exist.
        ExpressionEvalError: If an expression fails at runtime.
    """
    target_r = _resolve_type(target)
    is_dataclass = _is_struct_like(target_r)

    resolved = resolve_expressions(data)

    if not is_dataclass:
        raw = resolved.get("__root__", _MISSING)
        if raw is _MISSING:
            msg = (
                f"No value provided for target type {target_r!r}."
                " Provide a value via CLI flag (--<prefix> <value>), environment variable, or config file."
            )
            raise MissingFieldError(msg)
        return _tc(target_r, raw, union_tag=union_tag)  # type: ignore[return-value]

    return _tc(target_r, resolved, union_tag=union_tag)  # type: ignore[return-value]


def resolve(data: dict[str, Any]) -> dict[str, Any]:
    """Resolve ``${...}`` expressions in a merged config dict.

    Use this between ``merge()`` and ``from_dict()`` when you need the
    resolved dict itself (e.g. to inspect values or write it to a file):

        raw = confarg.merge(MyConfig, ...)
        resolved = confarg.resolve(raw)
        confarg.dump_file(resolved, "out.yaml")
        cfg = confarg.from_dict(MyConfig, resolved)

    Args:
        data: A plain config dict, e.g. the output of ``merge()``.

    Returns:
        A new dict with all ``${...}`` expression strings replaced by their values.

    Raises:
        CircularReferenceError: If expression references form a cycle.
        UnsafeExpressionError: If an expression contains disallowed constructs.
        MissingReferenceError: If an expression references a field that does not exist.
        ExpressionEvalError: If an expression fails at runtime.
    """
    return resolve_expressions(data)


def from_dict[T](
    target: type[T],
    data: dict[str, Any],
    *,
    union_tag: str = "class",
) -> T:
    """Construct a typed object from an already-resolved config dict.

    Unlike ``build()``, this does NOT resolve ``${...}`` expressions — call
    ``resolve()`` first if needed.

    Args:
        target: The dataclass or plain-class type to construct.
        data: A resolved config dict (output of resolve() or merge()).
        union_tag: The field name used as a discriminator tag in unions.

    Returns:
        An instance of the target type.

    Raises:
        MissingFieldError: If a required field is not provided.
        TypeCoercionError: If a value cannot be coerced to the target type.
        AmbiguousUnionError: If a Union cannot be disambiguated.
    """
    target_r = _resolve_type(target)
    return _tc(target_r, data, union_tag=union_tag)  # type: ignore[return-value]


def load[T](  # noqa: PLR0913
    target: type[T],
    *,
    args: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
    env_prefix: str | None = _defaults.ENV_PREFIX,
    env_separator: str = "__",
    cli_prefix: str = "",
    config_flag: str = "config",
    files: Sequence[str | Path] = (),
    env_config: str | None = None,
    union_tag: str = _defaults.UNION_TAG,
) -> T:
    """Merge configuration from all sources and construct the target type.

    Convenience wrapper for ``merge()`` + ``build()``. For more control —
    e.g. to inspect or save the raw merged dict — call those directly.
    See ``merge()`` for source priority and config file loading order.

    Args:
        target: The dataclass type (or scalar type) to load configuration into.
        args: CLI arguments to parse. Defaults to sys.argv[1:].
        env: Environment variable mapping to scan. Defaults to os.environ.
        env_prefix: Prefix that env vars must start with. Defaults to ``None``,
            which disables environment variable parsing entirely. Set to ``""``
            to read all env vars without filtering, or to e.g. ``"MYAPP_"`` to
            read only vars with that prefix.
        env_separator: Separator used to split env var names into nested keys.
            Defaults to ``"__"`` (double underscore).
        cli_prefix: Required prefix for all CLI flags. Defaults to ``""``,
            which means no prefix is required.
        config_flag: Flag name used to specify config files on the CLI
            (``--config path/to/file.yaml``). Set to ``""`` to disable.
            Defaults to ``"config"``.
        files: Paths to config files to load.
        env_config: Name of an env var whose value is a config file path to load.
            Loaded after ``files`` but before CLI ``--config`` files.
        union_tag: Field name used as a discriminator tag in union types.
            Defaults to ``"class"`` — a Python keyword that can never clash
            with a dataclass field name.

    Returns:
        An instance of the target type populated with the merged configuration.

    Raises:
        MissingFieldError: If a required field is not provided by any source.
        TypeCoercionError: If a value cannot be coerced to the target type.
        InvalidConfigFileError: If a config file cannot be loaded.
        UnknownArgumentError: If an unrecognized CLI argument is encountered.
        AmbiguousUnionError: If a Union cannot be disambiguated.
        CircularReferenceError: If expression references form a cycle.
        UnsafeExpressionError: If an expression contains disallowed constructs.
        MissingReferenceError: If an expression references a field that does not exist.
        ExpressionEvalError: If an expression fails at runtime.
    """
    data = merge(
        target,
        args=args,
        env=env,
        env_prefix=env_prefix,
        env_separator=env_separator,
        cli_prefix=cli_prefix,
        config_flag=config_flag,
        files=files,
        env_config=env_config,
        union_tag=union_tag,
    )
    return build(target, data, union_tag=union_tag)


def _strip_str_tokens(value: Any) -> Any:
    """Recursively convert _StrToken instances to plain str for serialization."""
    from confarg._types import _StrToken as _ST

    if type(value) is _ST:
        return str(value)
    if isinstance(value, dict):
        return {k: _strip_str_tokens(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_strip_str_tokens(v) for v in value]
    return value


def dump(
    value: Any,
    *,
    union_tag: str = "class",
    tag_policy: TagPolicy = "auto",
) -> dict[str, Any]:
    """Serialize a dataclass instance to a config-compatible plain dict.

    Args:
        value: A dataclass instance.
        union_tag: The field name used as a discriminator tag in unions.
        tag_policy: ``"auto"`` (tag only when needed) or ``"always"`` (tag every union member).

    Returns:
        A plain dict representation.

    Raises:
        TypeError: If value is not a dataclass instance.
    """
    if isinstance(value, dict):
        msg = (
            "dump() takes a dataclass instance, not a dict."
            " To write a raw config dict to a file, use dump_file() directly."
        )
        raise TypeError(msg)
    if isinstance(value, type) or not _is_dc(type(value)):
        tp_name = type(value).__name__
        if _is_struct(type(value)):
            msg = (
                f"dump() only supports dataclass instances, not plain classes.\n"
                f"{tp_name} is a plain class — keep the merged dict and dump that instead:\n"
                f"  raw = confarg.merge(...)\n"
                f"  confarg.dump_file(raw, path)"
            )
            raise TypeError(msg)
        msg = f"Expected a dataclass instance, got {tp_name}"
        raise TypeError(msg)
    tp = type(value)
    return _serialize(tp, value, "", union_tag, tag_policy)


def dump_file(
    value: Any,
    path: str | Path,
    *,
    union_tag: str = "class",
    tag_policy: TagPolicy = "auto",
) -> None:
    """Serialize and write to a config file.

    Accepts a dataclass instance or a raw config dict (e.g. from ``merge()``
    or ``resolve()``). The output format is determined by the file extension
    (.toml, .yaml, .yml, .json).

    Args:
        value: A dataclass instance or a raw config dict.
        path: Path to the output file.
        union_tag: The field name used as a discriminator tag in unions.
        tag_policy: ``"auto"`` or ``"always"``.

    Raises:
        TypeError: If value is not a dataclass instance or a dict.
        InvalidConfigFileError: If the format is unsupported or the required library is not installed.
    """
    if isinstance(value, dict):
        _dump_file(_strip_str_tokens(value), Path(path))
    else:
        _dump_file(dump(value, union_tag=union_tag, tag_policy=tag_policy), Path(path))


__all__ = [
    # Two-step API
    "merge",
    "build",
    # Three-step API (dict-centric)
    "resolve",
    "from_dict",
    # One-step convenience
    "load",
    # Dump
    "dump",
    "dump_file",
    # Types
    "TagPolicy",
    # Errors / warnings
    "ConfargError",
    "ConfargWarning",
    "MissingFieldError",
    "SymbolImportError",
    "TypeCoercionError",
    "InvalidConfigFileError",
    "UnknownArgumentError",
    "AmbiguousUnionError",
    "CircularReferenceError",
    "MissingReferenceError",
    "UnsafeExpressionError",
    "ExpressionEvalError",
    # Constants
    "INCLUDE_KEY",
]
