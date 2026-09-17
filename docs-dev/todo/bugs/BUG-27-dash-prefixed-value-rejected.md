# BUG-27 — A value starting with `--` is refused by the vanilla parser

**Where:** `src/confarg/_parse_cli.py` (`_looks_like_flag`, `_normalize_eq_args`)
· **Filed:** 2026-09-16
**Effort:** M · **Risk:** high · **Impact:** config

`_looks_like_flag` (`--` + letter/underscore) is the sole value-or-flag
discriminator, and every value-consumption site calls it, so a value that itself
starts with `--` (e.g. `--key --value`) is read as a new flag and raises
`Missing value for '--key'`. The `=` escape hatch that argparse and jsonargparse
use for this case does not help: `_normalize_eq_args` splits every
`--key=value` into `['--key', 'value']` before any flag-check runs, so
`--key=--value` becomes `['--key', '--value']` and hits the same gate.
There is also no bare `--` end-of-options separator.

The argparse adapter does not share the defect — argparse honors the `=` form
natively, so `make_parser(Cfg).parse_args(['--key=--value'])` succeeds — which
makes this a parity gap, not only an ergonomic one
([09-invariants.md#cross-channel-parity](../../architecture/09-invariants.md#cross-channel-parity)).
omegaconf is not a CLI parser and never tokenizes, so the case does not arise in
its merge layer. Fix direction: treat the `=` form as an explicit value
boundary (do not split when the value side starts with `--`), or teach the
consumers to accept a `--`-prefixed token when exactly one value is expected.

```python
from dataclasses import dataclass

import confarg
from confarg.cli.argparse import from_namespace, make_parser


@dataclass
class Cfg:
    key: str = ""


print("eq form:  ", confarg.load(Cfg, argv=["--key=--value"]))
print("space form:", confarg.load(Cfg, argv=["--key", "--value"]))
parser = make_parser(Cfg, argv=["--key=--value"])
print("argparse:  ", from_namespace(Cfg, parser.parse_args(["--key=--value"])))
# expected: all three print Cfg(key='--value')
# actual:   eq form:   ConfargError: Missing value for '--key'. Usage: --key <value>
#           space form: ConfargError: Missing value for '--key'. Usage: --key <value>
#           argparse:   Cfg(key='--value')
```
