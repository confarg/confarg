# BUG-96 — A bare scalar flag exits with the framework's own error on all four adapters

**Where:** `src/confarg/cli/cyclopts/_context.py`, `src/confarg/cli/argparse/`, `src/confarg/cli/_clicklike/` · **Filed:** 2026-09-30
**Effort:** M · **Risk:** low · **Impact:** behavior

Vanilla refuses a bare scalar flag with `ConfargError` (`_require_value`, the same error the
fixed-arity guard reproduces on argparse and cyclopts since BUG-58 closed). The four adapters
never got that treatment for the scalar spelling: argparse's parser prints `error: argument
--host: expected one argument` and exits 2 before the merge step runs, cyclopts prints
`Parameter --host requires an argument.` and exits 1, and the clicklike front-ends exit 2 with
`Option '--host' requires an argument.` A caller wrapping `load()` in `except ConfargError`
therefore answers the error on vanilla and a silent exit on every adapter. The refusal is not
an approved divergence — the note names the clicklike frameworks' own refusal only for the
flags that stand bare
([cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare](../../architecture/cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare)),
and nothing covers the scalar spelling at all.

Fix direction: the pre-parse refusal BUG-74 built extends naturally — `FlagSpec.refuses_bare`
on the scalar specs (every leaf spec whose `nargs` is `None`), answered by
`cli._argv.refuse_bare_occurrences` on cyclopts; argparse needs the scan before
`parse_args` too (its own parser exits first), and the clicklike parsers refuse before any
confarg code runs, so they need the same scan on the command hook. Setting the marker on
every scalar spec is what makes it a decision rather than a spot fix — but note the refusal
then fires before a framework's own `--help` handling, the ordering BUG-63 already tracks for
argparse.

```python
from dataclasses import dataclass

import click
import cyclopts

import confarg
from confarg.cli.argparse import make_parser, merge_namespace
from confarg.cli.click import populate_command
from confarg.cli.cyclopts import merge_app, populate_app
from click.testing import CliRunner


@dataclass
class T:
    host: str = "x"


argv = ["--host"]
try:
    confarg.merge(T, argv=argv, env={})
except Exception as e:
    print("vanilla :", type(e).__name__ + ":", e)
parser = make_parser(T, argv=argv)
try:
    merge_namespace(T, parser.parse_args(argv), argv=argv, env={})
except SystemExit as e:
    print("argparse: SystemExit", e.code)

app = cyclopts.App(name="demo")
populate_app(T, app, argv=argv)
try:
    merge_app(T, app, argv=argv, env={})
except SystemExit as e:
    print("cyclopts: SystemExit", e.code)

cmd = click.Command("demo")
populate_command(T, cmd, argv=argv)
res = CliRunner().invoke(cmd, argv)
print("click   : exit", res.exit_code, "-", res.output.strip().splitlines()[-1])

# expected: the four adapters raise ConfargError: Missing value for '--host', as vanilla does
# actual:
#   vanilla : ConfargError: Missing value for '--host'. Usage: --host <value>
#   argparse: SystemExit 2        (argparse: error: argument --host: expected one argument)
#   cyclopts: SystemExit 1        (Parameter --host requires an argument.)
#   click   : exit 2 - Error: Option '--host' requires an argument.
```
