---
filed: 2026-10-07
where:
  - src/confarg/cli/_build.py::_collect_callable_key_argv_specs
effort: S
risk: low
impact: behavior
severity: minor  # a vague help line; the flag itself works
introduced_by: [FEAT-32]  # the typed opener registered through the catch-all of argv keys
---
# BUG-197 — A typed call's opener flag is described as a value, not as the function to call

On a Callable field, `--f.call` is registered as an opener: metavar `DOTTED.PATH`, help saying
it names a factory whose result is the callable. On a field of any other type, `--n.call` is
registered by the catch-all for keys that no signature describes, as `VALUE` with "Value for
'n.call' in the callable spec": it names neither a dotted path nor a function whose result
becomes the field, and the field holds no callable spec. The opener is registered only when
typed ([CLI](../../architecture/callables.md#cli)), but once it is, its help should read as the
opener it is.

Origin: FEAT-32 registered the typed opener and its arguments through
`_collect_callable_key_argv_specs`, the pass BUG-25 wrote for keys with no signature to describe,
since both are registered only when typed. The opener was the one key there that does have a
known meaning. Latent since FEAT-32.

```python
from collections.abc import Callable
from dataclasses import dataclass

import confarg.cli.argparse as confparse


def count() -> int:
    return 3


@dataclass
class Config:
    n: int = 2
    f: Callable[[], int] = int


argv = ["--n.call", "__main__.count", "--f.call", "__main__.count"]
for line in confparse.make_parser(Config, argv=argv).format_help().splitlines():
    if line.lstrip().startswith(("--n.call", "--f.call")):
        print(line)
# expected: --n.call DOTTED.PATH, described as the function whose result is 'n'
# actual:
#   --f.call DOTTED.PATH  Dotted import path for the 'f' callable (factory
#   --n.call VALUE        Value for 'n.call' in the callable spec.
```
