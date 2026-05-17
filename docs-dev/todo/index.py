"""Regenerate each board's ticket table from the ticket files themselves.

Every ticket is its own file; a board's ``README.md`` carries a table of them. That table is a
*view*, so it must never be the thing anyone edits: a hand-maintained index drifts from the
files it claims to describe, and re-creates the shared file that one-ticket-one-file exists to
get rid of — two branches closing two tickets collide in it, exactly as they used to collide in
the old single-file boards.

Run it after filing, closing or re-sizing a ticket::

    uv run python docs-dev/todo/index.py

The table is written between the ``tickets:start`` and ``tickets:end`` markers in each board's
``README.md``; everything outside them is prose, and is left alone. ``--check`` writes nothing
and exits non-zero if a table is stale, which is the form to run in CI.

Regenerating is the smaller half. The script also *validates* what it reads, because the rules
in ``README.md`` are otherwise enforced by nobody: a ticket whose filename disagrees with its
heading, a board holding another board's prefix, a missing or misspelled effort/risk/impact, a
bug ticket with no reproduction, or two tickets claiming one ID — which is not hypothetical,
REF-26 was issued twice and went unnoticed because the duplicates sat in different sections of
one long file.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

TODO = Path(__file__).resolve().parent

#: Boards carrying effort, risk and impact. ``questions`` is exempt: a question is answered,
#: not implemented, so there is nothing to size.
SIZED = ("bugs", "features", "refactors")
BOARDS = (*SIZED, "questions")
PREFIXES = {"bugs": "BUG", "features": "FEAT", "refactors": "REF", "questions": "Q"}

RISKS = ("low", "medium", "high")
IMPACTS = ("none", "behavior", "api", "config")

START = "<!-- tickets:start -->"
END = "<!-- tickets:end -->"

_HEADING = re.compile(r"^# ((?:BUG|FEAT|REF|Q)-\d+) — (.+)$")
_FIELD = re.compile(r"\*\*(Effort|Risk|Impact):\*\* ([^·\n]+)")
_PARENTHETICAL = re.compile(r"\s*\*\(.*?\)\*")
_FENCE = re.compile(r"^\s*(?:`{3,}|~{3,})")


@dataclass(frozen=True)
class Ticket:
    """One ticket file, parsed into the columns its board's table shows."""

    number: int
    tid: str
    headline: str
    effort: str
    risk: str
    impact: str
    filename: str


def _fields(text: str) -> dict[str, str]:
    """Return the ``**Name:** value`` fields found in a ticket body."""
    return {name: value.strip() for name, value in _FIELD.findall(text)}


def _check_sizing(where: str, board: str, found: dict[str, str], lines: list[str], errors: list[str]) -> None:
    """Validate a ticket's effort, risk, impact and reproduction against its board's rules."""
    names = ("Effort", "Risk", "Impact")
    if board not in SIZED:
        errors.extend(
            f"{where}: {board}/ is exempt from sizing, so it must not carry **{name}:**"
            for name in names
            if name in found
        )
        return

    errors.extend(f"{where}: missing **{name}:**" for name in names if name not in found)
    risk, impact = found.get("Risk", ""), found.get("Impact", "")
    if risk and risk not in RISKS:
        errors.append(f"{where}: risk is {risk!r}, expected one of {', '.join(RISKS)}")
    if impact and impact not in IMPACTS:
        errors.append(f"{where}: impact is {impact!r}, expected one of {', '.join(IMPACTS)}")
    if board == "bugs" and not any(_FENCE.match(line) for line in lines):
        errors.append(f"{where}: a bug ticket ends with a reproduction, and this one has no fenced block")


def _parse(path: Path, board: str, errors: list[str]) -> Ticket | None:
    """Parse one ticket file, appending to ``errors`` and returning None if it is malformed."""
    where = f"{board}/{path.name}"
    lines = path.read_text(encoding="utf-8").splitlines()
    heading = _HEADING.match(lines[0]) if lines else None
    if heading is None:
        errors.append(f"{where}: first line must read '# <ID> — <headline>'")
        return None

    tid, headline = heading.group(1), heading.group(2)
    prefix, _, number = tid.partition("-")
    if prefix != PREFIXES[board]:
        errors.append(f"{where}: {tid} carries the {prefix} prefix, but this board issues {PREFIXES[board]}")
        return None
    if not path.name.startswith(f"{tid}-"):
        errors.append(f"{where}: filename does not start with '{tid}-', so the heading and the file disagree")
        return None

    found = _fields("\n".join(lines))
    _check_sizing(where, board, found, lines, errors)
    effort = _PARENTHETICAL.sub("", found.get("Effort", "")).strip()
    return Ticket(int(number), tid, headline, effort, found.get("Risk", ""), found.get("Impact", ""), path.name)


def _collect(board: str, errors: list[str]) -> list[Ticket]:
    """Return a board's tickets, sorted by ID, which is filing order."""
    folder = TODO / board
    if not folder.is_dir():
        errors.append(f"{board}/: no such board folder")
        return []

    tickets = [
        ticket
        for path in sorted(folder.glob("*.md"))
        if path.name != "README.md"
        for ticket in (_parse(path, board, errors),)
        if ticket is not None
    ]

    seen: dict[str, str] = {}
    for ticket in tickets:
        if ticket.tid in seen:
            errors.append(f"{board}/: {ticket.tid} is claimed by both {seen[ticket.tid]} and {ticket.filename}")
        seen[ticket.tid] = ticket.filename

    tickets.sort(key=lambda t: t.number)
    return tickets


def _table(board: str, tickets: list[Ticket]) -> str:
    """Render a board's tickets as a markdown table."""
    if not tickets:
        return "*No open tickets.*"
    if board not in SIZED:
        rows = [f"| [{t.tid} — {t.headline}]({t.filename}) |" for t in tickets]
        return "\n".join(["| Ticket |", "|---|", *rows])
    rows = [f"| [{t.tid} — {t.headline}]({t.filename}) | {t.effort} | {t.risk} | {t.impact} |" for t in tickets]
    return "\n".join(["| Ticket | Effort | Risk | Impact |", "|---|---|---|---|", *rows])


def _rewrite(readme: Path, table: str, errors: list[str]) -> str | None:
    """Return the README with its table replaced, or None if its markers are missing."""
    text = readme.read_text(encoding="utf-8")
    start, end = text.find(START), text.find(END)
    if start == -1 or end == -1 or end < start:
        errors.append(f"{readme.parent.name}/README.md: needs a '{START}' … '{END}' pair around its table")
        return None
    return f"{text[: start + len(START)]}\n\n{table}\n\n{text[end:]}"


def main(argv: list[str]) -> int:
    """Regenerate every board table, or check them when ``--check`` is passed."""
    check = "--check" in argv
    errors: list[str] = []
    stale: list[str] = []

    for board in BOARDS:
        tickets = _collect(board, errors)
        readme = TODO / board / "README.md"
        if not readme.is_file():
            errors.append(f"{board}/README.md: missing")
            continue

        updated = _rewrite(readme, _table(board, tickets), errors)
        if updated is None:
            continue
        if updated == readme.read_text(encoding="utf-8"):
            print(f"{board}/: {len(tickets)} ticket(s), table up to date")
            continue
        if check:
            stale.append(board)
            print(f"{board}/: {len(tickets)} ticket(s), TABLE STALE")
        else:
            readme.write_text(updated, encoding="utf-8", newline="\n")
            print(f"{board}/: {len(tickets)} ticket(s), table rewritten")

    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if stale:
        print(f"error: rerun 'uv run python docs-dev/todo/index.py' to refresh: {', '.join(stale)}", file=sys.stderr)
    return 1 if errors or stale else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
