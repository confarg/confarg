---
filed: 2026-10-25
where:
  - src/confarg/dictexpr/_expressions.py::resolve_expressions  # copy.deepcopy(data)
effort: S
risk: low  # tests already pin that resolution leaves the caller's dict, nested ones included, unchanged
impact: behavior
severity: critical  # the copy is silent; an object deepcopy refuses fails loudly instead
introduced_by: [PR-5]  # the initial version, whose resolve_expressions deep-copied its input
---

# BUG-284 — Resolving an expression deep-copies every value `build()` is handed

`resolve_expressions` deep-copies the whole merged dict before writing the resolved values into it, leaves included.
So an object handed to `build()` at an `Any` field is the object itself when the data holds no expression, and a copy of it as soon as one does, silently; an object `copy.deepcopy` refuses, a lock or a connection, raises a raw `TypeError` from `copy` instead.
Fix direction: copy the dicts and lists the resolution writes into, and keep each leaf the caller handed in, as construction does with no expression; the default layer's `_copied_if_changed` already copies only what changes.

Origin: latent since the initial version, PR-5, whose `resolve_expressions` deep-copied its input to leave the caller's dict unchanged; every later revision kept the copy.

```python
import threading
from dataclasses import dataclass
from typing import Any

import confarg


class Client:
    pass


@dataclass
class Config:
    client: Any = None
    name: str = "app"
    label: str = ""


client = Client()
print(confarg.build(Config, {"client": client}).client is client)
print(confarg.build(Config, {"client": client, "label": "${name}"}).client is client)
# expected: True, True
# actual:   True, False
confarg.build(Config, {"client": threading.Lock(), "label": "${name}"})
# expected: Config(client=<unlocked _thread.lock object at ...>, name='app', label='app')
# actual:   TypeError: cannot pickle '_thread.lock' object
```
