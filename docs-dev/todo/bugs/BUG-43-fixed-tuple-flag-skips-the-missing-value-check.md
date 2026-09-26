# BUG-43 — A fixed-arity tuple flag under-fills instead of reporting a missing value

**Where:** `src/confarg/_parse_cli.py` (`_consume_fixed_tuple_args`) · **Filed:** 2026-09-24
**Effort:** S · **Risk:** medium · **Impact:** behavior

The consume loop is `for et in tt: if i < len(args): …` with no `else`, so when argv runs out
the flag quietly stores fewer items than its arity — including none at all. Every other
value-consuming branch in the module raises `Missing value for '<flag>'`, and a flag missing its
value is named as one of the few things the parser *can* prove wrong at parse time
([01-pipeline-and-contracts.md#merge-build-contract](../../architecture/01-pipeline-and-contracts.md#merge-build-contract));
a value-taking flag always needing its value is the rule in
[03-cli-parsing.md#token-consumption](../../architecture/03-cli-parsing.md#token-consumption)
and the decision in
[10-design-decisions.md#a-whole-value-flag-needs-its-value](../../architecture/10-design-decisions.md#a-whole-value-flag-needs-its-value).

The failure still happens, in `build()`, with an arity message that names neither the flag nor
the missing token. Note `--pair` with nothing after it is *not* the bare-flag case: that is
reserved for varlen collections and the bare append
([04-cli-adapters.md#a-bare-append](../../architecture/04-cli-adapters.md#a-bare-append)), and a
fixed tuple is neither.

Fix direction: the guard belongs to the shared `_require_value` helper in
[REF-45](../refactors/REF-45-argv-value-run-scan-duplicated.md) — the check exists in four
hand-written copies elsewhere in the file and this is the branch that was left out of all four.

```python
from dataclasses import dataclass
import confarg


@dataclass
class T:
    pair: tuple[int, int] = (0, 0)


for argv in (["--pair", "1", "2"], ["--pair", "1"], ["--pair"]):
    print(argv, "->", confarg.merge(T, argv=argv, env={}))

# expected:
#   ['--pair', '1', '2'] -> {'pair': [1, 2]}
#   ['--pair', '1']      -> UnknownArgumentError: Missing value for '--pair'
#   ['--pair']           -> UnknownArgumentError: Missing value for '--pair'
# actual:
#   ['--pair', '1', '2'] -> {'pair': [1, 2]}
#   ['--pair', '1']      -> {'pair': [1]}
#   ['--pair']           -> {'pair': []}
```
