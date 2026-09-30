# BUG-79 — A repeated arity flag on an Optional fixed-arity field keeps only the last occurrence in the adapters

**Where:** `src/confarg/cli/_build.py` (`_build_leaf_spec`, the fixed-arity spec)
**Filed:** 2026-09-30
**Effort:** M · **Risk:** medium · **Impact:** behavior

Found while fixing BUG-61 (closed): the collector now routes an `Optional[<sequence>]` field
through the union shaper, but registration still builds the flag's spec from the unwrapped
core — `nargs=len(tt)` plus `whole_value`, no `accumulates`, no `stands_bare` — so the flag
behaves like a plain fixed-arity flag everywhere except in vanilla, where the *resolved*
union dispatches to the multi-token branch: occurrences accumulate (`_consume_multi_tokens`)
and a short run parses, deferring its arity error to `build()`. Two visible gaps:

- `--pair 1 2 --pair 3 4` on `tuple[int, int] | None`: vanilla joins the runs and fails at
  build; argparse keeps the last run and *builds* `(3, 4)`.
- click and typer register the exact count, so `--pair 1` never reaches the collector: the
  framework exits at parse where vanilla parses and raises `TypeCoercionError` at build. The
  plain spelling's count enforcement is the approved divergence
  ([cli-adapters/whole-value-flags.md#whole-value-flags](../../architecture/cli-adapters/whole-value-flags.md#whole-value-flags)),
  but there vanilla enforces at parse too; under `Optional` it does not, so the two sides
  refuse at different stages.

Fix direction: register the arity flag of an `Optional[<sequence>]` field the way the
multi-variant union branch registers its seq spec (`nargs="*"`, `accumulates=True`,
`stands_bare=True`), keeping the namedtuple sub-flag specs — the collector side already
shapes whatever arrives.

```python
from dataclasses import dataclass

import confarg
from confarg.cli.argparse import make_parser, merge_namespace


@dataclass
class T:
    pair: tuple[int, int] | None = None


argv = ["--pair", "1", "2", "--pair", "3", "4"]
print("vanilla :", confarg.merge(T, argv=argv, env={}))
parser = make_parser(T, argv=argv)
print("argparse:", merge_namespace(T, parser.parse_args(argv), argv=argv, env={}))

# expected: the two merged dicts are equal
# actual:
#   vanilla : {'pair': ['1', '2', '3', '4']}
#   argparse: {'pair': ['3', '4']}
```
