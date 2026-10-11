---
filed: 2026-10-01
where:
  - src/confarg/_parse_env.py::_parse_env  # the `if not is_struct:` branch
effort: S
risk: low
impact: behavior
severity: critical  # an unrelated variable silently replaces the root
introduced_by: [PR-5]  # the initial version's `if not is_struct:` branch in _parse_env
---
# BUG-115 — Every prefixed environment variable overwrites a scalar root

On a non-struct target, `_parse_env` writes every variable under the prefix to `__root__`,
whatever follows the prefix. So `MYAPP_DEBUG` or `MYAPP_HOME` silently replaces the root
value, and when several are set the mapping's iteration order picks the winner. The CLI
refuses the same sub-path (`--app.debug` → `UnknownArgumentError`), and a struct root warns
about an unknown segment and ignores the variable
([environment-parsing.md](../../architecture/environment-parsing.md#environment-parsing)).
Fix direction: only the bare `<PREFIX>` (and the `<PREFIX>JSON` cast, already handled before
this branch) should address a scalar root; anything else goes through the same unknown-field
warning, so no channel gets a rule of its own. Found while closing REF-44.
The CLI side is settled: a non-struct root is
[set whole](../../architecture/cli-parsing/cli-prefix.md#a-non-struct-root-is-set-whole), and
no flag addresses a path below it (BUG-172).

Origin: latent since the initial version (PR-5), whose `_parse_env` stored every prefixed variable
at the root of a non-struct target without reading the rest of its name. It has not changed since;
REF-44 made the root's JSON cast order-independent beside it, and BUG-172 settled the CLI side, both
without narrowing this branch.

```python
import warnings

import confarg

warnings.simplefilter("always")
print(confarg.merge(int, argv=[], env={"MYAPP_": "3", "MYAPP_DEBUG": "1"}, env_prefix="MYAPP_"))
# expected: {'__root__': 3} and a ConfargWarning naming MYAPP_DEBUG
# actual:   {'__root__': 1}, no warning
print(confarg.merge(int, argv=["--app.debug", "1"], env={}, cli_prefix="app"))
# the CLI refuses the same sub-path:
# confarg.exceptions.UnknownArgumentError: Unknown argument: '--app.debug' (field 'debug' not found)
```
