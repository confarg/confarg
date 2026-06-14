# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Branch-coverage tests for click-integration internals.

Relocated from tests/test_coverage_gaps.py so the test tree mirrors
src/confarg/cli/click/.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import click
from click.testing import CliRunner

from confarg.cli.click import from_context, populate_command
from confarg.cli.click._completion import setup_completion as _click_setup_completion
from tests._cov_helpers import _COV_MOD, _CovDCResult, _CovOuter, _WithCovCallable

if TYPE_CHECKING:
    from pathlib import Path


class TestClickContextGaps:
    """Uncovered branches in click/_context.py."""

    def test_from_context_subpath_config(self, tmp_path: Path) -> None:
        """from_context processes subpath config files."""
        # _CovOuter.inner is a struct field → populate_command registers --config.inner
        cfg = tmp_path / "inner.json"
        cfg.write_text(json.dumps({"value": "from_subpath"}))
        args = [f"--config.inner={cfg}"]

        @click.command()
        def cmd(**_kwargs):
            ctx = click.get_current_context()
            result = from_context(_CovOuter, ctx, env={}, env_prefix=None, argv=args)
            assert result.inner.value == "from_subpath"

        populate_command(_CovOuter, cmd)
        runner = CliRunner()
        r = runner.invoke(cmd, args)
        assert r.exit_code == 0, r.output

    def test_from_context_env_configs(self, tmp_path: Path) -> None:
        """from_context processes env_configs from _parse_env."""
        cfg = tmp_path / "cfg.json"
        cfg.write_text(json.dumps({"result_val": "from_env_file"}))

        @click.command()
        def cmd2(**_kwargs):
            ctx = click.get_current_context()
            result = from_context(
                _CovDCResult,
                ctx,
                env={"CONFARG_CONFIG__": str(cfg)},
                env_prefix="CONFARG_",
            )
            assert isinstance(result, _CovDCResult)

        populate_command(_CovDCResult, cmd2)
        runner = CliRunner()
        r = runner.invoke(cmd2, [])
        assert r.exit_code == 0, r.output

    def test_from_context_env_config_subpath(self, tmp_path: Path) -> None:
        """from_context processes env_configs with non-empty subpath."""
        cfg = tmp_path / "inner.json"
        cfg.write_text(json.dumps({"value": "from_env_subpath"}))

        @click.command()
        def cmd3(**_kwargs):
            ctx = click.get_current_context()
            result = from_context(
                _CovOuter,
                ctx,
                env={"CONFARG_CONFIG__INNER": str(cfg)},
                env_prefix="CONFARG_",
            )
            assert result.inner.value == "from_env_subpath"

        populate_command(_CovOuter, cmd3)
        runner = CliRunner()
        r = runner.invoke(cmd3, [])
        assert r.exit_code == 0, r.output


class TestClickRegisterGaps:
    """Uncovered branches in click/_register.py."""

    def test_populate_command_with_argv(self) -> None:
        """populate_command with argv registers dynamic bind specs."""

        @click.command()
        def cmd(**_kwargs):
            pass

        populate_command(
            _WithCovCallable,
            cmd,
            argv=[f"--fn.fn={_COV_MOD}._cov_call_fn"],
        )
        names = {p.name for p in cmd.params}
        assert "fn.bind.x" in names


class TestClickCompletionGaps:
    """Uncovered branches in click/_completion.py."""

    def test_setup_completion_outer_except(self, monkeypatch) -> None:
        """setup_completion swallows any outer exception."""
        monkeypatch.setenv("_CMD_COMPLETE", "bash_complete")

        # Monkeypatch _partial_argv_from_env to raise
        monkeypatch.setattr(
            "confarg.cli.click._completion._partial_argv_from_env",
            lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        )

        @click.command(name="cmd")
        def cmd(**_kwargs):
            pass

        # Must not raise
        _click_setup_completion(cmd, _CovDCResult)
