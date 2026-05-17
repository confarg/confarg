# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Loader wrappers that give each CLI integration a confarg.load()-compatible interface.

Each loader provides a ``load()`` method with the same signature as
``confarg.load()`` (minus the vanilla-only parameter ``cli_prefix``),
forwarding arguments unchanged to the underlying integration.

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
from confarg.cli.argparse import from_namespace, make_parser
from confarg.cli.click import populate_command
from confarg.cli.cyclopts import populate_app


class ConfargLoader(ABC):
    """Abstract base for CLI-integration loaders."""

    id: str

    @abstractmethod
    def load(  # noqa: PLR0913 — mirrors confarg.load's keyword-only signature
        self,
        target: type,
        *,
        argv: Sequence[str] | None = None,
        env: Mapping[str, str] | None = None,
        env_prefix: str | None = _defaults.ENV_PREFIX,
        env_separator: str = "__",
        files: Sequence[Path] = (),
        config_flag: str = "",
        env_config: str | None = None,
    ) -> Any:
        """Load *target* using this integration's CLI parser."""

    def __repr__(self) -> str:
        return self.id


class VanillaLoader(ConfargLoader):
    """Delegates directly to ``confarg.load()``."""

    id = "vanilla"

    def load(  # noqa: PLR0913 — mirrors confarg.load's keyword-only signature
        self,
        target: type,
        *,
        argv: Sequence[str] | None = None,
        env: Mapping[str, str] | None = None,
        env_prefix: str | None = _defaults.ENV_PREFIX,
        env_separator: str = "__",
        files: Sequence[Path] = (),
        config_flag: str = "",
        env_config: str | None = None,
    ) -> Any:
        return confarg.load(
            target,
            argv=argv,
            env=env,
            env_prefix=env_prefix,
            env_separator=env_separator,
            files=files,
            config_flag=config_flag,
            env_config=env_config,
        )


class ArgparseLoader(ConfargLoader):
    """Wraps ``make_parser`` → ``parse_args`` → ``from_namespace``."""

    id = "argparse"

    def load(  # noqa: PLR0913 — mirrors confarg.load's keyword-only signature
        self,
        target: type,
        *,
        argv: Sequence[str] | None = None,
        env: Mapping[str, str] | None = None,
        env_prefix: str | None = _defaults.ENV_PREFIX,
        env_separator: str = "__",
        files: Sequence[Path] = (),
        config_flag: str = "",
        env_config: str | None = None,
    ) -> Any:
        argv_ = list(argv) if argv is not None else []
        parser = make_parser(target, config_flag=config_flag, argv=argv_)
        ns = parser.parse_args(argv_)
        return from_namespace(
            target,
            ns,
            config_flag=config_flag,
            env=env,
            env_prefix=env_prefix,
            env_separator=env_separator,
            files=files,
            env_config=env_config,
            argv=argv_,
        )


class ClickLoader(ConfargLoader):
    """Wraps ``populate_command`` → ``CliRunner.invoke`` → ``from_context``.

    Click uses repeated flags for list fields (``--tags a --tags b``).
    Tests that exercise list CLI args must use that convention when parametrised
    with this loader.
    """

    id = "click"

    def load(  # noqa: PLR0913 — mirrors confarg.load's keyword-only signature
        self,
        target: type,
        *,
        argv: Sequence[str] | None = None,
        env: Mapping[str, str] | None = None,
        env_prefix: str | None = _defaults.ENV_PREFIX,
        env_separator: str = "__",
        files: Sequence[Path] = (),
        config_flag: str = "",
        env_config: str | None = None,
    ) -> Any:
        argv_ = list(argv) if argv is not None else []
        result_holder: list[Any] = []

        base_cmd = click.command()(lambda **kwargs: None)
        populate_command(target, base_cmd, config_flag=config_flag, argv=argv_)

        # Capture loader kwargs in the inner closure.
        _env = env
        _env_prefix = env_prefix
        _env_separator = env_separator
        _files = files
        _config_flag = config_flag
        _env_config = env_config

        @click.command()
        def _inner(**kwargs: Any) -> None:
            ctx = click.get_current_context()
            result_holder.append(
                confargclick.from_context(
                    target,
                    ctx,
                    config_flag=_config_flag,
                    env=_env,
                    env_prefix=_env_prefix,
                    env_separator=_env_separator,
                    files=_files,
                    env_config=_env_config,
                    argv=argv_,
                ),
            )

        real_cmd = click.Command(name="cli", callback=_inner.callback, params=base_cmd.params)
        CliRunner().invoke(real_cmd, argv_, catch_exceptions=False)
        return result_holder[0]


class CycloptsLoader(ConfargLoader):
    """Wraps ``populate_app`` → ``from_app``.

    Cyclopts accepts both space-separated (``--tags a b c``) and repeated
    (``--tags a --tags b``) flags for list fields.
    """

    id = "cyclopts"

    def load(  # noqa: PLR0913 — mirrors confarg.load's keyword-only signature
        self,
        target: type,
        *,
        argv: Sequence[str] | None = None,
        env: Mapping[str, str] | None = None,
        env_prefix: str | None = _defaults.ENV_PREFIX,
        env_separator: str = "__",
        files: Sequence[Path] = (),
        config_flag: str = "",
        env_config: str | None = None,
    ) -> Any:
        argv_ = list(argv) if argv is not None else []
        app = cyclopts.App()
        populate_app(target, app, config_flag=config_flag, argv=argv_)
        return confargcyclopts.from_app(
            target,
            app,
            argv=argv_,
            config_flag=config_flag,
            env=env,
            env_prefix=env_prefix,
            env_separator=env_separator,
            files=files,
            env_config=env_config,
        )


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
