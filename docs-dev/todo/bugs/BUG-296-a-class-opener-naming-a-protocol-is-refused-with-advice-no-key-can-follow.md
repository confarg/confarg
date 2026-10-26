---
filed: 2026-10-26
where:
  - src/confarg/typedload/_construct.py::construct_named_class
  - src/confarg/typedload/_construct.py::build_from_nothing  # writes the "supply the class's fields" advice
effort: S
risk: medium  # the refusal is loud either way; only its wording and its site move
impact: behavior  # the message changes
severity: minor  # a misleading message on invalid input
introduced_by: [PR-5, BUG-215]  # PR-5: class openers call any class; BUG-215: the "cannot be built with no arguments" wording
---

# BUG-296 — A class opener naming a Protocol is refused with advice no key can follow

A `class:` spec naming a `typing.Protocol` class is built like any class, and the refusal comes from the call: under `Any`, `{class: pkg.Greeter}` is refused as `cannot be built with no arguments: Protocols cannot be instantiated`, followed by "Supply the class's fields as keys beside the 'class' opener", and supplying one gives `Unknown field(s) ['name'] for Greeter … Valid fields: ['args', 'kwargs']`, the parameters of `typing`'s placeholder constructor.
No key can make a Protocol buildable, so both messages point the wrong way.
The same reaches a Callable's `class:`.
A plain-class field cannot meet one, since a Protocol may only inherit Protocols (`class P(Base, Protocol)` raises `Protocols can only inherit from other protocols`, run).

Fix direction, decided while designing Protocol fields ([the Protocol plan](../plans/protocol-typed-fields.md#a-protocol-is-an-abstract-base-its-implementers-are-named-into)): `construct_named_class`, the one constructor every named class goes through, refuses a Protocol class before calling anything, with a message saying it is a Protocol and that a class implementing it is wanted.
FEAT-57 adds the matching refusal under a `type[P]` field, in `_coerce_type_ref`.
Precedent: jsonargparse 4.53 refuses it wherever a `class_path` names one, `Expected an instantiatable class, but protomod.Greeter is a protocol`.

Origin: latent since the initial version (PR-5), whose class openers called whatever class they named; BUG-215 then read every empty build of a named class through `build_from_nothing`, which gave the refusal its current advice, written for a class that needs arguments.

```python
from dataclasses import dataclass
from typing import Any, Protocol

import confarg


class Greeter(Protocol):
    def greet(self) -> str: ...


@dataclass
class C:
    x: Any


for data in ({"x": {"class": "__main__.Greeter"}}, {"x": {"class": "__main__.Greeter", "name": "n"}}):
    try:
        print(data, "->", confarg.build(C, data))
    except confarg.exceptions.ConfargError as e:
        print(data, "->", type(e).__name__, e)

# expected: both refused as naming a Protocol, asking for a class that implements it
# actual:   {'x': {'class': '__main__.Greeter'}} -> TypeCoercionError Class '__main__.Greeter' at 'x' cannot be built with no arguments: Protocols cannot be instantiated. Supply the class's fields as keys beside the 'class' opener.
#           {'x': {'class': '__main__.Greeter', 'name': 'n'}} -> TypeCoercionError Unknown field(s) ['name'] for Greeter at 'x'. Valid fields: ['args', 'kwargs']
```
