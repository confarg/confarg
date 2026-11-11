---
filed: 2026-11-11
where:
  - src/confarg/_parse_env.py::_env_cast  # answers the `json` cast alone
  - src/confarg/_parse_cli.py::detect_force_cast  # the canonical "is the last segment a cast?"
effort: M  # the order `_env_order` gives a cast, the pin `_Pinned` it stores, and the namings scan
risk: medium  # every variable whose last segment spells str, int, float or bool
impact: behavior  # a refused variable starts pinning its value
severity: minor  # refused loudly; argv's `.str` and a file's `__cast__` pin the value
introduced_by: [PR-5]  # the initial version: `.str` on argv, no cast in the environment
---

# BUG-324 — The environment has no scalar cast

`--s.str 5` pins `5` as text at an `int | str` field, and `--v.str x` takes the `str` variant of a `str | Inner` field, but `APP_S__str=5` and `APP_V__str=x` are refused as naming no field: the environment reads a trailing `json` as a cast (`_parse_env._env_cast`) and no other.
The glossary promises `MYAPP_VALUE__STR=true`, and the cast note says `_cast.py` makes vanilla, the adapters and the environment produce byte-identical results ([force casts](../../architecture/cli-parsing/casts-and-reserved-words.md#force-casts)).
Fix direction: `_env_cast` asks `detect_force_cast` of every cast name, as the flag does, and stores `resolve_forced_value`'s `_Pinned`, so a variable and a flag of one path admit and pin the same casts ([cross-channel parity](../../architecture/invariants.md#cross-channel-parity)).

Origin: latent since the initial version (PR-5), whose CLI read `--foo.str VALUE` as a plain string and whose environment parser read no cast at all; the environment later gained the `json` cast alone (*inferred*, from `_env_cast` answering only `JSON_CAST_NAME`).

```python
from dataclasses import dataclass

import confarg
from confarg.exceptions import ConfargError


@dataclass
class Inner:
    a: int = 0


@dataclass
class C:
    s: int | str = 0
    v: str | Inner = ""


for argv, env in ((["--s.str", "5"], {}), ([], {"APP_S__str": "5"}), (["--v.str", "x"], {}), ([], {"APP_V__str": "x"})):
    try:
        print(confarg.load(C, argv=argv, env=env, env_prefix="APP_"))
    except ConfargError as e:
        print(f"{type(e).__name__}: {e}")
# expected: C(s='5', v='')
#           C(s='5', v='')
#           C(s=0, v='x')
#           C(s=0, v='x')
# actual:   C(s='5', v='')
#           ConfargError: Environment variable 'APP_S__str' has no matching field (field 's.str' not found).
#           C(s=0, v='x')
#           ConfargError: Environment variable 'APP_V__str' has no matching field (field 'v.str' not found).
```
