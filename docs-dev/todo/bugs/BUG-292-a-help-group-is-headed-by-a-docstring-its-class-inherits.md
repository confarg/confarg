---
filed: 2026-10-26
where:
  - src/confarg/cli/_spec.py::_struct_doc
effort: S
risk: low  # the help-text tests of every adapter read the group description
impact: behavior
severity: minor  # a wrong help line
introduced_by: [PR-13]  # the click and typer integration headed a group with inspect.getdoc(core)
---

# BUG-292 — A help group is headed by a docstring its class inherits

A struct's group in `--help` is described by "the struct's docstring, its author's prose" ([help text is format-neutral](../../architecture/cli-adapters/framework-specifics.md#help-text-is-format-neutral)), but `_struct_doc` falls back to `inspect.getdoc`, which inherits a docstring from the bases.
A class with none of its own is headed by its base's: `abc.ABC`'s "Helper class that provides a standard way to create an ABC using inheritance.", `typing.Generic`'s "Abstract base class for generic types." for any plain generic class, `Exception`'s, and `typing.Protocol`'s once Protocol fields are supported ([FEAT-57](../features/FEAT-57-protocol-typed-fields.md)).

Fix direction, decided while designing Protocol fields: read the class's own docstring only (`"__doc__" in tp.__dict__`, as the dataclass check beside it already does), so a subclass of a documented user class is headed by nothing too.
Precedent: jsonargparse 4.53 reads `component.__doc__`, which a class never inherits, and printed no description for an undocumented `ABC` subclass or generic class; pydantic's JSON-schema `description` reads `cls.__doc__` *(inferred, from its documentation)*.

Origin: latent since PR-13, which headed a click and typer group with `inspect.getdoc(core)`; PR-402 moved the call into `_struct_doc` and dropped the signature Python writes for a dataclass, and kept the inherited fallback.

```python
from abc import ABC
from dataclasses import dataclass

from confarg.cli.argparse import make_parser


class Base(ABC):
    def __init__(self, n: int = 1):
        self.n = n


@dataclass
class C:
    b: Base


make_parser(C).print_help()

# expected: the "b:" group has no description
# actual (tail of the output):
#   b:
#     Helper class that provides a standard way to create an ABC using
#     inheritance.
#
#     --b.n INT             (default: 1)
```
