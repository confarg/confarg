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

The notes cite each other as well, by relative Markdown link, and the same sweep follows those:
every link in ``docs-dev/``, ``docs-agents/`` and ``AGENTS.md`` has to name a file or folder that
exists, and its anchor a heading of that file. Links inside a fence or a code span are not links,
and a URL is not followed. Two more shapes are errors there: a link from ``docs-dev/`` into the
agent protocols, which the notes never depend on, and a note cited by line number
(``invariants.md:106``), which no edit of the note survives — link a heading instead. The
protocols are ``.gitignore``d, so a checkout without them sweeps ``docs-dev/`` alone.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

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
#: The opening or closing line of a fenced block: three or more backticks or tildes, then the rest.
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
#: An inline code span, delimited by equal runs of backticks.
_CODE_SPAN = re.compile(r"(`+)(.+?)\1")
#: An inline link or image, ``[text](target)``, with an optional title after the target.
_LINK = re.compile(r"\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
#: A target with a scheme: a URL, which this sweep leaves to the web.
_URL = re.compile(r"[a-z][\w+.-]*:")
#: A Markdown name followed by a line number: a note cited the way no edit of it survives.
_LINE_CITATION = re.compile(r"(?<![\w./-])[\w.-]+(?:/[\w.-]+)*\.md:\d+")
#: The Markdown the sweep of the notes reads, from the repository root. One that is absent is
#: skipped: the protocols are ``.gitignore``d, so a fresh checkout has none.
_NOTES = ("docs-dev", "docs-agents", "AGENTS.md")
#: What ``docs-dev/`` never links to: the protocols depend on the notes, never the reverse.
_PROTOCOLS = ("docs-agents", "AGENTS.md", "CLAUDE.md")


def _slug(text: str) -> str:
    """Return the GitHub anchor for one heading's text."""
    # Inline code renders before the anchor is generated, so its backticks are gone by then.
    text = text.replace("`", "").lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def _prose(text: str) -> Iterator[tuple[int, str]]:
    """Yield each line of a Markdown text that sits outside its fenced blocks, numbered from 1."""
    # A fence closes on a bare run of its own character at least as long as the one that opened
    # it, which is what lets a ```` block show a ``` block whole.
    fence = ""
    for number, line in enumerate(text.splitlines(), start=1):
        match = _FENCE.match(line)
        if fence:
            if match is not None and match.group(1).startswith(fence) and not match.group(2).strip():
                fence = ""
        elif match is not None:
            fence = match.group(1)
        else:
            yield number, line


def _anchors(document: Path) -> list[str]:
    """Return every anchor a document's headings generate, duplicates suffixed like GitHub's."""
    anchors: list[str] = []
    seen: Counter[str] = Counter()
    for _, line in _prose(document.read_text(encoding="utf-8")):
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


def _link(target: str, document: Path, root: Path, anchors: dict[Path, list[str]]) -> str | None:
    """Return the error for one relative link in a note, if it cannot be followed.

    ``anchors`` caches each linked document's anchors by its resolved path, and is filled here.
    """
    path, _, anchor = target.partition("#")
    resolved = (document.parent / path).resolve() if path else document
    if not resolved.exists():
        return f"links {target}, but there is no such file"
    if document.is_relative_to(root / "docs-dev") and any(resolved.is_relative_to(root / name) for name in _PROTOCOLS):
        return f"links {target}, but docs-dev/ never links to the agent protocols"
    if not anchor:
        return None
    if not resolved.is_file():
        return f"links {target}, but a folder has no headings"
    if resolved not in anchors:
        anchors[resolved] = _anchors(resolved)
    if anchor not in anchors[resolved]:
        return f"links {target}, but no heading in it generates #{anchor}"
    return None


def _sweep_notes(root: Path) -> tuple[list[str], int]:
    """Return every link in ``root``'s notes that cannot be followed, and how many links they hold."""
    root = root.resolve()
    documents: list[Path] = []
    for name in _NOTES:
        path = root / name
        documents += sorted(path.rglob("*.md")) if path.is_dir() else [path] if path.is_file() else []
    errors: list[str] = []
    anchors: dict[Path, list[str]] = {}
    links = 0
    for document in documents:
        for number, line in _prose(document.read_text(encoding="utf-8")):
            spans = [match.span() for match in _CODE_SPAN.finditer(line)]
            targets = [
                match.group(1)
                for match in _LINK.finditer(line)
                if not any(a <= match.start() < b for a, b in spans) and not _URL.match(match.group(1))
            ]
            links += len(targets)
            found = [_link(target, document, root, anchors) for target in targets]
            found += [
                f"cites {match.group(0)} by line number, which no edit of the note survives; link a heading"
                for match in _LINE_CITATION.finditer(line)
            ]
            where = f"{document.relative_to(root).as_posix()}:{number}"
            errors += [f"{where}: {error}" for error in found if error is not None]
    return errors, links


def main() -> int:
    """List every citation in the code and every link in the notes that cannot be followed, and fail if there is one."""
    errors, cited = _sweep(ROOT)
    note_errors, links = _sweep_notes(ROOT)
    errors += note_errors
    for error in errors:
        print(f"error: {error}")
    if not errors:
        print(f"{cited} document(s) cited, every anchor resolves")
        print(f"{links} link(s) between the notes, every one resolves")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
