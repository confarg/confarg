# BUG-112 — A namedtuple's non-struct field takes scalar flags on the adapters

**Where:** `src/confarg/cli/_build.py` (`_collect_namedtuple_specs`) ·
`src/confarg/cli/_collect.py` (`_namedtuple_deep_fields`, `_namedtuple_sub_flags`) ·
**Filed:** 2026-10-01
**Effort:** M · **Risk:** medium · **Impact:** behavior

BUG-68 sent a namedtuple's *struct-shaped* fields through the per-field dispatch
(`_specs_for_field` / `_collect_field`) and left every other field on a separate path: one
single-token `FlagSpec` per spelling, and `_coerce_leaf_value` for the value. Vanilla resolves
a namedtuple field like any other field, so a `list[str]` field there is a greedy multi-token
flag. On the adapters it takes one token and the framework rejects the rest. The same split
affects any field type the dispatch treats specially: varlen collections, dicts, callables,
registered leaves, unions of structs, Optional sequences *(inferred for the types other than
`list`)*.

The split is also written twice, and the two copies disagree on how they ask:
`_collect_namedtuple_specs` tests `_unwrap_optional(_resolve_type(ft))`, while
`_namedtuple_deep_fields` tests `_unwrap_optional(ft)` without resolving.

Fix direction: drop the struct-shaped special case and send every namedtuple field, at every
spelling, through `_specs_for_field` and `_collect_field`. A field then behaves the same at
every depth, which is the reason `_collect_field` was extracted. See
[namedtuple-is-a-fixed-length-sequence.md](../../architecture/design-decisions/namedtuple-is-a-fixed-length-sequence.md)
and
[invariants.md#delegate-to-the-canonical-function](../../architecture/invariants.md#delegate-to-the-canonical-function).

```python
from dataclasses import dataclass
from typing import NamedTuple

import confarg
from confarg.cli.argparse import make_parser, merge_namespace


class Pt(NamedTuple):
    x: int = 0
    tags: list[str] = []


@dataclass
class Cfg:
    pt: Pt = Pt()


argv = ["--pt.tags", "a", "b"]
print(f"vanilla:  {confarg.merge(Cfg, argv=argv, env={})!r}")
ns = make_parser(Cfg, argv=argv).parse_args(argv)
print(f"argparse: {merge_namespace(Cfg, ns, argv=argv, env={})!r}")

# expected:
#   vanilla:  {'pt': {'tags': ['a', 'b']}}
#   argparse: {'pt': {'tags': ['a', 'b']}}
# actual (click, typer exit 2 too; cyclopts exits 1 with "Unused Tokens: ['b']"):
#   vanilla:  {'pt': {'tags': ['a', 'b']}}
#   <script>.py: error: unrecognized arguments: b      (argparse exits 2)
```
