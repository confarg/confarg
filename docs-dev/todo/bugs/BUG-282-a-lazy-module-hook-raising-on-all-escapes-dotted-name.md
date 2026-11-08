---
filed: 2026-10-25
where:
  - src/confarg/_import.py::_published_name  # reads __all__ with getattr, which runs the hook unshielded
effort: S
risk: low  # what a failing hook publishes is already settled by _held; the __all__ read joins it
impact: none
severity: minor  # loud: an error from the user's module replaces confarg's own refusal or message
introduced_by: [BUG-279]  # its _published_name reads __all__ off every candidate module
---

# BUG-282 — A lazy module hook that raises on `__all__` escapes `dotted_name`

`_published_name` reads a candidate module's `__all__` with `getattr(module, "__all__", None)`, which runs the module's PEP 562 `__getattr__` when the module declares none, and shields only an `AttributeError`.
A hook that raises anything else for a name it does not hold — an `ImportError` naming an optional dependency is the usual one — escapes `dotted_name`, so `dump()`, and every message that names a class by its path (a union's variants, a subclass list, a completer), raises the hook's error instead of its own.
The object's own name is read through `_held`, which already decides that ["a lazy hook that fails publishes nothing under the name"](../../architecture/types/dotted-imports.md#a-path-names-the-module-that-publishes-the-object); the `__all__` read was left out of it.
Fix direction: read `__all__` through `_held`, a failing hook declaring none.
Found checking a static review of BUG-279's fix, whose finding about the own-name read had been addressed and whose `__all__` read had not.

Origin: BUG-279 made `dotted_name` look up which module publishes the object, reading `__all__` off each candidate; before it, `dotted_name` ran no module code, and the same dump was refused by confarg's own `ConfargError` (the hook makes `lazy.Plugin` fail to import back).
A regression.

```python
import sys
import types
from dataclasses import dataclass

import confarg

lazy = types.ModuleType("lazy")  # a module whose lazy hook raises on a name it does not hold
sys.modules["lazy"] = lazy


def _hook(name):
    raise ImportError(f"lazy needs an optional dependency for {name!r}")


lazy.__getattr__ = _hook
exec("class Plugin:\n    pass", lazy.__dict__)


@dataclass
class C:
    kind: type = object


try:
    print(confarg.dump(C(kind=lazy.Plugin)))
except Exception as e:
    print(f"{type(e).__name__}: {e}")

# expected (as before BUG-279): ConfargError: Cannot serialize class <class 'lazy.Plugin'>: 'lazy.Plugin' does not import back as it. A class defined in a function, or one its module no longer holds under that name, has no dotted path.
# actual: ImportError: lazy needs an optional dependency for '__all__'
```
