---
filed: 2026-10-10
where:
  - src/confarg/_parse_cli.py::_looks_like_flag
  - src/confarg/cli/argparse/_register.py
  - src/confarg/cli/cyclopts/_context.py
effort: M
needs_design: true  # which side gives way is a parity decision for the maintainer
risk: medium
impact: behavior
severity: minor  # --host=-x is the workaround on all five front-ends
introduced_by: [PR-5, PR-26]  # vanilla's `--word` flag test and the argparse adapter; the cyclopts adapter
---
# BUG-223 — A single-dash token after a value-taking flag is a value on three front-ends and refused on argparse and cyclopts

Vanilla's flag test (`_parse_cli._looks_like_flag`) calls only `--<word>` a flag, so `--host -x` sets `host` to `-x`, and click and typer bind the token the same way. argparse and cyclopts read `-x` as an option of their own: argparse exits 2 with `expected one argument`, cyclopts exits 1 with `requires an argument`, and on cyclopts `--host -h` shows help, because `-h` is one of its help flags. The `=` spelling (`--host=-x`) works on all five, which is what the dashed-value decision makes the escape for a `--`-prefixed value ([design-decisions/equals-escapes-a-dashed-value.md](../../architecture/design-decisions/equals-escapes-a-dashed-value.md#the--form-is-the-escape-for-a-dashed-value)). That decision never settled the single-dash case, so this is an unapproved gap ([invariants.md#cross-channel-parity](../../architecture/invariants.md#cross-channel-parity)).

On a config-file flag, argparse answers with confarg's `Missing file path after --config` since BUG-63: its refusing action sees the occurrence handed no value, because argparse kept `-x` as an option. Before BUG-63 it exited 2 with its own error.

Fix direction: either approve the split as each framework's own idiom, with argparse and cyclopts declining the space form and `=` as the escape everywhere, or make vanilla refuse a single-dash token as well. The precedents are split: getopt's required argument and click take the next token whatever it starts with, while argparse and cyclopts treat it as an option.

Origin: latent since the initial version (PR-5), which gave vanilla the `--<word>` flag test and registered argparse's options with the default `prefix_chars="-"`. The cyclopts adapter (PR-26) inherited cyclopts' own reading of a leading dash. No fix produced it.

```python
import contextlib
import io
import sys
from dataclasses import dataclass

import click
import cyclopts
from click.testing import CliRunner

import confarg
from confarg.cli.argparse import make_parser, merge_namespace
from confarg.cli.click import merge_context, populate_command
from confarg.cli.cyclopts import merge_app, populate_app

sys.stdout.reconfigure(encoding="utf-8")


@dataclass
class T:
    host: str = "x"


def first_text(out: str) -> str:
    """Return the first line of a rich error box that holds text."""
    return next(ln.strip("\u2502 ") for ln in out.splitlines() if "\u2500" not in ln and ln.strip("\u2502 "))


for argv in (["--host", "-x"], ["--host", "-h"], ["--config", "-x"]):
    print(argv)
    try:
        print("  vanilla :", confarg.merge(T, argv=argv, env={}))
    except Exception as e:
        print("  vanilla :", type(e).__name__ + ":", str(e).splitlines()[0])
    sink = io.StringIO()
    try:
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            parser = make_parser(T, argv=argv)
            ns = parser.parse_args(argv)
        print("  argparse:", merge_namespace(T, ns, argv=argv, env={}))
    except SystemExit as e:
        print("  argparse: SystemExit", e.code, "-", sink.getvalue().strip().splitlines()[-1])
    except Exception as e:
        print("  argparse:", type(e).__name__ + ":", str(e).splitlines()[0])

    @click.command()
    @click.pass_context
    def cmd(ctx, **_):
        try:
            click.echo(f"merged {merge_context(T, ctx, argv=argv, env={})}")
        except Exception as e:
            click.echo(f"{type(e).__name__}: {str(e).splitlines()[0]}")

    populate_command(T, cmd, argv=argv)
    res = CliRunner().invoke(cmd, argv)
    print("  click   : exit", res.exit_code, "-", res.output.strip().splitlines()[-1])

    app = cyclopts.App(name="demo")
    populate_app(T, app, argv=argv)
    sink = io.StringIO()
    try:
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            r = merge_app(T, app, argv=argv, env={})
        print("  cyclopts:", r)
    except SystemExit as e:
        print("  cyclopts: SystemExit", e.code, "-", first_text(sink.getvalue()))
    except Exception as e:
        print("  cyclopts:", type(e).__name__ + ":", str(e).splitlines()[0])

# expected: the five front-ends agree on each argv
# actual:
#   ['--host', '-x']
#     vanilla : {'host': '-x'}
#     argparse: SystemExit 2 - bug223.py: error: argument --host: expected one argument
#     click   : exit 0 - merged {'host': '-x'}
#     cyclopts: SystemExit 1 - Parameter --host requires an argument.
#   ['--host', '-h']
#     vanilla : {'host': '-h'}
#     argparse: SystemExit 2 - bug223.py: error: argument --host: expected one argument
#     click   : exit 0 - merged {'host': '-h'}
#     cyclopts: SystemExit 0 - Usage: demo [OPTIONS]
#   ['--config', '-x']
#     vanilla : InvalidConfigFileError: Cannot tell the format of ...\-x: it has no file extension. ...
#     argparse: ConfargError: Missing file path after --config. Usage: --config /path/to/config.yaml
#     click   : exit 0 - InvalidConfigFileError: Cannot tell the format of ...\-x: it has no file extension. ...
#     cyclopts: SystemExit 1 - Unknown option: -x.
```
