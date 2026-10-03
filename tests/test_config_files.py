# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for config file loading: TOML & YAML, nested, multiple files, subpath targeting."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tests._loaders import ConfargLoader

import pytest

import confarg
from confarg.exceptions import ConfargError
from tests.conftest import (
    AppConfig,
    Color,
    DeepNested,
    Flat,
    WithCollections,
    WithDefaults,
    make_target,
)

# ---------------------------------------------------------------------------
# JSON loading
# ---------------------------------------------------------------------------


class TestJsonLoading:
    """JSON config file loading."""

    def test_flat_json(self, loader: ConfargLoader, tmp_json) -> None:
        """Load all flat fields from JSON."""
        path = tmp_json('{"name": "json_name", "count": 42, "rate": 3.14, "verbose": true}')
        result = loader.load(Flat, argv=[], env={}, files=[path])
        assert result.name == "json_name"
        assert result.count == 42
        assert result.rate == pytest.approx(3.14)
        assert result.verbose is True

    def test_nested_json(self, loader: ConfargLoader, tmp_json) -> None:
        """Load nested dataclass fields from JSON."""
        path = tmp_json("""\
            {
              "debug": true,
              "db": {"host": "jhost", "port": 5432, "name": "jdb"},
              "cache": {"enabled": false, "ttl": 120}
            }
        """)
        result = loader.load(AppConfig, argv=[], env={}, files=[path])
        assert result.db.host == "jhost"
        assert result.db.port == 5432
        assert result.cache.enabled is False
        assert result.debug is True

    def test_json_list(self, loader: ConfargLoader, tmp_json) -> None:
        """List field from JSON array."""
        WithList = make_target("items", list[int], default_factory=list)
        path = tmp_json('{"items": [1, 2, 3]}')
        result = loader.load(WithList, argv=[], env={}, files=[path])
        assert result.items == [1, 2, 3]

    def test_json_dict(self, loader: ConfargLoader, tmp_json) -> None:
        """Dict field from JSON object."""
        WithDict = make_target("metadata", dict[str, int], default_factory=dict)
        path = tmp_json('{"metadata": {"a": 1, "b": 2}}')
        result = loader.load(WithDict, argv=[], env={}, files=[path])
        assert result.metadata == {"a": 1, "b": 2}

    def test_json_non_object_raises(self, loader: ConfargLoader, tmp_path) -> None:
        """JSON file whose top-level value is not an object raises an error."""
        p = tmp_path / "bad.json"
        p.write_text("[1, 2, 3]")
        with pytest.raises(confarg.exceptions.InvalidConfigFileError):
            loader.load(Flat, argv=[], env={}, files=[p])


# ---------------------------------------------------------------------------
# TOML loading
# ---------------------------------------------------------------------------


class TestTomlLoading:
    """TOML config file loading."""

    def test_flat_toml(self, loader: ConfargLoader, tmp_toml) -> None:
        """Load all flat fields from TOML."""
        path = tmp_toml("""\
            name = "toml_name"
            count = 42
            rate = 3.14
            verbose = true
        """)
        result = loader.load(Flat, argv=[], env={}, files=[path])
        assert result.name == "toml_name"
        assert result.count == 42
        assert result.rate == pytest.approx(3.14)
        assert result.verbose is True

    def test_nested_toml(self, loader: ConfargLoader, tmp_toml) -> None:
        """Load nested dataclass fields from TOML."""
        path = tmp_toml("""\
            debug = true

            [db]
            host = "dbhost"
            port = 5432
            name = "mydb"

            [cache]
            enabled = false
            ttl = 120
        """)
        result = loader.load(AppConfig, argv=[], env={}, files=[path])
        assert result.db.host == "dbhost"
        assert result.db.port == 5432
        assert result.cache.enabled is False
        assert result.cache.ttl == 120
        assert result.debug is True

    def test_deep_nested_toml(self, loader: ConfargLoader, tmp_toml) -> None:
        """Load three levels of nesting from TOML."""
        path = tmp_toml("""\
            version = "2.0"

            [app]
            debug = true

            [app.db]
            host = "deep"
            port = 1
            name = "d"

            [app.cache]
            enabled = true
            ttl = 10
        """)
        result = loader.load(DeepNested, argv=[], env={}, files=[path])
        assert result.app.db.host == "deep"
        assert result.version == "2.0"

    def test_toml_partial(self, loader: ConfargLoader, tmp_toml) -> None:
        """TOML provides only some fields; defaults fill the rest."""
        path = tmp_toml('name = "partial"\n')
        result = loader.load(WithDefaults, argv=[], env={}, files=[path])
        assert result.name == "partial"
        assert result.count == 0

    def test_toml_list(self, loader: ConfargLoader, tmp_toml) -> None:
        """List field from TOML array."""
        WithList = make_target("items", list[int], default_factory=list)
        path = tmp_toml("items = [1, 2, 3]\n")
        result = loader.load(WithList, argv=[], env={}, files=[path])
        assert result.items == [1, 2, 3]

    def test_toml_dict(self, loader: ConfargLoader, tmp_toml) -> None:
        """Dict field from TOML inline table."""
        WithDict = make_target("metadata", dict[str, int], default_factory=dict)
        path = tmp_toml("""\
            [metadata]
            a = 1
            b = 2
        """)
        result = loader.load(WithDict, argv=[], env={}, files=[path])
        assert result.metadata == {"a": 1, "b": 2}

    def test_toml_enum(self, loader: ConfargLoader, tmp_toml) -> None:
        """Enum field from TOML string value."""
        WithEnum = make_target("color", Color, default=Color.RED)
        path = tmp_toml('color = "green"\n')
        result = loader.load(WithEnum, argv=[], env={}, files=[path])
        assert result.color is Color.GREEN


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------


class TestYamlLoading:
    """YAML config file loading."""

    def test_flat_yaml(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Load all flat fields from YAML."""
        path = tmp_yaml("""\
            name: yaml_name
            count: 99
            rate: 2.718
            verbose: false
        """)
        result = loader.load(Flat, argv=[], env={}, files=[path])
        assert result.name == "yaml_name"
        assert result.count == 99
        assert result.rate == pytest.approx(2.718)
        assert result.verbose is False

    def test_nested_yaml(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Load nested dataclass fields from YAML."""
        path = tmp_yaml("""\
            debug: true
            db:
              host: yhost
              port: 3306
              name: ydb
            cache:
              enabled: true
              ttl: 600
        """)
        result = loader.load(AppConfig, argv=[], env={}, files=[path])
        assert result.db.host == "yhost"
        assert result.cache.ttl == 600

    def test_yaml_list(self, loader: ConfargLoader, tmp_yaml) -> None:
        """List field from YAML sequence."""
        WithList = make_target("items", list[int], default_factory=list)
        path = tmp_yaml("""\
            items:
              - 10
              - 20
              - 30
        """)
        result = loader.load(WithList, argv=[], env={}, files=[path])
        assert result.items == [10, 20, 30]

    def test_yaml_dict(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Dict field from YAML mapping."""
        WithDict = make_target("metadata", dict[str, int], default_factory=dict)
        path = tmp_yaml("""\
            metadata:
              x: 1
              y: 2
        """)
        result = loader.load(WithDict, argv=[], env={}, files=[path])
        assert result.metadata == {"x": 1, "y": 2}


# ---------------------------------------------------------------------------
# Multiple config files
# ---------------------------------------------------------------------------


class TestMultipleFiles:
    """Multiple config files with override semantics."""

    def test_later_file_overrides(self, loader: ConfargLoader, tmp_toml) -> None:
        """Second file overrides values from the first."""
        p1 = tmp_toml("name = 'first'\ncount = 1\nrate = 0.0\nverbose = false\n", "a.toml")
        p2 = tmp_toml("name = 'second'\n", "b.toml")
        result = loader.load(Flat, argv=[], env={}, files=[p1, p2])
        assert result.name == "second"
        assert result.count == 1  # from first file

    def test_three_files_layered(self, loader: ConfargLoader, tmp_toml) -> None:
        """Three files layered: each overrides the previous."""
        p1 = tmp_toml("name = 'a'\ncount = 1\nrate = 0.0\nverbose = false\n", "1.toml")
        p2 = tmp_toml("name = 'b'\ncount = 2\n", "2.toml")
        p3 = tmp_toml("count = 3\n", "3.toml")
        result = loader.load(Flat, argv=[], env={}, files=[p1, p2, p3])
        assert result.name == "b"
        assert result.count == 3

    def test_toml_and_yaml_mixed(self, loader: ConfargLoader, tmp_toml, tmp_yaml) -> None:
        """TOML and YAML files can be mixed."""
        p1 = tmp_toml("name = 'toml'\ncount = 1\nrate = 0.0\nverbose = false\n", "base.toml")
        p2 = tmp_yaml("name: yaml\n", "override.yaml")
        result = loader.load(Flat, argv=[], env={}, files=[p1, p2])
        assert result.name == "yaml"
        assert result.count == 1


# ---------------------------------------------------------------------------
# Subpath targeting
# ---------------------------------------------------------------------------


class TestSubpathTargeting:
    """Config file targeting a sub-path of the schema."""

    def test_subpath_via_cli_config_flag(self, tmp_toml) -> None:
        """--config.db targets the db subtree."""
        path = tmp_toml("""\
            host = "sub"
            port = 1234
            name = "subdb"
        """)
        result = confarg.load(AppConfig, argv=["--config.db", str(path)], env={})
        assert result.db.host == "sub"
        assert result.db.port == 1234


class TestCliMultipleConfigFiles:
    """Multiple config files passed to a single --config flag."""

    def test_two_files_right_overrides_left(self, tmp_toml) -> None:
        """Second path after --config overrides the first."""
        p1 = tmp_toml("name = 'first'\ncount = 1\nrate = 0.0\nverbose = false\n", "a.toml")
        p2 = tmp_toml("name = 'second'\n", "b.toml")
        result = confarg.load(Flat, argv=["--config", str(p1), str(p2)], env={})
        assert result.name == "second"
        assert result.count == 1  # from first file, not overridden

    def test_three_files_layered(self, tmp_toml) -> None:
        """Three paths after --config applied left-to-right."""
        p1 = tmp_toml("name = 'a'\ncount = 1\nrate = 0.0\nverbose = false\n", "1.toml")
        p2 = tmp_toml("name = 'b'\ncount = 2\n", "2.toml")
        p3 = tmp_toml("count = 3\n", "3.toml")
        result = confarg.load(Flat, argv=["--config", str(p1), str(p2), str(p3)], env={})
        assert result.name == "b"
        assert result.count == 3

    def test_subpath_multiple_files(self, tmp_toml) -> None:
        """Multiple paths after --config.db both target the db subtree."""
        p1 = tmp_toml("host = 'h1'\nport = 1111\nname = 'db'\n", "db1.toml")
        p2 = tmp_toml("host = 'h2'\n", "db2.toml")
        result = confarg.load(AppConfig, argv=["--config.db", str(p1), str(p2)], env={})
        assert result.db.host == "h2"  # second file wins
        assert result.db.port == 1111  # only in first file

    def test_cli_files_override_files_param(self, tmp_toml) -> None:
        """--config files (higher priority) override files= param."""
        p_base = tmp_toml("name = 'base'\ncount = 0\nrate = 0.0\nverbose = false\n", "base.toml")
        p_cli1 = tmp_toml("name = 'cli1'\n", "c1.toml")
        p_cli2 = tmp_toml("name = 'cli2'\n", "c2.toml")
        result = confarg.load(
            Flat,
            argv=["--config", str(p_cli1), str(p_cli2)],
            env={},
            files=[p_base],
        )
        assert result.name == "cli2"


# ---------------------------------------------------------------------------
# File format detection
# ---------------------------------------------------------------------------


class TestFileFormat:
    """Config file format is detected from extension."""

    def test_toml_extension(self, loader: ConfargLoader, tmp_path: Path) -> None:
        """File with .toml extension is parsed as TOML."""
        p = tmp_path / "test.toml"
        p.write_text('name = "ext"\ncount = 1\nrate = 0.0\nverbose = false\n')
        result = loader.load(Flat, argv=[], env={}, files=[p])
        assert result.name == "ext"

    def test_yaml_extension(self, loader: ConfargLoader, tmp_path: Path) -> None:
        """File with .yaml extension is parsed as YAML."""
        p = tmp_path / "test.yaml"
        p.write_text("name: yamlext\ncount: 1\nrate: 0.0\nverbose: false\n")
        result = loader.load(Flat, argv=[], env={}, files=[p])
        assert result.name == "yamlext"

    def test_yml_extension(self, loader: ConfargLoader, tmp_path: Path) -> None:
        """File with .yml extension is parsed as YAML."""
        p = tmp_path / "test.yml"
        p.write_text("name: ymlext\ncount: 1\nrate: 0.0\nverbose: false\n")
        result = loader.load(Flat, argv=[], env={}, files=[p])
        assert result.name == "ymlext"

    def test_json_extension(self, loader: ConfargLoader, tmp_path: Path) -> None:
        """File with .json extension is parsed as JSON."""
        p = tmp_path / "test.json"
        p.write_text('{"name": "jsonext", "count": 1, "rate": 0.0, "verbose": false}')
        result = loader.load(Flat, argv=[], env={}, files=[p])
        assert result.name == "jsonext"

    def test_unknown_extension_raises(self, loader: ConfargLoader, tmp_path: Path) -> None:
        """Unknown file extension raises an error."""
        p = tmp_path / "test.ini"
        p.write_text("[section]\nkey=val\n")
        with pytest.raises(confarg.exceptions.InvalidConfigFileError):
            loader.load(Flat, argv=[], env={}, files=[p])


# ---------------------------------------------------------------------------
# Invalid config files
# ---------------------------------------------------------------------------


class TestInvalidConfigFiles:
    """Error handling for invalid config files."""

    def test_nonexistent_file(self, loader: ConfargLoader) -> None:
        """Non-existent file raises an error."""
        with pytest.raises(confarg.exceptions.InvalidConfigFileError):
            loader.load(Flat, argv=[], env={}, files=[Path("/nonexistent.toml")])

    def test_malformed_toml(self, loader: ConfargLoader, tmp_path: Path) -> None:
        """Malformed TOML raises an error."""
        p = tmp_path / "bad.toml"
        p.write_text("this is not valid toml [[[")
        with pytest.raises(confarg.exceptions.InvalidConfigFileError):
            loader.load(Flat, argv=[], env={}, files=[p])

    def test_malformed_yaml(self, loader: ConfargLoader, tmp_path: Path) -> None:
        """Malformed YAML raises an error."""
        p = tmp_path / "bad.yaml"
        p.write_text(":\n  - :\n    - : :\n  [invalid")
        with pytest.raises(confarg.exceptions.InvalidConfigFileError):
            loader.load(Flat, argv=[], env={}, files=[p])

    def test_malformed_json(self, loader: ConfargLoader, tmp_path: Path) -> None:
        """Malformed JSON raises an error."""
        p = tmp_path / "bad.json"
        p.write_text("{name: no quotes}")
        with pytest.raises(confarg.exceptions.InvalidConfigFileError):
            loader.load(Flat, argv=[], env={}, files=[p])

    @pytest.mark.parametrize(
        ("suffix", "content"),
        [
            (".yaml", "- item1\n- item2\n"),
            (".yaml", "just a scalar\n"),
            (".yml", "- item1\n"),
            (".json", "[1, 2]"),
            (".json", '"just a scalar"'),
        ],
    )
    def test_non_dict_root_rejected(
        self,
        loader: ConfargLoader,
        tmp_path: Path,
        suffix: str,
        content: str,
    ) -> None:
        """A root config file whose top-level value is not a mapping is rejected, in every format."""
        p = tmp_path / f"root{suffix}"
        p.write_text(content)
        with pytest.raises(confarg.exceptions.InvalidConfigFileError, match="must be a mapping"):
            loader.load(WithDefaults, argv=[], env={}, files=[p])

    def test_non_dict_root_after_include_rejected(self, loader: ConfargLoader, tmp_path: Path) -> None:
        """A root file resolving to a non-mapping through __include__ is rejected the same way."""
        (tmp_path / "inner.yaml").write_text("- item1\n- item2\n")
        p = tmp_path / "root.yaml"
        p.write_text("__include__: inner.yaml\n")
        with pytest.raises(confarg.exceptions.InvalidConfigFileError, match="must be a mapping"):
            loader.load(WithDefaults, argv=[], env={}, files=[p])

    @pytest.mark.parametrize("content", ["", "null\n"])
    def test_empty_yaml_root_is_not_rejected(
        self,
        loader: ConfargLoader,
        tmp_path: Path,
        content: str,
    ) -> None:
        """An empty YAML document contributes nothing rather than raising."""
        p = tmp_path / "empty.yaml"
        p.write_text(content)
        result = loader.load(WithDefaults, argv=[], env={}, files=[p])
        assert result.name == "default"


# ---------------------------------------------------------------------------
# Config file with collections
# ---------------------------------------------------------------------------


class TestConfigFileCollections:
    """Collections loaded from config files."""

    def test_collections_from_toml(self, loader: ConfargLoader, tmp_toml) -> None:
        """Multiple collection types from TOML."""
        path = tmp_toml("""\
            names = ["a", "b"]
            counts = [1, 2, 3]
            tags = ["t1", "t2"]

            [mapping]
            k = 10
        """)
        result = loader.load(WithCollections, argv=[], env={}, files=[path])
        assert result.names == ["a", "b"]
        assert result.tags == {"t1", "t2"}
        assert result.mapping == {"k": 10}

    def test_collections_from_yaml(self, loader: ConfargLoader, tmp_yaml) -> None:
        """Multiple collection types from YAML."""
        path = tmp_yaml("""\
            names:
              - a
              - b
            counts:
              - 1
              - 2
            tags:
              - t1
            mapping:
              k: 10
        """)
        result = loader.load(WithCollections, argv=[], env={}, files=[path])
        assert result.names == ["a", "b"]
        assert result.tags == {"t1"}
        assert result.mapping == {"k": 10}


# ---------------------------------------------------------------------------
# env_config: config file path via env var
# ---------------------------------------------------------------------------


class TestEnvConfig:
    """Config file path specified via an env var (env_config parameter)."""

    def test_basic(self, tmp_toml) -> None:
        """Env var pointing to a file loads that file."""
        path = tmp_toml('name = "from_env_config"\ncount = 7\nrate = 1.5\nverbose = true')
        result = confarg.load(
            Flat,
            argv=[],
            env={"MYAPP_MY_CONFIG": str(path)},
            env_prefix="MYAPP_",
            env_config="MYAPP_MY_CONFIG",
        )
        assert result.name == "from_env_config"
        assert result.count == 7

    def test_env_var_not_set(self, tmp_toml) -> None:
        """When the named env var is absent, no file is loaded."""
        result = confarg.load(
            Flat,
            argv=["--name", "cli_name", "--count", "1", "--rate", "0.5", "--verbose", "true"],
            env={},
            env_config="MY_CONFIG",
        )
        assert result.name == "cli_name"

    def test_env_config_none_is_default(self, tmp_toml) -> None:
        """env_config=None (default) does nothing even if the dict has a path-like value."""
        path = tmp_toml('name = "should_not_load"\ncount = 99\nrate = 0.1\nverbose = false')
        result = confarg.load(
            Flat,
            argv=["--name", "cli_name", "--count", "1", "--rate", "0.5", "--verbose", "true"],
            env={"MY_CONFIG": str(path)},
        )
        assert result.name == "cli_name"

    def test_priority_over_files(self, tmp_toml) -> None:
        """env_config file overrides values from the static files= list."""
        base = tmp_toml('name = "base"\ncount = 1\nrate = 0.1\nverbose = false', "base.toml")
        override = tmp_toml('name = "env_override"', "override.toml")
        result = confarg.load(
            Flat,
            argv=[],
            env={"MY_CONFIG": str(override)},
            env_config="MY_CONFIG",
            files=[base],
        )
        assert result.name == "env_override"
        assert result.count == 1  # from base, not overridden

    def test_priority_under_env_vars(self, tmp_toml) -> None:
        """Regular env vars override values from the env_config file."""
        path = tmp_toml('name = "from_file"\ncount = 5\nrate = 1.0\nverbose = false')
        result = confarg.load(
            Flat,
            argv=[],
            env={"MYAPP_MY_CONFIG": str(path), "MYAPP_NAME": "from_env"},
            env_prefix="MYAPP_",
            env_config="MYAPP_MY_CONFIG",
        )
        assert result.name == "from_env"
        assert result.count == 5

    def test_priority_under_cli(self, tmp_toml) -> None:
        """CLI args override values from the env_config file."""
        path = tmp_toml('name = "from_file"\ncount = 5\nrate = 1.0\nverbose = false')
        result = confarg.load(
            Flat,
            argv=["--name", "from_cli"],
            env={"MYAPP_MY_CONFIG": str(path)},
            env_prefix="MYAPP_",
            env_config="MYAPP_MY_CONFIG",
        )
        assert result.name == "from_cli"
        assert result.count == 5

    def test_priority_under_cli_config(self, tmp_toml) -> None:
        """CLI --config file overrides the env_config file."""
        env_file = tmp_toml('name = "from_env_config"\ncount = 1\nrate = 0.1\nverbose = false', "env.toml")
        cli_file = tmp_toml('name = "from_cli_config"\ncount = 2\nrate = 0.2\nverbose = true', "cli.toml")
        result = confarg.load(
            Flat,
            argv=["--config", str(cli_file)],
            env={"MYAPP_MY_CONFIG": str(env_file)},
            env_prefix="MYAPP_",
            env_config="MYAPP_MY_CONFIG",
        )
        assert result.name == "from_cli_config"

    def test_bad_path_raises(self) -> None:
        """A non-existent path in the env var raises InvalidConfigFileError."""
        with pytest.raises(confarg.exceptions.InvalidConfigFileError):
            confarg.load(
                Flat,
                argv=[],
                env={"MY_CONFIG": "/nonexistent/path/config.toml"},
                env_config="MY_CONFIG",
            )


# ---------------------------------------------------------------------------
# Env var sub-config files: CONFARG_CONFIG__subpath=file.yaml
# ---------------------------------------------------------------------------


class TestEnvVarSubConfig:
    """Sub-config file loading via CONFARG_CONFIG[__subpath]=file.yaml."""

    def test_subpath(self, tmp_toml) -> None:
        """CONFARG_CONFIG__DB=db.toml loads db section from a file."""
        db_file = tmp_toml("host = 'dbhost'\nport = 5432\nname = 'mydb'\n", "db.toml")
        result = confarg.load(
            AppConfig,
            argv=[],
            env={"CONFARG_CONFIG__DB": str(db_file)},
            env_prefix="CONFARG_",
        )
        assert result.db.host == "dbhost"
        assert result.db.port == 5432

    def test_unknown_subpath_rejected(self, tmp_toml) -> None:
        """CONFARG_CONFIG__DBB is an error naming the variable, not a silent mount (BUG-50)."""
        db_file = tmp_toml("host = 'h'\nport = 1\nname = 'n'\n", "db.toml")
        with pytest.raises(ConfargError, match="names no field") as excinfo:
            confarg.load(
                AppConfig,
                argv=[],
                env={"CONFARG_CONFIG__DBB": str(db_file)},
                env_prefix="CONFARG_",
            )
        assert "CONFARG_CONFIG__DBB" in str(excinfo.value)
        assert "Valid fields" in str(excinfo.value)

    def test_lowercase_subpath_still_mounts(self, tmp_toml) -> None:
        """A case-insensitive match on a real field stays accepted (BUG-50)."""
        db_file = tmp_toml("host = 'h'\nport = 1\nname = 'n'\n", "db.toml")
        result = confarg.load(
            AppConfig,
            argv=[],
            env={"CONFARG_CONFIG__db": str(db_file)},
            env_prefix="CONFARG_",
        )
        assert result.db.host == "h"

    def test_root_load(self, tmp_toml) -> None:
        """CONFARG_CONFIG=file.toml (no subpath) loads the file at root."""
        path = tmp_toml(
            "name = 'from_env_file'\ncount = 7\nrate = 1.5\nverbose = true\n",
            "conf.toml",
        )
        result = confarg.load(
            Flat,
            argv=[],
            env={"CONFARG_CONFIG": str(path)},
            env_prefix="CONFARG_",
        )
        assert result.name == "from_env_file"
        assert result.count == 7

    def test_case_insensitive_flag(self, tmp_toml) -> None:
        """The CONFIG segment is matched case-insensitively."""
        db_file = tmp_toml("host = 'h'\nport = 1\nname = 'n'\n", "db.toml")
        result = confarg.load(
            AppConfig,
            argv=[],
            env={"CONFARG_config__DB": str(db_file)},
            env_prefix="CONFARG_",
        )
        assert result.db.host == "h"

    def test_priority_over_files_param(self, tmp_toml) -> None:
        """Env-var sub-config overrides the same keys from the files= param."""
        base = tmp_toml(
            "[db]\nhost = 'base'\nport = 1\nname = 'base'\n",
            "base.toml",
        )
        db_file = tmp_toml("host = 'env_file'\nport = 5432\nname = 'mydb'\n", "db.toml")
        result = confarg.load(
            AppConfig,
            argv=[],
            env={"CONFARG_CONFIG__DB": str(db_file)},
            env_prefix="CONFARG_",
            files=[base],
        )
        assert result.db.host == "env_file"

    def test_priority_under_inline_env(self, tmp_toml) -> None:
        """Inline env vars override keys from an env-var sub-config file."""
        db_file = tmp_toml("host = 'from_file'\nport = 5432\nname = 'mydb'\n", "db.toml")
        result = confarg.load(
            AppConfig,
            argv=[],
            env={
                "CONFARG_CONFIG__DB": str(db_file),
                "CONFARG_DB__HOST": "from_inline",
            },
            env_prefix="CONFARG_",
        )
        assert result.db.host == "from_inline"
        assert result.db.port == 5432  # still from the file

    def test_priority_under_cli_config(self, tmp_toml) -> None:
        """--config.db (CLI) overrides the env-var sub-config file."""
        env_file = tmp_toml("host = 'from_env_file'\nport = 1\nname = 'e'\n", "env.toml")
        cli_file = tmp_toml("host = 'from_cli_file'\nport = 2\nname = 'c'\n", "cli.toml")
        result = confarg.load(
            AppConfig,
            argv=["--config.db", str(cli_file)],
            env={"CONFARG_CONFIG__DB": str(env_file)},
            env_prefix="CONFARG_",
        )
        assert result.db.host == "from_cli_file"

    def test_priority_under_inline_cli(self, tmp_toml) -> None:
        """Inline CLI args override keys from an env-var sub-config file."""
        db_file = tmp_toml("host = 'from_file'\nport = 5432\nname = 'mydb'\n", "db.toml")
        result = confarg.load(
            AppConfig,
            argv=["--db.host", "from_cli"],
            env={"CONFARG_CONFIG__DB": str(db_file)},
            env_prefix="CONFARG_",
        )
        assert result.db.host == "from_cli"
        assert result.db.port == 5432

    def test_multiple_subpaths(self, tmp_toml) -> None:
        """Multiple env-var sub-config pointers load into separate subtrees."""
        db_file = tmp_toml("host = 'h'\nport = 5432\nname = 'db'\n", "db.toml")
        cache_file = tmp_toml("enabled = false\nttl = 60\n", "cache.toml")
        result = confarg.load(
            AppConfig,
            argv=[],
            env={
                "CONFARG_CONFIG__DB": str(db_file),
                "CONFARG_CONFIG__CACHE": str(cache_file),
            },
            env_prefix="CONFARG_",
        )
        assert result.db.host == "h"
        assert result.cache.enabled is False
        assert result.cache.ttl == 60

    def test_custom_config_flag(self, tmp_toml) -> None:
        """A custom config_flag= is honored in env var matching."""
        db_file = tmp_toml("host = 'h'\nport = 1\nname = 'n'\n", "db.toml")
        result = confarg.load(
            AppConfig,
            argv=[],
            env={"CONFARG_INCLUDE__DB": str(db_file)},
            env_prefix="CONFARG_",
            config_flag="include",
        )
        assert result.db.host == "h"

    def test_bad_path_raises(self) -> None:
        """A non-existent path in a CONFIG env var raises InvalidConfigFileError."""
        with pytest.raises(confarg.exceptions.InvalidConfigFileError):
            confarg.load(
                AppConfig,
                argv=[],
                env={"CONFARG_CONFIG__DB": "/nonexistent/db.toml"},
                env_prefix="CONFARG_",
            )

    def test_env_config_load_order_shallow_before_deep(self, tmp_toml) -> None:
        """Env-var config files are loaded shallower-path-first so deeper paths win.

        Without the sort, dict insertion order would determine the winner.  This
        test constructs the env dict so that the deeper var (CONFIG__DB) is
        inserted first; if no sort were applied the global file (CONFIG) would
        load second and its db.host value would incorrectly win.
        """
        global_file = tmp_toml(
            "[db]\nhost = 'global_host'\nport = 5432\nname = 'db'\n",
            "global.toml",
        )
        db_file = tmp_toml("host = 'db_host'\nport = 5432\nname = 'db'\n", "db.toml")
        # CONFIG__DB inserted first — without sorting it would load first and be
        # overridden by CONFIG (global), giving the wrong winner.
        result = confarg.load(
            AppConfig,
            argv=[],
            env={
                "CONFARG_CONFIG__DB": str(db_file),
                "CONFARG_CONFIG": str(global_file),
            },
            env_prefix="CONFARG_",
        )
        assert result.db.host == "db_host"  # deeper path wins


# ---------------------------------------------------------------------------
# Remote config sources
# ---------------------------------------------------------------------------


class TestRemoteConfigSources:
    """Every format loads over a URL exactly as it does from a path."""

    @pytest.mark.parametrize(
        ("name", "content"),
        [
            ("app.yaml", "name: served\ncount: 7\n"),
            ("app.yml", "name: served\ncount: 7\n"),
            ("app.json", '{"name": "served", "count": 7}'),
            ("app.toml", 'name = "served"\ncount = 7\n'),
        ],
    )
    def test_every_format_loads_over_http(self, tmp_path: Path, tmp_http: str, name: str, content: str) -> None:
        """The format is chosen by the URL's extension, for each supported format."""
        (tmp_path / name).write_text(content, encoding="utf-8")
        cfg = confarg.load(WithDefaults, files=[f"{tmp_http}/{name}"], argv=[])
        assert (cfg.name, cfg.count) == ("served", 7)

    @pytest.mark.parametrize(
        ("name", "content"),
        [
            ("app.yaml", "name: from-file-url\ncount: 2\n"),
            ("app.json", '{"name": "from-file-url", "count": 2}'),
            ("app.toml", 'name = "from-file-url"\ncount = 2\n'),
        ],
    )
    def test_every_format_loads_over_a_file_url(self, tmp_path: Path, name: str, content: str) -> None:
        """A file:// URL reaches the same loaders, with no network involved."""
        p = tmp_path / name
        p.write_text(content, encoding="utf-8")
        cfg = confarg.load(WithDefaults, files=[p.as_uri()], argv=[])
        assert (cfg.name, cfg.count) == ("from-file-url", 2)

    def test_a_url_and_its_path_produce_the_same_merged_dict(self, tmp_path: Path) -> None:
        """file:// is not a second code path."""
        p = tmp_path / "app.yaml"
        p.write_text("name: same\ncount: 1\n", encoding="utf-8")
        assert confarg.merge(WithDefaults, files=[str(p)], argv=[]) == confarg.merge(
            WithDefaults,
            files=[p.as_uri()],
            argv=[],
        )

    def test_a_query_string_does_not_confuse_the_format(self, tmp_path: Path, tmp_http: str) -> None:
        """An extension followed by a query string still dispatches on the extension."""
        (tmp_path / "app.yaml").write_text("name: served\n", encoding="utf-8")
        cfg = confarg.load(WithDefaults, files=[f"{tmp_http}/app.yaml?env=prod"], argv=[])
        assert cfg.name == "served"

    def test_an_extensionless_url_is_refused(self, tmp_http: str) -> None:
        """Nothing sniffs content, so a URL with no extension cannot be loaded."""
        with pytest.raises(confarg.exceptions.InvalidConfigFileError, match="no file extension"):
            confarg.load(WithDefaults, files=[f"{tmp_http}/api/config"], argv=[])

    def test_an_unsupported_extension_is_refused(self, tmp_path: Path, tmp_http: str) -> None:
        """An unsupported extension over HTTP gets the same verdict as on disk."""
        (tmp_path / "app.xyz").write_text("nope", encoding="utf-8")
        with pytest.raises(confarg.exceptions.InvalidConfigFileError, match="Unsupported"):
            confarg.load(WithDefaults, files=[f"{tmp_http}/app.xyz"], argv=[])

    def test_a_malformed_served_document_names_the_url(self, tmp_path: Path, tmp_http: str) -> None:
        """A parse failure reports the location it came from."""
        (tmp_path / "app.json").write_text("{bad json", encoding="utf-8")
        with pytest.raises(confarg.exceptions.InvalidConfigFileError, match=r"Malformed JSON.*app\.json"):
            confarg.load(WithDefaults, files=[f"{tmp_http}/app.json"], argv=[])

    def test_a_non_dict_root_over_http_is_refused(self, tmp_path: Path, tmp_http: str) -> None:
        """The root-is-a-mapping rule applies to a served document too."""
        (tmp_path / "app.yaml").write_text("- one\n- two\n", encoding="utf-8")
        with pytest.raises(confarg.exceptions.InvalidConfigFileError, match="must be a mapping"):
            confarg.load(WithDefaults, files=[f"{tmp_http}/app.yaml"], argv=[])

    def test_an_empty_served_document_contributes_nothing(self, tmp_path: Path, tmp_http: str) -> None:
        """An empty document is the one non-dict root that passes, over HTTP as on disk."""
        (tmp_path / "app.yaml").write_text("", encoding="utf-8")
        cfg = confarg.load(WithDefaults, files=[f"{tmp_http}/app.yaml"], argv=[])
        assert cfg == WithDefaults()

    def test_urls_layer_left_to_right(self, tmp_path: Path, tmp_http: str) -> None:
        """Two URLs in files= are one priority level, later winning."""
        (tmp_path / "base.yaml").write_text("name: base\ncount: 1\n", encoding="utf-8")
        (tmp_path / "over.yaml").write_text("count: 2\n", encoding="utf-8")
        cfg = confarg.load(
            WithDefaults,
            files=[f"{tmp_http}/base.yaml", f"{tmp_http}/over.yaml"],
            argv=[],
        )
        assert (cfg.name, cfg.count) == ("base", 2)

    def test_expressions_in_a_served_document_resolve(self, tmp_path: Path, tmp_http: str) -> None:
        """A served document is a configuration layer like any other, expressions included."""
        (tmp_path / "app.yaml").write_text("name: served\nrate: ${count * 1.5}\ncount: 4\n", encoding="utf-8")
        cfg = confarg.load(WithDefaults, files=[f"{tmp_http}/app.yaml"], argv=[])
        assert cfg.rate == 6.0

    def test_a_served_document_is_mounted_under_a_subpath(self, tmp_path: Path, tmp_http: str) -> None:
        """A URL mounts under --config.<subpath> as a path does."""
        (tmp_path / "db.yaml").write_text("host: h\nport: 1\nname: n\n", encoding="utf-8")
        cfg = confarg.load(AppConfig, argv=["--config.db", f"{tmp_http}/db.yaml"], env={})
        assert (cfg.db.host, cfg.db.port, cfg.db.name) == ("h", 1, "n")
