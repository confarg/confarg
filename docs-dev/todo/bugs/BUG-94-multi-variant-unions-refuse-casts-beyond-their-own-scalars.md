# BUG-94 — Multi-variant unions refuse the scalar casts beyond the union's own scalars

**Where:** `src/confarg/cli/_build.py` (`_scalar_cast_types_in_union`) · **Filed:** 2026-09-30 ·
**Effort:** S · **Risk:** medium · **Impact:** behavior

Vanilla accepts *every* scalar cast on *any* multi-variant union — the trailing segment
names no member of the union — but `_scalar_cast_types_in_union` offers only the union's own
scalar variants, and only when the stealing rule is non-obvious (an enum variant, or `str`
beside another variant). So `int | float` registers no cast flag at all, and `str | bool`
registers `.str`/`.bool` but refuses `.float`, while vanilla pins any of them
(`--a.float 5` → `a=5.0`, `--b.float 1.5` → `b=1.5`). Fix direction: the argv scan registers
the typed cast dynamically (the BUG-72 route — the union branch of the collector already
honours any cast in the flat result), or vanilla stops accepting a cast that names none of
the union's variants; the second is a breaking change to the documented member-based rule in
[cli-parsing/casts-and-reserved-words.md#real-field-wins](../../architecture/cli-parsing/casts-and-reserved-words.md#real-field-wins),
which argues for the first.
See also [cli-adapters/union-inheritance-and-cast-flags.md#union-inheritance-and-cast-flags](../../architecture/cli-adapters/union-inheritance-and-cast-flags.md#union-inheritance-and-cast-flags).

```python
from dataclasses import dataclass
from typing import Union
import confarg
from confarg.cli.argparse import make_parser, merge_namespace


@dataclass
class Cfg:
    a: Union[int, float] = 0
    b: "str | bool" = None


argv = ["--a.float", "5", "--b.float", "1.5"]
print("vanilla :", confarg.load(Cfg, argv=argv, env={}))
parser = make_parser(Cfg, argv=argv)
print("argparse:", merge_namespace(Cfg, parser.parse_args(argv), argv=argv))

# expected: both halves build Cfg(a=5.0, b=1.5)
# actual:
#   vanilla : Cfg(a=5.0, b=1.5)
#   argparse: error: unrecognized arguments: --a.float 5 --b.float 1.5
#             (click, typer and cyclopts exit the same way; only the message differs)
```
