---
filed: 2026-10-22
where:
  - src/confarg/typedload/_construct.py::_call_struct
  - src/confarg/typedload/_construct.py::build_from_nothing  # wraps the empty build only
effort: L  # the design pass: which exceptions are wrapped, and whether a __post_init__ validation error is one
needs_design: true
risk: high
impact: api  # a caller catching the constructor's TypeError or ValueError would catch a ConfargError instead
severity: minor  # invalid input answered with a raw exception; the message is Python's own and still readable
introduced_by: [PR-5]  # the initial version called a struct's constructor unguarded
---

# BUG-269 — A constructor's own exception escapes construction raw, with no path

When a struct's constructor refuses the data it is given, the exception it raises leaves `build()` as it is: a bare `TypeError` (an abstract class, an `__init__` that refuses its arguments), naming neither the field's path nor the class confarg was building.
Only a class asked to build from nothing gets its refusal read ([a class built from nothing](../../architecture/types/construction.md#a-class-built-from-nothing)); `build_from_nothing`'s docstring says a constructor's `TypeError` about supplied data "still escapes as its own", but no note says why.

Fix direction, for the design pass: whether `_call_struct` wraps what the constructor raises in a `TypeCoercionError` naming the path and the class, its cause chained, and which exceptions that covers — a `ValueError` from a `__post_init__` check is the user's own validation, which a caller may be catching by type.
Precedents to run then: cattrs wraps them in `ClassValidationError`, pydantic only a validator's `ValueError` and `AssertionError`, dacite lets them through *(inferred, from their documentation)*.

`re.Pattern` and `re.Match` used to reach this too, with `cannot create 're.Pattern' instances`; since BUG-268 they are unsupported leaves, refused before any call.

Origin: latent since the initial version (PR-5), whose `_construct_struct` ended in `tp(**kwargs, **var_kw)` with no handler; BUG-213 and BUG-215 later read the refusal of an empty build only, the one their reproductions reached.

```python
import abc
from dataclasses import dataclass

import confarg


class Base(abc.ABC):
    def __init__(self, n: int = 1):
        self.n = n

    @abc.abstractmethod
    def run(self): ...


class Refuses:
    def __init__(self, n: int = 1):
        raise TypeError("nope")


@dataclass
class H:
    b: Base | None = None
    r: Refuses | None = None


confarg.from_dict(H, {"b": {"n": 2}})
# expected: a TypeCoercionError naming 'b' and Base
# actual:   builtins.TypeError: Can't instantiate abstract class Base without an implementation for abstract method 'run'
confarg.from_dict(H, {"r": {"n": 2}})
# expected: a TypeCoercionError naming 'r' and Refuses
# actual:   builtins.TypeError: nope
```
