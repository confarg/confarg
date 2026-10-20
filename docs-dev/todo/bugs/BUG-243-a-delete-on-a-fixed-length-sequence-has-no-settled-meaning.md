---
filed: 2026-10-15
where:
  - src/confarg/_parse_cli.py::_handle_delete_token
  - src/confarg/_parse_env.py::_handle_env_delete
  - src/confarg/_merge.py::_apply_list_ops
  - src/confarg/typedload/_construct.py::_patched_positions
effort: M
needs_design: true  # unset the position, or refuse the delete
risk: high  # the merge and construction every channel shares
impact: config  # `--pt.0-` builds something else once settled
severity: critical  # `--pt.0-` silently shifts the next field into the deleted one
introduced_by: [PR-39]  # namedtuple support carried a namedtuple's patch in the list ops, a delete included
---
# BUG-243 — A delete on a fixed-length sequence has no settled meaning

A namedtuple and a fixed tuple are fixed-length sequences ([namedtuple is a fixed-length sequence](../../architecture/design-decisions/namedtuple-is-a-fixed-length-sequence.md)), yet their deletes go through the list ops, which shorten a list. `--pt.0-` removes position 0 and the namedtuple's defaults fill the end, so `y` silently moves into `x`. `--pt.x-` spells the same position by name and fails on the leaked delete sentinel, since a namedtuple's field-name key over a base (a file's `pt: [7, 8]`, or the class's own tuple default, which the [default layer](../../architecture/design-decisions/a-field-default-is-the-base-layer.md) lays as `[1, 2]`) is neither applied nor dropped. A fixed tuple's `--t.0-` is refused by arity. Fix direction, to decide first: a delete on a fixed-length sequence either unsets the position (its default, `None` where the type allows, else a missing field), whichever spelling names it, or is refused at parse with a hint to set the position instead. The baseless `--pt.x-` (no file, no laid default) already falls back to the field default, as any key delete that meets nothing does (BUG-98).

The settled design and its build order: [fixed-length deletes and key identity](../plans/fixed-length-deletes-and-key-identity.md).

Origin: latent since namedtuple support (PR-39), which carried a namedtuple's patch in the list ops so that its index flags would patch as a list's do, and with them the index delete, which no revision since has given a fixed-length meaning.

```python
from dataclasses import dataclass
from typing import NamedTuple

import confarg


class Pt(NamedTuple):
    x: int = 1
    y: int = 2


@dataclass
class Config:
    pt: Pt = Pt()
    t: tuple[int, int] = (1, 2)


for argv in (["--pt.0-"], ["--pt.x-"], ["--t.0-"]):
    try:
        cfg = confarg.load(Config, argv=argv, env={})
        print(argv, "->", cfg.pt if argv[0].startswith("--pt") else cfg.t)
    except Exception as e:
        print(argv, "->", f"{type(e).__name__}: {e}")

# expected: one meaning for all three, e.g. Pt(x=1, y=2) twice (x unset to its default) and an unset or a refusal for t
# actual:
#   ['--pt.0-'] -> Pt(x=2, y=2)
#   ['--pt.x-'] -> TypeCoercionError: Cannot coerce _DeleteSentinel _DELETE_ to int at 'pt.x'
#   ['--t.0-'] -> TypeCoercionError: Cannot construct tuple[int, int] at 't': expected 2 elements, got 1
```
