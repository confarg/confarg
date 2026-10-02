# BUG-63 — A bare `--config` before `--help` shows help on argparse and errors on the other four

**Where:** `src/confarg/cli/argparse/_namespace.py` · **Filed:** 2026-09-29
**Effort:** S · **Risk:** medium · **Impact:** behavior

`--config --help` is refused by every front-end but argparse: vanilla always raised, and since
BUG-51's strict rescan click, typer and cyclopts refuse it with confarg's own
`Missing file path after --config` too. argparse's `--help` is eager — `parser.parse_args`
prints help and exits 0 before `from_namespace`'s rescan can refuse the bare `--config` — so the
same command line ends in help on one front-end and an error on four, an unapproved parity gap
([09-invariants.md#cross-channel-parity](../../architecture/09-invariants.md#cross-channel-parity)).
Fixing it means validating argv before `parse_args` in `from_namespace`/`merge_namespace`; the
alternative is deciding help-wins is argparse's own idiom and recording the divergence as
approved.

Nothing covers the corner today, so a mistake in the fix would stay silent on argparse while the
other four stay correct — closing it means adding a test there
([12-testing.md#examples-and-documentation](../../architecture/12-testing.md#examples-and-documentation)
for where parity tests live).

```python
from dataclasses import dataclass

import confarg
from confarg.cli.argparse import from_namespace, make_parser


@dataclass
class Config:
    host: str = "h"


ARGV = ["--config", "--help"]

try:
    parser = make_parser(Config, argv=ARGV)
    print("argparse:", from_namespace(Config, parser.parse_args(ARGV), argv=ARGV, env={}, env_prefix=None))
except SystemExit as e:
    print("argparse: exited", e.code)
try:
    print("vanilla: ", confarg.load(Config, argv=ARGV, env={}, env_prefix=None))
except Exception as e:
    print("vanilla: ", type(e).__name__, e)
# expected: both front-ends agree
# actual:   argparse: exited 0   (its eager --help wins before the rescan can refuse the
#                             bare --config)
#           vanilla:  ConfargError Missing file path after --config.
#                             Usage: --config /path/to/config.yaml
```
