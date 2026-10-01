# BUG-105 — The anchor sweep cannot see citations under `tests/`, nor short-form spellings

**Where:** `docs-dev/todo/anchors.py` · **Filed:** 2026-10-01
**Effort:** S · **Risk:** medium · **Impact:** none

The sweep collects citations only from `.py` files under `src/` (`SRC = ROOT / "src"`), and its
`_CITATION` regex matches only the repo-root spelling `docs-dev/architecture/<doc>.md#<anchor>`.
Both halves have already let real citations go stale silently: the architecture tree was
reorganized from numbered notes (`09-invariants.md`, `10-design-decisions.md`) into the current
topic folders, and twelve citations — five of them in `tests/cli/test_backend_contract.py`, the
rest in `src/confarg/` — pointed at files that no longer existed while the sweep reported
"every anchor resolves" (repointed in the revision that filed this ticket). Fix direction: add
`tests/` to the swept roots, and decide whether a citation that *looks* like the convention
(`NN-<name>.md#<anchor>`, or any `<name>.md#<anchor>` in a docstring or comment) but cannot
match the regex should be flagged rather than skipped — the convention that keeps cited
headings stable is
[architecture/README.md § Conventions](../../architecture/README.md#conventions), and the
sweep is what enforces it.

```console
$ grep -rnE "\((0[0-9]|1[0-2])-[a-z-]+\.md(#[a-z-]+)?\)" src tests --include=*.py | grep -v Binary
src/confarg/_files.py:306:    (10-design-decisions.md#a-class-tag-replaces-not-merges). Anything else is replaced by the
src/confarg/_files.py:430:    (10-design-decisions.md#the--suffix-is-a-merge-operator-not-a-list-spelling). A list of
tests/cli/test_backend_contract.py:1455:        The approved divergence (09-invariants.md#cross-channel-parity): click's options
... (nine more, run with the same tree)
$ uv run python docs-dev/todo/anchors.py
44 document(s) cited, every anchor resolves
# expected: a non-zero exit listing every citation whose document (let alone anchor) is gone
# actual:   exit 0 — the twelve citations name files deleted by the docs-tree reorganization
```
