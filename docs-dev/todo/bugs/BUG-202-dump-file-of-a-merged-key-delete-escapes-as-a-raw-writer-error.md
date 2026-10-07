---
filed: 2026-10-07
where:
  - src/confarg/_serialize.py::_serialize_untyped
effort: S
risk: low
impact: behavior
severity: major  # a raw writer exception, and no spelling of the dict that dumps
introduced_by: [PR-5]  # dump_file took a raw merged dict, and the merge left its key delete in it
---
# BUG-202 — `dump_file` of a merged key delete escapes as a raw writer error

A dict-key delete with no base dict below it stays in the merged dict as `DICT_DELETE`
([BUG-98](BUG-98-a-dict-key-delete-with-no-base-dict-leaks-the-delete-sentinel.md) is what
`build()` makes of it). `dump_file(merge(...))` hands that sentinel to the writer, which raises
its own exception: PyYAML's `RepresenterError`, `json`'s `TypeError`. A file spells the same
delete as `key-:`, so the dump has a spelling to write, as it writes a list op the merged dict
still holds by the reserved key a file writes it with
([deep merge](../../architecture/pipeline/deep-merge.md#no-channel-types-an-op)). Fix direction:
`_serialize_untyped` writes a key holding `DICT_DELETE` as `key-`, so the dump reads back through
`merge(files=[saved])` as the dict it was.

Origin: latent since the initial version (PR-5), whose `dump_file` accepted a raw merged dict and
whose merge leaves a key delete with nothing to delete in it, the leak BUG-98 is about. BUG-10's
fix (PR-126) gave raw dicts a serializer of their own, `_serialize_untyped`, for coerced leaves
only. It reproduces unchanged at PR-28, the oldest revision the reproduction runs on.

```python
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import confarg


@dataclass
class D:
    data: dict[str, int] = field(default_factory=dict)


raw = confarg.merge(D, argv=["--data.x-"], env={})
print("merged:", raw)
for name in ("out.yaml", "out.json"):
    try:
        confarg.dump_file(raw, Path(tempfile.mkdtemp()) / name)
    except Exception as e:
        print(name, "->", type(e).__name__, e)

# expected: both dumps written, the delete as `x-`, reading back as the merged dict
# actual:
#   merged: {'data': {'x': _DELETE_}}
#   out.yaml -> RepresenterError ('cannot represent an object', _DELETE_)
#   out.json -> TypeError Object of type _DeleteSentinel is not JSON serializable
```
