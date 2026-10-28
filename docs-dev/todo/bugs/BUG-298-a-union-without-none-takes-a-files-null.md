---
filed: 2026-10-28
where:
  - src/confarg/typedload/_construct.py::_construct_union  # returns None for any None, its guard dropped
effort: S
risk: medium  # the fix makes a refusal louder; an Any variant must still take the None through the leaf rung
impact: config  # a file holding null for such a field stops loading
severity: critical  # a file's null loads into a field whose annotation holds no None, with no error
introduced_by: [PR-11]  # refactor: Refactor internals and improve documentation (#11)
---

# BUG-298 — A union without `None` takes a file's `null`

A field typed by a union that lists no `None` builds `None` from a native `None`, a file's `null`, a YAML key left empty or a `from_dict()` value, where the same field typed by one of its variants refuses it: `a: int | str` holds `None`, `b: str` gets `Cannot coerce NoneType None to str`.
A token is unaffected, since a none word reaches `int | str` as the text `'none'`.

`construct()` takes a `None` itself only where `_allows_none` says the type holds one; any other `None` reaches `_construct_union`, whose first test returns it for any union, under a `# pragma: no cover` that calls the branch unreachable.

Fix direction: drop the branch, so a `None` meets the union's variants as any value does; an `Any` variant still takes it, as the leaf rung's last step (`int | Any` holding `None` is right).
Found designing [FEAT-59](../features/FEAT-59-a-protocol-scalars-satisfy-reads-as-their-union.md), whose `ratio: SupportsFloat` would read as `int | float | bool` and take a file's `null` the same way.

Origin: a regression from PR-11, a refactor of the internals.
Before it, the branch read `if data is None and type(None) in all_args:  # pragma: no cover`, the guard keeping it to the unions `construct()` had already short-circuited; PR-11 rewrote it as `if data is None:` with the comment `construct() short-circuits before reaching here`, which holds only for a union holding `None`.

```python
from dataclasses import dataclass

import confarg
import confarg.exceptions


@dataclass
class C:
    a: int | str = 0
    b: str = ""


for data in ({"a": None}, {"b": None}):
    try:
        print(data, "->", confarg.from_dict(C, data))
    except confarg.exceptions.ConfargError as e:
        print(data, "->", type(e).__name__, e)

# expected: both refused, since neither annotation holds None
# actual:   {'a': None} -> C(a=None, b='')
#           {'b': None} -> TypeCoercionError Cannot coerce NoneType None to str at 'b'
```
