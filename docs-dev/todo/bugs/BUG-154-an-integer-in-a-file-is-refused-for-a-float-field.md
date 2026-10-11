---
filed: 2026-10-05
where:
  - src/confarg/typedload/_coerce.py::_coerce_float_value
effort: S
risk: high
impact: behavior
severity: minor  # workaround: write 1.0
introduced_by: [PR-5]  # the float coercion has no branch for a native int
---
# BUG-154 — An integer in a file is refused for a `float` field

`_coerce_float_value` passes a native `float` through and parses a token, but refuses a native
`int`. So `timeout: 1` in a JSON, YAML or TOML file fails to build a `timeout: float` field, while
`--timeout 1` and `MYAPP_TIMEOUT=1` build `1.0` from the same text. That is a gap in
[cross-channel parity](../../architecture/invariants.md#cross-channel-parity). It also refuses
what PEP 484's numeric tower allows: an `int` is acceptable wherever `float` is annotated, and
pydantic and msgspec both accept one for a `float` field. Fix direction: accept a native `int`
(never a `bool`) and convert it to `float`, then check that a union holding a `float` variant
still picks the variant it picks today for a native `int`.

Origin: latent since the initial version (PR-5), whose float coercion passed a native `float` and
parsed a token, but had no branch for a native `int`. No revision since has revisited it.

```python
import json
import pathlib
from dataclasses import dataclass

import confarg


@dataclass
class Config:
    timeout: float


pathlib.Path("cfg.json").write_text(json.dumps({"timeout": 1}))
print(confarg.load(Config, argv=["--timeout", "1"]))
print(confarg.load(Config, argv=["--config", "cfg.json"]))
# expected: Config(timeout=1.0), twice
# actual:   Config(timeout=1.0)
#           confarg.exceptions.TypeCoercionError: Cannot coerce int 1 to float at 'timeout'
```
