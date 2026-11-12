---
filed: 2026-09-30
where:
  - src/confarg/cli/_spec.py::FlagSpec  # refuses_bare on every one-token spec, if confarg's error is chosen
  - src/confarg/cli/_build.py::_shaped
  - src/confarg/cli/_build.py::_collect_patch_argv_specs  # the subkey or element spec, scalar since BUG-179
  - src/confarg/cli/argparse/_register.py::_RefusingBareAction
  - src/confarg/cli/_clicklike/_options.py::_install_bare_filter
  - src/confarg/cli/cyclopts/_context.py
effort: M  # the design pass: who words the refusal, settled with BUG-181's either/or
needs_design: true  # the choice is who words a refusal the framework raises natively, confarg or the framework; BUG-181 asks it too
risk: low
impact: behavior
severity: minor
introduced_by: [PR-5, PR-13, PR-26, BUG-179]  # the argparse, click and cyclopts adapters, typer on click's seam; BUG-179 for element flags
---

# BUG-96 — A bare scalar flag exits with the framework's own error on all four adapters

A bare one-token flag is refused on all five front-ends, so *whether* it is refused is at parity.
What differs is *who words the refusal*.
Vanilla raises `ConfargError` (`_require_value`). argparse exits 2 with `expected one argument`, cyclopts exits with `Parameter --host requires an argument.`, and click and typer exit 2 with `Option '--host' requires an argument.`.
A caller wrapping `load()` in `except ConfargError` gets the error on vanilla and a process exit on every adapter.
Every one-token kind behaves this way: a leaf of any scalar type, `bool`, `Literal`, `Enum`, a struct's whole-value flag, a subkey or element of a one-token type (since BUG-179), a plain union, a cast (`--u.int`, `--host.json`, the root `--json`), a tag or opener (`--u.class`, `--f.call`), a callable's argument flag, and the same under `cli_prefix`.

One part is not about wording, and the notes already settle it: on cyclopts, `--host --help` shows help (exit 0), while the other four refuse.
[A flag that stands bare](../../architecture/cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare) answers a refused bare flag and `--help` in argv order and rejects letting cyclopts' help win wherever it sits (BUG-63).
Its natural fix is `refuse_bare_occurrences` on cyclopts.
That also hands a lone bare `--host` confarg's wording there, so it waits on the same choice.

The wording is BUG-181's question for another case ([BUG-181](BUG-181-an-out-of-domain-literal-or-enum-flag-exits-with-the-frameworks-choice-error.md)): when the host framework refuses a CLI token by itself, at parse time, must confarg get there first with its own error?
The notes do not settle it:

- They commit confarg to vanilla's error wherever confarg's own code refuses: BUG-51, BUG-58, BUG-63 and BUG-74 each registered `nargs="*"` (the framework took zero tokens) or met a cyclopts assertion, and in neither case did the framework refuse.
- They keep the framework's own refusal wherever it refuses natively:
  - click and typer "refuse the bare form in their own parser, with the framework's 'requires an argument'" for `--config` and the whole-value flags ([a flag that stands bare](../../architecture/cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare));
  - argparse and cyclopts decline a dashed value "in their own words" ([equals escapes a dashed value](../../architecture/design-decisions/equals-escapes-a-dashed-value.md#a-single-dash-value-is-the-backends-to-read));
  - "the framework's rejection stands in for vanilla's `no_such_field`" for an unknown flag ([whole-value flags](../../architecture/cli-adapters/whole-value-flags.md#whole-value-flags));
  - "the refusal a user meets is the one their host framework raises at its own arguments" ([design decisions](../../architecture/design-decisions/divergence-leans-to-the-backend.md#a-divergence-leans-towards-the-affected-backends-own-idiom)).

## The options

- **A, confarg's error on all four.**
  Checked on a prototype: all five then answer `Missing value for '--host'. Usage: --host <value>` for every kind above, and the root `--json` keeps `Usage: --json '<json>'`.
  No argv that parses today parses differently (checked with argparse on Python 3.12 to 3.15: `--hos a` abbreviations, `--host=`, `--host ''`, `--host -5`, `--host -.5` are unchanged).
  The cost falls on argparse, which reaches an action only through `nargs="?"`, and argparse always brackets that in help:
  - usage `[--host STR]` becomes `[--host [STR]]`, and the help line `--host STR` becomes `--host [STR]`, for every one-token flag;
  - argcomplete offers every option beside the values: `--lit <TAB>` on a `Literal["aa", "ab"]` lists `aa ab` today and `--help --host --lit --verbose -h aa ab` after;
  - the approved `--host -x` divergence is then refused in confarg's words on argparse and in cyclopts' own (`Parameter --host requires an argument.`) on cyclopts, as `--config -x` already is.
- **B, approve the framework's refusal of a bare one-token flag as a divergence**, as BUG-181's second option does for a choice.
  That leaves only the cyclopts `--host --help` gap, which then needs a fix that keeps cyclopts' wording.
- **C, confarg's error on cyclopts, click and typer** (a pre-parse scan, with no visible cost there), while **argparse keeps its own**.
  The divergence is "narrowed to the backend that imposes it", and argparse's cost is its help text.

## What A or C needs

- `refuses_bare` on every spec whose `nargs` is `None`, decided in one place.
  Many specs are built outside `_build._shaped` (openers, tags, casts, callable and leaf-tag arguments, the plain union scalar), so a `FlagSpec`-level rule beats eleven call sites.
  The root `--json` cast carries `usage="'<json>'"`.
- argparse (A only): register such a spec `nargs="?"` with `_RefusingBareAction`, which must test `values is None or values == []`.
  Its `not values` today would refuse `--host ''`.
- click and typer: the scan goes on the parser hook (`_clicklike._install_bare_filter`, armed from the option's `add_to_parser`), not on a command hook, because the note rejects a command hook (`params` copying loses it).
  It reads `args` up to the first of `ctx.help_option_names`, and is skipped under `ctx.resilient_parsing`: without that skip, shell completion of `--host <TAB>` raises `ConfargError`.
  The config specs join it through `bare_refusal()`, so a bare `--config` on click and typer gets confarg's error too.
- cyclopts: `meta["refuses_bare"]` picks the scalars up through the marker.
  `_before_eager_flag` already keeps `--help --host` answering help.
- Tests: one contract class on `loader`, every kind × {alone, before another flag, after a valued occurrence}.
  `--host --help` refused on all five; `--help --host` shows help on argparse and cyclopts and keeps the clicklike usage error (BUG-63); `--host ''` stays `''`.
- On click, the scan reads exactly what today's loop reads: `--name --host` and `-- --host` are refused the same way before and after (see BUG-332).

Origin: latent since each adapter was written: argparse in the initial version (PR-5), click in PR-13, cyclopts in PR-26, and typer on click's seam (BUG-7).
Each registered a scalar flag with its framework's one-value arity and let the framework refuse a bare occurrence before any confarg code runs.
BUG-58's and BUG-74's fixes gave the fixed-arity flags confarg's refusal, which their `nargs="*"` registration needed, without extending it to the scalar spelling.
BUG-179's fix extended the gap to the subkey and element flags of a one-token type.
Those had answered a bare occurrence with confarg's refusal on argparse and cyclopts while they were registered `nargs="*"`.

```python
from dataclasses import dataclass

import click
import cyclopts
from click.testing import CliRunner

import confarg
from confarg.cli.argparse import make_parser, merge_namespace
from confarg.cli.click import merge_context, populate_command
from confarg.cli.cyclopts import merge_app, populate_app


@dataclass
class T:
    host: str = "x"


for argv in (["--host"], ["--host", "--help"]):
    print(argv)
    try:
        confarg.merge(T, argv=argv, env={})
    except confarg.exceptions.ConfargError as e:
        print("  vanilla : ConfargError:", e)
    try:
        merge_namespace(T, make_parser(T, argv=argv).parse_args(argv), argv=argv, env={})
    except SystemExit as e:
        print("  argparse: SystemExit", e.code)
    app = cyclopts.App(name="demo")
    populate_app(T, app, argv=argv)
    try:
        merge_app(T, app, argv=argv, env={})
    except SystemExit as e:
        print("  cyclopts: SystemExit", e.code)
    cmd = click.Command("demo", callback=lambda: merge_context(T, click.get_current_context(), argv=argv, env={}))
    populate_command(T, cmd, argv=argv)
    res = CliRunner().invoke(cmd, argv)
    print("  click   :", repr(res.exception) if not isinstance(res.exception, SystemExit) else f"exit {res.exit_code}")

# expected: ConfargError: Missing value for '--host' on all five, for both argvs
# actual:
# ['--host']
#   vanilla : ConfargError: Missing value for '--host'. Usage: --host <value>
#   argparse: SystemExit 2        (error: argument --host: expected one argument)
#   cyclopts: SystemExit 2        (Parameter --host requires an argument.)
#   click   : exit 2              (Error: Option '--host' requires an argument.)
# ['--host', '--help']
#   vanilla : ConfargError: Missing value for '--host'. Usage: --host <value>
#   argparse: SystemExit 2        (error: argument --host: expected one argument)
#   cyclopts: SystemExit 0        (prints help)
#   click   : ConfargError("Missing value for '--host'. Usage: --host <value>")
```
