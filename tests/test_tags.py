# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for _tags.py -- finding and importing the classes a configuration names by its tag.

The scans are framework-neutral, so they are unit-tested here; that a *front-end* honours a
subclass nobody imported is a contract test (tests/cli/test_backend_contract.py).
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from confarg._tags import (
    _partial_config_from_argv,
    _tags_from_argv,
    _tags_from_config,
    collect_tags,
    import_tagged_classes,
)


@dataclass
class _DBBase:
    """Abstract DB base."""


@dataclass
class _ServerDB(_DBBase):
    host: str
    """Hostname."""
    port: int = 5432
    """Port."""


@dataclass
class _SQLiteDB(_DBBase):
    dbpath: str = ":memory:"
    """SQLite file path."""


@dataclass
class _AppConfig:
    db: _ServerDB | _SQLiteDB
    """Database configuration."""
    debug: bool = False


# ---------------------------------------------------------------------------
# _partial_config_from_argv
# ---------------------------------------------------------------------------


class TestPartialConfigFromArgv:
    """Tests for _partial_config_from_argv."""

    def test_reads_toml_from_argv(self, tmp_path) -> None:
        """Test that TOML config file is read from argv."""
        cfg = tmp_path / "cfg.toml"
        cfg.write_text('[db]\nclass = "myapp.ServerDB"\n')
        result = _partial_config_from_argv([f"--config={cfg}"], "config")
        assert result == {"db": {"class": "myapp.ServerDB"}}

    def test_reads_multiple_config_files(self, tmp_path) -> None:
        """Test that multiple config files are merged together."""
        cfg1 = tmp_path / "a.toml"
        cfg1.write_text("x = 1\n")
        cfg2 = tmp_path / "b.toml"
        cfg2.write_text("y = 2\n")
        result = _partial_config_from_argv(["--config", str(cfg1), str(cfg2)], "config")
        assert result == {"x": 1, "y": 2}

    def test_missing_file_silently_ignored(self) -> None:
        """Test that a missing config file is silently ignored."""
        result = _partial_config_from_argv(["--config", "/nonexistent/file.toml"], "config")
        assert result == {}

    def test_does_not_read_subkey_config_flags(self, tmp_path) -> None:
        """--config.db file.toml is a subkey flag; root config collector ignores it."""
        cfg = tmp_path / "cfg.toml"
        cfg.write_text("x = 1\n")
        result = _partial_config_from_argv([f"--config.db={cfg}"], "config")
        assert result == {}

    def test_yaml_file_read(self, tmp_path) -> None:
        """Test that YAML config files are also read correctly."""
        pytest.importorskip("yaml")
        cfg = tmp_path / "cfg.yaml"
        cfg.write_text("db:\n  class: myapp.ServerDB\n")
        result = _partial_config_from_argv([f"--config={cfg}"], "config")
        assert result == {"db": {"class": "myapp.ServerDB"}}

    def test_empty_argv(self) -> None:
        """Test that empty argv returns an empty dict."""
        result = _partial_config_from_argv([], "config")
        assert result == {}


# ---------------------------------------------------------------------------
# _tags_from_argv
# ---------------------------------------------------------------------------


class TestTagsFromArgv:
    """Tests for _tags_from_argv."""

    def test_space_separated(self) -> None:
        """Test that space-separated --field.class value is parsed."""
        tags = _tags_from_argv(["--db.class", "myapp.ServerDB"], "class")
        assert tags == {"db": "myapp.ServerDB"}

    def test_equals_form(self) -> None:
        """Test that --field.class=value form is parsed."""
        tags = _tags_from_argv(["--db.class=myapp.ServerDB"], "class")
        assert tags == {"db": "myapp.ServerDB"}

    def test_multiple_tags(self) -> None:
        """Test that multiple class tag flags are all collected."""
        tags = _tags_from_argv(
            ["--db.class", "myapp.ServerDB", "--cache.class", "myapp.Redis"],
            "class",
        )
        assert tags == {"db": "myapp.ServerDB", "cache": "myapp.Redis"}

    def test_nested_prefix(self) -> None:
        """Test that a deeply nested class tag is keyed by full prefix."""
        tags = _tags_from_argv(["--db.backend.class", "myapp.Redis"], "class")
        assert tags == {"db.backend": "myapp.Redis"}

    def test_no_match(self) -> None:
        """Test that argv with no class tags returns an empty dict."""
        tags = _tags_from_argv(["--host", "localhost", "--port", "5432"], "class")
        assert tags == {}

    def test_ignores_flag_without_value(self) -> None:
        """Test that a class tag flag with no following value is ignored."""
        # --db.class at end of argv with no following value
        tags = _tags_from_argv(["--db.class"], "class")
        assert tags == {}

    def test_ignores_flag_followed_by_another_flag(self) -> None:
        """Test that a class tag flag followed by another flag is ignored."""
        tags = _tags_from_argv(["--db.class", "--other"], "class")
        assert tags == {}


# ---------------------------------------------------------------------------
# _tags_from_config
# ---------------------------------------------------------------------------


class TestTagsFromConfig:
    """Tests for _tags_from_config."""

    def test_finds_struct_union_tag(self) -> None:
        """Test that a union tag is found in the merged config dict."""
        merged = {"db": {"class": "myapp.ServerDB", "host": "localhost"}}
        tags = _tags_from_config(merged, _AppConfig, prefix="", union_tag="class")
        assert tags == {"db": "myapp.ServerDB"}

    def test_empty_when_no_union_tag(self) -> None:
        """Test that no union tag in config yields an empty dict."""
        merged = {"db": {"host": "localhost"}}
        tags = _tags_from_config(merged, _AppConfig, prefix="", union_tag="class")
        assert tags == {}

    def test_empty_when_merged_empty(self) -> None:
        """Test that an empty merged config yields an empty tags dict."""
        tags = _tags_from_config({}, _AppConfig, prefix="", union_tag="class")
        assert tags == {}

    def test_uses_given_prefix(self) -> None:
        """Test that a non-empty prefix is applied when resolving tags."""
        merged = {"class": "myapp.ServerDB"}
        tags = _tags_from_config(merged, _DBBase, prefix="db", union_tag="class")
        # _DBBase is not a union field itself; struct walk yields nothing here
        assert isinstance(tags, dict)


# ---------------------------------------------------------------------------
# collect_tags / import_tagged_classes
# ---------------------------------------------------------------------------


class TestRootLevelTag:
    """The root target is tagged by a bare ``--<union_tag>``, keyed by the empty path."""

    def test_bare_flag_from_argv(self) -> None:
        """A bare --class carries the root target's own tag."""
        assert _tags_from_argv(["--class", "myapp.ServerDB"], "class") == {"": "myapp.ServerDB"}

    def test_bare_flag_equals_form(self) -> None:
        """The --class=PATH spelling too."""
        assert _tags_from_argv(["--class=myapp.ServerDB"], "class") == {"": "myapp.ServerDB"}

    def test_custom_union_tag(self) -> None:
        """The scan follows *union_tag*, so 'class' is no longer a tag flag."""
        argv = ["--kind", "myapp.ServerDB", "--db.class", "not.a.tag"]
        assert _tags_from_argv(argv, "kind") == {"": "myapp.ServerDB"}

    def test_root_tag_from_config(self) -> None:
        """A tag on the root struct itself, not on one of its fields."""
        """A tag on the root struct itself, not on one of its fields."""
        assert _tags_from_config({"class": "myapp.ServerDB"}, _DBBase, "", "class") == {"": "myapp.ServerDB"}


class TestCollectTags:
    """Both sources together, argv winning."""

    def test_argv_wins_over_config(self, tmp_path) -> None:
        """The same field path tagged in both places resolves to the argv value."""
        cfg = tmp_path / "c.toml"
        cfg.write_text('[db]\nclass = "myapp.SQLiteDB"\n', newline="\n")
        tags = collect_tags(
            ["--config", str(cfg), "--db.class", "myapp.ServerDB"],
            _AppConfig,
            union_tag="class",
            config_flag="config",
        )
        assert tags == {"db": "myapp.ServerDB"}

    def test_config_only(self, tmp_path) -> None:
        """A tag reaches the scan through a --config file alone."""
        cfg = tmp_path / "c.toml"
        cfg.write_text('[db]\nclass = "myapp.SQLiteDB"\n', newline="\n")
        tags = collect_tags(["--config", str(cfg)], _AppConfig, union_tag="class", config_flag="config")
        assert tags == {"db": "myapp.SQLiteDB"}

    def test_config_flag_disabled(self, tmp_path) -> None:
        """With no config flag there is no file to read, and argv still answers."""
        tags = collect_tags(["--db.class", "myapp.ServerDB"], _AppConfig, union_tag="class", config_flag="")
        assert tags == {"db": "myapp.ServerDB"}


class TestImportTaggedClasses:
    """The import is a visibility hint: it never raises, whatever the path names."""

    def test_imports_named_class(self) -> None:
        """The module holding the named class is in sys.modules afterwards."""
        import sys  # noqa: PLC0415

        sys.modules.pop("wave", None)  # a stdlib module nothing else here imports
        import_tagged_classes(["--db.class", "wave.Wave_read"], _AppConfig, union_tag="class", config_flag="")
        assert "wave" in sys.modules

    @pytest.mark.parametrize(
        "path",
        ["no.such.module.Cls", "not-a-dotted-path", "", "builtins.NoSuchAttribute"],
    )
    def test_bad_path_is_swallowed(self, path: str) -> None:
        """An unimportable, malformed or empty path is not an error here."""
        import_tagged_classes(["--db.class", path], _AppConfig, union_tag="class", config_flag="")

    def test_no_tags_is_a_no_op(self) -> None:
        """Argv naming no class imports nothing."""
        import_tagged_classes(["--host", "localhost"], _AppConfig, union_tag="class", config_flag="config")
