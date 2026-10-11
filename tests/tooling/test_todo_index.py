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

SIZING = "effort: S\nrisk: low\nimpact: none\n"
WHERE = "where:\n  - src/confarg/_merge.py::_merge\n"


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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _ticket(tid: str, *, sizing: str = SIZING, where: str = WHERE, repro: bool = False, heading: str = "") -> str:
    """Return the text of one ticket file, well-formed unless a caller breaks a part of it.

    ``sizing`` is the front matter below ``where``; a test adding a key appends it there.
    """
    first = heading or f"# {tid} — A headline"
    body = f"---\nfiled: 2026-09-28\n{where}{sizing}---\n{first}\n\nWhat is wrong.\n"
    return f"{body}\n```python\nprint(1)\n```\n" if repro else body


def _readme(table: str) -> str:
    """Return a board README with ``table`` between the markers and prose on both sides."""
    return f"# Board\n\nIntro prose.\n\n{todo_index.START}\n\n{table}\n\n{todo_index.END}\n\nClosing prose.\n"


@pytest.fixture
def boards(tmp_path, monkeypatch):
    """A throwaway four-board tree with empty tables, and a source file for ``where`` to name."""
    todo = tmp_path / "docs-dev" / "todo"
    for board in todo_index.BOARDS:
        _write(todo / board / "README.md", _readme("*No open tickets.*"))
    _write(tmp_path / "src" / "confarg" / "_merge.py", "def _merge():\n    pass\n")
    monkeypatch.setattr(todo_index, "TODO", todo)
    monkeypatch.setattr(todo_index, "ROOT", tmp_path)
    return todo


def _errors(boards: Path, capsys: pytest.CaptureFixture[str], filename: str, text: str) -> str:
    """File one refactor ticket, run the generator, and return what it reported."""
    _write(boards / "refactors" / filename, text)
    assert todo_index.main([]) == 1
    return capsys.readouterr().err


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
        _write(boards / "refactors" / "REF-1-unsized.md", _ticket("REF-1", sizing="effort: S\nimpact: none\n"))
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


class TestFrontMatter:
    """What the front matter must hold, and what it must not."""

    def test_a_ticket_without_front_matter_is_refused(self, boards, capsys):
        """The fields live in the front matter only; a preamble in the body is not read."""
        err = _errors(boards, capsys, "REF-1-a.md", "# REF-1 — A headline\n\n**Effort:** S\n")
        assert "must open with front matter" in err

    def test_front_matter_that_is_not_yaml_is_refused(self, boards, capsys):
        """A parse error is reported against the ticket, not raised."""
        err = _errors(boards, capsys, "REF-1-a.md", _ticket("REF-1", sizing=SIZING + "where: [unclosed\n"))
        assert "not valid YAML" in err

    def test_an_unknown_key_is_refused(self, boards, capsys):
        """A misspelled key would otherwise be dropped silently, taking its value with it."""
        err = _errors(boards, capsys, "REF-1-a.md", _ticket("REF-1", sizing=SIZING + "priority: high\n"))
        assert "unknown front matter key 'priority'" in err

    def test_an_effort_off_the_scale_is_refused(self, boards, capsys):
        """Effort is an enum like risk and impact, not free text."""
        err = _errors(boards, capsys, "REF-1-a.md", _ticket("REF-1", sizing="effort: XXL\nrisk: low\nimpact: none\n"))
        assert "effort is 'XXL'" in err

    def test_a_filed_that_is_not_a_date_is_refused(self, boards, capsys):
        """``filed`` must parse as a YAML date, so the board can sort and age by it."""
        text = _ticket("REF-1").replace("filed: 2026-09-28", "filed: last tuesday")
        err = _errors(boards, capsys, "REF-1-a.md", text)
        assert "filed must be a date" in err

    def test_a_question_carries_no_sizing(self, boards, capsys):
        """``questions/`` is exempt from sizing, and that includes ``needs_design``."""
        _write(boards / "questions" / "Q-1-a.md", _ticket("Q-1", sizing="needs_design: true\n"))
        assert todo_index.main([]) == 1
        assert "must not carry needs_design" in capsys.readouterr().err

    def test_a_flag_must_be_a_boolean(self, boards, capsys):
        """``inferred: yes-ish`` is a string, which would read as true and mean nothing."""
        err = _errors(boards, capsys, "REF-1-a.md", _ticket("REF-1", sizing=SIZING + "inferred: maybe\n"))
        assert "inferred must be true or false" in err


class TestWhere:
    """A ``where`` entry names a path, and optionally a symbol, that still exist."""

    def test_a_moved_file_is_reported(self, boards, capsys):
        """The point of a structured ``where``: a rename that orphans a ticket is caught."""
        err = _errors(boards, capsys, "REF-1-a.md", _ticket("REF-1", where="where:\n  - src/confarg/_gone.py\n"))
        assert "'src/confarg/_gone.py' names a path that does not exist" in err

    def test_a_renamed_symbol_is_reported(self, boards, capsys):
        """The symbol after ``::`` must still appear in the file it is filed against."""
        gone = "where:\n  - src/confarg/_merge.py::_gone\n"
        err = _errors(boards, capsys, "REF-1-a.md", _ticket("REF-1", where=gone))
        assert "names a symbol src/confarg/_merge.py no longer holds" in err

    def test_a_glob_must_match_a_file(self, boards, capsys):
        """A glob entry is checked by matching, not by existence."""
        _write(boards / "refactors" / "REF-1-a.md", _ticket("REF-1", where="where:\n  - src/*/_merge.py\n"))
        _write(boards / "refactors" / "REF-2-a.md", _ticket("REF-2", where="where:\n  - src/*/_gone.py\n"))
        assert todo_index.main([]) == 1
        err = capsys.readouterr().err
        assert "REF-1" not in err
        assert "'src/*/_gone.py' matches no file" in err

    def test_an_unversioned_agent_file_is_not_checked(self, boards):
        """``AGENTS.md`` and ``docs-agents/`` are ignored by version control, so may be absent."""
        _write(boards / "questions" / "Q-1-a.md", _ticket("Q-1", sizing="", where="where:\n  - AGENTS.md\n"))
        assert todo_index.main([]) == 0

    def test_where_may_be_empty_for_code_that_does_not_exist_yet(self, boards):
        """A feature adding a new module has nothing to point at; a YAML comment says so."""
        _write(boards / "features" / "FEAT-1-a.md", _ticket("FEAT-1", where="where: []  # a new module\n"))
        assert todo_index.main([]) == 0


class TestBlockedBy:
    """A ``blocked_by`` entry names another ticket that is still open."""

    def test_an_open_blocker_on_another_board_is_accepted(self, boards):
        """Blockers cross boards: a feature can wait on a bug."""
        _write(boards / "bugs" / "BUG-1-a.md", _ticket("BUG-1", repro=True))
        _write(boards / "features" / "FEAT-1-a.md", _ticket("FEAT-1", sizing=SIZING + "blocked_by: [BUG-1]\n"))
        assert todo_index.main([]) == 0

    def test_a_closed_blocker_is_reported(self, boards, capsys):
        """Closing the blocker deletes its file, which is the moment the dependent is unblocked."""
        err = _errors(boards, capsys, "REF-1-a.md", _ticket("REF-1", sizing=SIZING + "blocked_by: [FEAT-9]\n"))
        assert "blocked by FEAT-9, which is no longer open" in err


class TestQuery:
    """``--where PATH`` lists the open tickets that touch a path."""

    @pytest.fixture
    def filed(self, boards):
        """Three tickets: one on a file, one on its directory, one on a glob over its siblings."""
        _write(boards / "refactors" / "REF-1-a.md", _ticket("REF-1"))
        _write(boards / "refactors" / "REF-2-a.md", _ticket("REF-2", where="where:\n  - src/confarg/\n"))
        _write(boards / "refactors" / "REF-3-a.md", _ticket("REF-3", where="where:\n  - src/*/_merge.py\n"))
        return boards

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            pytest.param("src/confarg/_merge.py", {"REF-1", "REF-2", "REF-3"}, id="file"),
            pytest.param(".\\src\\confarg\\_merge.py", {"REF-1", "REF-2", "REF-3"}, id="windows-spelling"),
            pytest.param("src/confarg/", {"REF-1", "REF-2"}, id="directory"),
            pytest.param("src/confarg/_other.py", {"REF-2"}, id="sibling"),
            pytest.param("tests/", set(), id="elsewhere"),
        ],
    )
    def test_query(self, filed, capsys, query, expected):
        """A ticket matches on its file, a directory above it, a file below it, or its glob."""
        assert todo_index.main(["--where", query]) == 0
        out = capsys.readouterr().out
        assert {tid for tid in ("REF-1", "REF-2", "REF-3") if f"  {tid} — " in out} == expected

    def test_a_stale_ticket_does_not_hide_the_answer(self, filed, capsys):
        """The query answers anyway, and reports the stale entry as a warning."""
        _write(filed / "refactors" / "REF-4-a.md", _ticket("REF-4", where="where:\n  - src/confarg/_gone.py\n"))
        assert todo_index.main(["--where", "src/confarg/_merge.py"]) == 0
        captured = capsys.readouterr()
        assert "REF-1 — " in captured.out
        assert "warning:" in captured.err


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
