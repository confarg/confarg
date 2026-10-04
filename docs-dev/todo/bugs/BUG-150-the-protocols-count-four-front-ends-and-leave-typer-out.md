---
filed: 2026-10-04
where:
  - docs-agents/bug-fixing.md
  - docs-agents/feature-design.md
  - docs-agents/testing.md  # § Front-end parity: write it once
effort: S
risk: low
impact: none
---
# BUG-150 — The protocols count four front-ends and leave typer out

`docs-agents/testing.md` says parity holds "between the four front-ends (vanilla, argparse,
click, cyclopts)" and that `tests/_loaders.py` "wraps all four", and that `repeated_loader`
covers "click/cyclopts"; `feature-design.md` designs for "four front-ends × three channels" and
`bug-fixing.md` for "the four front-ends". `tests/_loaders.py` wraps five, typer included, the
`repeated_loader` fixture runs click, typer and cyclopts, and the architecture counts five
([invariants.md#cross-channel-parity](../../architecture/invariants.md#cross-channel-parity)).
An agent reading the protocols cold can conclude typer is outside the parity mandate. Same drift
as [BUG-119](BUG-119-defaults-module-counts-four-front-ends.md) in `_defaults.py`. Fix
direction: say five and list typer, or drop the count. `docs-agents/` is `.gitignore`d, so the
text is the same on every revision; editing it means running
`uv run python docs-agents/archive.py` afterwards.

```console
$ grep -n "four front-ends\|all four\|(click/cyclopts)" docs-agents/*.md
docs-agents/bug-fixing.md:7:   layout in [testing.md](testing.md) dictates. Behavior shared by the four front-ends goes once
docs-agents/feature-design.md:5:A feature is designed for **four front-ends × three channels at once**: vanilla `load()`,
docs-agents/testing.md:33:Parity between the four front-ends (vanilla, argparse, click, cyclopts) is enforced by tests,
docs-agents/testing.md:34:not by review. `tests/_loaders.py` wraps all four behind one `confarg.load()`/`merge()`-shaped
docs-agents/testing.md:47:  (click/cyclopts) instead of hiding it behind a helper.
$ grep -n "^class .*Loader(ConfargLoader)" tests/_loaders.py
120:class VanillaLoader(ConfargLoader):
130:class ArgparseLoader(ConfargLoader):
178:class ClickLoader(ConfargLoader):
241:class TyperLoader(ConfargLoader):
314:class CycloptsLoader(ConfargLoader):
# expected: the protocols name the five front-ends the loaders wrap
# actual:   they name four, without typer
```
