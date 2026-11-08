---
filed: 2026-10-28
where:
  - src/confarg/typedload/_construct.py::_construct_union_by_tag  # refuses matches from two variant classes
  - src/confarg/typedload/_construct.py::_construct_bound_tag  # tries one class's bindings in order
  - src/confarg/_naming.py::named_variant  # types the keys below a tag by the first binding of one class
  - src/confarg/_default_layer.py::_union  # lays defaults below a tag only for exactly one binding
effort: M  # one decision-maker for three sites that each spell the question their own way
risk: high  # the naming walk types every channel's keys below a tag; a mistake there is silent everywhere
impact: behavior  # a refusal becomes a build
severity: major  # a valid configuration is refused, and nothing in it can avoid the refusal
introduced_by: [PR-5, FEAT-13]  # PR-5: a tag matching two variants is ambiguous; FEAT-13: one class's bindings tried in order
---

# BUG-300 — A tag matching variants of two classes is refused as ambiguous

A tag naming a class that two variants of a union admit is refused with `AmbiguousUnionError` when the variants are of different classes, even where both would build the very same object: `AB(A, B)` under `A | B`, or a class implementing two Protocol variants once [FEAT-57](../features/FEAT-57-protocol-typed-fields.md) lands (`Structural` under `Greeter | Named`).
Two variants of one class are not refused: `Box[int] | Box[str]` with `{class: Box, item: 'x'}` tries `Box[int]`, which refuses `'x'`, then builds `Box[str]` (`_construct_bound_tag`).
So "several bindings" has two answers by whether the variants share a class, and the configuration has no way to pick a variant the tag names already.

Three sites answer which bindings a tag selects, each its own way: construction groups them by variant class and refuses two classes, `_naming.named_variant` takes the first binding of one class and none for two, and `_default_layer._union` lays defaults only for exactly one binding.

Fix direction, decided while designing [FEAT-59](../features/FEAT-59-a-protocol-scalars-satisfy-reads-as-their-union.md): one decision-maker answers the distinct bindings a tag selects in a union, in declaration order, equal bindings once (`AB` from `A` and from `B` is one); construction tries them in that order and builds the first that builds, as `_construct_bound_tag` does today for one class, the naming walk types the keys by the first, as construction tries it first, and the default layer lays below exactly one.
A tag then never raises `AmbiguousUnionError` of its own; structural matching without a tag still does, and one met building a binding still ends the walk (`_first_that_builds`, [an ambiguity met inside a variant](../../architecture/types/construction.md#an-ambiguity-met-inside-a-variant-ends-the-walk)).
A structural implementer binds by its defaults under every Protocol variant, so its bindings are one ([the Protocol plan](../plans/protocol-typed-fields.md#a-protocol-is-an-abstract-base-its-implementers-are-named-into)).

Origin: latent since PR-5, which refused a tag matching more than one variant; FEAT-13, reading a parameterized generic as a struct with bound parameters, grouped the matches by variant class so that `Box[int] | Box[str]` could pick its binding by the value, and left two classes refused, with `_naming.named_variant` and `_default_layer._union` each spelling the grouping again.

```python
from dataclasses import dataclass

import confarg
import confarg.exceptions


class A:
    pass


class B:
    pass


@dataclass
class AB(A, B):
    n: int = 0


class Src[T]:
    pass


class Snk[T]:
    pass


@dataclass
class Both[T](Src[T], Snk[T]):
    item: T


@dataclass
class Box[T]:
    item: T


@dataclass
class C:
    x: A | B | None = None
    s: Src[int] | Snk[str] | None = None
    b: Box[int] | Box[str] | None = None


for data in (
    {"x": {"class": "__main__.AB", "n": 1}},
    {"s": {"class": "__main__.Both", "item": 3}},
    {"b": {"class": "__main__.Box", "item": "x"}},
):
    try:
        print(data, "->", confarg.from_dict(C, data))
    except confarg.exceptions.ConfargError as e:
        print(data, "->", type(e).__name__, e)

# expected: C(x=AB(n=1), ...), C(s=Both(item=3), ...) and C(b=Box(item='x'), ...)
# actual:   {'x': ...} -> AmbiguousUnionError Class '__main__.AB' at 'x' matches multiple union variants: __main__.A, __main__.B
#           {'s': ...} -> AmbiguousUnionError Class '__main__.Both' at 's' matches multiple union variants: __main__.Src, __main__.Snk
#           {'b': ...} -> C(x=None, s=None, b=Box(item='x'))
```
