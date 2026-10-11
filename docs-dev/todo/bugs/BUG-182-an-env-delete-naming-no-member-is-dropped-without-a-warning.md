---
filed: 2026-10-06
where:
  - src/confarg/_parse_env.py::_parse_env  # the delete branch, which `continue`s before the unknown-field check
  - src/confarg/_parse_env.py::_handle_env_delete
effort: S
risk: low
impact: behavior
severity: critical  # a mistyped delete is dropped with no warning, where a mistyped value warns
introduced_by: [PR-5]  # the initial version's delete branch, ahead of the unknown-field warning
---
# BUG-182 — An env delete naming no member is dropped without a warning

A variable whose first segment names no member is warned about and ignored
([environment-parsing.md](../../architecture/environment-parsing.md#environment-parsing)), but
a delete skips that check. So `APP_NAEM-` (a typo for `APP_NAME-`) stores a delete under a key
no field has, and the merge drops it without a word, while `APP_NAEM=y` warns and the CLI
refuses `--naem-`. The same holds on a non-struct root: `APP_DEBUG-` beside an `int` root
says nothing. Fix direction: put the delete through the same first-segment check as every
other variable, `_warn_unknown_env_field` asked of the resolved delete path, so the check
sits in one place for every kind of variable. That check is `_parse_cli._path_unknown`
against the walk target, the question the CLI's delete handler already asks.

Origin: latent since the initial version (PR-5). Its `_parse_env` handled a delete in a branch of
its own that ended in `continue` before the loop reached the unknown-field warning, so the
warning only ever applied to value variables. BUG-90 changed the warning's predicate and passed the
union tag to `_handle_env_delete`, and BUG-115 moved the check onto the walk target; neither moved it
ahead of the delete branch. The reproduction gives the same output at PR-5 and at every revision
since that touched the delete branch or the warning.

```python
import warnings
from dataclasses import dataclass

import confarg

warnings.simplefilter("always")


@dataclass
class Cfg:
    name: str = "x"


for env in ({"APP_NAEM": "y"}, {"APP_NAEM-": ""}):
    with warnings.catch_warnings(record=True) as caught:
        print(env, "->", confarg.merge(Cfg, argv=[], env=env, env_prefix="APP_"), [str(w.message) for w in caught])
try:
    confarg.merge(Cfg, argv=["--naem-"])
except Exception as e:
    print(type(e).__name__, e)

# expected: the delete warned about as the value is
# actual:
#   {'APP_NAEM': 'y'} -> {} ["Environment variable 'APP_NAEM' has no matching field (segment 'naem' not found in Cfg). Known fields: ['name']. The variable will be ignored."]
#   {'APP_NAEM-': ''} -> {} []
#   UnknownArgumentError Unknown argument: '--naem-' (field 'naem' not found)
```
