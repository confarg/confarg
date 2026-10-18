---
filed: 2026-10-13
where:
  - src/confarg/typedload/_construct.py::_construct_typed
  - src/confarg/typedload/_construct.py::_takes_typed_call
  - src/confarg/typedload/_construct.py::_construct_union_by_tag
  - src/confarg/typedload/_coerce.py::_held_by_any
  - src/confarg/_serialize.py::_serialize_by_type
  - src/confarg/_serialize.py::_serialize_union
  - src/confarg/_parse_cli.py::_advance_field_type
  - src/confarg/cli/_build.py
  - docs-dev/architecture/design-decisions/call-yields-to-the-data-a-type-holds.md
  - docs-dev/architecture/limitations.md
effort: L  # crosses every channel and front-end, and reverses a recorded decision
risk: high  # the coercion rules and the CLI walk; a mistake is silent everywhere at once
impact: config  # a `class` or `call` key in data an `Any` field holds starts meaning a spec
severity: major  # a struct default on an `Any` field makes load-then-dump_file fail with a raw writer error
---
# FEAT-42 — An `Any` field reads callable specs and dumps an object as the spec that rebuilds it

An `Any` field keeps a `class:` or `call:` dict as data, so no configuration can put an object in it: only Python code can, through a field default, a dict passed to `from_dict()` or an object built by hand. And `dump()` writes such an object untouched, so `dump_file` fails on it with the writer's own error, even after a plain `load()` with nothing supplied.

Settled with the maintainer (2026-10-13):

- **All four openers** — `class`, `classfn`, `bind`, `call` — work on `Any`, as on a Callable field, through `_callable._spec_parts`. `class:` names any importable class. A bare dotted string stays a string: the shorthand applies only where the type asks for a callable.
- **At every depth.** A dict an `Any` holds is `dict[Any, Any]` and a list is `list[Any]` (BUG-187's reading of the bare forms), so every nested value is an `Any` node and reads a spec.
- **A tag that names no class is an error**, on a bare `Any` as beside other variants: in `X | Any`, a tag naming no variant is the `Any` variant's spec, and one that does not import is refused.
- **Every channel and front-end.** `--x.class pkg.S --x.a 1`, `--x.call pkg.f --x.args.p 1`, their environment spellings, and the adapters' registration of the named class's fields when argv names it.
- **Dump by runtime type, with the opener, when it reads back.** A struct is written `{class: <path>, <fields>}`, a callable as the spec a Callable field dumps, a container recursed as `Any`, a leaf through `_serialize_leaf`. That form is kept only if `_serialize._reads_back` confirms it; otherwise the value is written untyped (`_serialize_untyped`) with a `ConfargWarning`.

The decision [a call spec yields to data the annotation can hold](../../architecture/design-decisions/call-yields-to-the-data-a-type-holds.md) loses `Any` from its yield list (a dict type and a member named `call` still keep the key). A new boundary goes into [limitations](../../architecture/limitations.md): any `Any` slot lets a file, a variable or a flag instantiate any importable class. Precedent: Hydra reads `_target_` in any node, though it builds only on an explicit `instantiate()` call.

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import confarg


@dataclass
class S:
    a: int = 0


@dataclass
class C:
    x: Any = field(default_factory=lambda: [Path("p")])
    y: Any = field(default_factory=lambda: S(1))


print(confarg.dump(confarg.load(C, argv=[], env={})))
print(confarg.from_dict(C, {"y": {"class": "__main__.S", "a": 2}}).y)

# today:  {'x': [WindowsPath('p')], 'y': S(a=1)}
#         {'class': '__main__.S', 'a': 2}
# wanted: {'x': ['p'], 'y': {'class': '__main__.S', 'a': 1}}
#         S(a=2)
```
