# BUG-95 — A union's cast flag beats its plain flag whatever the argv order

**Where:** `src/confarg/cli/_collect.py` (`_find_json_cast`'s write, ahead of the type
dispatch; the union branch's and `_collect_ns_optional_seq`'s scalar-cast sites, which
BUG-94's refusal gates) · **Filed:** 2026-09-30 · **Effort:** S · **Risk:** medium ·
**Impact:** behavior

Vanilla writes flag occurrences sequentially, so on a union the *last* of a cast spelling
and the plain flag wins. BUG-85's argv-order reader (`_arity_flag_writes_last`) settled the
scalar-cast pair: `--b.str yes --b no` keeps `{'b': 'no'}` on every front-end, and the
reverse order agreed all along. What still inverts is the `.json` cast, the pair this
ticket once marked *(inferred)* and has now observed: `_find_json_cast` runs before the
type dispatch, writes and returns, so it never asks the reader — `--b.json 5 --b no` keeps
`{'b': 5}` on the adapters where vanilla keeps the plain token (the reverse order agrees).
The scalar casts at `_collect_ns_optional_seq` and the union branch's struct variants are
unreachable today — BUG-94's refusal exits the framework's parse before the collector runs
— so their order question reopens with BUG-94's fix.
Rationale: [cli-adapters/union-inheritance-and-cast-flags.md#union-inheritance-and-cast-flags](../../architecture/cli-adapters/union-inheritance-and-cast-flags.md#union-inheritance-and-cast-flags),
[cli-parsing/casts-and-reserved-words.md#force-casts](../../architecture/cli-parsing/casts-and-reserved-words.md#force-casts).

```python
from dataclasses import dataclass

import confarg
from confarg.cli.argparse import make_parser, merge_namespace


@dataclass
class Cfg:
    b: "str | bool" = None


argv = ["--b.json", "5", "--b", "no"]
van = confarg.merge(Cfg, argv=argv, env={})
ns = make_parser(Cfg, argv=argv).parse_args(argv)
arg = merge_namespace(Cfg, ns, argv=argv, env={})
print(f"vanilla : {van!r}")
print(f"argparse: {arg!r}")

# expected (vanilla, last write in argv order):
#   vanilla : {'b': 'no'}
# actual (argparse; the reversed argv spelling agrees on both):
#   argparse: {'b': 5}
```
