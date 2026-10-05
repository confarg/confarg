---
filed: 2026-10-05
where:
  - src/confarg/_callable.py::_acceptable_kwarg_names
  - src/confarg/_callable.py::_resolve_fn_spec
  - src/confarg/_callable.py::_resolve_call_spec
effort: S
risk: high
impact: behavior
---
# BUG-156 — A positional-only parameter in a callable spec is passed by keyword

`_acceptable_kwarg_names` counts a positional-only parameter among the names a spec may fill, but
`bind:` and `call:` then pass every kwarg by keyword, which CPython refuses for a positional-only
parameter. A `bind:` loads without complaint and fails only when the application calls the
result, with a stdlib `TypeError`. A `call:` fails at load, but as "Failed to call" wrapping that
same `TypeError`. Fix direction: decide as [BUG-152](BUG-152-a-positional-only-init-parameter-fails-build-with-a-raw-typeerror.md)
does for `__init__`. Either fill positional-only parameters by position, or refuse them at load
by leaving them out of `_acceptable_kwarg_names`. `_fillable_params` is where the rule belongs
([callables](../../architecture/callables.md#one-coercion-route)).

```python
from collections.abc import Callable
from dataclasses import dataclass

import confarg


def scale(v: int, /, factor: int) -> int:
    return v * factor


def make_scaler(factor: int, /) -> Callable[[int], int]:
    return lambda v: v * factor


@dataclass
class Config:
    f: Callable[..., int]


cfg = confarg.load(Config, argv=["--f.fn", "__main__.scale", "--f.bind.v", "3"])
print(cfg.f(factor=2))
# expected: 6, or a ConfargError from load() naming 'v'
# actual:   TypeError: scale() got some positional-only arguments passed as keyword arguments: 'v'

confarg.load(Config, argv=["--f.call", "__main__.make_scaler", "--f.factor", "2"])
# expected: a working callable, or a ConfargError naming the positional-only 'factor'
# actual:   TypeCoercionError: Failed to call '__main__.make_scaler' at 'f': make_scaler() got some
#           positional-only arguments passed as keyword arguments: 'factor'
```
