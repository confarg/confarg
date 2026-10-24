---
filed: 2026-10-04
where:
  - docs-agents/testing.md  # the "Where a test goes" table
effort: S
risk: low
impact: none
severity: trivial
introduced_by: [BUG-52]  # PR-225, which deleted tests/examples/
---

# BUG-149 — The testing protocol routes example tests to a folder that does not exist

The "Where a test goes" table in `docs-agents/testing.md` sends a change to an example under `examples/` to `tests/examples/`, and there is no such folder: the examples are tested by replaying their README console blocks through `pytest-markdown-console`, which the same protocol's § Examples are tests describes.
The in-process harness that once lived under `tests/examples/` was deleted (BUG-52, [testing.md#examples-and-documentation](../../architecture/testing.md#examples-and-documentation)).
An agent following the table creates a test file in a folder nothing else uses.
Fix direction: route the row to the example's own `README.md` console blocks.
`docs-agents/` is `.gitignore`d, so the stale row is the same on every revision; editing it means running `uv run python docs-agents/archive.py` afterwards.

Origin: regression from BUG-52's fix, which deleted `tests/examples/` and updated `docs-dev/architecture/testing.md` but not this row.
`docs-agents/` is `.gitignore`d, so the fix's diff could not show the row it left stale; BUG-150 went stale the same way.

```console
$ grep -n "tests/examples" docs-agents/testing.md
25:| an example under `examples/` | `tests/examples/` — see below |
$ ls tests/examples
ls: cannot access 'tests/examples': No such file or directory
# expected: the row names where an example's test lives (its README's console blocks)
# actual:   it names a folder that does not exist
```
