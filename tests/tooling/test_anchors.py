# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for ``docs-dev/todo/anchors.py``, the sweep of architecture citations."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "docs-dev" / "todo" / "anchors.py"


def _load_script() -> ModuleType:
    """Import the sweep by path: ``docs-dev`` is not a legal package name."""
    spec = importlib.util.spec_from_file_location("todo_anchors", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


anchors = _load_script()


def _write(path: Path, text: str) -> None:
    """Write UTF-8 with LF endings."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


@pytest.fixture
def tree(tmp_path):
    """A throwaway repository with two architecture notes, one of them in a topic folder."""
    architecture = tmp_path / "docs-dev" / "architecture"
    _write(architecture / "invariants.md", "# Invariants\n\n## Cross-channel parity\n")
    _write(architecture / "cli-adapters" / "README.md", "# CLI adapters\n")
    _write(architecture / "cli-adapters" / "list-syntax-divergence.md", "# List syntax divergence\n")
    return tmp_path


def _errors(tree: Path, relative: str, text: str) -> list[str]:
    """Write one Python file under ``tree`` and return what the sweep reports."""
    _write(tree / relative, text)
    errors, _ = anchors._sweep(tree)
    return errors


class TestStaleCitationsAreReported:
    """A citation that cannot be followed is an error wherever the code or the tests hold it (BUG-105)."""

    def test_a_stale_anchor_under_tests_is_reported(self, tree):
        """``tests/`` cites the notes as ``src/`` does, so it is swept as well."""
        errors = _errors(tree, "tests/test_x.py", '"""docs-dev/architecture/invariants.md#gone"""\n')
        assert len(errors) == 1
        assert errors[0].startswith("tests/test_x.py:1:")
        assert "#gone" in errors[0]

    def test_a_short_form_with_an_anchor_is_reported(self, tree):
        """``<name>.md#<anchor>`` outside the repo-root form is a citation the sweep cannot check."""
        errors = _errors(tree, "src/m.py", "# See (09-invariants.md#cross-channel-parity).\n")
        assert len(errors) == 1
        assert "09-invariants.md#cross-channel-parity" in errors[0]

    def test_a_bare_note_name_is_reported_with_its_canonical_spelling(self, tree):
        """A note's own file name, spelled without its path, is a citation too."""
        errors = _errors(tree, "tests/test_x.py", "# keeps the list syntax (list-syntax-divergence.md).\n")
        assert len(errors) == 1
        assert "docs-dev/architecture/cli-adapters/list-syntax-divergence.md#list-syntax-divergence" in errors[0]

    def test_an_anchorless_citation_of_a_missing_note_is_reported(self, tree):
        """A whole-note citation still names a document, and that document has to exist."""
        errors = _errors(tree, "src/m.py", '"""Dev Notes:\n    docs-dev/architecture/locals.md\n"""\n')
        assert len(errors) == 1
        assert "no such document" in errors[0]


class TestValidCitationsAreNotReported:
    """The sweep must stay quiet on a clean tree, or nobody runs it."""

    def test_a_canonical_citation_that_resolves(self, tree):
        """The spelling the convention asks for, naming a heading that exists."""
        assert _errors(tree, "src/m.py", "# docs-dev/architecture/invariants.md#cross-channel-parity\n") == []

    def test_an_anchorless_citation_of_an_existing_note(self, tree):
        """A whole-note citation needs no anchor, only a note."""
        assert _errors(tree, "src/m.py", "# docs-dev/architecture/cli-adapters/README.md\n") == []

    def test_markdown_names_that_are_not_notes(self, tree):
        """Fixture file names and a topic ``README.md`` are not citations of a note."""
        text = '_write(boards / "bugs" / "BUG-1-good.md", "")\n_write(boards / "README.md", "")\n'
        assert _errors(tree, "tests/tooling/test_x.py", text) == []


class TestFencedLinesAreNotHeadings:
    """A ``#`` line inside a fenced block is code, so it generates no anchor (BUG-148)."""

    def test_a_comment_in_a_fence_generates_no_anchor(self, tmp_path):
        """A console block's ``# expected:`` line is output, not a heading."""
        note = tmp_path / "note.md"
        _write(note, "# Note\n\n```console\n# expected: one line\n```\n\n````md\n```\n# Inner\n```\n````\n")
        assert anchors._anchors(note) == ["note"]

    def test_a_fenced_twin_does_not_suffix_the_real_heading(self, tmp_path):
        """GitHub suffixes a repeated heading, and a fenced line is no repeat."""
        note = tmp_path / "note.md"
        _write(note, "~~~python\n# Setup\n~~~\n\n## Setup\n")
        assert anchors._anchors(note) == ["setup"]


def _note_errors(tree: Path, relative: str, text: str) -> list[str]:
    """Write one Markdown file under ``tree`` and return what the sweep of the notes reports."""
    _write(tree / relative, text)
    errors, _ = anchors._sweep_notes(tree)
    return errors


class TestStaleLinksBetweenNotesAreReported:
    """A link between the internal notes that cannot be followed is an error (BUG-148)."""

    def test_a_link_to_a_missing_file(self, tree):
        """A closed ticket's file is gone, and so is every link to it."""
        text = "# REF-1 — x\n\nSame family as [REF-38](REF-38-closed.md).\n"
        errors = _note_errors(tree, "docs-dev/todo/refactors/REF-1-x.md", text)
        assert len(errors) == 1
        assert errors[0].startswith("docs-dev/todo/refactors/REF-1-x.md:3:")
        assert "REF-38-closed.md" in errors[0]

    def test_a_link_to_a_missing_anchor(self, tree):
        """The file resolves, the heading does not."""
        text = "See [parity](../architecture/invariants.md#gone).\n"
        errors = _note_errors(tree, "docs-dev/plans/p.md", text)
        assert len(errors) == 1
        assert "#gone" in errors[0]

    def test_a_link_to_a_missing_anchor_in_the_same_note(self, tree):
        """An anchor-only link names a heading of the note it sits in."""
        errors = _note_errors(tree, "docs-dev/plans/p.md", "# Plan\n\nSee [below](#gone).\n")
        assert len(errors) == 1
        assert "#gone" in errors[0]

    def test_an_anchor_only_a_fenced_line_generates(self, tree):
        """A link to a fenced ``#`` line resolves to nothing on GitHub."""
        text = "# Plan\n\n```console\n# expected: x\n```\n\nSee [it](#expected-x).\n"
        errors = _note_errors(tree, "docs-dev/plans/p.md", text)
        assert len(errors) == 1
        assert "#expected-x" in errors[0]

    def test_a_stale_link_in_the_protocols(self, tree):
        """``docs-agents/`` links into ``docs-dev/`` and goes stale with it (BUG-141)."""
        text = "Read [invariants](../docs-dev/architecture/09-invariants.md).\n"
        errors = _note_errors(tree, "docs-agents/bug-fixing.md", text)
        assert len(errors) == 1
        assert errors[0].startswith("docs-agents/bug-fixing.md:1:")

    def test_a_stale_link_in_agents_md(self, tree):
        """``AGENTS.md`` routes to the protocols, so its links are checked with theirs."""
        errors = _note_errors(tree, "AGENTS.md", "Open [the protocol](docs-agents/gone.md).\n")
        assert len(errors) == 1
        assert "docs-agents/gone.md" in errors[0]

    def test_a_note_cited_by_line_number(self, tree):
        """A line number never survives an edit of the note, so it is never a citation."""
        text = "Env is parsed first (`01-pipeline-and-contracts.md:106`).\n"
        errors = _note_errors(tree, "docs-dev/plans/p.md", text)
        assert len(errors) == 1
        assert "01-pipeline-and-contracts.md:106" in errors[0]

    def test_a_link_from_docs_dev_into_the_protocols(self, tree):
        """The dependency is one-way: ``docs-dev/`` never links to ``docs-agents/``."""
        _write(tree / "docs-agents" / "boards.md", "# Boards\n")
        errors = _note_errors(tree, "docs-dev/todo/README.md", "See [boards](../../docs-agents/boards.md).\n")
        assert len(errors) == 1
        assert "docs-agents" in errors[0]


class TestValidLinksBetweenNotesAreNotReported:
    """The sweep of the notes must stay quiet on a clean tree, or nobody runs it."""

    def test_a_link_with_an_anchor_that_resolves(self, tree):
        """The common shape: a relative path and a heading that exists."""
        text = "See [parity](../architecture/invariants.md#cross-channel-parity).\n"
        assert _note_errors(tree, "docs-dev/plans/p.md", text) == []

    def test_links_to_a_folder_a_heading_here_and_the_web(self, tree):
        """A folder exists without an anchor, and a URL is not this sweep's to follow."""
        text = "# Plan\n\n[a](../architecture/cli-adapters/) [b](#plan) [c](https://example.com/x.md#y)\n"
        assert _note_errors(tree, "docs-dev/plans/p.md", text) == []

    def test_links_in_code_are_not_links(self, tree):
        """A fence or a code span shows Markdown, it does not render it."""
        text = "`[x](gone.md)`\n\n````markdown\n[y](../architecture/gone.md#z)\n````\n"
        assert _note_errors(tree, "docs-dev/todo/README.md", text) == []

    def test_a_python_file_cited_by_line_number(self, tree):
        """Only a note's line numbers are banned: a plan points into code by them."""
        assert _note_errors(tree, "docs-dev/plans/p.md", "Env first (`_pipeline.py:320-334`).\n") == []
