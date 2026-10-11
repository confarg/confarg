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

SIZING = "effort: S\nrisk: low\nimpact: none\nseverity: minor\n"
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
        err = _errors(boards, capsys, "REF-1-a.md", _ticket("REF-1", sizing=SIZING.replace("effort: S", "effort: XXL")))
        assert "effort is 'XXL'" in err

    def test_a_sized_ticket_must_carry_a_severity(self, boards, capsys):
        """Severity is required beside effort, risk and impact: the work order reads it."""
        err = _errors(boards, capsys, "REF-1-a.md", _ticket("REF-1", sizing="effort: S\nrisk: low\nimpact: none\n"))
        assert "missing severity" in err

    def test_a_severity_off_the_scale_is_refused(self, boards, capsys):
        """``high`` is a risk rung, not a severity one."""
        err = _errors(boards, capsys, "REF-1-a.md", _ticket("REF-1", sizing=SIZING.replace("minor", "high")))
        assert "severity is 'high'" in err

    def test_a_question_carries_no_severity(self, boards, capsys):
        """A question only ever inherits a severity from the tickets it blocks."""
        _write(boards / "questions" / "Q-1-a.md", _ticket("Q-1", sizing="severity: major\n"))
        assert todo_index.main([]) == 1
        assert "must not carry severity" in capsys.readouterr().err

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

    def test_a_cycle_is_reported(self, boards, capsys):
        """Two tickets blocking each other can never start, and leave no order to inherit along."""
        _write(boards / "refactors" / "REF-1-a.md", _ticket("REF-1", sizing=SIZING + "blocked_by: [REF-2]\n"))
        err = _errors(boards, capsys, "REF-2-a.md", _ticket("REF-2", sizing=SIZING + "blocked_by: [REF-1]\n"))
        assert "blocked_by forms a cycle" in err


def _bug(tid: str, origin: str = "", filed: str = "2026-09-28") -> str:
    """Return a bug ticket filed on ``filed``, its front matter ending in ``origin`` if given."""
    return _ticket(tid, sizing=SIZING + origin, repro=True).replace("filed: 2026-09-28", f"filed: {filed}")


class TestIntroducedBy:
    """A bug ticket names the revision that introduced the bug, by its ticket or its PR."""

    def test_a_bug_filed_since_the_rule_must_name_its_origin(self, boards, capsys):
        """From the day the rule took effect, a bug is not filed until its history has been read."""
        _write(boards / "bugs" / "BUG-1-a.md", _bug("BUG-1", filed=todo_index.ORIGIN_SINCE.isoformat()))
        assert todo_index.main([]) == 1
        assert "missing introduced_by" in capsys.readouterr().err

    def test_a_bug_filed_before_the_rule_may_wait_for_a_sweep(self, boards):
        """Older tickets gain an origin when a sweep reaches them, not all at once."""
        _write(boards / "bugs" / "BUG-1-a.md", _bug("BUG-1"))
        assert todo_index.main([]) == 0

    @pytest.mark.parametrize("origin", ["[BUG-97]", "[PR-268]", "[REF-72, BUG-97]", "unknown  # searched"])
    def test_ticket_ids_pr_numbers_and_unknown_are_accepted(self, boards, origin):
        """A closed ticket is a valid origin: the revision that introduced the bug usually closed one."""
        _write(boards / "bugs" / "BUG-1-a.md", _bug("BUG-1", f"introduced_by: {origin}\n", filed="2026-10-07"))
        assert todo_index.main([]) == 0

    @pytest.mark.parametrize("origin", ["[d76854c6e]", "['#268']", "[]", "BUG-97", "maybe"])
    def test_anything_else_is_refused(self, boards, capsys, origin):
        """A commit ID is rewritten by a rebase or a squash merge, so it is no stable origin."""
        _write(boards / "bugs" / "BUG-1-a.md", _bug("BUG-1", f"introduced_by: {origin}\n"))
        assert todo_index.main([]) == 1
        assert "introduced_by must be" in capsys.readouterr().err

    def test_only_a_bug_carries_an_origin(self, boards, capsys):
        """A missing feature or an untidy module was never introduced by a revision that broke it."""
        err = _errors(boards, capsys, "REF-1-a.md", _ticket("REF-1", sizing=SIZING + "introduced_by: [BUG-1]\n"))
        assert "must not carry introduced_by" in err

    def test_the_bugs_table_shows_the_origin(self, boards):
        """Two open bugs from one revision sit side by side in one column, where a reader sees them."""
        _write(boards / "bugs" / "BUG-1-a.md", _bug("BUG-1", "introduced_by: [PR-268]\n"))
        _write(boards / "bugs" / "BUG-2-a.md", _bug("BUG-2"))
        assert todo_index.main([]) == 0
        lines = (boards / "bugs" / "README.md").read_text(encoding="utf-8").splitlines()
        assert lines[lines.index(todo_index.START) + 2].endswith("| Introduced by |")
        assert [line.rsplit("|", 2)[1] for line in lines if line.startswith("| [")] == [" PR-268 ", "  "]


def _rows(readme: Path) -> list[str]:
    """Return the ticket IDs of a board table, in the order its rows are written."""
    text = readme.read_text(encoding="utf-8")
    return [line.split(" — ")[0].removeprefix("| [") for line in text.splitlines() if line.startswith("| [")]


def _sized(severity: str, effort: str = "S", blocked_by: str = "") -> str:
    """Return front matter sized at ``severity`` and ``effort``, blocked by ``blocked_by`` if given."""
    sizing = f"effort: {effort}\nrisk: low\nimpact: none\nseverity: {severity}\n"
    return f"{sizing}blocked_by: [{blocked_by}]\n" if blocked_by else sizing


class TestWorkOrder:
    """The tables, and ``--next``, sort by effective severity, readiness, effort, then filing order."""

    def test_a_table_sorts_by_severity_then_readiness_then_effort(self, boards):
        """Filing order only breaks the last tie."""
        refactors = boards / "refactors"
        _write(refactors / "REF-1-a.md", _ticket("REF-1", sizing=_sized("trivial")))
        _write(refactors / "REF-2-a.md", _ticket("REF-2", sizing=_sized("major", effort="L")))
        _write(refactors / "REF-3-a.md", _ticket("REF-3", sizing=_sized("major", effort="M")))
        _write(refactors / "REF-4-a.md", _ticket("REF-4", sizing=_sized("major", effort="S", blocked_by="REF-1")))
        _write(refactors / "REF-5-a.md", _ticket("REF-5", sizing=_sized("major", effort="M")))

        assert todo_index.main([]) == 0
        # REF-1 blocks a major ticket, so it sorts as major too, and its S effort puts it first.
        assert _rows(refactors / "README.md") == ["REF-1", "REF-3", "REF-5", "REF-2", "REF-4"]

    def test_a_blocker_inherits_the_highest_severity_it_blocks_across_boards(self, boards):
        """Inheritance is transitive, crosses boards, and names the ticket it comes from."""
        _write(
            boards / "bugs" / "BUG-1-a.md",
            _ticket("BUG-1", sizing=_sized("critical", blocked_by="FEAT-1"), repro=True),
        )
        _write(boards / "features" / "FEAT-1-a.md", _ticket("FEAT-1", sizing=_sized("minor", blocked_by="REF-1")))
        _write(boards / "refactors" / "REF-1-a.md", _ticket("REF-1", sizing=_sized("trivial")))

        assert todo_index.main([]) == 0
        assert "| critical (via BUG-1) |" in (boards / "features" / "README.md").read_text(encoding="utf-8")
        assert "| critical (via BUG-1) |" in (boards / "refactors" / "README.md").read_text(encoding="utf-8")
        assert "| critical | FEAT-1 |" in (boards / "bugs" / "README.md").read_text(encoding="utf-8")

    def test_a_question_inherits_a_severity_and_has_none_otherwise(self, boards):
        """A question blocking a major ticket is major; one blocking nothing carries a blank cell."""
        _write(boards / "questions" / "Q-1-a.md", _ticket("Q-1", sizing=""))
        _write(boards / "questions" / "Q-2-a.md", _ticket("Q-2", sizing=""))
        _write(boards / "features" / "FEAT-1-a.md", _ticket("FEAT-1", sizing=_sized("major", blocked_by="Q-2")))

        assert todo_index.main([]) == 0
        readme = boards / "questions" / "README.md"
        assert _rows(readme) == ["Q-2", "Q-1"]
        assert "| major (via FEAT-1) |" in readme.read_text(encoding="utf-8")

    def test_next_lists_unblocked_tickets_across_boards(self, boards, capsys):
        """``--next N`` skips a blocked ticket however severe, and stops after N."""
        _write(
            boards / "bugs" / "BUG-1-a.md",
            _ticket("BUG-1", sizing=_sized("critical", blocked_by="REF-1"), repro=True),
        )
        _write(boards / "features" / "FEAT-1-a.md", _ticket("FEAT-1", sizing=_sized("major")))
        _write(boards / "features" / "FEAT-2-a.md", _ticket("FEAT-2", sizing=_sized("minor")))
        _write(boards / "refactors" / "REF-1-a.md", _ticket("REF-1", sizing=_sized("trivial")))

        assert todo_index.main(["--next", "2"]) == 0
        out = capsys.readouterr().out
        assert " 1. REF-1 — " in out
        assert "critical (via BUG-1) · S · refactors/REF-1-a.md" in out
        assert " 2. FEAT-1 — " in out
        assert "BUG-1" not in out.replace("via BUG-1", "")
        assert "FEAT-2" not in out


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
