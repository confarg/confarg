"""Check that every architecture anchor cited in the code names a heading that exists.

A ``Dev Notes:`` section or a comment cites one document and one heading
(``docs-dev/architecture/cli-adapters/model.md#the-quartet``), and the cited headings are kept
stable *because* of those citations. A rename that forgets one leaves a citation that resolves
to the document and then to nothing — a reader following it lands at the top of the note and
has to guess which section was meant. This script is the sweep that convention asks for
(``grep -rn "<old-anchor>" src/``), run over every citation at once, so nothing depends on a
rename remembering to run it.

Run it after renaming a heading in an architecture note::

    uv run python docs-dev/todo/anchors.py

It exits non-zero and lists every stale citation. It writes nothing.

Anchors are generated the way GitHub generates them, since the citations are read as links
there: lowercase, punctuation dropped, spaces to hyphens, underscores kept, a repeated
heading suffixed ``-1``, ``-2``, … The same rule is what mkdocs calls ``slugify(case="lower",
separator="-")``, so it holds on the documentation site as well. Citations are collected from
every ``.py`` file under ``src/`` and ``tests/``, so a cited anchor cannot go stale in a
docstring a sweep forgot to include. A citation without an anchor names the whole note, and
only the note's existence is checked.

A citation the sweep cannot follow is an error too, or it goes stale unseen: a Markdown name
with an anchor that is not spelled from the repository root (``09-invariants.md#…``), or a
note's bare file name (``list-syntax-divergence.md``). The error gives the repo-root spelling
when the file name points at a single note.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: A citation as the ``Dev Notes:`` convention writes it: repo-root path, ``.md``, an anchor
#: unless the whole note is meant. The path may name a subtopic inside a topic folder, so it
#: carries ``/`` segments.
_CITATION = re.compile(r"docs-dev/architecture/([\w.-]+(?:/[\w.-]+)*\.md)(?:#([\w-]+))?")
#: Anything spelled like a Markdown file, starting at a token boundary, with an optional anchor.
_MARKDOWN = re.compile(r"(?<![\w./-])([\w.-]+(?:/[\w.-]+)*\.md)(?:#([\w-]+))?")
#: This sweep's own tests, whose fixtures spell broken citations on purpose.
_OWN_TESTS = "tests/tooling/test_anchors.py"
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def _slug(text: str) -> str:
    """Return the GitHub anchor for one heading's text."""
    # Inline code renders before the anchor is generated, so its backticks are gone by then.
    text = text.replace("`", "").lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def _anchors(document: Path) -> list[str]:
    """Return every anchor a document's headings generate, duplicates suffixed like GitHub's."""
    anchors: list[str] = []
    seen: Counter[str] = Counter()
    for line in document.read_text(encoding="utf-8").splitlines():
        heading = _HEADING.match(line)
        if heading is None:
            continue
        slug = _slug(heading.group(2))
        seen[slug] += 1
        anchors.append(slug if seen[slug] == 1 else f"{slug}-{seen[slug] - 1}")
    return anchors


def _canonical(match: re.Match[str], architecture: Path, anchors: dict[str, list[str]]) -> str | None:
    """Return the error for a repo-root citation that does not resolve, if it does not.

    ``anchors`` caches each existing cited note's anchors by its path, and is filled here.
    """
    name, anchor = match.group(1), match.group(2)
    if name not in anchors:
        document = architecture / name
        if not document.is_file():
            return f"cites {match.group(0)}, but there is no such document"
        anchors[name] = _anchors(document)
    if anchor is not None and anchor not in anchors[name]:
        return f"cites {match.group(0)}, but no heading in it generates #{anchor}"
    return None


def _short_form(match: re.Match[str], notes: dict[str, list[str]], architecture: Path) -> str | None:
    """Return the error for a Markdown name that cites a note outside the repo-root form, if it does.

    A name with an anchor is a citation whatever it names; a bare name is one only when it is a
    note's file name. ``README.md`` is no note's name: every topic folder has one, and the tests
    write it as a fixture.
    """
    name, anchor = match.group(1), match.group(2)
    candidates = notes.get(name.rsplit("/", 1)[-1], [])
    if anchor is None and not candidates:
        return None
    error = f"cites {match.group(0)} in short form, which this sweep cannot follow"
    if len(candidates) != 1:
        return f"{error}; spell it docs-dev/architecture/<note>.md#<anchor>"
    target = anchor or _anchors(architecture / candidates[0])[0]
    return f"{error}; spell it docs-dev/architecture/{candidates[0]}#{target}"


def _sweep(root: Path) -> tuple[list[str], int]:
    """Return every stale citation under ``root``'s ``src/`` and ``tests/``, and how many notes are cited."""
    # An error is a source location plus the citation it holds, not a missing anchor alone: the
    # fix happens where the citation is written, so that is what the message has to name.
    architecture = root / "docs-dev" / "architecture"
    notes: dict[str, list[str]] = {}
    for note in sorted(architecture.rglob("*.md")):
        if note.name != "README.md":
            notes.setdefault(note.name, []).append(note.relative_to(architecture).as_posix())
    errors: list[str] = []
    anchors: dict[str, list[str]] = {}
    paths = [path for folder in ("src", "tests") for path in sorted((root / folder).rglob("*.py"))]
    for path in paths:
        if path.relative_to(root).as_posix() == _OWN_TESTS:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            where = f"{path.relative_to(root).as_posix()}:{number}"
            citations = list(_CITATION.finditer(line))
            spans = [match.span() for match in citations]
            shorts = [match for match in _MARKDOWN.finditer(line) if not any(a <= match.start() < b for a, b in spans)]
            found = [_canonical(match, architecture, anchors) for match in citations]
            found += [_short_form(match, notes, architecture) for match in shorts]
            errors += [f"{where}: {error}" for error in found if error is not None]
    return errors, len(anchors)


def main() -> int:
    """List every citation in ``src/`` and ``tests/`` that cannot be followed, and fail if there is one."""
    errors, cited = _sweep(ROOT)
    for error in errors:
        print(f"error: {error}")
    if not errors:
        print(f"{cited} document(s) cited, every anchor resolves")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
