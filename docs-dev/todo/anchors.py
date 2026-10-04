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
every ``.py`` file under ``src/``, so a cited anchor cannot go stale in a docstring a sweep
forgot to include. Tests cite notes too, so ``tests/`` is swept alongside ``src/``.

A citation spelled any other way is an error rather than something to skip: a ``<name>.md#<anchor>``
without the repo-root ``docs-dev/architecture/`` prefix, or a numbered ``NN-<name>.md`` from the
retired flat layout, cannot be checked, and a citation nobody checks is how twelve of them went
stale unnoticed.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCHITECTURE = ROOT / "docs-dev" / "architecture"
#: Every root a citation can be written under.
SWEPT = (ROOT / "src", ROOT / "tests")

#: A citation as the ``Dev Notes:`` convention writes it: repo-root path, ``.md``, one anchor.
#: The path may name a subtopic inside a topic folder, so it carries ``/`` segments.
_CITATION = re.compile(r"docs-dev/architecture/([\w.-]+(?:/[\w.-]+)*\.md)#([\w-]+)")
#: What looks like a citation but is not spelled as one: an anchored ``.md`` path that the
#: ``docs-dev/architecture/`` form above does not cover, or a numbered note of the retired layout.
_LOOKALIKE = re.compile(r"(?<![\w./-])(?:[\w./-]+\.md#[\w-]+|\d\d-[\w-]+\.md)")
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


def _lookalikes(path: Path, number: int, line: str) -> list[str]:
    """Return an error for every citation-shaped string in ``line`` that is not spelled as one."""
    covered = [match.span() for match in _CITATION.finditer(line)]
    return [
        f"{path.relative_to(ROOT)}:{number}: cites {match.group(0)}, which is not spelled"
        " docs-dev/architecture/<document>.md#<anchor>, so it cannot be checked"
        for match in _LOOKALIKE.finditer(line)
        if not any(start <= match.start() < end for start, end in covered)
    ]


def main() -> int:
    """List every citation under ``src/`` and ``tests/`` that does not resolve, and fail if there is one."""
    # An error is a source location plus the citation it holds, not a missing anchor alone: the
    # fix happens where the citation is written, so that is what the message has to name.
    errors: list[str] = []
    anchors: dict[str, list[str]] = {}
    paths = sorted(path for root in SWEPT for path in root.rglob("*.py"))
    for path in paths:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            errors.extend(_lookalikes(path, number, line))
            for match in _CITATION.finditer(line):
                document, anchor = ARCHITECTURE / match.group(1), match.group(2)
                if match.group(1) not in anchors:
                    if document.is_file():
                        anchors[match.group(1)] = _anchors(document)
                    else:
                        errors.append(
                            f"{path.relative_to(ROOT)}:{number}: cites {match.group(0)}, but there is no such document",
                        )
                        continue
                if anchor not in anchors[match.group(1)]:
                    errors.append(
                        f"{path.relative_to(ROOT)}:{number}: cites {match.group(0)},"
                        f" but no heading in it generates #{anchor}",
                    )

    for error in errors:
        print(f"error: {error}")
    if not errors:
        print(f"{len(anchors)} document(s) cited, every anchor resolves")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
