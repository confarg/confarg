# BUG-119 — `_defaults.py` says four front-ends must agree; there are five

**Where:** `src/confarg/_defaults.py` (module docstring, `ROOT_KEY` docstring) ·
**Filed:** 2026-10-03
**Effort:** S · **Risk:** low · **Impact:** none

The module docstring says the constants exist "so the four front-ends cannot drift apart", and
`ROOT_KEY` says "all four front-ends have to agree on the spelling". The architecture counts five
— vanilla, argparse, click, typer, cyclopts
([invariants.md#cross-channel-parity](../../architecture/invariants.md#cross-channel-parity),
[pipeline/api-seams.md#public-api-seams](../../architecture/pipeline/api-seams.md#public-api-seams)) —
and the constants are read by all five. Fix direction: say five, or drop the count.

```console
$ grep -n "four front-ends" src/confarg/_defaults.py
7:Always reference these constants instead of repeating the literals, so the four front-ends
63:Every channel writes it and ``build`` reads it, so all four front-ends have to agree on the
$ grep -n "five front-ends" docs-dev/architecture/invariants.md docs-dev/architecture/pipeline/api-seams.md
docs-dev/architecture/invariants.md:7:Every feature behaves identically across the five front-ends (vanilla, argparse, click,
docs-dev/architecture/pipeline/api-seams.md:13:Shared keyword defaults and reserved key names live in `_defaults.py` so the five front-ends
```
