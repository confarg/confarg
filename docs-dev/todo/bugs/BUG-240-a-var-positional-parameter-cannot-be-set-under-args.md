---
filed: 2026-10-14
where:
  - src/confarg/_callable.py::_fillable_params
  - src/confarg/_callable.py::_coerce_kwargs
  - src/confarg/_callable.py::_serialize_callable
effort: M
risk: medium
impact: behavior
severity: minor  # refused with a clear error; a class: of a wrapper or a list parameter works around it
introduced_by: [PR-5]  # the bind kwarg check left out *args from the first version
---
# BUG-240 — A `*args` parameter cannot be set under the `args` of `bind:` or `call:`

A struct reads its `__init__`'s `*items` as a list field, so `--bag.items '[1, 2]'` builds `Bag(1, 2)`, but the `args` of a `bind:` or `call:` spec refuses the same name as unknown, since `_fillable_params` leaves `*args` out of the names a spec may fill. The two routes into one signature disagree on what it accepts ([one coercion route](../../architecture/callables.md#one-coercion-route)). Fix direction: read a `*args` parameter under `args` as a list, passed after the positional prefix as the struct path does, and let `_serialize_callable` write a partial's spilled positional arguments under that name instead of refusing them. The CLI registration of `--f.args.<p>` and the arity check read the same `_fillable_params`, so they move with it. [FEAT-2](../features/FEAT-2-protocol-callables-and-kwargs.md) is the `**kwargs` side of the same question.

Origin: latent since the initial version (PR-5), whose bind and factory kwarg checks already left `VAR_POSITIONAL` out of the valid names while the struct path read it as a list.

```python
from collections.abc import Callable
from dataclasses import dataclass

import confarg


class Bag:
    def __init__(self, *items: int) -> None:
        self.items = items


def total(*xs: int) -> int:
    return sum(xs)


@dataclass
class Config:
    bag: Bag
    f: Callable[..., int] = total


print(confarg.load(Config, argv=["--bag.items", "[1, 2]"]).bag.items)
# (1, 2)
print(confarg.load(Config, argv=["--bag.items", "[1]", "--f.bind", "__main__.total", "--f.args.xs", "[1, 2]"]).f())
# expected: 3
# actual:   TypeCoercionError: Unknown bind parameter(s) ['xs'] for total at 'f.args'. Valid parameters: [].
```
