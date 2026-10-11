---
filed: 2026-10-05
where:
  - src/confarg/_parse_cli.py::_is_dict_at_path
effort: S
risk: high
impact: behavior
---
# BUG-158 — A path below a union-typed dict field is refused on the CLI

A path no branch of the walk accepts is still a key when a dict lies above it, and
`_is_dict_at_path` decides that on the fold of what the branches reach at each prefix, as
`_resolve_field_type` of the prefix would answer. A field typed `dict[str, Any] | None` or
`dict[str, Any] | Inner` reaches the union there, unexpanded, so the dict variant is never seen:
`--opt.a.b 1` is an unknown argument where the plain `dict[str, Any]` field takes `--plain.a.b 1`
as a key, and the environment takes `APP_OPT__A__B=1` for the union too. Fix direction: decide
what a prefix the branches disagree on lands on. Reading the nodes the branches stand on
("does any branch stand on a dict above the path?") accepts the key wherever one variant is a
dict. See [one walk, many questions](../../architecture/cli-parsing/type-guided-parsing.md#one-walk-many-questions)
and [type-guided parsing](../../architecture/cli-parsing/type-guided-parsing.md#type-guided-parsing).

```python
from dataclasses import dataclass, field
from typing import Any

import confarg


@dataclass
class Inner:
    q: int = 0


@dataclass
class Cfg:
    plain: dict[str, Any] = field(default_factory=dict)
    opt: dict[str, Any] | None = None
    either: dict[str, Any] | Inner = field(default_factory=dict)


for name in ("plain", "opt", "either"):
    argv = [f"--{name}.a.b", "1"]
    try:
        print(f"{name:6}:", confarg.merge(Cfg, argv=argv, env={}, config_flag=""))
    except confarg.exceptions.ConfargError as e:
        print(f"{name:6}:", type(e).__name__, e)
    env = {f"APP_{name.upper()}__A__B": "1"}
    print(f"{name:6} (env):", confarg.merge(Cfg, argv=[], env=env, env_prefix="APP_", config_flag=""))

# expected: the CLI accepts `opt.a.b` and `either.a.b` as keys, as it does `plain.a.b` and as the
# environment does
# actual:
#   plain : {'plain': {'a': {'b': '1'}}}
#   plain  (env): {'plain': {'a': {'b': '1'}}}
#   opt   : UnknownArgumentError Unknown argument: '--opt.a.b' (field 'opt.a.b' not found)
#   opt    (env): {'opt': {'a': {'b': '1'}}}
#   either: UnknownArgumentError Unknown argument: '--either.a.b' (field 'either.a.b' not found)
#   either (env): {'either': {'a': {'b': '1'}}}
# argparse, click, typer and cyclopts refuse `--opt.a.b` and `--either.a.b` the same way.
```
