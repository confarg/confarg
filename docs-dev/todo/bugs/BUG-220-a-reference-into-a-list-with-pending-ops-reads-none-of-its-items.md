---
filed: 2026-10-10
where:
  - src/confarg/dictexpr/_expressions.py::_step
  - src/confarg/_merge.py::_deep_merge
effort: M
risk: high
impact: behavior
severity: minor  # a loud MissingReferenceError; writing the whole list (`--names a b`) works around it
needs_design: true  # read through the ops at evaluation, or apply a layer's own ops in the merge
introduced_by: [PR-5]  # expressions resolved over the merged dict before build() applies its list ops
---
# BUG-220 — A reference into a list with pending ops reads none of its items

`build()` resolves `${...}` over the merged dict before construction applies the list ops it still holds. The merge applies an op only onto a list base from an earlier layer ([deep merge](../../architecture/pipeline/deep-merge.md#deep-merge-semantics)): an append with no base anywhere stays `{ListOp.APPEND: [...]}`, and a base and an append given in the same layer stay `{ListOp.BASE: [...], ListOp.APPEND: [...]}`. A reference such as `${names[0]}` walks into that dict, finds no key `0`, and is refused, though the list `build()` makes from it has the item. With the base in a file and the append on the command line, the merge has applied the append and the same reference resolves.

Fix direction: either the walk (`_step`, the one walk evaluation and the dependency graph share) reads a node of pending ops as the list they make, when they need no type; or the merge applies a layer's own ops when no type is needed, as it does across layers. The first keeps `merge()`'s output as written; the second changes it.

Origin: latent since the initial version (PR-5), whose expressions resolved over the merged dict and whose CLI recorded `--names+` as an append op; the refusal was an `ExpressionEvalError` (`Error in expression '${names[0]}': 0`) until BUG-121 (PR-280) read the subscript as a path segment and made it a `MissingReferenceError`. It reproduces at PR-5 with `args=` for `argv=`.

```python
from dataclasses import dataclass, field

import confarg


@dataclass
class Cfg:
    names: list[str] = field(default_factory=list)
    first: str = ""


for argv in (["--names+", "b"], ["--names", "a", "--names+", "b"]):
    try:
        print(argv, "->", confarg.load(Cfg, argv=[*argv, "--first", "${names[0]}"], env={}))
    except Exception as e:
        print(argv, "->", type(e).__name__, e)

# expected: first='b', then first='a'
# actual:
#   ['--names+', 'b'] -> MissingReferenceError Field 'names.0' not found in configuration
#   ['--names', 'a', '--names+', 'b'] -> MissingReferenceError Field 'names.0' not found in configuration
```
