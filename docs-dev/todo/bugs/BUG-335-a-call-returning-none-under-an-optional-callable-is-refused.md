---
filed: 2026-11-12
where:
  - src/confarg/typedload/_construct.py::_takes_typed_call  # drops None, so Callable | None reads as a lone Callable
  - src/confarg/typedload/_construct.py::spec_reading_variant  # hands the call to the Callable variant
  - src/confarg/_parse_cli.py::_opens_spec_subtree  # the CLI walk asks _takes_typed_call of call and args
effort: M  # the routing is one predicate, but the CLI walk, registration and the merge ask it too
risk: medium  # _takes_typed_call decides how argv, registration and the merge read call and args
impact: behavior  # a call returning None builds None, where it was refused
severity: minor  # a loud refusal; a function returning a no-op callable works around it
introduced_by: [FEAT-61]  # read a Callable's call value as configuration, at the variant rather than the field
---

# BUG-335 — A call returning `None` under an optional Callable is refused

A call's value is configuration written in its place ([a call's value is read by construction](../../architecture/design-decisions/a-calls-value-is-read-by-construction.md#a-calls-value-is-configuration-written-in-its-place)), and `f: null` builds `None` on `f: Callable[[int], int] | None`, so `{call: g}` with `g` returning `None` should too, as it does on `n: int | None` and on `Callable[[int], int] | int`.
It is refused instead: the union hands the `call:` to its Callable variant (`spec_reading_variant`, since `_takes_typed_call` drops `None` and sees one member), so the value is read at the variant, which takes no `None`.
Fix direction: send a `call:` on a union whose only other member is `None` to the union, as the typed-call route does, so the union reads the value.
That moves `Callable | None` onto the typed-call route, whose predicate `_takes_typed_call` is also asked by the CLI walk (`_parse_cli._opens_spec_subtree`, which accepts `--f.call` and `--f.args.<p>`), by registration through it, and by the merge's `reads_as_new_value` through `_is_typed_call`; each must keep reading `--f.call pkg.g --f.args.x 1` on `Callable | None` as it does today, and the five front-ends checked in the contract suite.

Origin: FEAT-61 read a Callable's call value as configuration and, by the maintainer's ruling in its session, left the value read at the Callable variant on `Callable | None`, where before FEAT-61 a call's value had to be callable anyway.

```python
from collections.abc import Callable
from dataclasses import dataclass

import confarg


def nothing() -> None:
    return None


@dataclass
class Config:
    n: int | None = 0
    f: Callable[[int], int] | None = None


for data in [{"n": {"call": "__main__.nothing"}}, {"f": None}, {"f": {"call": "__main__.nothing"}}]:
    try:
        print(confarg.build(Config, data))
    except Exception as e:
        print(type(e).__name__, e)
# expected: Config(n=None, f=None), Config(n=0, f=None), Config(n=0, f=None)
# actual:
# Config(n=None, f=None)
# Config(n=0, f=None)
# TypeCoercionError Cannot construct Callable at 'f': expected a callable, str or dict, got NoneType None
```
