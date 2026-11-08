---
filed: 2026-11-02
where:
  - src/confarg/typedload/_construct.py::_structurally_matches  # counts a required struct field whose fields all default as required
  - src/confarg/typedload/_construct.py::_construct_struct  # builds that field from nothing
  - src/confarg/typedload/_construct.py::_try_construct_union_struct  # falls back to the first variant that builds
  - src/confarg/typedload/_construct.py::_construct_shadowed_subclass  # its loop builds the first subclass that builds
effort: M
needs_design: true  # whether the structural match reads such a field as optional, or the fallback refuses two variants that build
risk: high  # the structural match is what dump()'s _needs_tag and the default layer ask too
impact: config  # a value one variant builds today would be refused as ambiguous, or another variant selected
severity: critical  # the value is built as a variant the user did not choose, with no error
introduced_by: [PR-5, BUG-103]  # PR-5: the build from nothing and the union's try-each fallback; PR-263: the subclass loop
---

# BUG-304 — A required field built from nothing lets a fallback pick the first variant silently

A union whose struct variants both declare a required field of a struct type whose fields all default, `N1 | N2` each holding `inner: Inner`, refuses `{inner: {}}` as ambiguous, yet builds `{}` as `N1`, the first variant: giving less data avoids the refusal.
The structural match counts `inner` as required (`_struct_required`), so `{}` matches no variant, while `_construct_struct` builds a missing field of that type from nothing, so the fallback that tries each variant in turn builds the first.
`_construct_shadowed_subclass`'s loop does the same for subclasses whose own field owns the tag's spelling: `{Kind: y}` under a base whose subclasses `K1` and `K2` each hold `Kind: str` and `inner: Inner` builds `K1`, against its docstring's "never a silent pick" ([construction](../../architecture/types/construction.md#inheritance)).
Fix direction, for the design pass: one answer to "which variants build this value by its fields", either the structural match reading such a field as optional, as construction does, so both variants match and the ambiguity is loud, or the fallback refusing where more than one variant builds; the structural match is asked by `dump()`'s `_needs_tag` and the default layer too ([a variant that demands its tag](../../architecture/types/construction.md#a-variant-that-demands-its-tag-takes-no-untagged-value)).
Related: [BUG-288](BUG-288-an-ambiguity-inside-a-union-variant-lets-the-next-variant-take-the-value.md), another way the same fallback lets a value through that the union's own position would refuse.

Origin: latent since the initial version (PR-5), which both built a required struct field whose fields all default from nothing and tried each union variant in turn when none matched structurally; BUG-103 (PR-263) added the subclass loop on the union's model, a bug fix that copied the gap.
Found fixing BUG-303, whose fallbacks these are ([real field wins](../../architecture/cli-parsing/casts-and-reserved-words.md#real-field-wins)).

```python
from dataclasses import dataclass

import confarg
import confarg.exceptions


@dataclass
class Inner:
    a: int = 0


@dataclass
class N1:
    inner: Inner


@dataclass
class N2:
    inner: Inner


@dataclass
class U:
    g: N1 | N2


for data in ({"g": {"inner": {}}}, {"g": {}}):
    try:
        print(data, "->", confarg.build(U, data))
    except confarg.exceptions.ConfargError as e:
        print(data, "->", type(e).__name__, str(e).splitlines()[0])

# expected: both refused as ambiguous, since N1 and N2 both build from either
# actual:   {'g': {'inner': {}}} -> AmbiguousUnionError Ambiguous union at 'g': cannot distinguish between N1, N2.
#           {'g': {}} -> U(g=N1(inner=Inner(a=0)))
```
