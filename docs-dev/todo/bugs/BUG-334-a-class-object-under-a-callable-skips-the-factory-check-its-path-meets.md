---
filed: 2026-11-12
where:
  - src/confarg/_callable.py::_resolve_callable_spec  # the callable(spec) branch takes a class as it is
  - src/confarg/_callable.py::_unproducible_return  # asked only by _import_target, for a path
effort: S
risk: low
impact: behavior  # a class object a Callable cannot use as a factory is refused, where it was taken
severity: minor  # a wrong callable taken silently, but only from Python data or a call's value, never a file
introduced_by: [PR-93]  # feat: Improve handling of Callables, which added the factory check to the import path
---

# BUG-334 — A class object under a Callable skips the factory check its path meets

A Callable whose declared return type a class cannot produce refuses that class named by its path, `would be used as a factory, but its instances are not int`, and takes the same class handed as an object: in `build()` data, or as the value of a `call:`, which since FEAT-61 reads a returned path and a returned class through the same Callable construction.
`_resolve_callable_spec` asks `_unproducible_return` only through `_import_target`, on a dotted path; its `callable(spec)` branch returns the class as it is, so calling the field builds an `Adder` where the annotation promises an `int`.
Fix direction: the one check applies wherever a class reaches a Callable node as its factory, the `callable(spec)` branch asking `_unproducible_return` of a class as `_import_target` does ([class as factory versus class as instance](../../architecture/callables.md#class-as-factory-versus-class-as-instance)).

Origin: latent since PR-93, which added the factory check (`_unproducible_return`) to the import of a bare path and a `bind:` target, the spellings a file has, and left the branch taking a callable object unchecked; FEAT-61 made the gap reachable from a configuration file, through a `call:` returning the class.

```python
from collections.abc import Callable
from dataclasses import dataclass

import confarg


@dataclass
class Adder:
    k: int = 1

    def __call__(self, x: int) -> int:
        return x + self.k


def adder_class() -> type[Adder]:
    return Adder


@dataclass
class Config:
    f: Callable[[int], int]


for data in [{"f": "__main__.Adder"}, {"f": Adder}, {"f": {"call": "__main__.adder_class"}}]:
    try:
        print(confarg.build(Config, data).f)
    except Exception as e:
        print(type(e).__name__, e)
# expected: the same refusal three times
# actual:
# TypeCoercionError Callable at 'f': class '__main__.Adder' would be used as a factory, but its instances are not int (the Callable's declared return type). To use an instance of __main__.Adder as the callable, use the dict form: 'class: __main__.Adder'.
# <class '__main__.Adder'>
# <class '__main__.Adder'>
```
