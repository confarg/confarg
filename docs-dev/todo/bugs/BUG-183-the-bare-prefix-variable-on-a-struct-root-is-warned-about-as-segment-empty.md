---
filed: 2026-10-06
where:
  - src/confarg/_parse_env.py::_warn_unknown_env_field
effort: S
risk: low
impact: none
severity: minor  # a misleading warning; the variable is ignored as it should be
introduced_by: [PR-5]  # the initial version's warning formats the empty first segment like any other
---
# BUG-183 — The bare prefix variable on a struct root is warned about as segment ''

On a struct root the bare `<PREFIX>` variable addresses nothing, and is warned about and
ignored, but the warning reads as a field lookup that failed: "segment '' not found in Cfg".
The CLI says what went wrong for the same mistake: the bare `--<prefix>` flag carries a value
only for a scalar root, so address a field instead (`bare_prefix_on_struct_root`). Fix
direction: the environment's warning names the same cause, for an empty first segment on a
struct-like root
([cli-prefix.md](../../architecture/cli-parsing/cli-prefix.md#cli_prefix)).

Origin: latent since the initial version (PR-5), whose unknown-field warning formatted whatever
the first segment was, the empty one included. BUG-91 later gave the CLI its own error for the
bare flag on a struct-like root, which until then dropped its value without a word; its change
touched `_parse_cli.py` and `exceptions.py` only, so the environment's warning stayed as it was.
The environment half of the reproduction gives the same output at PR-5 and at every revision since.

```python
import warnings
from dataclasses import dataclass

import confarg

warnings.simplefilter("always")


@dataclass
class Cfg:
    port: int = 0


with warnings.catch_warnings(record=True) as caught:
    confarg.merge(Cfg, argv=[], env={"APP_": "8080"}, env_prefix="APP_")
print(caught[0].message)
try:
    confarg.merge(Cfg, argv=["--app", "8080"], cli_prefix="app")
except Exception as e:
    print(type(e).__name__, e)

# expected: the warning says the bare variable sets only a scalar root, as the CLI's error does
# actual:
#   Environment variable 'APP_' has no matching field (segment '' not found in Cfg). Known fields: ['port']. The variable will be ignored.
#   UnknownArgumentError Unknown argument: '--app'. The bare --app flag carries a value only for a scalar root; this target is structured. Address one of its fields (--app.<field>) instead.
```
