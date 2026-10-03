# BUG-93 — Scalar cast flags stay refused on struct, collection and registered-leaf fields

**Where:** `src/confarg/cli/_build.py` (`_scalar_cast_parent_is_leaf`, `_collect_patch_argv_specs`) ·
`src/confarg/cli/_collect.py` (`_collect_field` struct and registered-leaf branches) ·
**Filed:** 2026-09-30 · **Effort:** M · **Risk:** medium · **Impact:** behavior

BUG-72 registered the typed scalar cast flags on *plain leaf* fields only. Vanilla's
`detect_force_cast` accepts them wherever the trailing segment names no real member of the
parent type — and a struct, a collection or a registered leaf (e.g. `Path`) has no member
named `str` either — so vanilla pins the *whole field* (`--nested.str x` builds
`nested='x'`, `--items.str 3` builds `items='3'`, `--p.str y` builds `p='y'`) while every
adapter still refuses the flag at parse time. Fix direction: widen `_scalar_cast_parent_is_leaf`
(the collection-parent write already lands in the leaf branch the collector honours), add the
cast override to the struct branch with the argv-order interplay vanilla gives
(`--nested.str x --nested.n 5` builds `Nested(n=5)`; reversed, `nested='x'`), and decide what
the registered-leaf branch does with a cast beside its tag hatch. A maintainer may instead
prefer to refuse the whole family in vanilla — the spellings disambiguate nothing there
either; BUG-72 chose registration for leaves, which sets the precedent.
Rationale: [cli-parsing/casts-and-reserved-words.md#real-field-wins](../../architecture/cli-parsing/casts-and-reserved-words.md#real-field-wins),
[cli-adapters/static-and-dynamic-flags.md#static-and-dynamic-flags](../../architecture/cli-adapters/static-and-dynamic-flags.md#static-and-dynamic-flags).

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
