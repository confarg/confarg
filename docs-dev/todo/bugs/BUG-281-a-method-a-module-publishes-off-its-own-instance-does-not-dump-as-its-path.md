---
filed: 2026-10-25
where:
  - src/confarg/_import.py::has_dotted_name  # a C method bound to an instance has no path
  - src/confarg/_callable.py::_object_spec  # a Python method bound to an instance dumps its owner's state
effort: S
needs_design: true  # the effort sizes the design pass: is a module's bound method a reference or its owner's state?
risk: medium  # every bound method's dump goes through the answer
impact: behavior  # random.random starts dumping; calendar.month may dump as its path
severity: minor  # refused at dump(), and the merged dict keeps the spec that produced it
introduced_by: [PR-5]  # the initial version writes a callable as __module__ plus __qualname__, which a C method bound to an instance lacks
---

# BUG-281 — A method a module publishes off its own instance does not dump as its path

`random.random`, `random.randint`, `calendar.month` and `secrets.randbits` are methods bound to an instance the module creates at import time (`random._inst`, `calendar.c`, `secrets._sysrand`), which the module publishes as functions.
`random.random` is a C method bound to an instance, which has no `__module__` and no owner class to be named through, so `dump()` refuses it as one "no configuration spells", though `random.random` reads it back; `secrets.randbits` is refused because `SystemRandom` does not hold the `x` it is built from; `calendar.month` dumps as a `classfn:` spec over a fresh `TextCalendar` holding the module instance's state, which reads back as another object than the one the module publishes.
The module publishes each under a path that imports back as the object itself (`random.random == random._inst.random`), which BUG-279's `_public_path` could find, but writing that path makes the value a reference to the module's instance where [an object dumps the state it holds](../../architecture/callables.md#an-object-dumps-the-state-it-holds) writes the owner's state.
Design question: is a method a module publishes off its own instance a reference, dumped as its path like a function, or a bound method like any other, refused when its owner's state cannot be read?
Found while settling BUG-279, whose walk spells a module-level object and leaves bound methods to their owner.

Origin: latent since the initial version (PR-5), which wrote a callable as `__module__` plus `__qualname__`; a C method bound to an instance has neither, and BUG-195, which named a C type's method through its class, kept `"abc".upper` refused as a method no spec builds without considering a module's own instance.

```python
from collections.abc import Callable
from dataclasses import dataclass

import confarg


@dataclass
class F:
    fn: Callable


for path in ["random.random", "secrets.randbits", "calendar.month"]:
    try:
        print(path, "->", confarg.dump(confarg.build(F, {"fn": path}))["fn"])
    except Exception as e:
        print(path, "->", f"{type(e).__name__}: {e}")

# expected, if a module's bound method is a reference: each dumps as its path
# actual:
# random.random -> ConfargError: Cannot serialize callable <built-in method random of Random object at 0x...>: no configuration spells it, since it has no dotted path. Dump the merged configuration instead, which keeps the spec that produced it.
# secrets.randbits -> ConfargError: Cannot serialize SystemRandom at 'fn': field 'x' is declared in SystemRandom.__init__ but not accessible on the instance as self.x. Plain classes must store every __init__ parameter as a same-named instance attribute.
# calendar.month -> {'classfn': 'calendar.TextCalendar.formatmonth', 'firstweekday': 0}
```
