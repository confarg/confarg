---
filed: 2026-10-05
where:
  - src/confarg/_parse_cli.py
  - src/confarg/typedload/_construct.py::_construct_single_variant_union
effort: M
risk: high
impact: behavior
needs_design: true
---
# BUG-163 — A none word on the CLI cannot null an optional collection

`APP_XS=none` sets a `list[int] | None` field to `None`, but `--xs none` does not: the flag
consumes its run as a list, so `build()` receives `['none']`, which is no token, and the
none word is never read. The same holds for a `tuple[int, int] | None` field. On the CLI, only
the JSON cast (`--xs.json null`) spells `None` for such a field, so the none word works in the
environment and not on the CLI. This breaks
[cross-channel parity](../../architecture/invariants.md#cross-channel-parity). Merge output is
the same on all five front-ends.

The design pass has to settle which layer reads the word. The parser could read a lone
none-word run as `None` before it becomes a list, or construction could read a one-token list
under `X | None`. It also has to settle `list[str] | None`, where `--xs none` could mean
`['none']`. The environment already answers `None` there, because the single-variant union
reads the none word before the variant sees the value. Precedent *(inferred)*: jsonargparse
parses a flag's value as YAML, so `--xs null` sets an `Optional[List[int]]` to `None`.

```python
from dataclasses import dataclass

import confarg


@dataclass
class Config:
    xs: list[int] | None = None


print("env:", confarg.load(Config, argv=[], env={"APP_XS": "none"}, env_prefix="APP_"))
try:
    print("cli:", confarg.load(Config, argv=["--xs", "none"], env={}))
except confarg.exceptions.TypeCoercionError as e:
    print("cli:", e)

# expected: env: Config(xs=None)
#           cli: Config(xs=None)
# actual:   env: Config(xs=None)
#           cli: Cannot coerce str 'none' to int at 'xs[0]'
```
