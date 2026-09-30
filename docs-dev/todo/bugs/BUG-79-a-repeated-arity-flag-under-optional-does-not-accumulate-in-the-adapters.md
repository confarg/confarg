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

Found while fixing BUG-74 (closed): the *bare* spelling diverges the same way, by argv order.
Vanilla accumulates the occurrences (`_consume_multi_tokens`) and shapes the run at each
occurrence, so `--pair --pair 3 4` is a missing value — the shaper meets the still-empty run at
the first occurrence — while `--pair 1 2 --pair` is accepted as `{'pair': ['1', '2']}`. The
adapters keep only the last occurrence's run: argparse answers `{'pair': ['3', '4']}` for the
first argv and a missing value for the second, and cyclopts asserts inside its own parse on
both. BUG-74's pre-parse refusal deliberately does not fire here — `refuses_bare` is asked of
the resolved type and stays off the `Optional` spelling, because vanilla accepts the trailing
bare occurrence — so the fix needs the argv-order read: refuse a bare occurrence whose
accumulated run is still empty, which neither the drop (`stands_bare`) nor the bare-only
read-back answers today.

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
