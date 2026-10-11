---
filed: 2026-10-08
where:
  - src/confarg/typedload/_construct.py::_resolve_tuple_partial  # the tolerated stray that spells a reserved key
effort: S
risk: low
impact: none
severity: minor  # out-of-contract input answered one of two ways; no channel can produce it
introduced_by: [FEAT-3]  # the markers-no-channel-types revision; it also closed BUG-199 and BUG-175
---
# BUG-209 — A plain-string list-op key in `build()` data is skipped against a default and refused without one

`build()` takes the merge's output, whose list ops are `_OpKey` markers, and a marker equals only
another marker — so a plain-string `'__base__'` in data handed to `build()` directly is a data key,
never the op
([deep-merge](../../architecture/pipeline/deep-merge.md#no-channel-types-an-op)). On a defaulted
sequence field that key reaches `_resolve_tuple_partial`, whose `tolerate_non_int` skips it as a
stray while patching the default: the base the user spelled never enters, and the refusal
misleads. The same data on the field without a default is refused as the non-integer patch key it
is. No supported channel can produce the plain string — a file's `__base__` is normalized to the
marker at merge, and the CLI, the environment and the mount check refuse the reserved segment — so
only a direct `build()` call meets this. Fix direction: make the stray-skipping refuse a key that
spells a reserved list op (`_defaults.RESERVED_KEYS`), or normalize the reserved spellings in
`build()`, so both spellings meet one rule.

Origin: regression from FEAT-3's markers, which made a plain string unequal to the op key and
renamed the base key from `*` to `__base__`. Before it, the reserved spelling was a plain string
construction read as the base, with a default and without one alike; after it only the marker is,
and the defaulted path's stray-skipping silently drops the key.

```python
from dataclasses import dataclass, field

import confarg


@dataclass
class WithDefault:
    u: tuple[int, int] = field(default_factory=tuple)


@dataclass
class WithoutDefault:
    u: tuple[int, int]


data = {"u": {"__base__": [1, 2], "z": 5}}
confarg.build(WithDefault, data)
confarg.build(WithoutDefault, data)

# expected: the same refusal from both targets, naming the key it cannot place
# actual, WithDefault:    TypeCoercionError: Cannot construct tuple[int, int] at 'u': expected 2 elements, got 0
# actual, WithoutDefault: TypeCoercionError: Cannot construct tuple[int, int] at 'u': dict keys must be integer indices
```
