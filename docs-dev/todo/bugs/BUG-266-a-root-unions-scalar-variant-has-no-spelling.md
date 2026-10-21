---
filed: 2026-10-21
where:
  - src/confarg/_types.py::_is_struct_like  # a union with one struct variant is struct-like whole
  - src/confarg/_parse_cli.py::_parse_cli  # the bare-prefix refusal on a struct-like root
  - src/confarg/_parse_cli.py::_handle_root_cast  # a structured target's cast must be an object
  - src/confarg/_parse_env.py::_parse_env
  - src/confarg/_parse_env.py::_apply_env_json_cast
effort: M
risk: medium  # the root's classification is read by every channel and the adapters' registration
impact: behavior
severity: minor  # refused loudly; a dataclass field holding the union is the workaround
needs_design: true  # which spelling sets a mixed root, and whether a struct variant's fields stay patchable beside it
introduced_by: [PR-5]  # the initial version classifies a union with any struct variant as struct-like
---

# BUG-266 — A root union's scalar variant has no spelling in any channel

A union with at least one struct variant is struct-like (`_is_struct_like`), so as a root, `int | A`, it is patched one field at a time, and nothing sets its `int` variant.
The bare `--app 5` and `APP_=5` are refused as the bare prefix on a struct-like root, the root cast `--app.json 5` and `APP_JSON=5` are refused because a structured target's cast must be a JSON object, and a root configuration file must be a mapping.
The same union as a field takes either variant (`--x 5`, `--x.a 3`).
Fix direction: a design question first: whether the bare prefix and the root cast set a mixed root whole, as they do a non-struct one, while its struct variants' fields stay addressable, and how a value set whole meets a field flag beside it ([cli_prefix](../../architecture/cli-parsing/cli-prefix.md#cli_prefix), [a non-struct root is set whole](../../architecture/cli-parsing/cli-prefix.md#a-non-struct-root-is-set-whole)).
If the answer is that it stays unspelled, the case belongs in [limitations.md](../../architecture/limitations.md), beside the registered leaf root.

Origin: latent since the initial version (PR-5), whose `_is_struct_like` already counted a union with any struct variant as struct-like, and whose CLI loop wrote the bare flag's value at the empty path, where it was dropped: `--app 5` built `A(a=0)` without a word.
BUG-91 turned that drop into the refusal, which is right about the struct variant and leaves the scalar one with no spelling at all.

```python
from dataclasses import dataclass

import confarg


@dataclass
class A:
    a: int = 0


for kw in (
    {"argv": ["--app", "5"], "cli_prefix": "app"},
    {"argv": ["--app.json", "5"], "cli_prefix": "app"},
    {"env": {"APP_JSON": "5"}, "env_prefix": "APP_"},
):
    try:
        print(confarg.load(int | A, **{"argv": [], "env": {}, **kw}))
    except Exception as e:
        print(type(e).__name__, e)

# expected: 5, from at least one spelling
# actual:
#   UnknownArgumentError Unknown argument: '--app'. The bare --app flag carries a value only for a scalar root, and the root has fields; set one of them (--app.<field>) instead.
#   ConfargError --app.json for a structured target must be a JSON object, got int.
#   ConfargError APP_JSON for a structured target must be a JSON object, got int.
```
