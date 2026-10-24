---
filed: 2026-10-17
where:
  - src/confarg/_types.py::_is_plain_class
  - src/confarg/_types.py::_is_dict
effort: M
needs_design: true  # bare and parameterized subclasses, defaultdict's factory, Counter's counts
risk: high
impact: config  # --d.kwargs.a stops working, d: {a: 1} starts
severity: major  # a valid mapping is refused, parameterized or not; only annotating plain dict works
introduced_by: [PR-5]  # _is_plain_class excluded the builtins module, not the classes subclassing a builtin
---

# BUG-253 — A dict subclass reads as a struct of its constructor's parameters

A field annotated with a `dict` subclass of the standard library, `collections.OrderedDict` or `collections.Counter`, is no mapping to confarg: the bare class is a plain class, a struct of its constructor's parameters (`args` and `kwargs` for `OrderedDict`, `iterable` and `kwds` for `Counter`), and the parameterized `OrderedDict[str, int]` an unsupported leaf.
So a file's `d: {a: 1}` is refused, and `--d.kwargs.a 1` is the only spelling that builds, untyped.
`_is_plain_class` excludes the `builtins` module and a few bases (`Enum`, `PurePath`, `tuple`), not a subclass of `dict`, `list` or `set` defined elsewhere.
Fix direction: read a subclass of a builtin collection as that collection, built as the subclass, which needs a design for `defaultdict` (its factory is no item) and `Counter` (its values are counts).
Precedents: pydantic validates `OrderedDict[str, int]` and `Counter[str]` as mappings and builds the subclass; msgspec refuses them.
Found while settling [the signature a struct is read by](../../architecture/design-decisions/a-structs-members-are-its-constructors-parameters.md#which-signature-is-read).

Origin: latent since the initial version (PR-5), whose plain-class test excluded the builtins by module name.

```python
import collections
from dataclasses import dataclass, field

import confarg


@dataclass
class Config:
    d: collections.OrderedDict = field(default_factory=collections.OrderedDict)
    c: collections.Counter = field(default_factory=collections.Counter)


for label, run in (
    ("--d.a 1", lambda: confarg.load(Config, argv=["--d.a", "1"], env={})),
    ("--d.kwargs.a 1", lambda: confarg.load(Config, argv=["--d.kwargs.a", "1"], env={})),
    ("file d: {a: 1}", lambda: confarg.build(Config, {"d": {"a": 1}})),
    ("file c: {a: 2}", lambda: confarg.build(Config, {"c": {"a": 2}})),
):
    try:
        print(label, "->", run())
    except Exception as e:
        print(label, "->", f"{type(e).__name__}: {e}")

# expected: d holds OrderedDict({'a': 1}) and c Counter({'a': 2}), from every channel
# actual:
#   --d.a 1 -> UnknownArgumentError: Unknown argument: '--d.a' (field 'd.a' not found)
#   --d.kwargs.a 1 -> Config(d=OrderedDict({'a': '1'}), c=Counter())
#   file d: {a: 1} -> TypeCoercionError: Unknown field(s) ['a'] for OrderedDict at 'd'. Valid fields: ['args', 'kwargs']
#   file c: {a: 2} -> TypeCoercionError: Unknown field(s) ['a'] for Counter at 'c'. Valid fields: ['iterable', 'kwds']
```
