# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for ``docs-dev/todo/index.py``, the board-table generator."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "docs-dev" / "todo" / "index.py"

SIZING = "**Effort:** S · **Risk:** low · **Impact:** none"


def _load_script() -> ModuleType:
    """Import the generator by path: ``docs-dev`` is not a legal package name."""
    spec = importlib.util.spec_from_file_location("todo_index", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # `@dataclass` looks its defining module up in `sys.modules`, so register before executing.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


todo_index = _load_script()


def _write(path: Path, text: str) -> None:
    """Write UTF-8 with LF endings, which is what the generator itself writes."""
    path.write_text(text, encoding="utf-8", newline="\n")


def _ticket(tid: str, *, sizing: str = SIZING, repro: bool = False, heading: str | None = None) -> str:
    """Return the text of one ticket file, well-formed unless a caller breaks a part of it."""
    first = heading if heading is not None else f"# {tid} — A headline"
    body = f"{first}\n\n**Where:** `src/confarg/_merge.py` · **Filed:** 2026-09-28\n{sizing}\n\nWhat is wrong.\n"
    return f"{body}\n```python\nprint(1)\n```\n" if repro else body


def _readme(table: str) -> str:
    """Return a board README with ``table`` between the markers and prose on both sides."""
    return f"# Board\n\nIntro prose.\n\n{todo_index.START}\n\n{table}\n\n{todo_index.END}\n\nClosing prose.\n"


@pytest.fixture
def boards(tmp_path, monkeypatch):
    """A throwaway four-board tree with empty tables, installed as the generator's root."""
    for board in todo_index.BOARDS:
        folder = tmp_path / board
        folder.mkdir()
        _write(folder / "README.md", _readme("*No open tickets.*"))
    monkeypatch.setattr(todo_index, "TODO", tmp_path)
    return tmp_path


class TestValidationGatesTheRewrite:
    """A board never loses a row for a ticket that is still open (BUG-36)."""

    def test_a_malformed_heading_leaves_the_table_alone(self, boards, capsys):
        """A ticket whose heading stops matching blocks the rewrite instead of losing its row."""
        _write(boards / "refactors" / "REF-1-good.md", _ticket("REF-1"))
        _write(boards / "refactors" / "REF-2-broken.md", _ticket("REF-2", heading="# REF-2 - A headline"))
        readme = boards / "refactors" / "README.md"
        before = readme.read_text(encoding="utf-8")

        assert todo_index.main([]) == 1
        assert readme.read_text(encoding="utf-8") == before, "the table was rewritten without REF-2"
        assert "no table was rewritten" in capsys.readouterr().err

    def test_a_missing_sizing_field_leaves_the_table_alone(self, boards):
        """The softer failure: a ticket ``_parse`` keeps must not land a row with a blank cell."""
        _write(boards / "refactors" / "REF-1-unsized.md", _ticket("REF-1", sizing="**Effort:** S · **Impact:** none"))
        readme = boards / "refactors" / "README.md"
        before = readme.read_text(encoding="utf-8")

        assert todo_index.main([]) == 1
        assert readme.read_text(encoding="utf-8") == before, "a row with an empty Risk cell was written"

    def test_an_error_on_one_board_blocks_every_board(self, boards):
        """The run is atomic: a broken ticket on one board leaves the other boards untouched too."""
        _write(boards / "bugs" / "BUG-1-good.md", _ticket("BUG-1", repro=True))
        _write(boards / "refactors" / "REF-1-broken.md", _ticket("REF-1", heading="# REF-1 - A headline"))
        bugs = boards / "bugs" / "README.md"
        before = bugs.read_text(encoding="utf-8")

        assert todo_index.main([]) == 1
        assert bugs.read_text(encoding="utf-8") == before, "bugs/ was rewritten while refactors/ was invalid"

    def test_a_valid_ticket_that_fails_no_rule_is_not_reported(self, boards, capsys):
        """The gate must not fire on a clean tree: nothing above is a validation error."""
        _write(boards / "bugs" / "BUG-1-good.md", _ticket("BUG-1", repro=True))

        assert todo_index.main([]) == 0
        assert capsys.readouterr().err == ""


class TestRewriting:
    """What the generator writes when every ticket it reads is well-formed."""

    def test_a_clean_tree_is_rewritten_between_the_markers(self, boards):
        """A valid ticket gets its row, and the prose around the markers is left alone."""
        _write(boards / "bugs" / "BUG-1-good.md", _ticket("BUG-1", repro=True))
        readme = boards / "bugs" / "README.md"

        assert todo_index.main([]) == 0
        text = readme.read_text(encoding="utf-8")
        assert "BUG-1-good.md" in text
        assert "*No open tickets.*" not in text
        assert text.startswith("# Board\n\nIntro prose.\n")
        assert text.endswith("Closing prose.\n")

    def test_check_reports_a_stale_table_without_writing(self, boards, capsys):
        """``--check`` is the CI form: it reports staleness and writes nothing."""
        _write(boards / "bugs" / "BUG-1-good.md", _ticket("BUG-1", repro=True))
        readme = boards / "bugs" / "README.md"
        before = readme.read_text(encoding="utf-8")

        assert todo_index.main(["--check"]) == 1
        assert readme.read_text(encoding="utf-8") == before
        assert "TABLE STALE" in capsys.readouterr().out
