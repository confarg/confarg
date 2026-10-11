---
filed: 2026-09-30
where:
  - src/confarg/cli/_build.py::_scalar_cast_parent_is_leaf
  - src/confarg/cli/_build.py::_collect_patch_argv_specs
effort: S
risk: medium
impact: behavior
severity: minor
introduced_by: [PR-50]  # feat: Enum priority in stealing rule, which made vanilla accept a typed cast on any field
---
# BUG-93 — Scalar cast flags stay refused on struct, collection and registered-leaf fields

BUG-72 registered the typed scalar cast flags on *plain leaf* fields only. Vanilla's
`detect_force_cast` accepts them wherever the trailing segment names no real member of the
parent type — and a struct, a collection or a registered leaf (e.g. `Path`) has no member
named `str` either — so vanilla pins the *whole field* (`--nested.str x` builds
`nested='x'`, `--items.str 3` builds `items='3'`, `--p.str y` builds `p='y'`) while every
adapter still refuses the flag at parse time. Fix direction: widen `_scalar_cast_parent_is_leaf`
— registration is all that is left, since the adapters' CLI channel is vanilla's loop (REF-72)
and writes the cast, with its argv-order interplay (`--nested.str x --nested.n 5` builds
`Nested(n=5)`; reversed, `nested='x'`), exactly as vanilla does. A maintainer may instead
prefer to refuse the whole family in vanilla — the spellings disambiguate nothing there
either; BUG-72 chose registration for leaves, which sets the precedent.
Rationale: [cli-parsing/casts-and-reserved-words.md#real-field-wins](../../architecture/cli-parsing/casts-and-reserved-words.md#real-field-wins),
[cli-adapters/static-and-dynamic-flags.md#static-and-dynamic-flags](../../architecture/cli-adapters/static-and-dynamic-flags.md#static-and-dynamic-flags).

Origin: parity gap since PR-50, a feature that taught vanilla's loop to accept a typed scalar cast
wherever the trailing segment names no member, and registered on the adapters only the casts of a
union's own scalars. Bisected with `parse_args`: before PR-50 vanilla could not build `--nested.str
x` or `--items.str 3` either; from PR-50 it builds them and every adapter refuses them. BUG-72's fix
then registered the casts on plain leaf fields only. BUG-94 shares this origin.

```python
from dataclasses import dataclass
from pathlib import Path
import confarg
from confarg.cli.argparse import make_parser, merge_namespace


@dataclass
class Nested:
    n: int = 0


@dataclass
class Cfg:
    nested: Nested = None
    items: list[int] = None
    p: Path = None


argv = ["--nested.str", "x", "--items.str", "3", "--p.str", "y"]
print("vanilla :", confarg.load(Cfg, argv=argv, env={}))
parser = make_parser(Cfg, argv=argv)
print("argparse:", merge_namespace(Cfg, parser.parse_args(argv), argv=argv))

# expected: both halves build Cfg(nested='x', items='3', p='y')
# actual:
#   vanilla : Cfg(nested='x', items='3', p='y')
#   argparse: error: unrecognized arguments: --nested.str x --items.str 3 --p.str y
#             (click, typer and cyclopts exit the same way; only the message differs)
```
