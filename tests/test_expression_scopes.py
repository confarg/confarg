# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for the anchoring of ``${...}`` references to the file that wrote them.

A configuration file's root lands wherever the file is mounted, so a bare
reference is anchored at that file's root and moves with it, while ``${::path}``
names the configuration root.  That rewriting happens as files are mounted
(``_files._resolve_dict``, ``_pipeline._load_cli_config``), which is the only
point at which the file boundary is still known.

``${.path}`` is a third thing again: relative to the node that wrote it, one
level per dot.  It is resolved at evaluation time rather than at mount time,
because only then does the node have a position — which is what lets a list
element name its own keys without knowing its index.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import pytest

import confarg
from confarg._files import INCLUDE_KEY
from confarg.exceptions import MissingReferenceError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write(tmp_path: Path, name: str, content: str) -> Path:
    """Write content to a named file inside tmp_path and return the path."""
    p = tmp_path / name
    p.write_text(content)
    return p


@dataclass
class Db:
    """Nested block a fragment can describe on its own."""

    host: str = ""
    port: int = 0


@dataclass
class Cfg:
    """Root config mounting a fragment under ``db``."""

    db: Db = field(default_factory=Db)
    name: str = ""


#: A fragment that is self-contained: its only reference is to its own sibling.
FRAGMENT = "host: base-${port}\nport: 5432\n"


# ---------------------------------------------------------------------------
# A fragment reads itself, from every mounting route
# ---------------------------------------------------------------------------


class TestFragmentReadsItself:
    """Bare references follow the file to wherever it is mounted."""

    def test_via_include(self, tmp_path: Path) -> None:
        """__include__ mounts the fragment's root at the including key."""
        write(tmp_path, "db.yaml", FRAGMENT)
        cfg = write(tmp_path, "app.yaml", f"name: myapp\ndb:\n  {INCLUDE_KEY}: ./db.yaml\n")
        assert confarg.load(Cfg, argv=["--config", str(cfg)], env={}).db.host == "base-5432"

    def test_via_config_subpath_flag(self, tmp_path: Path) -> None:
        """--config.db mounts the same fragment the same way."""
        frag = write(tmp_path, "db.yaml", FRAGMENT)
        assert confarg.load(Cfg, argv=["--config.db", str(frag)], env={}).db.host == "base-5432"

    def test_via_env_config_pointer(self, tmp_path: Path) -> None:
        """A CONFIG__<subpath> env pointer is a mount like any other."""
        frag = write(tmp_path, "db.yaml", FRAGMENT)
        result = confarg.load(Cfg, argv=[], env={"MYAPP_CONFIG__DB": str(frag)}, env_prefix="MYAPP_")
        assert result.db.host == "base-5432"

    def test_at_the_root(self, tmp_path: Path) -> None:
        """Loaded directly, the file root is the document root and nothing moves."""
        frag = write(tmp_path, "db.yaml", FRAGMENT)
        assert confarg.load(Db, argv=["--config", str(frag)], env={}).host == "base-5432"

    def test_two_depths_agree(self, tmp_path: Path) -> None:
        """The same fragment mounted at different depths yields the same values."""
        write(tmp_path, "db.yaml", FRAGMENT)
        shallow = write(tmp_path, "shallow.yaml", f"db:\n  {INCLUDE_KEY}: ./db.yaml\n")
        deep = write(tmp_path, "deep.yaml", f"{INCLUDE_KEY}: ./shallow.yaml\n")
        first = confarg.load(Cfg, argv=["--config", str(shallow)], env={})
        second = confarg.load(Cfg, argv=["--config", str(deep)], env={})
        assert first == second == Cfg(db=Db(host="base-5432", port=5432))


# ---------------------------------------------------------------------------
# Reaching out of the file
# ---------------------------------------------------------------------------


class TestDocumentRootReferences:
    """``${::path}`` is the deliberate, marked way to leave your own file."""

    def test_dotted_reference_reaches_the_document_root(self, tmp_path: Path) -> None:
        """A fragment names an outer value explicitly."""
        write(tmp_path, "db.yaml", "host: ${::name}-db\nport: 1\n")
        cfg = write(tmp_path, "app.yaml", f"name: myapp\ndb:\n  {INCLUDE_KEY}: ./db.yaml\n")
        assert confarg.load(Cfg, argv=["--config", str(cfg)], env={}).db.host == "myapp-db"

    def test_bare_reference_cannot_reach_out(self, tmp_path: Path) -> None:
        """Without the marker the same name is looked for inside the fragment."""
        write(tmp_path, "db.yaml", "host: ${name}-db\nport: 1\n")
        cfg = write(tmp_path, "app.yaml", f"name: myapp\ndb:\n  {INCLUDE_KEY}: ./db.yaml\n")
        with pytest.raises(MissingReferenceError, match=r"db\.name"):
            confarg.load(Cfg, argv=["--config", str(cfg)], env={})

    def test_dotted_reference_at_the_root_is_an_ordinary_path(self, tmp_path: Path) -> None:
        """In an unnested file the two anchors coincide."""
        cfg = write(tmp_path, "app.yaml", "name: myapp\ndb:\n  host: ${::name}-db\n  port: 1\n")
        assert confarg.load(Cfg, argv=["--config", str(cfg)], env={}).db.host == "myapp-db"


# ---------------------------------------------------------------------------
# Canonical form and round-tripping
# ---------------------------------------------------------------------------


class TestCanonicalForm:
    """merge() returns references anchored at the merged root, and only there."""

    def test_unnested_file_keeps_its_text(self, tmp_path: Path) -> None:
        """A config loaded at the root is never rewritten, so dump_file is verbatim."""
        cfg = write(tmp_path, "app.yaml", "name: myapp\ndb:\n  host: base-${db.port}\n  port: 5432\n")
        data = confarg.merge(Cfg, argv=["--config", str(cfg)], env={})
        assert data["db"]["host"] == "base-${db.port}"

    def test_mounted_fragment_is_rewritten_to_the_merged_root(self, tmp_path: Path) -> None:
        """A mounted reference is prefixed, so the raw dict resolves on its own."""
        write(tmp_path, "db.yaml", FRAGMENT)
        cfg = write(tmp_path, "app.yaml", f"name: myapp\ndb:\n  {INCLUDE_KEY}: ./db.yaml\n")
        data = confarg.merge(Cfg, argv=["--config", str(cfg)], env={})
        assert data["db"]["host"] == "base-${db.port}"

    def test_document_root_marker_is_canonicalized_away(self, tmp_path: Path) -> None:
        """Once every file is mounted the marker has served its purpose."""
        write(tmp_path, "db.yaml", "host: ${::name}-db\nport: 1\n")
        cfg = write(tmp_path, "app.yaml", f"name: myapp\ndb:\n  {INCLUDE_KEY}: ./db.yaml\n")
        data = confarg.merge(Cfg, argv=["--config", str(cfg)], env={})
        assert data["db"]["host"] == "${name}-db"

    def test_merged_dict_is_itself_includable(self, tmp_path: Path) -> None:
        """The canonical form is still a fragment: mount it again and it re-anchors."""
        write(tmp_path, "db.yaml", FRAGMENT)
        cfg = write(tmp_path, "app.yaml", f"name: myapp\ndb:\n  {INCLUDE_KEY}: ./db.yaml\n")
        data = confarg.merge(Cfg, argv=["--config", str(cfg)], env={})
        confarg.dump_file(data, str(tmp_path / "saved.yaml"))
        outer = write(tmp_path, "outer.yaml", f"inner:\n  {INCLUDE_KEY}: ./saved.yaml\n")

        @dataclass
        class Outer:
            inner: Cfg = field(default_factory=Cfg)

        assert confarg.load(Outer, argv=["--config", str(outer)], env={}).inner.db.host == "base-5432"


# ---------------------------------------------------------------------------
# Marker detection is lexical
# ---------------------------------------------------------------------------


@dataclass
class Inner:
    """Leaf block used to exercise one expression per case."""

    n: int = 2
    flag: bool = True
    out: str = ""


@dataclass
class Root:
    """Root mounting :class:`Inner` under a key, so rewriting actually runs."""

    inner: Inner = field(default_factory=Inner)
    name: str = "top"


class TestAnchorDetection:
    """A marker is one only where it begins an operand.

    These are the cases a lookbehind regex gets wrong, which is why the scan is
    lexical: a dot inside a float or after a string literal belongs to a single
    token, while a dot after a keyword really does start a new operand.
    """

    @pytest.mark.parametrize(
        ("expr", "expected"),
        [
            pytest.param("${'a.b'.upper()}", "A.B", id="after-string-literal"),
            pytest.param("${1.5 + n}", "3.5", id="inside-float"),
            pytest.param("${str(n)[0].upper()}", "2", id="after-closing-bracket"),
            pytest.param("${n if .n else 0}", "2", id="after-keyword-is-a-marker"),
            pytest.param("${n if ::name else 0}", "2", id="root-marker-after-keyword"),
            pytest.param("${max(n, 1)}", "2", id="whitelisted-function"),
        ],
    )
    def test_lexical_cases(self, tmp_path: Path, expr: str, expected: str) -> None:
        """Each case survives being mounted, which is when rewriting happens.

        Written as interpolation so every case yields a string regardless of the
        expression's own result type.
        """
        write(tmp_path, "frag.yaml", f"n: 2\nout: v={expr}\n")
        cfg = write(tmp_path, "app.yaml", f"name: top\ninner:\n  {INCLUDE_KEY}: ./frag.yaml\n")
        assert confarg.load(Root, argv=["--config", str(cfg)], env={}).inner.out == f"v={expected}"

    def test_escaped_expression_is_untouched(self, tmp_path: Path) -> None:
        """A $${...} escape is literal text and must not be prefixed."""
        write(tmp_path, "db.yaml", "host: $${port}\nport: 1\n")
        cfg = write(tmp_path, "app.yaml", f"db:\n  {INCLUDE_KEY}: ./db.yaml\n")
        assert confarg.load(Cfg, argv=["--config", str(cfg)], env={}).db.host == "${port}"


# ---------------------------------------------------------------------------
# Known limit
# ---------------------------------------------------------------------------


@dataclass
class Item:
    """One appended list element."""

    name: str = ""
    label: str = ""


@dataclass
class Holder:
    """Root owning the list an appended fragment lands in."""

    items: list[Item] = field(default_factory=list)
    title: str = "top"


class TestAppendedFragment:
    """``--config.<path>+`` appends at an index only the merge knows.

    Where an appended fragment lands depends on how long the target list already
    is, which is not knowable while the file is being loaded, so its references
    are left anchored at the merged root rather than prefixed by a guess.
    """

    def test_appended_fragment_uses_document_paths(self, tmp_path: Path) -> None:
        """A bare reference in an appended item resolves from the merged root."""
        base = write(tmp_path, "base.yaml", "title: top\nitems: []\n")
        extra = write(tmp_path, "extra.yaml", "name: one\nlabel: ${title}\n")
        result = confarg.load(
            Holder,
            argv=["--config", str(base), "--config.items+", str(extra)],
            env={},
        )
        assert result.items[0].label == "top"


# ---------------------------------------------------------------------------
# Node-relative references
# ---------------------------------------------------------------------------


@dataclass
class Server:
    """One list element, describing itself without ever naming its index."""

    name: str = ""
    host: str = ""
    url: str = ""


@dataclass
class Fleet:
    """Root holding a list of self-describing elements."""

    tier: str = ""
    servers: list[Server] = field(default_factory=list)


#: Two elements whose expressions are identical because neither names its position.
FLEET = (
    "tier: gold\n"
    "servers:\n"
    "  - name: web\n"
    "    host: web.example.com\n"
    "    url: https://${.host}/\n"
    "  - name: api\n"
    "    host: api.example.com\n"
    "    url: https://${.host}/\n"
)


class TestNodeRelativeReferences:
    """``${.x}`` counts upwards from the value being written, one level per dot."""

    def test_single_dot_names_a_sibling(self, tmp_path: Path) -> None:
        """One dot drops the value's own key, leaving the block that holds it."""
        cfg = write(tmp_path, "app.yaml", "db:\n  host: base-${.port}\n  port: 5432\n")
        assert confarg.load(Cfg, argv=["--config", str(cfg)], env={}).db.host == "base-5432"

    def test_two_dots_climb_to_the_enclosing_block(self, tmp_path: Path) -> None:
        """Each further dot drops one more segment of the value's own path."""
        cfg = write(tmp_path, "app.yaml", "name: myapp\ndb:\n  host: ${..name}-db\n  port: 1\n")
        assert confarg.load(Cfg, argv=["--config", str(cfg)], env={}).db.host == "myapp-db"

    def test_list_element_reads_itself_without_an_index(self, tmp_path: Path) -> None:
        """The whole point: two elements share one expression because neither is positional."""
        cfg = write(tmp_path, "fleet.yaml", FLEET)
        fleet = confarg.load(Fleet, argv=["--config", str(cfg)], env={})
        assert [s.url for s in fleet.servers] == ["https://web.example.com/", "https://api.example.com/"]

    def test_a_list_index_is_a_level(self, tmp_path: Path) -> None:
        """Climbing twice from an element lands on the list, which has no such key."""
        cfg = write(tmp_path, "fleet.yaml", "tier: gold\nservers:\n  - name: web\n    url: ${..host}\n")
        with pytest.raises(MissingReferenceError, match=r"servers\.host"):
            confarg.load(Fleet, argv=["--config", str(cfg)], env={})

    def test_cli_expression_is_relative_to_where_it_lands(self, tmp_path: Path) -> None:
        """A flag's value has no writing file, so its dots count from the path it lands on."""
        cfg = write(tmp_path, "app.yaml", "db:\n  host: x\n  port: 5432\n")
        result = confarg.load(Cfg, argv=["--config", str(cfg), "--db.host", "base-${.port}"], env={})
        assert result.db.host == "base-5432"


class TestDotsAreClampedToTheirFile:
    """A fragment may look at itself with dots; reaching outside takes ``::``.

    Without the clamp a fragment's meaning would depend on how deep it happens to
    be mounted, which is exactly what anchoring a bare name to the file avoids.
    """

    def test_a_fragment_reads_itself_at_any_depth(self, tmp_path: Path) -> None:
        """Dots inside the file mean the same however deep the file is mounted."""
        write(tmp_path, "db.yaml", "host: base-${.port}\nport: 5432\n")
        mounted = write(tmp_path, "app.yaml", f"db:\n  {INCLUDE_KEY}: ./db.yaml\n")
        at_root = write(tmp_path, "root.yaml", f"{INCLUDE_KEY}: ./db.yaml\n")
        first = confarg.load(Cfg, argv=["--config", str(mounted)], env={})
        second = confarg.load(Db, argv=["--config", str(at_root)], env={})
        assert first.db == second == Db(host="base-5432", port=5432)

    def test_climbing_out_of_the_file_is_refused(self, tmp_path: Path) -> None:
        """The error names the offending run and points at the root marker."""
        cfg = write(tmp_path, "app.yaml", "db:\n  host: ${...escapes}\n  port: 1\n")
        with pytest.raises(MissingReferenceError, match=r"above the file root"):
            confarg.load(Cfg, argv=["--config", str(cfg)], env={})


class TestRelativeReferencesSurviveSerialization:
    """merge() writes a node-relative reference back out exactly as written.

    Resolving it to an absolute path would pin a list element to the index it
    happens to hold, so a dumped configuration would break on the next edit —
    silently, because nothing about the file would look wrong.
    """

    def test_merge_keeps_the_marker_verbatim(self, tmp_path: Path) -> None:
        """No ``${servers.0.host}`` appears anywhere in the merged dict."""
        cfg = write(tmp_path, "fleet.yaml", FLEET)
        data = confarg.merge(Fleet, argv=["--config", str(cfg)], env={})
        assert [s["url"] for s in data["servers"]] == ["https://${.host}/"] * 2

    def test_reordering_the_list_does_not_break_the_elements(self, tmp_path: Path) -> None:
        """Insert ahead of them and each element still reads its own host."""
        cfg = write(tmp_path, "fleet.yaml", FLEET)
        data = confarg.merge(Fleet, argv=["--config", str(cfg)], env={})
        data["servers"].insert(0, {"name": "new", "host": "new.example.com", "url": "https://${.host}/"})
        built = confarg.build(Fleet, data)
        assert [s.url for s in built.servers] == [
            "https://new.example.com/",
            "https://web.example.com/",
            "https://api.example.com/",
        ]

    def test_dumped_merge_round_trips_through_a_mount(self, tmp_path: Path) -> None:
        """Re-including a dump reparses and unparses every marker, so it must survive."""
        cfg = write(tmp_path, "fleet.yaml", FLEET)
        data = confarg.merge(Fleet, argv=["--config", str(cfg)], env={})
        confarg.dump_file(data, str(tmp_path / "saved.yaml"))
        outer = write(tmp_path, "outer.yaml", f"inner:\n  {INCLUDE_KEY}: ./saved.yaml\n")

        @dataclass
        class Outer:
            inner: Fleet = field(default_factory=Fleet)

        result = confarg.load(Outer, argv=["--config", str(outer)], env={})
        assert [s.url for s in result.inner.servers] == ["https://web.example.com/", "https://api.example.com/"]
