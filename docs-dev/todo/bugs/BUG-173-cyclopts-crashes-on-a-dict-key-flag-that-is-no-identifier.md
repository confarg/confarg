---
filed: 2026-10-05
where:
  - src/confarg/cli/cyclopts/_register.py::_pyname
effort: S
risk: medium
impact: behavior
---
# BUG-173 — cyclopts crashes on a dict-key flag whose key is no identifier

`populate_app` names each flag's `inspect.Parameter` through `_pyname`, which promises "a
valid, unique Python identifier" but maps only `.`, `+` and `-`. A dict key holding any other
character (`[`, `/`, `:`, a space) leaves the name invalid, and `inspect.Parameter` raises a
raw `ValueError` before parsing starts. The other four front-ends accept the flag and build the
key. The `name_map` already restores the CLI spelling, so the fix only has to escape every
non-identifier character, keeping the mapping unique
([CLI adapters](../../architecture/cli-adapters/README.md)). The contract test
`test_remedy_flag_keeps_a_dict_key_spelled_like_an_index` xfails strictly on cyclopts for
this; the fix removes the marker.

```python
from dataclasses import dataclass

import cyclopts

import confarg
from confarg.cli.cyclopts import from_app, populate_app


@dataclass
class D:
    d: dict[str, int]


for key in ("web-1", "x[0]", "a/b", "a:b"):
    argv = [f"--d.{key}", "1"]
    print(key, "vanilla:", confarg.load(D, argv=argv, env={}))
    app = cyclopts.App()
    try:
        populate_app(D, app, argv=argv)
        print(key, "cyclopts:", from_app(D, app, argv=argv))
    except Exception as e:
        print(key, "cyclopts:", type(e).__name__, e)

# expected: cyclopts builds D(d={'x[0]': 1}), D(d={'a/b': 1}) and D(d={'a:b': 1}), as vanilla does
# actual:
#   web-1 vanilla: D(d={'web-1': 1})
#   web-1 cyclopts: D(d={'web-1': 1})
#   x[0] vanilla: D(d={'x[0]': 1})
#   x[0] cyclopts: ValueError 'd__x[0]' is not a valid parameter name
#   a/b vanilla: D(d={'a/b': 1})
#   a/b cyclopts: ValueError 'd__a/b' is not a valid parameter name
#   a:b vanilla: D(d={'a:b': 1})
#   a:b cyclopts: ValueError 'd__a:b' is not a valid parameter name
```
