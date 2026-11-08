---
filed: 2026-10-26
where:
  - src/confarg/_callable.py::_check_callable_signature
  - src/confarg/_callable.py::_callable_param_types  # reads Concatenate[int, ...] as one fixed parameter
effort: M  # a new call-shape checker in a new leaf module, which FEAT-57 reuses
risk: high  # construction is shared by every channel, and a false acceptance is silent in all of them
impact: config  # a Callable field holding a function with a required keyword-only parameter stops loading
severity: minor  # the false refusals have a workaround: annotate Callable[..., R]
introduced_by: [PR-5]  # _check_callable_signature counted required parameters from the initial version
---

# BUG-291 — A Callable's arity check refuses an optional parameter and accepts a keyword-only one

`_check_callable_signature` compares the number of required parameters with the number `Callable[[...], R]` declares, using `!=`.
So it refuses a function a type checker accepts, `def f(x: int = 0)` under `Callable[[int], int]`, and accepts one it refuses, `def f(*, x: int)`, which cannot be called with a positional argument.
`ty` answers the opposite on both: it accepts `optional_x` and refuses `kw_only` with `def kw_only(*, x: int) -> int is not assignable to (int, /) -> int`.
`_callable_param_types` also reads `Callable[Concatenate[int, ...], int]` as one fixed parameter, so `def pfx(x: int, y: str)`, which `ty` accepts, is refused with a message naming `typing.Unpack[typing.Concatenate[int, ...]]`.

Fix direction, settled in [the Protocol plan](../plans/protocol-typed-fields.md#one-call-shape-checker-serves-protocol-methods-and-callable-r): `Callable[[A, B], R]` is the expected signature `(a, b, /)`, `Concatenate[A, B, P]` its prefix `(a, b, /)` with the rest left open, checked by the typing specification's assignability rule for callables with the types left out, in a new `_conformance.call_conforms` that FEAT-57 reuses for a Protocol's methods.
A refusal names positions and kinds, since a `Callable[[int], int]` has no parameter names.
See [callables](../../architecture/callables.md).

Origin: latent since the initial version (PR-5), which checked the count of required parameters only; a parameter's kind (keyword-only), an optional parameter filling a declared position and a ParamSpec's open tail were never considered.

```python
from collections.abc import Callable
from dataclasses import dataclass
from typing import Concatenate

import confarg


def optional_x(x: int = 0) -> int:
    return x


def kw_only(*, x: int) -> int:
    return x


def pfx(x: int, y: str) -> int:
    return x


@dataclass
class C:
    f: Callable[[int], int]


@dataclass
class P:
    f: Callable[Concatenate[int, ...], int]


for target, name in ((C, "optional_x"), (C, "kw_only"), (P, "pfx")):
    try:
        print(name, "->", confarg.build(target, {"f": f"__main__.{name}"}))
    except confarg.exceptions.ConfargError as e:
        print(name, "->", type(e).__name__, e)

# expected: optional_x -> C(f=<function optional_x at 0x...>)
#           kw_only -> TypeCoercionError naming the keyword-only parameter
#           pfx -> P(f=<function pfx at 0x...>)
# actual:   optional_x -> TypeCoercionError Callable at 'f': annotation expects 1 parameter(s) ['int'], but <function optional_x at 0x0000010E9A749260> has 0 required parameter(s) []
#           kw_only -> C(f=<function kw_only at 0x0000010E9AD7F7E0>)
#           pfx -> TypeCoercionError Callable at 'f': annotation expects 1 parameter(s) ['typing.Unpack[typing.Concatenate[int, ...]]'], but <function pfx at 0x0000010E9B073C40> has 2 required parameter(s) ['x', 'y']
```
