"""Regenerate each board's ticket table from the ticket files themselves, and query them.

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

A ticket's fields live in YAML front matter, above its ``# <ID> — <headline>`` heading, so this
script reads them with a YAML parser rather than with patterns over prose. ``--where PATH``
lists the open tickets whose ``where`` names that file or directory — the question to ask
before editing one::

    uv run python docs-dev/todo/index.py --where src/confarg/_parse_env.py

Regenerating is the smaller half. The script also *validates* what it reads, because the rules
in ``README.md`` are otherwise enforced by nobody: a ticket whose filename disagrees with its
heading, a board holding another board's prefix, a missing, unknown or misspelled field, a bug
ticket with no reproduction, two tickets claiming one ID — which is not hypothetical, REF-26 was
issued twice and went unnoticed because the duplicates sat in different sections of one long
file — a ``where`` naming a file or symbol that no longer exists, and a ``blocked_by`` naming a
ticket that is no longer open.

Validation *gates* the rewrite: when anything is wrong, every table is left exactly as it was
and the run exits non-zero. A table written beside an error is a table missing the row of a
ticket that is still open, which is the drift this script exists to prevent.
"""

from __future__ import annotations

import argparse
import datetime
import fnmatch
import io
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

TODO = Path(__file__).resolve().parent
#: What a ``where`` path is relative to.
ROOT = TODO.parents[1]

#: Boards carrying effort, risk and impact. ``questions`` is exempt: a question is answered,
#: not implemented, so there is nothing to size.
SIZED = ("bugs", "features", "refactors")
BOARDS = (*SIZED, "questions")
PREFIXES = {"bugs": "BUG", "features": "FEAT", "refactors": "REF", "questions": "Q"}

EFFORTS = ("S", "M", "L", "XL")
RISKS = ("low", "medium", "high")
IMPACTS = ("none", "behavior", "api", "config")

#: The front matter keys only a sized board may carry.
SIZING = ("effort", "risk", "impact", "needs_design")
KEYS = ("filed", "where", *SIZING, "inferred", "blocked_by")

#: The agent-facing files are ``.gitignore``d, so they exist in a contributor's checkout but not
#: in the repository: a ``where`` naming one is not checked against the working tree.
UNVERSIONED = ("AGENTS.md", "CLAUDE.md", "docs-agents/")

START = "<!-- tickets:start -->"
END = "<!-- tickets:end -->"

_HEADING = re.compile(r"^# ((?:BUG|FEAT|REF|Q)-\d+) — (.+)$")
_TICKET_ID = re.compile(r"(?:BUG|FEAT|REF|Q)-\d+")
_FENCE = re.compile(r"^\s*(?:`{3,}|~{3,})")
_GLOB = re.compile(r"[*?\[]")


@dataclass(frozen=True)
class Ticket:
    """One ticket file, parsed into the columns its board's table shows and the fields queried."""

    number: int
    tid: str
    headline: str
    effort: str
    risk: str
    impact: str
    filename: str
    board: str
    where: tuple[str, ...]
    blocked_by: tuple[str, ...]


def _front(where: str, text: str, errors: list[str]) -> tuple[dict[str, object], list[str]] | None:
    """Return a ticket's front matter and the lines after it, or None if it has no readable one."""
    lines = text.splitlines()
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        errors.append(f"{where}: must open with front matter between two '---' lines")
        return None
    end = lines.index("---", 1)
    try:
        meta = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError as exc:
        errors.append(f"{where}: front matter is not valid YAML: {exc}")
        return None
    if not isinstance(meta, dict):
        errors.append(f"{where}: front matter must be a mapping of keys to values")
        return None
    return meta, lines[end + 1 :]


def _strings(where: str, key: str, value: object, errors: list[str]) -> tuple[str, ...]:
    """Return ``value`` as a tuple of strings, or report that it is not a list of them."""
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        errors.append(f"{where}: {key} must be a list of strings")
        return ()
    return tuple(value)


def _check_where(where: str, entries: tuple[str, ...], errors: list[str]) -> None:
    """Check that each ``where`` entry names a path, and a symbol, that still exist."""
    for entry in entries:
        path, _, symbol = entry.partition("::")
        if path.startswith(("/", "../")) or "\\" in path:
            errors.append(f"{where}: where entry {entry!r} must be a repository-root path with '/' separators")
        elif path.startswith(UNVERSIONED):
            continue
        elif _GLOB.search(path):
            if not any(ROOT.glob(path.rstrip("/"))):
                errors.append(f"{where}: where entry {entry!r} matches no file; was it moved?")
        elif not (ROOT / path).exists():
            errors.append(f"{where}: where entry {entry!r} names a path that does not exist; was it moved?")
        elif symbol:
            target = ROOT / path
            text = target.read_text(encoding="utf-8") if target.is_file() else ""
            if not re.search(rf"(?<![\w.]){re.escape(symbol)}\b", text):
                errors.append(f"{where}: where entry {entry!r} names a symbol {path} no longer holds; was it renamed?")


def _check_fields(where: str, board: str, meta: dict[str, object], errors: list[str]) -> None:
    """Validate the front matter keys against the board's rules; ``where`` is checked apart."""
    errors.extend(f"{where}: unknown front matter key {key!r}" for key in meta if key not in KEYS)
    filed = meta.get("filed")
    if not isinstance(filed, datetime.date) or isinstance(filed, datetime.datetime):
        errors.append(f"{where}: filed must be a date, YYYY-MM-DD")
    flags = ("needs_design", "inferred")
    errors.extend(f"{where}: {key} must be true or false" for key in flags if not isinstance(meta.get(key, True), bool))

    if board not in SIZED:
        errors.extend(
            f"{where}: {board}/ is exempt from sizing, so it must not carry {key}" for key in SIZING if key in meta
        )
        return
    for key, allowed in (("effort", EFFORTS), ("risk", RISKS), ("impact", IMPACTS)):
        if key not in meta:
            errors.append(f"{where}: missing {key}")
        elif meta[key] not in allowed:
            errors.append(f"{where}: {key} is {meta[key]!r}, expected one of {', '.join(allowed)}")


def _parse(path: Path, board: str, errors: list[str]) -> Ticket | None:
    """Parse one ticket file, appending to ``errors`` and returning None if it is malformed."""
    where = f"{board}/{path.name}"
    front = _front(where, path.read_text(encoding="utf-8"), errors)
    if front is None:
        return None
    meta, lines = front

    heading = _HEADING.match(lines[0]) if lines else None
    if heading is None:
        errors.append(f"{where}: the line after the front matter must read '# <ID> — <headline>'")
        return None
    tid, headline = heading.group(1), heading.group(2)
    prefix, _, number = tid.partition("-")
    if prefix != PREFIXES[board]:
        errors.append(f"{where}: {tid} carries the {prefix} prefix, but this board issues {PREFIXES[board]}")
        return None
    if not path.name.startswith(f"{tid}-"):
        errors.append(f"{where}: filename does not start with '{tid}-', so the heading and the file disagree")
        return None

    _check_fields(where, board, meta, errors)
    entries = _strings(where, "where", meta.get("where", []), errors)
    _check_where(where, entries, errors)
    blocked_by = _strings(where, "blocked_by", meta.get("blocked_by", []), errors)
    if board == "bugs" and not any(_FENCE.match(line) for line in lines):
        errors.append(f"{where}: a bug ticket ends with a reproduction, and this one has no fenced block")

    return Ticket(
        number=int(number),
        tid=tid,
        headline=headline,
        effort=str(meta.get("effort", "")),
        risk=str(meta.get("risk", "")),
        impact=str(meta.get("impact", "")),
        filename=path.name,
        board=board,
        where=entries,
        blocked_by=blocked_by,
    )


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


def _check_blockers(tickets: list[Ticket], errors: list[str]) -> None:
    """Check that every ``blocked_by`` names another ticket that is still open, on any board."""
    open_ids = {ticket.tid for ticket in tickets}
    for ticket in tickets:
        where = f"{ticket.board}/{ticket.filename}"
        for blocker in ticket.blocked_by:
            if not _TICKET_ID.fullmatch(blocker):
                errors.append(f"{where}: blocked_by entry {blocker!r} is not a ticket ID")
            elif blocker == ticket.tid:
                errors.append(f"{where}: a ticket cannot be blocked by itself")
            elif blocker not in open_ids:
                errors.append(f"{where}: blocked by {blocker}, which is no longer open; drop it from blocked_by")


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


@dataclass(frozen=True)
class _Board:
    """One board's README, and the text its ticket files say that README should hold."""

    name: str
    readme: Path
    updated: str
    count: int


def _plan(board: str, tickets: list[Ticket], errors: list[str]) -> _Board | None:
    """Return what one board's README should hold, or None if it cannot be read."""
    readme = TODO / board / "README.md"
    if not readme.is_file():
        errors.append(f"{board}/README.md: missing")
        return None

    updated = _rewrite(readme, _table(board, tickets), errors)
    return None if updated is None else _Board(board, readme, updated, len(tickets))


def _touches(entry: str, query: str) -> bool:
    """Whether a ``where`` entry names ``query``, a directory holding it, or a file inside it."""
    path = entry.partition("::")[0].rstrip("/")
    return (
        path == query
        or query.startswith(f"{path}/")
        or path.startswith(f"{query}/")
        or (_GLOB.search(path) is not None and fnmatch.fnmatchcase(query, path))
    )


def _query(tickets: list[Ticket], queries: list[str], errors: list[str]) -> int:
    """Print the open tickets whose ``where`` touches any of ``queries``."""
    wanted = [query.replace("\\", "/").removeprefix("./").rstrip("/") for query in queries]
    # Headlines carry an em dash, which a Windows pipe would otherwise encode in its code page.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    for ticket in sorted(tickets, key=lambda t: (BOARDS.index(t.board), t.number)):
        hits = [entry for entry in ticket.where if any(_touches(entry, query) for query in wanted)]
        if hits:
            print(f"{ticket.board}/{ticket.filename}")
            print(f"  {ticket.tid} — {ticket.headline}")
            print("".join(f"  where: {entry}\n" for entry in hits), end="")
    # A stale entry elsewhere on a board must not hide the answer, but it must not go unseen.
    for error in errors:
        print(f"warning: {error}", file=sys.stderr)
    return 0


def main(argv: list[str]) -> int:
    """Regenerate every board table, check them with ``--check``, or query them with ``--where``."""
    parser = argparse.ArgumentParser(prog="index.py", description="Regenerate, check or query the ticket boards.")
    parser.add_argument("--check", action="store_true", help="write nothing; exit non-zero on a stale table")
    parser.add_argument("--where", nargs="+", metavar="PATH", help="list the open tickets touching PATH")
    args = parser.parse_args(argv)

    # Every board is read and validated before anything is written.  A ticket `_parse` rejects is
    # dropped by `_collect`, so a table generated beside an error is a table missing the row of a
    # ticket that is still open -- the drift this script exists to prevent, produced by the script
    # itself (BUG-36).  Validation therefore gates the rewrite instead of running beside it.
    errors: list[str] = []
    boards = {board: _collect(board, errors) for board in BOARDS}
    tickets = [ticket for board in BOARDS for ticket in boards[board]]
    _check_blockers(tickets, errors)
    if args.where:
        return _query(tickets, args.where, errors)

    plans = [plan for board in BOARDS for plan in (_plan(board, boards[board], errors),) if plan is not None]
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        print("error: no table was rewritten; fix the error(s) above and rerun", file=sys.stderr)
        return 1

    stale: list[str] = []
    for plan in plans:
        if plan.updated == plan.readme.read_text(encoding="utf-8"):
            print(f"{plan.name}/: {plan.count} ticket(s), table up to date")
        elif args.check:
            stale.append(plan.name)
            print(f"{plan.name}/: {plan.count} ticket(s), TABLE STALE")
        else:
            plan.readme.write_text(plan.updated, encoding="utf-8", newline="\n")
            print(f"{plan.name}/: {plan.count} ticket(s), table rewritten")

    if stale:
        print(f"error: rerun 'uv run python docs-dev/todo/index.py' to refresh: {', '.join(stale)}", file=sys.stderr)
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
