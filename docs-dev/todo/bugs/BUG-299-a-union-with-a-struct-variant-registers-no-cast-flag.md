---
filed: 2026-10-28
where:
  - src/confarg/cli/_build.py::_specs_for_field  # the struct-union branch returns before the cast flags are added
effort: S
risk: medium  # registration is shared by the adapters; vanilla already takes the flag
impact: behavior  # a cast flag starts working on the adapters
severity: minor  # a file's __cast__ still pins the value; the CLI has no spelling for it on an adapter
introduced_by: [PR-54]  # fix: Register CLI flags for pure scalar unions (#54)
---

# BUG-299 — A union with a struct variant registers no cast flag

On a union holding a struct beside scalars, `u: int | float | Opts`, vanilla takes `--u.int 3` and `--u.float 3`, which the one admission rule `_cast.holds_the_cast` lets through since the union holds the scalar, while every adapter refuses them as unrecognized arguments: registration adds the cast flags (`_union_cast_flag_specs`) to a union of leaves and to one with a sequence variant, but its struct-union branch returns the whole-value flag, the tag and the variants' fields without them.
`--help` lists none either.
On an adapter the CLI has no other spelling for the cast: a whole value carrying `__cast__` is refused as a key only a file may write.

Fix direction: the struct-union branch adds `_union_cast_flag_specs(flag, _scalar_cast_types_in_union(resolved), …)` as the other two do, so registration and vanilla's `detect_force_cast` keep asking the one rule ([union, inheritance and cast flags](../../architecture/cli-adapters/union-inheritance-and-cast-flags.md)).
[FEAT-59](../features/FEAT-59-a-protocol-scalars-satisfy-reads-as-their-union.md) is blocked by it: a Protocol a scalar satisfies reads as such a union, and its plan promises `--ratio.int`, `--ratio.float` and `--ratio.bool` on every front-end ([its plan](../plans/a-protocol-reads-the-scalars-that-satisfy-it.md#--help-shows-the-unions-flags)).

Origin: latent since PR-54, which registered cast flags for unions of scalars only; the struct-union branch, which returns before that code, has never registered one, and PR-77 then factored the flags into `_union_cast_flag_specs` for the scalar and sequence branches alone.
Shown on argparse; click, typer and cyclopts register through the same `_specs_for_field` *(inferred)*.

```python
from dataclasses import dataclass

import confarg
from confarg.cli.argparse import from_namespace, make_parser


@dataclass
class Opts:
    scale: float = 1.0


@dataclass
class C:
    u: int | float | Opts = 1


argv = ["--u.int", "3"]
print("vanilla  ->", confarg.load(C, argv=argv))
try:
    print("argparse ->", from_namespace(C, make_parser(C).parse_args(argv), argv=argv))
except SystemExit as e:
    print("argparse -> SystemExit", e.code)

# expected: vanilla  -> C(u=3)
#           argparse -> C(u=3)
# actual:   vanilla  -> C(u=3)
#           argparse prints "error: unrecognized arguments: --u.int 3", then SystemExit 2
```
