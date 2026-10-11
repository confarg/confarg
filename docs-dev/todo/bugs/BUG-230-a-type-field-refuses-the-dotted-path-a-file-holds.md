---
filed: 2026-10-11
where:
  - src/confarg/typedload/_coerce.py::_coerce_type_ref
effort: S
risk: medium
impact: behavior
severity: major  # a file can set no type[X] field, and no cast spells one; only argv and the environment can
needs_design: true  # how a file's plain string meets a str variant in `type | str`
introduced_by: [PR-5]  # the initial version coerces a type reference from a token only
---
# BUG-230 — A `type[X]` field refuses the dotted path a file holds, so its own dump does not load

`_coerce_type_ref` imports a class only from a `_StrToken`, the text of argv or the environment.
A plain string, which is what a file and `from_dict()` hold, is refused, so a `type` or `type[X]`
field cannot be set from a file at all, and the dotted path `dump()` writes for it
([the object dump writes state](../../architecture/design-decisions/the-object-dump-writes-state.md#the-object-dump-writes-state))
does not load back
([dump round-trips at the built object](../../architecture/design-decisions/dump-round-trips-at-the-built-object.md#dump-round-trips-at-the-built-object)).
A Callable field takes the same string from a file, and BUG-32 made a `Literal` over an `Enum` read
the value `dump()` writes for the same reason.

The design question is the union: native file values keep declaration order
([stealing rule](../../architecture/types/stealing-rule.md#stealing-rule)), so in `type | str` a
file's `"builtins.int"` would have to stay a string, or the order decides which variant reads it.

Origin: the initial version coerced a type reference only from a token, and treated any other
value as the wrong type. Latent since then: every test that reads a `type[X]` back goes through a
token (`test_dump_and_build_roundtrip` wraps the dump in `_StrToken` by hand).

```python
import pathlib
import tempfile
from dataclasses import dataclass

import confarg


@dataclass
class Config:
    t: type


path = pathlib.Path(tempfile.mkdtemp()) / "config.json"
confarg.dump_file(Config(t=int), path)
print(path.read_text())
# {"t": "builtins.int"}
print(confarg.load(Config, argv=["--t", "builtins.int"], env={}))
# Config(t=<class 'int'>)
print(confarg.load(Config, argv=[], env={}, files=[path]))
# expected: Config(t=<class 'int'>)
# actual:   confarg.exceptions.TypeCoercionError: Cannot coerce str 'builtins.int' to type at 't'
```
