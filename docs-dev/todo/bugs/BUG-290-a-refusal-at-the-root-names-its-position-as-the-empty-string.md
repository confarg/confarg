---
filed: 2026-10-26
where:
  - src/confarg/exceptions.py::_spell_field_path  # "()", the target itself, is "" by contract
  - src/confarg/exceptions.py::TypeCoercionError  # its factories quote the spelled path, at '{path}'
  - src/confarg/typedload/_construct.py  # every refusal construction raises carries the path it stands at
effort: M  # one spelling, but every factory that quotes a path and the tests pinning their text
risk: medium  # the message pins are spread over many test files; a factory missed keeps the old text
impact: behavior
severity: minor  # a misleading message; the refusal is loud and names the value and the type
introduced_by: [PR-5]
---

# BUG-290 — A refusal at the root names its position as the empty string

A refusal of the value at the root says it stands `at ''`, a position no user can read: `build(int, {"__root__": "x"})` says `Cannot coerce str 'x' to int at ''`, a root union of structs handed an unknown key says `Cannot coerce dict {'zz': 1} to A | B at '':`, and a struct root `Unknown field(s) ['zz'] for A at ''`.
One level down the position reads, `at 'port'`, so only the root is misnamed; an element of a root list drops the root and starts at its index, `at '[0]'`.
The refusals that already say where the root is do it by hand, `_spell_field_path(path) or _defaults.ROOT_KEY` ([REF-109](../refactors/REF-109-a-message-names-the-root-position-by-hand.md)), and that spelling is itself wrong at a struct root ([BUG-285](BUG-285-a-shadowed-tag-warning-at-a-struct-root-names-the-key-root.md)).

Fix direction: one spelling of a position for every message, saying "at the root" where the path is empty and `at 'port'` elsewhere, which is REF-109's `_spelled_where(path)`; fixing this, REF-109 and BUG-285 together closes all three, since each is the root's spelling in a message.

Origin: latent since the initial version (PR-5), whose construction carried the path as a dotted string starting at `""`, quoted into each refusal as `at '{path}'`.
BUG-169 (PR-335) carried the path as segments and wrote the empty spelling into `_spell_field_path`'s contract, `()` being `""`, unchanged.
BUG-285 shares no origin with it but the same cause, a message spelling the root by the path's text.

```python
from dataclasses import dataclass

import confarg
from confarg.exceptions import ConfargError


@dataclass
class A:
    a: int = 0


@dataclass
class B:
    b: int = 0


for tp, data in [(int, {"__root__": "x"}), (A | B, {"zz": 1}), (A, {"zz": 1}), (list[int], {"__root__": ["x"]})]:
    try:
        confarg.build(tp, data)
    except ConfargError as e:
        print(str(e).splitlines()[0])
# expected: each refusal says the value is at the root, and the last one at the root's element [0]
# actual:   Cannot coerce str 'x' to int at ''
#           Cannot coerce dict {'zz': 1} to A | B at '':
#           Unknown field(s) ['zz'] for A at ''. Valid fields: ['a']
#           Cannot coerce str 'x' to int at '[0]'
```
