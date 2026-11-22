---
filed: 2026-11-12
where:
  - src/confarg/typedload/_construct.py::_build_items
  - src/confarg/typedload/_construct.py::_refuse_a_position_spelled_twice
effort: S
risk: low
impact: behavior  # a dict that builds today is refused
severity: minor  # a wrong result with no error, but only a direct build() caller can hold both spellings: every channel types a key as text
introduced_by: [PR-5]  # latent: the index comprehension {int(k): v} collapsed two spellings from the start; BUG-312 refused them for a fixed-length sequence and a dict only
---

# BUG-338 — A list keeps the last of two spellings of one index

`_build_items` reads a list's index keys into `{int(k): v}`, so `"0"` and `0` are one key and the later one's value wins, the other dropped with no error.
A fixed tuple or a namedtuple refuses the same dict (BUG-312, [one value holds each key once](../../architecture/pipeline/deep-merge.md#one-value-holds-each-key-once)): `_refuse_a_position_spelled_twice` files each key under its position and `_refuse_keys_read_as_one` raises.
Fix direction: ask the same refusal of a list's keys, after `_read_index_keys` (REF-94) has read them, so one rule holds on every sequence; the spellings are the keys read to one index, `"01"` and `"1"` too, since a list reads a key with `int()`.
Reachable only from a direct `build()` call: a YAML key is its text (`1:` is `"1"`), so no file, flag or variable holds two spellings of one index.

Origin: latent since PR-5, whose `int(k)` comprehension collapsed the spellings; BUG-312 added the refusal for a fixed-length sequence and a dict and did not reach the list.

```python
from dataclasses import dataclass

from confarg import build


@dataclass
class L:
    x: list[int]


@dataclass
class T:
    x: tuple[int, int]


print(build(L, {"x": {"0": 1, 0: 2}}))
try:
    print(build(T, {"x": {"0": 1, 0: 2}}))
except Exception as e:
    print(type(e).__name__, e)
# expected: the list refuses as the tuple does
# actual:
# L(x=[2])
# TypeCoercionError Cannot construct tuple[int, int] at 'x': keys '0' and 0 both name position 0
```
