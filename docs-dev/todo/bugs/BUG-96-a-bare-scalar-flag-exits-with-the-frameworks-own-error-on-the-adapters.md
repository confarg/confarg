---
filed: 2026-09-30
where:
  - src/confarg/cli/cyclopts/_context.py
  - src/confarg/cli/argparse/
  - src/confarg/cli/_clicklike/
  - src/confarg/cli/_build.py::_collect_patch_argv_specs  # the subkey or element spec, scalar since BUG-179
effort: M
risk: low
impact: behavior
severity: minor
introduced_by: [PR-5, PR-13, PR-26, BUG-179]  # the argparse, click and cyclopts adapters, typer on click's seam; BUG-179 for element flags
---

# BUG-96 — A bare scalar flag exits with the framework's own error on all four adapters

Vanilla refuses a bare scalar flag with `ConfargError` (`_require_value`, the same error the fixed-arity guard reproduces on argparse and cyclopts since BUG-58 closed).
The four adapters never got that treatment for the scalar spelling: argparse's parser prints `error: argument --host: expected one argument` and exits 2 before the merge step runs, cyclopts prints `Parameter --host requires an argument.` and exits 1, and the clicklike front-ends exit 2 with `Option '--host' requires an argument.` A caller wrapping `load()` in `except ConfargError` therefore answers the error on vanilla and a silent exit on every adapter.
The refusal is not an approved divergence — the note names the clicklike frameworks' own refusal only for the flags that stand bare ([cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare](../../architecture/cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare)), and nothing covers the scalar spelling at all.

A subkey or element flag over a one-token type (`--d.a` on a `dict[str, int]`, `--xs.0` on a `list[int]`) is the same scalar spec since BUG-179's fix, which registers it with the one-token arity a field flag of that type has, and its bare occurrence meets the same framework refusal.

Fix direction: the pre-parse refusal BUG-74 built extends naturally — `FlagSpec.refuses_bare` on the scalar specs (every leaf, subkey and element spec whose `nargs` is `None`), answered by `cli._argv.refuse_bare_occurrences` on cyclopts; argparse cannot be scanned before `parse_args`, which the host calls, but the config-file flags show its seam since BUG-63 closed: an action (`cli/argparse/_register._RefusingBareAction`) refuses the occurrence argparse hands no value, in argv order.
A scalar flag's `nargs=None` makes argparse refuse before any action runs, so its spec would have to register `"?"` to reach one.
The clicklike parsers refuse before any confarg code runs, so they need the same scan on the command hook.
Setting the marker on every scalar spec is what makes it a decision rather than a spot fix — and a refusal answers `--help` in argv order: a pre-parse scan reads argv only up to the first help flag, as cyclopts' `_context._before_eager_flag` does for the config-file and fixed-arity refusals ([a flag that stands bare](../../architecture/cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare)).

Origin: latent since each adapter was written: argparse in the initial version (PR-5), click in PR-13, cyclopts in PR-26, and typer on click's seam (BUG-7).
Each registered a scalar flag with its framework's one-value arity and let the framework refuse a bare occurrence before any confarg code runs.
BUG-58's and BUG-74's fixes gave the fixed-arity flags confarg's refusal without extending it to the scalar spelling.
BUG-179's fix extended the gap to the subkey and element flags of a one-token type, which had answered a bare occurrence with confarg's refusal on argparse and cyclopts while they were registered `nargs="*"`.

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
