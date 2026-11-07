---
filed: 2026-11-07
where:
  - src/confarg/typedload/_construct.py::_construct_dict  # builds the dict by a comprehension over the coerced keys, the last one winning
  - src/confarg/typedload/_construct.py::read_key
needs_design: true
effort: M  # the design pass: refuse, warn, or keep the last as pydantic does
risk: high  # every typed dict's construction, on every channel
impact: behavior  # a dict that built with one entry dropped is refused, or warns
severity: critical  # a configured value is dropped with no error
introduced_by: [PR-5]  # the initial version, which built a typed dict from its coerced keys
---

# BUG-312 — Construction drops a dict key another key of the same dict reads as

A typed dict whose data holds two keys its key type reads as one builds with one of them silently dropped, the last in the data's order winning: `{'0': 'text', 0: 'int'}` under `dict[int, str]` builds `{0: 'int'}`, `{'1': …, '1.0': …}` under `dict[float, str]` and `{'RED': …, 'red': …}` under `dict[Color, str]` likewise.
The merge already treats such keys as one between layers and within the CLI's and the environment's writers ([which keys are one key](../../architecture/pipeline/deep-merge.md#which-keys-are-one-key)), so they collide only within one value handed whole: a caller's dict, or a YAML mapping spelling `0:` beside `!!int 0:`.
A `default_factory` such as `{0: …}` laid below a flag's `--m.0` once FEAT-38 lands goes through the merge's combiner too, which would meet the two keys as one *(inferred: the default layer lays defaults through the merge's combiner)*.
Nothing says a value was dropped, though a reference to that entry refuses the dict as ambiguous (BUG-311, [spelling a path](../../architecture/expressions/values-and-references.md#spelling-a-path)).

Fix direction, for the design pass: refuse a dict two of whose keys `read_key` reads as one key, naming both spellings (OmegaConf refuses `'0'` beside `0` when the configuration is created), warn and keep the last, or keep the last silently, as pydantic v2 and cattrs do (`{0: 'int'}`, `{1.0: 'float'}`).

Origin: latent since PR-5, the initial version, whose `_construct_dict` built the dict by a comprehension over the coerced keys; BUG-244 made the merge read such keys as one key between layers and within a source's writers, which left the value handed whole as the one place two of them meet.

```python
import enum
from dataclasses import dataclass, field

import confarg


class Color(enum.Enum):
    RED = "red"


@dataclass
class C:
    i: dict[int, str] = field(default_factory=dict)
    f: dict[float, str] = field(default_factory=dict)
    e: dict[Color, str] = field(default_factory=dict)


print(
    confarg.build(
        C, {"i": {"0": "text", 0: "int"}, "f": {"1": "text", "1.0": "float"}, "e": {"RED": "name", "red": "value"}}
    )
)
# expected: a ConfargError naming both spellings of each key (or a warning that one was dropped)
# actual:   C(i={0: 'int'}, f={1.0: 'float'}, e={<Color.RED: 'red'>: 'value'})
```
