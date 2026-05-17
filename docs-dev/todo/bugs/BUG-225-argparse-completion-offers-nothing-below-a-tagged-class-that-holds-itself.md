---
filed: 2026-10-11
where:
  - src/confarg/cli/argparse/_completion.py::_extend_walk_specs
  - src/confarg/cli/argparse/_completion.py::_extend_walk_field
effort: M
risk: medium
impact: behavior
severity: minor  # completion only: the flags still parse, the shell just offers none
introduced_by: [PR-5]  # the initial _completion._extend_walk recursed into every struct field
---

# BUG-225 — argparse completion offers nothing below a tagged class that holds itself

argparse's completion pre-extend walks the class a `--<field>.class` tag names (`_extend_walk_specs` through `_extend_walk_field`) and recurses into every struct field with no cycle guard.
On a class that holds itself (`child: Node | None`) the walk recurses until Python's limit; `_pre_extend_parser_for_completion` swallows the `RecursionError`, as completion must never raise, so the shell is offered none of that class's flags, not even the shallow ones a class without the cycle gets.

Fix direction: stop at a node already on the path, as the flag walk and the mount-point listing do ([a node already on the path is not entered](../../architecture/design-decisions/a-node-already-on-the-path-is-not-entered.md#a-node-already-on-the-path-is-not-entered)), by asking `cli._build._Descent.into` rather than a third guard ([invariants](../../architecture/invariants.md#delegate-to-the-canonical-function)).
The walk is a hand-kept copy of `_specs_for_field`'s dispatch (its docstring says it mirrors it; see [completion](../../architecture/cli-adapters/completion.md#completion) for why it never raises), so registering what that function returns for the tagged class, instead of mirroring it, would close this and keep the two from drifting again.

Origin: latent since PR-5.
The initial version's `_completion._extend_walk` recursed into `_is_struct(core)` fields with no guard, and REF-3 (PR-176) carried the recursion into `_extend_walk_specs` unchanged.
Until BUG-224 the static walk crashed first on any target holding such a type; a tag below a field the static walk does not enter (`slot: Any`) reached this walk even then.
BUG-224 shares the origin and is closed.

```python
from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any

from confarg.cli.argparse import populate_parser
from confarg.cli.argparse._completion import _pre_extend_parser_for_completion


@dataclass
class Flat:
    a: int = 0


@dataclass
class Node:
    a: int = 0
    child: Node | None = None


@dataclass
class App:
    slot: Any = None


for cls in (Flat, Node):
    parser = argparse.ArgumentParser()
    populate_parser(App, parser, argv=[])
    _pre_extend_parser_for_completion(parser, App, "class", "config", ["--slot.class", f"__main__.{cls.__name__}"])
    print(cls.__name__, sorted(a.dest for a in parser._actions if a.dest.startswith("slot.")))

# expected: completion offers the tagged class's flags below --slot, a self-holding one too
#   Flat ['slot.a']
#   Node ['slot.a', 'slot.child']
# actual:   the walk into Node never ends; its RecursionError is swallowed and nothing is offered
#   Flat ['slot.a']
#   Node []
```
