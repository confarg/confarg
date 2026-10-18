---
filed: 2026-10-12
where:
  - src/confarg/_merge.py::_is_call_dict
  - src/confarg/_merge.py::_starts_afresh
effort: M
risk: high
impact: behavior
severity: critical  # the first case binds a stale argument with no error; the others fail loudly
needs_design: true  # widening the replace-by-key rule to bind/classfn also widens its data-loss cost
introduced_by: [PR-5]  # an opener over another opener merged key by key from the initial version
---
# BUG-231 — A callable opener merges with the spec a lower layer set instead of replacing it

On a Callable field, a higher layer's `bind:` (or `classfn:`, or `class:` under a custom `union_tag`) merges key by key with the spec a lower layer set there. The lower spec's `args` stay under the new target: when the new target takes them, the result is a partial over arguments the user never wrote for it, with no error; when it does not, the load fails on an unknown parameter. Over a lower `call:`, the merged dict holds two openers and is refused. A `call:` already replaces what lies below ([a call replaces what lies below](../../architecture/design-decisions/a-call-replaces-what-lies-below.md#a-call-replaces-what-lies-below)), and so does the default union tag, `class`; `bind` and `classfn` do not.

The fix is a design question first: making every opener replace by key, as `call` does, is the one-line change in `_merge._is_call_dict`, but each word added there also drops lower layers' keys where the type holds it as data (a `dict` field with a `bind` key), the cost [limitations](../../architecture/limitations.md#callables-and-serialization) records for `call`.

Origin: latent since the initial version (PR-5), where `{fn: g}` over `{fn: f, bind: {a: 1, b: 2}}` already kept the stale `bind` kwargs and `{fn: g}` over `{call: …}` held two openers (reproduced against PR-5 in its own grammar). FEAT-30 renamed the openers and BUG-190's fix made `call` replace; neither touched the other openers.

```python
import pathlib
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import confarg


def f(a: int = 0, b: int = 0) -> tuple[int, int]:
    return (a, b)


def g(a: int = 0) -> int:
    return a


def make() -> Callable[..., Any]:
    return f


@dataclass
class Config:
    fn: Callable[..., Any] = f


d = pathlib.Path(tempfile.mkdtemp())
for lower, upper in [
    ("fn: {bind: __main__.f, args: {a: 1}}\n", "fn: {bind: __main__.g}\n"),  # expected: 0
    ("fn: {bind: __main__.f, args: {a: 1, b: 2}}\n", "fn: {bind: __main__.g}\n"),  # expected: 0
    ("fn: {call: __main__.make}\n", "fn: {bind: __main__.g}\n"),  # expected: 0
]:
    (d / "base.yaml").write_text(lower)
    (d / "over.yaml").write_text(upper)
    try:
        print(confarg.load(Config, argv=[], env={}, files=[d / "base.yaml", d / "over.yaml"]).fn())
    except confarg.exceptions.ConfargError as e:
        print(f"{type(e).__name__}: {e}")
```

Actual output, from the revision that filed this:

```text
1
TypeCoercionError: Unknown bind parameter(s) ['b'] for g at 'fn.args'. Valid parameters: ['a'].
TypeCoercionError: Callable dict at 'fn' must not specify more than one of ['bind', 'class', 'call', 'classfn'] (got: ['bind', 'call'])
```
