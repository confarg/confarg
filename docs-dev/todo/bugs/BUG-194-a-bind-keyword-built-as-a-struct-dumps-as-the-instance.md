---
filed: 2026-10-07
where:
  - src/confarg/_callable.py::_serialize_callable  # the partial branch
effort: M
risk: low
impact: behavior
severity: minor  # dump_file() raises a raw TypeError; the merged dict saves the config
introduced_by: [PR-93]  # bind keywords started to be built with construct()
---
# BUG-194 — A `bind:` keyword built as a struct dumps as the instance, which no file format writes

A `bind:` partial dumps as `{bind: <target>, <keywords>}`, and the keywords are written as the
partial holds them. Since bound arguments go through typed construction
([one coercion route](../../architecture/callables.md#one-coercion-route)), a keyword annotated
with a dataclass holds an instance. `dump()` returns it inside the dict, and `dump_file()` fails
in the format writer. An `Enum` or `Path` keyword is written as its value, because the callable's
dump leaves through `_serialize_untyped`. A struct has no untyped rule. The fix is to serialize
each keyword against the target's parameter annotation, which is where construction read its
type (`_hints_source`), through the typed `_serialize`.

Origin: PR-93 replaced the scalar-only coercion of bind kwargs with full typed construction,
so that enums, dataclasses and unions work as bound arguments. The serializer kept writing
keywords raw, which had been safe while they were scalars. A regression from PR-93.

```python
from collections.abc import Callable
from dataclasses import dataclass

import confarg


@dataclass
class Db:
    host: str


def connect(db: Db) -> None: ...


@dataclass
class Config:
    f: Callable


cfg = confarg.from_dict(Config, {"f": {"bind": "__main__.connect", "db": {"host": "h"}}})
print(confarg.dump(cfg))
# expected: {'f': {'bind': '__main__.connect', 'db': {'host': 'h'}}}
# actual:   {'f': {'bind': '__main__.connect', 'db': Db(host='h')}}
```
