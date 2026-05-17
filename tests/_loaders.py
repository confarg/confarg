# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Loader wrappers that give each CLI integration a confarg.load()-compatible interface.

Each loader provides ``load()`` and ``merge()`` methods with the same signature
as ``confarg.load()`` / ``confarg.merge()`` (minus the vanilla-only parameter
``cli_prefix``), forwarding arguments unchanged to the underlying integration.
``registered_flags()`` exposes the dotted flag names that ``populate_*``
registers on the host framework (``None`` for vanilla, which has no
registration step).

List-field CLI syntax differs between loaders:
- ``VanillaLoader``, ``ArgparseLoader``, ``CycloptsLoader``: space-separated
  (``--tags a b c``, nargs="*" style)
- ``ClickLoader``: repeated flags (``--tags a --tags b --tags c``)
- ``CycloptsLoader``: accepts both forms

This difference is intentional and must be visible in tests: write separate
test functions for each convention rather than hiding the difference.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import click
import cyclopts
from click.testing import CliRunner

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

import confarg
import confarg.cli.click as confargclick
import confarg.cli.cyclopts as confargcyclopts
from confarg import _defaults
from confarg.cli.argparse import from_namespace, make_parser, merge_namespace
from confarg.cli.click import populate_command
from confarg.cli.cyclopts import populate_app
from confarg.cli.cyclopts._register import _app_meta


class ConfargLoader(ABC):
    """Abstract base for CLI-integration loaders."""

    id: str

    @abstractmethod
    def _run(self, target: type, *, construct: bool, **kw: Any) -> Any:
        """Run the integration's full pipeline; construct the target or return the raw dict."""

    def load(  # noqa: PLR0913 — mirrors confarg.load's keyword-only signature
        self,
        target: type,
        *,
        argv: Sequence[str] | None = None,
        env: Mapping[str, str] | None = None,
        env_prefix: str | None = _defaults.ENV_PREFIX,
        env_separator: str = _defaults.ENV_SEPARATOR,
        config_flag: str = _defaults.CONFIG_FLAG,
        files: Sequence[Path] = (),
        env_config: str | None = None,
        union_tag: str = _defaults.UNION_TAG,
    ) -> Any:
        """Load *target* using this integration's CLI parser (mirrors ``confarg.load``)."""
        return self._run(
            target,
            construct=True,
            argv=argv,
            env=env,
            env_prefix=env_prefix,
            env_separator=env_separator,
            config_flag=config_flag,
            files=files,
            env_config=env_config,
            union_tag=union_tag,
        )

    def merge(  # noqa: PLR0913 — mirrors confarg.merge's keyword-only signature
        self,
        target: type,
        *,
        argv: Sequence[str] | None = None,
        env: Mapping[str, str] | None = None,
        env_prefix: str | None = _defaults.ENV_PREFIX,
        env_separator: str = _defaults.ENV_SEPARATOR,
        config_flag: str = _defaults.CONFIG_FLAG,
        files: Sequence[Path] = (),
        env_config: str | None = None,
        union_tag: str = _defaults.UNION_TAG,
    ) -> dict[str, Any]:
        """Merge all sources into a raw dict (mirrors ``confarg.merge``)."""
        return self._run(
            target,
            construct=False,
            argv=argv,
            env=env,
            env_prefix=env_prefix,
            env_separator=env_separator,
            config_flag=config_flag,
            files=files,
            env_config=env_config,
            union_tag=union_tag,
        )

    def registered_flags(
        self,
        target: type,
        *,
        config_flag: str = _defaults.CONFIG_FLAG,
        config_subkeys: bool = True,
        union_tag: str = _defaults.UNION_TAG,
    ) -> set[str] | None:
        """Dotted flag names that ``populate_*`` registers, or None (vanilla: no registration)."""
        return None

    def __repr__(self) -> str:
        return self.id


class VanillaLoader(ConfargLoader):
    """Delegates directly to ``confarg.load()`` / ``confarg.merge()``."""

    id = "vanilla"

    def _run(self, target: type, *, construct: bool, **kw: Any) -> Any:
        fn = confarg.load if construct else confarg.merge
        return fn(target, **kw)


class ArgparseLoader(ConfargLoader):
    """Wraps ``make_parser`` → ``parse_args`` → ``from_namespace`` / ``merge_namespace``."""

    id = "argparse"

    def _run(self, target: type, *, construct: bool, **kw: Any) -> Any:
        argv = list(kw.pop("argv") or [])
        config_flag = kw.pop("config_flag")
        union_tag = kw.pop("union_tag")
        parser = make_parser(target, config_flag=config_flag, union_tag=union_tag, argv=argv)
        ns = parser.parse_args(argv)
        fn = from_namespace if construct else merge_namespace
        return fn(target, ns, argv=argv, config_flag=config_flag, union_tag=union_tag, **kw)

    def registered_flags(
        self,
        target: type,
        *,
        config_flag: str = _defaults.CONFIG_FLAG,
        config_subkeys: bool = True,
        union_tag: str = _defaults.UNION_TAG,
    ) -> set[str] | None:
        parser = make_parser(target, config_flag=config_flag, config_subkeys=config_subkeys, union_tag=union_tag)
        return {s[2:] for a in parser._actions for s in a.option_strings if s.startswith("--") and s != "--help"}


class ClickLoader(ConfargLoader):
    """Wraps ``populate_command`` → ``CliRunner.invoke`` → ``from_context`` / ``merge_context``.

    Click uses repeated flags for list fields (``--tags a --tags b``).
    Tests that exercise list CLI args must use that convention when parametrised
    with this loader.
    """

    id = "click"

    def _run(self, target: type, *, construct: bool, **kw: Any) -> Any:
        argv = list(kw.pop("argv") or [])
        config_flag = kw.pop("config_flag")
        result_holder: list[Any] = []

        base_cmd = click.command()(lambda **kwargs: None)
        populate_command(target, base_cmd, config_flag=config_flag, union_tag=kw["union_tag"], argv=argv)

        @click.command()
        def _inner(**kwargs: Any) -> None:
            ctx = click.get_current_context()
            fn = confargclick.from_context if construct else confargclick.merge_context
            result_holder.append(fn(target, ctx, argv=argv, config_flag=config_flag, **kw))

        real_cmd = click.Command(name="cli", callback=_inner.callback, params=base_cmd.params)
        CliRunner().invoke(real_cmd, argv, catch_exceptions=False)
        return result_holder[0]

    def registered_flags(
        self,
        target: type,
        *,
        config_flag: str = _defaults.CONFIG_FLAG,
        config_subkeys: bool = True,
        union_tag: str = _defaults.UNION_TAG,
    ) -> set[str] | None:
        cmd = click.command()(lambda **kwargs: None)
        populate_command(target, cmd, config_flag=config_flag, config_subkeys=config_subkeys, union_tag=union_tag)
        return {opt[2:] for p in cmd.params for opt in p.opts if opt.startswith("--")}


class CycloptsLoader(ConfargLoader):
    """Wraps ``populate_app`` → ``from_app`` / ``merge_app``.

    Cyclopts accepts both space-separated (``--tags a b c``) and repeated
    (``--tags a --tags b``) flags for list fields.
    """

    id = "cyclopts"

    def _run(self, target: type, *, construct: bool, **kw: Any) -> Any:
        argv = list(kw.pop("argv") or [])
        config_flag = kw.pop("config_flag")
        app = cyclopts.App()
        populate_app(target, app, config_flag=config_flag, union_tag=kw["union_tag"], argv=argv)
        fn = confargcyclopts.from_app if construct else confargcyclopts.merge_app
        return fn(target, app, argv=argv, config_flag=config_flag, **kw)

    def registered_flags(
        self,
        target: type,
        *,
        config_flag: str = _defaults.CONFIG_FLAG,
        config_subkeys: bool = True,
        union_tag: str = _defaults.UNION_TAG,
    ) -> set[str] | None:
        app = cyclopts.App()
        populate_app(target, app, config_flag=config_flag, config_subkeys=config_subkeys, union_tag=union_tag)
        meta = _app_meta[id(app)]
        return set(meta["name_map"].values())


# ---------------------------------------------------------------------------
# Loader sets for fixture parametrisation
# ---------------------------------------------------------------------------

ALL_LOADERS: list[ConfargLoader] = [
    VanillaLoader(),
    ArgparseLoader(),
    ClickLoader(),
    CycloptsLoader(),
]

SPACE_SEP_LOADERS: list[ConfargLoader] = [
    VanillaLoader(),
    ArgparseLoader(),
    CycloptsLoader(),
]

REPEATED_FLAG_LOADERS: list[ConfargLoader] = [
    ClickLoader(),
    CycloptsLoader(),
]

# Loaders with a populate_* registration step (registered_flags() returns a set).
POPULATING_LOADERS: list[ConfargLoader] = [
    ArgparseLoader(),
    ClickLoader(),
    CycloptsLoader(),
]
