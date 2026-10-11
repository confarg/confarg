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
