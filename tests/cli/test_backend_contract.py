# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contract tests: every CLI integration must behave exactly like ``confarg.load()``.

All tests here run against the parametrised ``loader`` fixture (vanilla,
argparse, click, cyclopts).  They pin the behaviors that historically diverged
between the vanilla pipeline and the CLI adapters before both were routed
through ``confarg._pipeline._merge_sources``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.conftest import AppConfig, CacheConfig, DbConfig, make_target

if TYPE_CHECKING:
    from tests._loaders import ConfargLoader


class TestPipelineParity:
    """Regression tests for former vanilla-vs-adapter divergences (one per bug)."""

    def test_custom_config_flag_env_pointer(self, loader: ConfargLoader, tmp_yaml) -> None:
        """A custom config_flag is honored for env-specified config files.

        Adapters used to hard-default the env-pointer segment to "config",
        silently ignoring a custom flag name.
        """
        cfg = tmp_yaml("host: envhost\nport: 5432\nname: envdb\n")
        result = loader.load(
            DbConfig,
            argv=[],
            env={"MYAPP_CONF": str(cfg)},
            env_prefix="MYAPP_",
            config_flag="conf",
        )
        assert result == DbConfig(host="envhost", port=5432, name="envdb")

    def test_config_append_syntax(self, loader: ConfargLoader, tmp_yaml) -> None:
        """--config.field+ appends file items to a list instead of replacing it.

        Adapters used to load all CLI config files with plain replace semantics,
        ignoring the trailing ``+``.
        """
        base = tmp_yaml("users:\n  - alice\n  - bob\n", filename="base.yaml")
        extra = tmp_yaml("users:\n  - carol\n", filename="extra.yaml")
        target = make_target("users", list[str])
        result = loader.load(
            target,
            argv=["--config.users+", str(extra)],
            env={},
            env_prefix=None,
            files=[base],
            config_flag="config",
        )
        assert result.users == ["alice", "bob", "carol"]

    def test_env_config_loads_named_file(self, loader: ConfargLoader, tmp_yaml) -> None:
        """env_config names an env var whose value is a config file path.

        Adapters used to not support env_config at all.  The env var itself must
        not be parsed as a field (no unknown-field warning / stray value).
        """
        cfg = tmp_yaml("host: filehost\nport: 1234\nname: filedb\n")
        result = loader.load(
            DbConfig,
            argv=[],
            env={"MYAPP_CONFIG_FILE": str(cfg), "MYAPP_PORT": "9999"},
            env_prefix="MYAPP_",
            env_config="MYAPP_CONFIG_FILE",
        )
        # Inline env var wins over the env_config file; other fields come from the file.
        assert result == DbConfig(host="filehost", port=9999, name="filedb")

    def test_env_config_subpath_ordering(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Env-specified config files load shallow-to-deep, so deeper paths win.

        Adapters used to load env config files in mapping order without sorting.
        """
        base = tmp_yaml(
            """\
            db:
              host: basehost
              port: 1111
              name: basedb
            cache:
              enabled: false
            """,
            filename="base.yaml",
        )
        db = tmp_yaml("host: dbhost\nport: 2222\nname: dbdb\n", filename="db.yaml")
        # Mapping order is deliberately deep-first; the pipeline must sort so the
        # global file loads first and the subpath file overrides it.
        result = loader.load(
            AppConfig,
            argv=[],
            env={"MYAPP_CONFIG__DB": str(db), "MYAPP_CONFIG": str(base)},
            env_prefix="MYAPP_",
            config_flag="config",
        )
        assert result.db == DbConfig(host="dbhost", port=2222, name="dbdb")
        assert result.cache == CacheConfig(enabled=False)

    def test_empty_config_flag_treats_config_as_field(self, loader: ConfargLoader) -> None:
        """config_flag="" disables config handling; a field named "config" stays a field."""
        target = make_target("config", str)
        result = loader.load(
            target,
            argv=[],
            env={"MYAPP_CONFIG": "hello"},
            env_prefix="MYAPP_",
            config_flag="",
        )
        assert result.config == "hello"

    def test_cli_config_interleaved_ordering(self, loader: ConfargLoader, tmp_yaml) -> None:
        """--config.subpath and --config flags load left-to-right, later files win."""
        sub = tmp_yaml("host: subhost\nport: 1111\nname: subdb\n", filename="sub.yaml")
        full = tmp_yaml(
            """\
            db:
              host: fullhost
              port: 2222
              name: fulldb
            cache:
              enabled: true
            """,
            filename="full.yaml",
        )
        result = loader.load(
            AppConfig,
            argv=["--config.db", str(sub), "--config", str(full)],
            env={},
            env_prefix=None,
            config_flag="config",
        )
        # full.yaml comes later on the CLI, so it wins over the earlier subpath file.
        assert result.db == DbConfig(host="fullhost", port=2222, name="fulldb")
