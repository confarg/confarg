---
filed: 2026-10-14
where:
  - src/confarg/_merge.py::_merge_existing_value
effort: S
risk: low
impact: behavior
severity: minor  # an Any field holds the pin's keys as data with no error; a typed field fails loudly, naming them
introduced_by: [PR-50]  # the file-side pin {__cast__, __value__}; the merge already merged dict-on-dict
---
# BUG-239 — A cast pin below a dict is merged into it

A file's cast pin, `{__cast__: int, __value__: '5'}`, is a value, which construction resolves wherever it stands. A higher layer's dict over it should replace it, as a dict replaces the plain `5` a lower layer set. The merge reads a pin as a value only in the override (`_merge._replaces_what_lies_below`, BUG-210); in the base it is a dict, and a dict over it merges into it key by key. An `Any` field then holds the pin's two keys as data beside the higher layer's, and `int | dict[str, int]` refuses a dict holding them.

Origin: latent since PR-50, which introduced the file-side pin and let it reach a `_deep_merge` that merges any dict-on-dict *(inferred from the code; not reproduced at PR-50)*. BUG-210's fix taught the merge that a pin over a list or a dict replaces it, the override half, and left the pin below a dict to the dict-on-dict rule. Found settling BUG-232.

```python
import pathlib
import tempfile
from dataclasses import dataclass
from typing import Any

import confarg


@dataclass
class Config:
    extra: Any = None
    port: int | dict[str, int] = 0


d = pathlib.Path(tempfile.mkdtemp())
for lower in ("{__cast__: int, __value__: '5'}", "5"):
    for field, upper in (("extra", "{a: 1}"), ("port", "{https: 443}")):
        (d / "a.yaml").write_text(f"{field}: {lower}\n")
        (d / "b.yaml").write_text(f"{field}: {upper}\n")
        try:
            print(
                lower, field, getattr(confarg.load(Config, argv=[], env={}, files=[d / "a.yaml", d / "b.yaml"]), field)
            )
        except confarg.exceptions.ConfargError as e:
            print(lower, field, f"{type(e).__name__}: {e}")
# expected: the pin's two lines print what the plain 5's do
```

Actual output, from the revision that filed this:

```text
{__cast__: int, __value__: '5'} extra {'__cast__': 'int', '__value__': '5', 'a': 1}
{__cast__: int, __value__: '5'} port TypeCoercionError: Cannot coerce dict {'__cast__': 'int', '__value__': '5', 'https': 443} to int | dict at 'port'
5 extra {'a': 1}
5 port {'https': 443}
```
