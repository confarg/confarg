# BUG-82 — A bare non-JSON token on a struct field is dropped by the adapters

**Where:** `src/confarg/cli/_collect.py` (struct branch of `_collect_field`) · **Filed:** 2026-09-30
**Effort:** S · **Risk:** medium · **Impact:** behavior

Vanilla stores the raw token a struct field's whole-value flag consumed when it is not a
`{`-prefixed blob (`--inner 7` → `{'inner': '7'}`) and lets `build()` refuse it
(`TypeCoercionError: Cannot construct SI at 'inner': expected dict, got str '7'`). The
adapters' collector stores only the decoded blob, so the token vanishes: `merge()` returns
a dict missing the key, and `load()` silently builds the field's default where vanilla
errors loudly — a typo'd CLI value is swallowed on four of the five front-ends.

Affects the plain-struct branch of `_collect_field`; the union branch stores the raw token
already (`_collect_union_seq_value`), as do the dict and registered-leaf branches. A
struct field below a namedtuple reaches the same branch since BUG-68, so the drop now
occurs at that depth too. Fix direction: store `_str_token(flat[flag])` when no blob
decoded, the token vanilla's own `_consume_value` leaves behind.

Found while fixing BUG-68.

[whole-value-flags.md#whole-value-flags](../../architecture/cli-adapters/whole-value-flags.md#whole-value-flags)

```python
from dataclasses import dataclass, field

import confarg
from confarg.cli.argparse import make_parser, merge_namespace


@dataclass
class Inner:
    a: int = 0


@dataclass
class T:
    inner: Inner = field(default_factory=Inner)


argv = ["--inner", "7"]

print("vanilla :", confarg.merge(T, argv=argv, env={}))
parser = make_parser(T, argv=argv)
print("argparse:", merge_namespace(T, parser.parse_args(argv), argv=argv))

# expected: argparse prints the same dict vanilla does, {'inner': '7'}
# actual:
#   vanilla : {'inner': '7'}
#   argparse: {}
```
