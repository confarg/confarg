# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""A configuration nests at most 64 levels, and holds no value that contains itself (BUG-248).

Every check point is tested at the bound, which builds, and one level past it, which is
refused: a document (offset by where it is mounted), a decoded JSON value, a variable's path,
the data handed to ``build()`` / ``from_dict()`` / ``resolve()``, the tree expressions resolve
to, and what ``dump()`` writes. The argv channel, shared by the five front-ends, is tested in
``tests/cli/test_backend_contract.py``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pytest
import tomli_w

import confarg
from confarg._depth import MAX_DEPTH, overflow
from confarg.exceptions import ConfargError, InvalidConfigFileError

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def chain(n: int, leaf: Any = 1, key: str = "a") -> Any:
    """Return *leaf* held *n* levels down a chain of one-key dicts."""
    value = leaf
    for _ in range(n):
        value = {key: value}
    return value


def list_chain(n: int, leaf: Any = 1) -> Any:
    """Return *leaf* held *n* levels down a chain of one-item lists."""
    value = leaf
    for _ in range(n):
        value = [value]
    return value


def called_from(frames: int, fn: Callable[[], Any]) -> Any:
    """Call *fn* with *frames* more frames on the stack."""
    return fn() if frames == 0 else called_from(frames - 1, fn)


@dataclass
class Config:
    """A field below which any depth can be spelled, and a list to append to."""

    d: Any = None
    items: list[Any] = field(default_factory=list)


@dataclass
class Node:
    """A struct that holds itself, the costliest shape to construct per level."""

    child: Node | None = None
    v: int = 0


@dataclass
class Tagged:
    """A variant of a recursive union, which the data names by its tag at every level."""

    child: Tagged | Untagged | None = None
    v: int = 0


@dataclass
class Untagged:
    """The variant no level of the tagged chain names."""

    child: Tagged | Untagged | None = None


@dataclass
class Pair:
    """Two chains, one of which an expression can copy below the other."""

    left: Node = field(default_factory=Node)
    right: Node = field(default_factory=Node)


AT, PAST = MAX_DEPTH - 1, MAX_DEPTH  # chain lengths below `d`: the leaf at 64, then at 65

TOO_DEEP = re.escape(f"deeper than {MAX_DEPTH} levels")

APIS, API_IDS = [confarg.build, confarg.from_dict, confarg.resolve], ["build", "from_dict", "resolve"]


def bound_test_ids(param: int) -> str:
    """Name a chain length by which side of the bound its leaf lands on."""
    return "at-the-bound" if param == AT else "past-the-bound"


def test_the_bound_is_64() -> None:
    """The documented bound (docs-dev/architecture/design-decisions/a-configuration-nests-at-most-64-levels.md)."""
    assert MAX_DEPTH == 64


# ---------------------------------------------------------------------------
# A document, offset by where it lands
# ---------------------------------------------------------------------------


def _write(path: Path, data: Any) -> Path:
    """Write *data* to *path* in the format its suffix names; JSON is YAML, so YAML is written as JSON."""
    text = tomli_w.dumps(data) if path.suffix == ".toml" else json.dumps(data)
    path.write_text(text, encoding="utf-8")
    return path


class TestDocument:
    """A document is counted from where it lands, before anything walks it."""

    @pytest.mark.parametrize("suffix", [".json", ".yaml", ".toml"])
    def test_a_file_at_the_bound_loads(self, tmp_path: Path, suffix: str) -> None:
        """A leaf 64 levels down loads in every format."""
        path = _write(tmp_path / f"c{suffix}", {"d": chain(AT)})
        assert confarg.load(Config, argv=[], env={}, files=[path]).d == chain(AT)

    @pytest.mark.parametrize("suffix", [".json", ".yaml", ".toml"])
    def test_a_file_past_the_bound_is_refused(self, tmp_path: Path, suffix: str) -> None:
        """A leaf 65 levels down is refused naming the file and the depth; it was a raw RecursionError past 245."""
        path = _write(tmp_path / f"c{suffix}", {"d": chain(PAST)})
        with pytest.raises(InvalidConfigFileError, match=TOO_DEEP) as info:
            confarg.load(Config, argv=[], env={}, files=[path])
        assert f"c{suffix}" in str(info.value)
        assert f"({MAX_DEPTH + 1} levels)" in str(info.value)

    def test_merge_refuses_it_too(self, tmp_path: Path) -> None:
        """The document is refused where it is loaded, so ``merge()``, which constructs nothing, refuses it."""
        path = _write(tmp_path / "c.json", {"d": chain(PAST)})
        with pytest.raises(InvalidConfigFileError, match=TOO_DEEP):
            confarg.merge(Config, argv=[], env={}, files=[path])

    @pytest.mark.parametrize(
        ("name", "text"),
        [
            ("c.yaml", "d: " + "[" * 600 + "]" * 600),
            ("c.toml", "d = " + "[" * 600 + "]" * 600),
            ("c.json", '{"d": ' + "[" * 5000 + "]" * 5000 + "}"),
        ],
        ids=["yaml", "toml", "json"],
    )
    def test_a_document_too_deep_for_its_parser_is_refused(self, tmp_path: Path, name: str, text: str) -> None:
        """PyYAML's, tomllib's and json's own walks give up first; their RecursionError is the same refusal."""
        (tmp_path / name).write_text(text, encoding="utf-8")
        with pytest.raises(InvalidConfigFileError, match=TOO_DEEP):
            confarg.load(Config, argv=[], env={}, files=[tmp_path / name])

    def test_a_long_toml_table_header_is_refused(self, tmp_path: Path) -> None:
        """A dotted table header nests without the parser recursing, so the count meets it."""
        (tmp_path / "c.toml").write_text("[d." + ".".join(["a"] * 600) + "]\nb = 1\n", encoding="utf-8")
        with pytest.raises(InvalidConfigFileError, match=TOO_DEEP):
            confarg.load(Config, argv=[], env={}, files=[tmp_path / "c.toml"])

    @pytest.mark.parametrize("n", [32, 33], ids=["at-the-bound", "past-the-bound"])
    def test_a_mounted_fragment_counts_from_the_root(self, tmp_path: Path, n: int) -> None:
        """32 segments of mount path and 32 levels of fragment put the leaf at 64."""
        frag = _write(tmp_path / "frag.json", chain(n))
        argv = ["--config.d" + ".m" * 31, str(frag)]
        if n == 32:
            assert confarg.load(Config, argv=argv, env={}).d == chain(31, chain(32), key="m")
        else:
            with pytest.raises(InvalidConfigFileError, match=TOO_DEEP) as info:
                confarg.load(Config, argv=argv, env={})
            assert "frag.json" in str(info.value)

    @pytest.mark.parametrize("n", [62, 63], ids=["at-the-bound", "past-the-bound"])
    def test_an_appended_fragment_counts_its_index(self, tmp_path: Path, n: int) -> None:
        """`items`, the item's index and 62 levels of fragment put the leaf at 64."""
        frag = _write(tmp_path / "frag.json", chain(n))
        argv = ["--config.items+", str(frag)]
        if n == 62:
            assert confarg.load(Config, argv=argv, env={}).items == [chain(62)]
        else:
            with pytest.raises(InvalidConfigFileError, match=TOO_DEEP):
                confarg.load(Config, argv=argv, env={})

    @pytest.mark.parametrize("n", [31, 32], ids=["at-the-bound", "past-the-bound"])
    def test_an_include_counts_from_where_it_lands(self, tmp_path: Path, n: int) -> None:
        """`d`, 32 levels of the including file and 31 of the included one put the leaf at 64."""
        _write(tmp_path / "frag.json", chain(n))
        main = _write(tmp_path / "main.json", {"d": chain(32, {"__include__": "frag.json"})})
        if n == 31:
            assert confarg.load(Config, argv=[], env={}, files=[main]).d == chain(32, chain(31))
        else:
            with pytest.raises(InvalidConfigFileError, match=TOO_DEEP) as info:
                confarg.load(Config, argv=[], env={}, files=[main])
            assert "frag.json" in str(info.value)

    def test_an_env_mount_counts_from_the_root(self, tmp_path: Path) -> None:
        """A variable's mount point is the fragment's offset, as a flag's is."""
        frag = _write(tmp_path / "frag.json", chain(33))
        env = {"APP_CONFIG__D" + "__M" * 31: str(frag)}
        with pytest.raises(InvalidConfigFileError, match=TOO_DEEP):
            confarg.load(Config, argv=[], env=env, env_prefix="APP_")

    def test_an_op_key_is_no_level(self, tmp_path: Path) -> None:
        """A cast pin's ``__value__`` is the value at the pin's own position."""
        path = _write(tmp_path / "c.json", {"d": chain(AT, {"__cast__": "str", "__value__": "x"})})
        assert confarg.load(Config, argv=[], env={}, files=[path]).d == chain(AT, "x")


# ---------------------------------------------------------------------------
# The environment
# ---------------------------------------------------------------------------


class TestEnvironment:
    """A variable's path, and the position its JSON value lands at, count."""

    @pytest.mark.parametrize("n", [AT, PAST], ids=bound_test_ids)
    def test_a_json_value_counts_from_the_variables_path(self, n: int) -> None:
        """``APP_D__JSON`` lands its value at ``d``, one level down."""
        env = {"APP_D__JSON": json.dumps(chain(n))}
        if n == AT:
            assert confarg.load(Config, argv=[], env=env, env_prefix="APP_").d == chain(AT)
        else:
            with pytest.raises(ConfargError, match=TOO_DEEP) as info:
                confarg.load(Config, argv=[], env=env, env_prefix="APP_")
            assert "APP_D__JSON" in str(info.value)

    @pytest.mark.parametrize("n", [AT, PAST], ids=bound_test_ids)
    def test_a_variables_path_is_counted(self, n: int) -> None:
        """A path of 64 segments writes at 64, one of 65 at 65."""
        env: dict[str, str] = {"APP_D" + "__A" * n: "1"}
        if n == AT:
            assert confarg.load(Config, argv=[], env=env, env_prefix="APP_").d == chain(AT, "1")
        else:
            with pytest.raises(ConfargError, match=TOO_DEEP):
                confarg.load(Config, argv=[], env=env, env_prefix="APP_")

    def test_a_very_long_variable_is_refused_before_it_is_typed(self) -> None:
        """The type walk recurses once per segment, so the path is refused before it; it was a raw RecursionError."""
        env = {"APP_D" + "__A" * 600: "1"}
        with pytest.raises(ConfargError, match=TOO_DEEP):
            confarg.load(Config, argv=[], env=env, env_prefix="APP_")


# ---------------------------------------------------------------------------
# Data a Python caller hands in, and the tree its expressions resolve to
# ---------------------------------------------------------------------------


class TestPythonData:
    """The data a caller hands in is counted, and so is the tree its expressions resolve to."""

    @pytest.mark.parametrize(
        ("api", "action"),
        [(confarg.build, "build"), (confarg.from_dict, "construct"), (confarg.resolve, "resolve")],
        ids=["build", "from_dict", "resolve"],
    )
    def test_data_past_the_bound_is_refused(self, api: Callable[..., Any], action: str) -> None:
        """Each function names what it was doing."""
        with pytest.raises(ConfargError, match=TOO_DEEP) as info:
            api(Config, {"d": chain(PAST)})
        assert f"Cannot {action} Config" in str(info.value)

    @pytest.mark.parametrize("api", APIS, ids=API_IDS)
    def test_data_at_the_bound_is_read(self, api: Callable[..., Any]) -> None:
        """A leaf 64 levels down is read by each."""
        result = api(Config, {"d": chain(AT)})
        assert (result["d"] if isinstance(result, dict) else result.d) == chain(AT)

    def test_a_list_is_a_level(self) -> None:
        """A list holding a list is one level deeper, as a dict holding a dict is."""
        with pytest.raises(ConfargError, match=TOO_DEEP):
            confarg.build(Config, {"d": list_chain(PAST)})
        assert confarg.build(Config, {"d": list_chain(AT)}).d == list_chain(AT)

    def test_an_expression_that_copies_a_value_deeper_is_refused(self) -> None:
        """Both inputs nest 40 levels; `right` holds `left` 40 levels down once resolved."""
        data = {"left": chain(40, {"v": 1}, key="child"), "right": chain(40, "${left}", key="child")}
        for api in (confarg.build, confarg.resolve):
            with pytest.raises(ConfargError, match=TOO_DEEP) as info:
                api(Pair, data)
            assert "right.child" in str(info.value)
            assert "expressions" in str(info.value)

    def test_an_untouched_deep_default_is_not_counted(self) -> None:
        """Construction never walks a default nothing touched, so it is no part of what is counted."""

        class Plain:
            def __init__(self, d: Any = chain(PAST)) -> None:  # noqa: B008  # a default built once, as the test wants
                self.d = d

        assert confarg.build(Plain, {}).d == chain(PAST)


# ---------------------------------------------------------------------------
# A value that holds itself
# ---------------------------------------------------------------------------


class TestCycles:
    """A container met again below itself is refused naming both positions; a shared part is no cycle."""

    @pytest.mark.parametrize(
        ("text", "where", "holder"),
        [("d: &a\n  x: *a\n", "'d.x'", "'d'"), ("d: &a [*a]\n", "'d[0]'", "'d'")],
        ids=["mapping", "sequence"],
    )
    def test_a_yaml_anchor_that_holds_its_alias_is_refused(
        self, tmp_path: Path, text: str, where: str, holder: str
    ) -> None:
        """It recursed until a raw RecursionError."""
        (tmp_path / "c.yaml").write_text(text, encoding="utf-8")
        with pytest.raises(InvalidConfigFileError, match="contains itself") as info:
            confarg.load(Config, argv=[], env={}, files=[tmp_path / "c.yaml"])
        assert f"{where} holds {holder}" in str(info.value)

    def test_a_shared_yaml_alias_is_no_cycle(self, tmp_path: Path) -> None:
        """One anchor aliased at two sibling positions is read at both."""
        (tmp_path / "c.yaml").write_text("d:\n  base: &b {retries: 3}\n  a: *b\n  b: *b\n", encoding="utf-8")
        cfg = confarg.load(Config, argv=[], env={}, files=[tmp_path / "c.yaml"])
        assert cfg.d == {"base": {"retries": 3}, "a": {"retries": 3}, "b": {"retries": 3}}

    @pytest.mark.parametrize("api", APIS, ids=API_IDS)
    def test_a_python_dict_that_holds_itself_is_refused(self, api: Callable[..., Any]) -> None:
        """A caller's dict holding itself is refused as a document's would be."""
        loop: dict[str, Any] = {}
        loop["x"] = loop
        with pytest.raises(ConfargError, match="contains itself") as info:
            api(Config, {"d": loop})
        assert "'d.x' holds 'd'" in str(info.value)

    def test_an_instance_that_holds_itself_is_not_dumped(self) -> None:
        """The serializer tracks the instances it is serializing."""
        node = Node()
        node.child = node
        with pytest.raises(ConfargError, match="contains itself") as info:
            confarg.dump(Pair(left=node))
        assert "'left.child' holds 'left'" in str(info.value)

    def test_a_dict_that_holds_itself_is_not_dumped(self, tmp_path: Path) -> None:
        """A dict ``dump_file()`` writes is counted whole."""
        loop: dict[str, Any] = {}
        loop["x"] = loop
        with pytest.raises(ConfargError, match="contains itself"):
            confarg.dump_file({"d": loop}, tmp_path / "out.json")


# ---------------------------------------------------------------------------
# What dump() writes
# ---------------------------------------------------------------------------


class TestDump:
    """``dump()`` never writes what ``load()`` refuses."""

    def test_an_instance_at_the_bound_is_dumped(self) -> None:
        """A leaf 64 levels down is written."""
        assert confarg.dump(Config(d=chain(AT)))["d"] == chain(AT)

    def test_an_instance_past_the_bound_is_not_dumped(self) -> None:
        """An ``Any`` field's dict 65 levels down is refused naming the dump."""
        with pytest.raises(ConfargError, match=TOO_DEEP) as info:
            confarg.dump(Config(d=chain(PAST)))
        assert "Cannot dump Config" in str(info.value)

    def test_a_typed_chain_past_the_bound_is_not_dumped(self) -> None:
        """A struct chain is counted by the serializer's own descent."""
        node = Node()
        for _ in range(MAX_DEPTH):
            node = Node(child=node)
        with pytest.raises(ConfargError, match=TOO_DEEP):
            confarg.dump(node)

    def test_a_dict_past_the_bound_is_not_written(self, tmp_path: Path) -> None:
        """A dict ``dump_file()`` writes is counted before the file is opened."""
        with pytest.raises(ConfargError, match=TOO_DEEP):
            confarg.dump_file({"d": chain(PAST)}, tmp_path / "out.json")
        assert not (tmp_path / "out.json").exists()


# ---------------------------------------------------------------------------
# The count itself
# ---------------------------------------------------------------------------


class TestCounter:
    """``_depth.overflow``, the one count."""

    @pytest.mark.parametrize("n", [AT, PAST], ids=bound_test_ids)
    def test_a_shared_node_is_not_walked_again(self, n: int) -> None:
        """Each list holds the one below it twice: 2**63 paths, which only a walk of each node once ends."""
        node: Any = 1
        for _ in range(n):
            node = [node, node]
        assert (overflow({"d": node}) is None) == (n == AT)

    def test_it_reports_the_first_position_past_the_bound(self) -> None:
        """The position is a tuple of segments, the holder None for a value that does not hold itself."""
        found = overflow({"d": chain(PAST)})
        assert found is not None
        assert found.path == ("d", *["a"] * MAX_DEPTH)
        assert found.holder is None

    def test_an_offset_counts(self) -> None:
        """A value held 54 levels down may nest 10 more."""
        assert overflow(chain(10), at=("x",) * (MAX_DEPTH - 10)) is None
        assert overflow(chain(11), at=("x",) * (MAX_DEPTH - 10)) is not None


# ---------------------------------------------------------------------------
# Headroom: a tree at the bound builds with 300 frames already on the stack
# ---------------------------------------------------------------------------


HEADROOM = 300


class TestHeadroom:
    """What the walkers cost per level leaves a caller 300 frames at the bound."""

    def test_a_recursive_struct(self) -> None:
        """The costliest shape per level, about 8 frames."""
        data = chain(MAX_DEPTH, {}, key="child")
        assert called_from(HEADROOM, lambda: confarg.build(Node, data)) is not None
        assert called_from(HEADROOM, lambda: confarg.from_dict(Node, data)) is not None

    def test_a_tagged_union(self) -> None:
        """A recursive struct built through a union, each level naming its variant."""
        data: dict[str, Any] = {"class": f"{__name__}.Tagged", "v": 1}
        for _ in range(MAX_DEPTH - 2):
            data = {"class": f"{__name__}.Tagged", "child": data}
        assert called_from(HEADROOM, lambda: confarg.build(Tagged, {"child": data})) is not None

    def test_any_dicts_and_lists(self) -> None:
        """An ``Any`` field's dicts and lists."""
        assert called_from(HEADROOM, lambda: confarg.build(Config, {"d": chain(AT)})).d == chain(AT)
        assert called_from(HEADROOM, lambda: confarg.build(Config, {"d": list_chain(AT)})).d == list_chain(AT)

    def test_a_file(self, tmp_path: Path) -> None:
        """Loading, merging two files and construction."""
        path = _write(tmp_path / "c.yaml", {"d": chain(AT)})
        cfg = called_from(HEADROOM, lambda: confarg.load(Config, argv=[], env={}, files=[path, path]))
        assert cfg.d == chain(AT)

    def test_dump(self) -> None:
        """A struct chain and an ``Any`` field's dicts."""
        node = Node()
        for _ in range(MAX_DEPTH - 1):
            node = Node(child=node)
        assert called_from(HEADROOM, lambda: confarg.dump(node)) is not None
        assert called_from(HEADROOM, lambda: confarg.dump(Config(d=chain(AT)))) is not None
