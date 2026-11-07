---
filed: 2026-11-07
where:
  - src/confarg/_callable.py::_coerce_kwargs  # passes a value through where no annotation types it, and every value where no signature reads
effort: S
risk: medium  # every bind:, call: and class-key argument goes through it; a typed one must stay built as today
impact: behavior  # a callee sees a str where it saw a str subclass
severity: minor  # the token is a str subclass, so a callee works unless it reads the exact type; refusals name the internal class
introduced_by: [PR-93]
---

# BUG-308 — An unannotated argument of a call target receives the argv token

Under the `args` of `bind:` or `call:`, a parameter with no annotation receives argv's `_StrToken` itself, where a file's value reaches it as a `str`, against [tokens never leak out](../../architecture/types/token-model.md#token-model): an `Any` field holds a token's text, not the token.
A parameter annotated `Any` gets a `str` (`_coerce._held_by_any`), and so does an unannotated parameter of a struct, so only the callable route skips it: `_callable._coerce_kwargs` passes the value through when `hints` has no entry for it, and passes every value through when the target's signature does not read.
A refusal then names the internal class, `must be real number, not _StrToken` for `math.pow`, and a callee that reads `type(x)` sees it.
Fix direction: hand a value no annotation types to construction as `Any`, so it is held as a bare `Any` field holds it, on both pass-through branches.

Origin: latent since PR-93, which read a callable's arguments through its signature and passed an unannotated one through as given, before tokens were unwrapped where an `Any` holds them.

```python
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import confarg


def kind(x):
    return type(x).__name__


def kind_any(x: Any):
    return type(x).__name__


@dataclass
class C:
    value: Any = None
    f: Callable[[], str] | None = None


for target in ("__main__.kind", "__main__.kind_any", "math.pow"):
    argv = ["--value.call", target, "--value.args.x", "5"] + (["--value.args.y", "2"] if target == "math.pow" else [])
    try:
        print(target, "call: argv ->", confarg.load(C, argv=argv, env={}).value)
    except confarg.exceptions.ConfargError as e:
        print(target, "call: argv ->", type(e).__name__, str(e)[:100])
print("bind: argv ->", confarg.load(C, argv=["--f.bind", "__main__.kind", "--f.args.x", "5"], env={}).f())
print("bind: file ->", confarg.build(C, {"f": {"bind": "__main__.kind", "args": {"x": "5"}}}).f())
# expected: str for every line; math.pow refused as 'must be real number, not str'
# actual:
#   __main__.kind call: argv -> _StrToken
#   __main__.kind_any call: argv -> str
#   math.pow call: argv -> TypeCoercionError Failed to call 'math.pow' at 'value': must be real number, not _StrToken
#   bind: argv -> _StrToken
#   bind: file -> str
```
