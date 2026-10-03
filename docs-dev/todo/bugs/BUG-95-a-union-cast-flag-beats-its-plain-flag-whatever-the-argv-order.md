# BUG-95 — A union's cast flag beats its plain flag whatever order they were typed in

**Where:** `src/confarg/cli/_collect.py` (`_collect_field` union branch,
`_find_scalar_cast_override`, `_collect_ns_optional_seq`) · **Filed:** 2026-09-30 ·
**Effort:** S · **Risk:** medium · **Impact:** behavior

Vanilla writes flag occurrences sequentially, so on a multi-variant union the *last* of
`--b.str` and `--b` wins; the adapters' union branch consults
`_find_scalar_cast_override` unconditionally, so the cast always wins. `--b.str yes --b no`
builds `b=False` in vanilla (the plain `no`, stolen to bool) and `b='yes'` on argparse,
click, typer and cyclopts. Reversed, the two agree. BUG-72 added the argv-order reader for
plain leaf fields (`_last_leaf_cast_spelling`, read off argv as
`_arity_flag_writes_last` is); the union branch and `_collect_ns_optional_seq` need the same
reader. *(inferred)* `.json` beside a scalar cast at one field should disagree the same way
— `_find_json_cast` runs before the dispatch, so the adapters always let the json cast win —
but that spelling pair is untested.
Rationale: [cli-adapters/union-inheritance-and-cast-flags.md#union-inheritance-and-cast-flags](../../architecture/cli-adapters/union-inheritance-and-cast-flags.md#union-inheritance-and-cast-flags),
[cli-parsing/casts-and-reserved-words.md#force-casts](../../architecture/cli-parsing/casts-and-reserved-words.md#force-casts).

```python
from dataclasses import dataclass
import confarg
from confarg.cli.argparse import make_parser, from_namespace


@dataclass
class Cfg:
    b: "str | bool" = None


argv = ["--b.str", "yes", "--b", "no"]
print("vanilla :", confarg.load(Cfg, argv=argv, env={}))
parser = make_parser(Cfg, argv=argv)
print("argparse:", from_namespace(Cfg, parser.parse_args(argv), argv=argv))

# expected: both halves build Cfg(b=False)
# actual:
#   vanilla : Cfg(b=False)
#   argparse: Cfg(b='yes')
#             (click, typer and cyclopts build Cfg(b='yes') the same way)
```
