---
filed: 2026-10-08
where:
  - src/confarg/typedload/_construct.py::_resolve_tuple_partial  # whose gate in _constructStruct reads a defaulted field's dict as an index patch
effort: S
risk: low
impact: behavior
severity: critical  # a file's pinned value loads as the default, no error; the pinned spelling under a fixed sequence is a corner, but the rungs score the symptom
introduced_by: [PR-50]  # the pin spelling's own revision; the gate and its non-integer skip predate it (PR-11, respelled as tolerate_non_int by BUG-80)
---
# BUG-210 — A pinned cast at a defaulted fixed-sequence field is silently dropped, its default built

A file may pin a value with `{__cast__: <type>, __value__: <raw>}`
([cast pinning](../../architecture/types/stealing-rule.md#cast-pinning-in-files)), and
`construct()` honors the pin before dispatching on the field's type. But `_constructStruct`'s
gate reads a dict at a defaulted fixed-sequence field (a fixed tuple, or a union's only
sequence variant) as an index patch and hands it to `_resolve_tuple_partial`, whose
stray-skipping drops the pin's two keys and builds the default instead — the file's value
never enters, with no error. Without the default the same file is honored, so the pin is read
one of two ways by whether the field happens to carry a default. BUG-209's fix refuses a
reserved list-op spelling in that skipping; the pin pair stays tolerated there, which is what
leaves this path open. Fix direction: exempt a pin dict from the gate, so both paths read it
alike.

Origin: latent since PR-50, which introduced the `{__cast__, __value__}` spelling into a gate
that already read a defaulted fixed-tuple field's dict as an index patch and skipped its
non-integer keys (`except ValueError: pass`); the gate and the skip predate the pin (PR-11),
and BUG-80's fix respelled the skip as `tolerate_non_int` without changing what it drops.

```python
# pin.yaml:
#   u:
#     __cast__: int
#     __value__: 5
from dataclasses import dataclass
import confarg


@dataclass
class WithDefault:
    u: tuple[int, int] = (0, 0)


@dataclass
class WithoutDefault:
    u: tuple[int, int]


print(confarg.load(WithDefault, files=["pin.yaml"], env={}, argv=[]))
print(confarg.load(WithoutDefault, files=["pin.yaml"], env={}, argv=[]))

# expected: the pin read one way from both targets — honored alike, or refused alike
# actual:   WithDefault(u=(0, 0))    # the file's pin silently dropped, the default built
# actual:   WithoutDefault(u=5)      # the pin honored, its coerced value never meeting the field's type
```

The second actual line is context, not the defect: a pin's coerced value never meets the
field's type — that is the escape hatch's design — but a fix here should decide whether the
honored side of a fixed-sequence field keeps that freedom.
