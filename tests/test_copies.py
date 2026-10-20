# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""A configuration copies at most 100 000 positions (BUG-259).

A copy is a position an alias, a YAML merge key, a location read again, a reference or a
part a caller's data shares produces beyond its first occurrence; a written position is never
counted. Each route is tested at the bound, which loads, and one position past it, which is
refused, with the bound lowered to 100 so that a test stays fast; and with a bomb a few
hundred bytes long against the real bound, refused in seconds where it took minutes. The
front-ends share the count, which ``tests/cli/test_backend_contract.py`` checks.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest

import confarg
from confarg import _depth
from confarg.exceptions import ConfargError, InvalidConfigFileError, UnsafeExpressionError

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class Config:
    """A field below which any value can be written."""

    d: Any = None


@pytest.fixture
def bound_100(monkeypatch: pytest.MonkeyPatch) -> int:
    """Lower the bound to 100 copied positions, so a test reaches it without building 100 000."""
    monkeypatch.setattr(_depth, "MAX_COPIED", 100)
    return 100


def items(n: int, item: str = "x") -> str:
    """Return a YAML flow sequence of *n* copies of *item*."""
    return "[" + ", ".join([item] * n) + "]"


def load_text(tmp_path: Path, text: str, name: str = "c.yaml", **opts: Any) -> Config:
    """Write *text* to *name* and load it."""
    path = tmp_path / name
    path.write_text(text)
    return confarg.load(Config, argv=[], env={}, files=[path], **opts)


def refused_within(seconds: float, error: type[Exception], match: str, fn: Any) -> None:
    """Assert that *fn* raises *error* matching *match*, in less than *seconds*."""
    start = time.perf_counter()
    with pytest.raises(error, match=match):
        fn()
    assert time.perf_counter() - start < seconds


def test_the_bound_is_100000() -> None:
    """Fixed, not configurable: the measured cost is about 45 microseconds and 130 bytes a position."""
    assert _depth.MAX_COPIED == 100_000


class TestYamlAliases:
    """An alias to a mapping or a sequence copies every position below it."""

    @pytest.mark.usefixtures("bound_100")
    def test_the_bound_loads(self, tmp_path: Path) -> None:
        """Ten aliases of ten items copy 100 positions; aliases of a scalar copy none."""
        text = f"d:\n  l0: &l0 {items(10)}\n  refs: {items(10, '*l0')}\n  s: &s 1\n  t: {items(50, '*s')}\n"
        assert len(load_text(tmp_path, text).d["refs"]) == 10

    @pytest.mark.usefixtures("bound_100")
    def test_one_position_past_the_bound_is_refused(self, tmp_path: Path) -> None:
        """The refusal names the alias that crossed the bound, and the count there."""
        text = f"d:\n  l0: &l0 {items(10)}\n  refs: {items(10, '*l0')}\n  e: &e [x]\n  f: *e\n"
        refusal = r"Cannot read .*c\.yaml: it copies more than 100 positions, at 'd\.f' \(101 copied\)\."
        with pytest.raises(InvalidConfigFileError, match=refusal):
            load_text(tmp_path, text)

    @pytest.mark.usefixtures("bound_100")
    def test_a_nested_alias_copies_what_it_expands_to(self, tmp_path: Path) -> None:
        """``*l1`` holds two ``*l0``: each copy of it copies the 20 positions they expand to, and its 2 own."""
        text = f"d:\n  l0: &l0 {items(10)}\n  l1: &l1 [*l0, *l0]\n  refs: {items(3, '*l1')}\n"
        # Both *l0 in l1 copy 10, l0 being written at d.l0; each *l1 copies 22: 86 in all.
        assert len(load_text(tmp_path, text).d["refs"]) == 3
        with pytest.raises(InvalidConfigFileError, match=r"at 'd\.refs\[3\]' \(108 copied\)"):
            load_text(tmp_path, text.replace(items(3, "*l1"), items(4, "*l1")))

    def test_the_tickets_bomb_is_refused_at_once(self, tmp_path: Path) -> None:
        """BUG-259's reproduction, one level deeper: 10**7 leaves from 410 bytes."""
        lines = ["d:", f"  l0: &l0 {items(10)}"]
        lines += [f"  l{i}: &l{i} {items(10, f'*l{i - 1}')}" for i in range(1, 7)]
        text = "\n".join(lines) + "\n"
        refused_within(
            5, InvalidConfigFileError, r"copies more than 100000 positions", lambda: load_text(tmp_path, text)
        )


class TestYamlMergeKeys:
    """A merge key copies each pair it merges; flattening is linear whatever the anchors."""

    @pytest.mark.usefixtures("bound_100")
    def test_the_bound_loads(self, tmp_path: Path) -> None:
        """Ten mappings merging a ten-key anchor copy 100 positions."""
        keys = ", ".join(f"k{j}: {j}" for j in range(10))
        text = f"d:\n  b: &b {{{keys}}}\n  svc:\n" + "    - {<<: *b}\n" * 10
        assert load_text(tmp_path, text).d["svc"][9] == {f"k{j}": j for j in range(10)}

    @pytest.mark.usefixtures("bound_100")
    def test_one_position_past_the_bound_is_refused(self, tmp_path: Path) -> None:
        """The refusal names the line of the mapping whose merge crossed the bound."""
        keys = ", ".join(f"k{j}: {j}" for j in range(10))
        text = f"d:\n  b: &b {{{keys}}}\n  e: &e {{z: 0}}\n  svc:\n" + "    - {<<: *b}\n" * 10 + "    - {<<: *e}\n"
        refusal = r"it copies more than 100 positions, at line 15 \(101 copied\)\."
        with pytest.raises(InvalidConfigFileError, match=refusal):
            load_text(tmp_path, text)

    def test_a_mappings_own_key_wins_then_the_earlier_merged_one(self, tmp_path: Path) -> None:
        """YAML's merge precedence, which the linear flattening keeps."""
        text = "d:\n  a: &a {x: 1, y: 1}\n  b: &b {x: 2, z: 2}\n  m: {<<: [*a, *b], k: own}\n  o: {<<: *a, x: 3}\n"
        loaded = load_text(tmp_path, text).d
        assert loaded["m"] == {"x": 1, "y": 1, "z": 2, "k": "own"}
        assert loaded["o"] == {"x": 3, "y": 1}

    def test_a_chain_of_merges_flattens_at_once(self, tmp_path: Path) -> None:
        """Each line merging the one before ten times held 10**(n+1) pairs before PyYAML's dict collapsed them."""
        lines = ["d:", "  l0: &l0 {" + ", ".join(f"k{j}: {j}" for j in range(10)) + "}"]
        lines += [f"  l{i}: &l{i} {{<<: {items(10, f'*l{i - 1}')}}}" for i in range(1, 9)]
        start = time.perf_counter()
        loaded = load_text(tmp_path, "\n".join(lines) + "\n").d
        assert time.perf_counter() - start < 5
        assert loaded["l8"] == {f"k{j}": j for j in range(10)}


class TestLocationsReadAgain:
    """The first read of a location is written; every later one in the configuration copies it."""

    @pytest.mark.usefixtures("bound_100")
    def test_the_bound_loads(self, tmp_path: Path) -> None:
        """Eleven includes of a ten-item list: ten reads again copy 100 positions."""
        (tmp_path / "t.json").write_text(json.dumps(["x"] * 10))
        text = "d: " + items(11, "{__include__: t.json}") + "\n"
        assert len(load_text(tmp_path, text, "root.yaml").d) == 11

    @pytest.mark.usefixtures("bound_100")
    def test_one_read_past_the_bound_is_refused(self, tmp_path: Path) -> None:
        """The refusal names the location and where its read crossed the bound."""
        (tmp_path / "t.json").write_text(json.dumps(["x"] * 10))
        text = "d: " + items(12, "{__include__: ./t.json}") + "\n"
        refusal = r"Cannot read .*t\.json again: it copies more than 100 positions, at 'd\.11' \(110 copied\)\."
        with pytest.raises(InvalidConfigFileError, match=refusal):
            load_text(tmp_path, text, "root.yaml")

    @pytest.mark.usefixtures("bound_100")
    @pytest.mark.parametrize("route", ["files", "argv", "env", "mixed"])
    def test_every_route_reads_a_location_once_for_free(self, tmp_path: Path, route: str) -> None:
        """A root file, ``--config.<path>`` and ``CONFIG__<PATH>`` read again copy as an include does."""
        a = tmp_path / "a.json"
        a.write_text(json.dumps({"d": {f"k{j}": j for j in range(60)}}))  # 61 positions: twice is past 100
        a_ = str(a)

        def merge() -> Any:
            if route == "files":
                return confarg.merge(Config, argv=[], env={}, files=[a, a, a])
            if route == "argv":
                return confarg.merge(Config, argv=["--config.d.x", a_, "--config.d.y", a_], env={}, files=[a])
            if route == "env":
                env = {"APP_CONFIG__D__X": a_, "APP_CONFIG__D__Y": a_}
                return confarg.merge(Config, argv=[], env=env, env_prefix="APP_", files=[a])
            env = {"APP_CONFIG__D__Y": a_}
            return confarg.merge(Config, argv=["--config.d.x", a_], env=env, env_prefix="APP_", files=[a])

        with pytest.raises(InvalidConfigFileError, match=r"a\.json again: it copies more than 100 positions"):
            merge()

    def test_an_include_bomb_is_refused_at_once(self, tmp_path: Path) -> None:
        """Ten includes of ten includes, five deep: no alias, 10**6 leaves from six small files."""
        (tmp_path / "f0.json").write_text(json.dumps(["x"] * 10))
        for i in range(1, 6):
            (tmp_path / f"f{i}.json").write_text(json.dumps([{"__include__": f"f{i - 1}.json"}] * 10))
        refusal = r"again: it copies more than 100000 positions"
        refused_within(5, InvalidConfigFileError, refusal, lambda: load_text(tmp_path, "d: {__include__: f5.json}\n"))


def references(n: int, body: str = "d.base") -> list[str]:
    """Return *n* whole-value references to *body*."""
    return ["${" + body + "}"] * n


class TestReferences:
    """A reference charges every position below what it reads, whatever it yields."""

    @pytest.mark.usefixtures("bound_100")
    def test_the_bound_loads(self) -> None:
        """Ten reads of a ten-item list copy 100 positions; a read of a scalar copies none."""
        d = {"base": ["x"] * 10, "refs": references(10), "one": references(50, "d.base[0]")}
        assert len(confarg.build(Config, {"d": d}).d["refs"]) == 10

    @pytest.mark.usefixtures("bound_100")
    def test_one_read_past_the_bound_is_refused(self) -> None:
        """The refusal quotes the expression and says what the configuration had copied already."""
        d = {"base": ["x"] * 10, "refs": references(11)}
        with pytest.raises(
            UnsafeExpressionError,
            match=r"Error in expression '\$\{d\.base\}': Reading 'd\.base' copies 10 positions, over the limit of 100 "
            r"positions one configuration copies \(100 already copied\)",
        ):
            confarg.build(Config, {"d": d})

    @pytest.mark.usefixtures("bound_100")
    def test_a_read_that_yields_a_scalar_is_charged(self) -> None:
        """``len()`` walks what it reads as a copy does."""
        d = {"base": ["x"] * 10, "n": references(11, "len(d.base)")}
        with pytest.raises(UnsafeExpressionError, match=r"Reading 'd\.base' copies 10 positions"):
            confarg.build(Config, {"d": d})

    @pytest.mark.usefixtures("bound_100")
    def test_the_configuration_shares_one_budget(self, tmp_path: Path) -> None:
        """A file's aliases and the expressions over it are one configuration's copies."""
        text = f"d:\n  l0: &l0 {items(10)}\n  refs: {items(9, '*l0')}\n  r: '${{d.l0}}'\n  s: '${{d.l0}}'\n"
        with pytest.raises(UnsafeExpressionError, match=r"\(100 already copied\)"):
            load_text(tmp_path, text)

    @pytest.mark.parametrize("channel", ["argv", "env", "toml"])
    def test_a_reference_bomb_is_refused_at_once(self, tmp_path: Path, channel: str) -> None:
        """Each line references the one before ten times: 10**7 leaves, whichever channel carries them."""
        d: dict[str, Any] = {"l0": ["x"] * 10}
        for i in range(1, 7):
            d[f"l{i}"] = references(10, f"d.l{i - 1}")
        path = tmp_path / "c.toml"
        path.write_text("[d]\n" + "".join(f"{k} = {json.dumps(v)}\n" for k, v in d.items()))

        def load() -> Config:
            if channel == "toml":
                return confarg.load(Config, argv=[], env={}, files=[path])
            if channel == "argv":
                return confarg.load(Config, argv=["--d.json", json.dumps(d)], env={})
            return confarg.load(Config, argv=[], env={"APP_D__JSON": json.dumps(d)}, env_prefix="APP_")

        refused_within(5, UnsafeExpressionError, r"over the limit of 100000 positions", load)


class TestCallerData:
    """A part the data handed to ``build()``, ``from_dict()`` or ``resolve()`` shares is copied where met again."""

    @pytest.mark.usefixtures("bound_100")
    @pytest.mark.parametrize("call", ["build", "from_dict", "resolve"])
    def test_the_bound_loads(self, call: str) -> None:
        """One ten-item list at eleven keys: ten copies of 10 positions."""
        shared = ["x"] * 10
        getattr(confarg, call)(Config, {"d": {f"k{i}": shared for i in range(11)}})

    @pytest.mark.usefixtures("bound_100")
    @pytest.mark.parametrize(
        ("call", "action"), [("build", "build"), ("from_dict", "construct"), ("resolve", "resolve")]
    )
    def test_one_copy_past_the_bound_is_refused(self, call: str, action: str) -> None:
        """The refusal names the key that crossed the bound."""
        shared = ["x"] * 10
        refusal = rf"Cannot {action} Config: it copies more than 100 positions, at 'd\.k11' \(110 copied\)\."
        with pytest.raises(ConfargError, match=refusal):
            getattr(confarg, call)(Config, {"d": {f"k{i}": shared for i in range(12)}})

    @pytest.mark.usefixtures("bound_100")
    def test_dump_counts_nothing(self, tmp_path: Path) -> None:
        """What ``dump()`` writes holds no copy, and its cost is the size of what it writes."""
        shared = ["x"] * 10
        out = tmp_path / "out.yaml"
        confarg.dump_file(Config(d={f"k{i}": shared for i in range(20)}), out)
        assert "&" not in out.read_text()

    @pytest.mark.usefixtures("bound_100")
    def test_merge_returns_no_shared_part(self, tmp_path: Path) -> None:
        """``load()`` counts a file's aliases once: ``merge()`` hands ``build()`` copies, not shared parts."""
        text = f"d:\n  l0: &l0 {items(10)}\n  refs: {items(10, '*l0')}\n"
        (tmp_path / "c.yaml").write_text(text)
        merged = confarg.merge(Config, argv=[], env={}, files=[tmp_path / "c.yaml"])
        assert len(confarg.build(Config, merged).d["refs"]) == 10


class TestOneBudgetPerConfiguration:
    """Every source, channel and resolution of one ``load()`` share one budget; each public call opens its own."""

    @pytest.mark.usefixtures("bound_100")
    def test_two_files_copying_under_the_bound_each_are_refused_together(self, tmp_path: Path) -> None:
        """60 copies in each of two files are 120 in the configuration."""
        for name in ("a.yaml", "b.yaml"):
            (tmp_path / name).write_text(f"d:\n  {name[0]}: &l {items(10)}\n  {name[0]}s: {items(6, '*l')}\n")
        with pytest.raises(InvalidConfigFileError, match=r"b\.yaml: it copies more than 100 positions"):
            confarg.load(Config, argv=[], env={}, files=[tmp_path / "a.yaml", tmp_path / "b.yaml"])

    @pytest.mark.usefixtures("bound_100")
    def test_merge_and_build_called_apart_count_apart(self, tmp_path: Path) -> None:
        """90 alias copies in ``merge()`` and 20 read copies in ``build()`` are two calls, each under the bound."""
        text = f"d:\n  l0: &l0 {items(10)}\n  refs: {items(9, '*l0')}\n  r: '${{d.l0}}'\n  s: '${{d.l0}}'\n"
        (tmp_path / "c.yaml").write_text(text)
        merged = confarg.merge(Config, argv=[], env={}, files=[tmp_path / "c.yaml"])
        assert confarg.build(Config, merged).d["r"] == ["x"] * 10
