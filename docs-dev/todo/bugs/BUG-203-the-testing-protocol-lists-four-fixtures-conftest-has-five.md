---
filed: 2026-10-07
where:
  - docs-agents/testing.md  # the fixture list under "Front-end parity: write it once"
effort: S
risk: low
impact: none
severity: trivial
introduced_by: [BUG-20]  # PR-161, which added the fixture; docs-agents/ is unversioned, so the sweep missed it
---
# BUG-203 — The testing protocol lists four fixtures, conftest defines five

`docs-agents/testing.md` says "Fixtures live in `tests/conftest.py`: `loader`, `space_sep_loader`,
`repeated_loader`, `populating_loader`", but `conftest.py` defines a fifth, `whole_value_arity_loader`
(vanilla/argparse/cyclopts,
[whole-value-flags.md](../../architecture/cli-adapters/whole-value-flags.md)). An agent writing an
arity test does not learn the fixture exists and may write it against `loader` instead. Found while
fixing BUG-150 in the same section. Fix direction: add `whole_value_arity_loader` to the list. `docs-agents/` is `.gitignore`d,
so the text is the same on every revision; editing it means running
`uv run python docs-agents/archive.py` afterwards.

Origin: regression from BUG-20 (PR-161), which added `whole_value_arity_loader` to
`tests/conftest.py` and updated the versioned notes but could not see the unversioned protocols —
the same blind spot as BUG-149 and BUG-150.

```console
$ grep -n "Fixtures live" docs-agents/testing.md
docs-agents/testing.md:43:- Fixtures live in `tests/conftest.py`: `loader`, `space_sep_loader`, `repeated_loader`,
docs-agents/testing.md:44:  `populating_loader`.
$ grep -n "^def .*loader(request: pytest.FixtureRequest)" tests/conftest.py
626:def loader(request: pytest.FixtureRequest) -> ConfargLoader:
632:def space_sep_loader(request: pytest.FixtureRequest) -> ConfargLoader:
638:def repeated_loader(request: pytest.FixtureRequest) -> ConfargLoader:
647:def whole_value_arity_loader(request: pytest.FixtureRequest) -> ConfargLoader:
653:def populating_loader(request: pytest.FixtureRequest) -> ConfargLoader:
# expected: the protocol lists the five fixtures conftest defines
# actual:   it lists four; whole_value_arity_loader is missing
```
