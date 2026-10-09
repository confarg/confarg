---
filed: 2026-10-03
where:
  - src/confarg/typedload/_construct.py::_is_index_key
effort: S
risk: medium
impact: config
severity: minor  # the odd spellings build the right position
introduced_by: [PR-39, BUG-97]  # PR-39 wrote the isdigit() test; PR-268, which closed BUG-97, narrowed the CLI alone
---
# BUG-142 — A namedtuple built from a dict accepts index keys the CLI refuses

BUG-97 limited a namedtuple position on the CLI to its two canonical spellings, `str(i)` and
`str(i - n)` (`_parse_cli._namedtuple_index_spellings`). Construction decides with its own
predicate, `_is_index_key`, which asks `str.isdigit()`, so a config file (or anything `build()`
receives) still addresses a position as `01`, `-0` or `١` (an Arabic-Indic digit), all of which
`--pt.<key>` refuses. That breaks
[cross-channel parity](../../architecture/invariants.md#cross-channel-parity). `isdigit()` also
admits `²`, which `int()` then rejects, so that key gets the misleading
`dict keys must be integer indices`. The expressions draw the same line since BUG-133
(`dictexpr._expressions._list_index`), and BUG-108 tracks the CLI's plain fixed tuple. Fix
direction: one canonical index rule, `str(int(k)) == k` within the field count, asked by both
construction and the CLI walk.

Origin: two revisions. PR-39 added namedtuple support with construction's `isdigit()` test for an
index key (moved into `_is_index_key` by BUG-80's fix); the CLI read positions as loosely, so the
channels agreed. BUG-97's fix then limited the CLI to the canonical spellings through
`_namedtuple_index_spellings` and left construction on `isdigit()`, which opened the gap (bisected:
before it, `--pt.01` builds as the file does). BUG-108 is the same rule missing from the CLI's fixed
tuple, and BUG-109 and BUG-112 (closed, the adapters' registration) also come from PR-39.

```python
from dataclasses import dataclass
from typing import NamedTuple
import confarg


class Pt(NamedTuple):
    x: int = 0
    y: int = 0


@dataclass
class Cfg:
    pt: Pt = Pt()


for key in ("01", "-0", "١", "²"):
    for label, run in (
        ("file", lambda: confarg.build(Cfg, {"pt": {key: 5}})),
        ("cli ", lambda: confarg.load(Cfg, argv=[f"--pt.{key}", "5"], env={})),
    ):
        try:
            out = repr(run())
        except Exception as exc:
            out = f"{type(exc).__name__}: {str(exc)[:60]}"
        print(f"{ascii(key)} {label}: {out}")

# expected: each file line refused as its cli line is (an unknown field, not an index)
# actual:
# '01' file: Cfg(pt=Pt(x=0, y=5))
# '01' cli : UnknownArgumentError: Unknown argument: '--pt.01' (field 'pt.01' not found)
# '-0' file: Cfg(pt=Pt(x=5, y=0))
# '-0' cli : UnknownArgumentError: Unknown argument: '--pt.-0' (field 'pt.-0' not found)
# '١' file: Cfg(pt=Pt(x=0, y=5))
# '١' cli : UnknownArgumentError: Unknown argument: '--pt.١' (field 'pt.١' not found)
# '\xb2' file: TypeCoercionError: Cannot construct Pt at 'pt': dict keys must be integer indic
# '\xb2' cli : UnknownArgumentError: Unknown argument: '--pt.²' (field 'pt.²' not found)
```

Run with `PYTHONIOENCODING=utf-8` on a Windows console.
