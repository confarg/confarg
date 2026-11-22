---
filed: 2026-11-12
where:
  - src/confarg/_parse_cli.py::_parse_cli  # the host_parsed skip branches
  - src/confarg/_parse_cli.py::_skip_flag_values  # skips a host flag's values up to the next flag-shaped token
effort: M  # the design pass: how the loop learns what the host bound (a `--` it honored, a host option's arity)
needs_design: true
risk: medium  # adapters only; vanilla has no host and is unaffected
impact: config  # a command line that sets the confarg field today would stop doing so
severity: critical  # silent: the host and confarg both take the token, with no error anywhere
introduced_by: [PR-72, REF-72]  # PR-72's patch scan read patch flags off argv; REF-72 (PR-274) made the loop over argv write every flag
---

# BUG-332 — A token the host framework bound as a value is read again as a confarg flag

On the adapters, confarg's CLI channel is vanilla's loop over the argv the user typed, run in `host_parsed` mode ([argv is the only writer](../../architecture/cli-adapters/model.md#argv-is-the-only-writer)).
The loop skips a host flag "with its values", but it counts as values only the tokens that do not look like a flag (`_skip_flag_values`).
It also treats a `--` as an ordinary token.
The host framework binds more than that.
A token that spells a confarg flag ends up taken twice, once by the host and once by confarg, with no error:

- **The value of a host option** on click and typer, which bind the next token whatever it starts with.
  With `--name --host x`, the host gets `name='--host'` and the positional `x`, and confarg gets `host='x'`.
- **A positional after `--`** on argparse, click and typer, which all honor the separator.
  With `-- --host y`, the host gets `rest=['--host', 'y']`, and confarg gets `host='y'`.

Vanilla is not affected, since it has no host. cyclopts was not checked: a host cannot add a positional to confarg's default command.
The fix needs the loop to know what the host bound.
That is not evident:

- a `--` the host honored could end the loop's reading in `host_parsed` mode;
- a host option's arity is the framework's to report (click's `Option.nargs`, argparse's action `nargs`), and the loop has no channel for it today.

Related: [FEAT-17](../features/FEAT-17-end-of-options-separator.md), vanilla's own `--`, whose design pass has to agree with whatever the loop does with the host's `--`.
A pre-parse refusal scan such as the one [BUG-96](BUG-96-a-bare-scalar-flag-exits-with-the-frameworks-own-error-on-the-adapters.md) would add on click reads argv the same way, so it would inherit this bug and not add a new one.

Origin: REF-72 (PR-274) replaced the adapters' collector, which read field values off the framework's parse result, with vanilla's loop over argv.
That made the loop the only writer for every flag, and from then on it took a token the host had bound.
Before it, a field flag spelled after `--` or as a host option's value was never written.
That is checked: this reproduction gives `confarg: {}` on all three lines at PR-274's parent and the actual output below at PR-274.
Patch flags (`--d.a 1`) were already read off argv by the patch scan PR-72 added (`_parse_cli(..., patch_only=True)`), so for them the bug is latent since PR-72.
That is checked too: `-- --d.a 1` on argparse merges `{'d': {'a': 1}}` at PR-274's parent.
REF-72 was a refactor and closed no bug, so this is a regression it introduced, not the second half of a fix loop.

```python
import argparse
from dataclasses import dataclass

import click

from confarg.cli.argparse import merge_namespace, populate_parser
from confarg.cli.click import merge_context, populate_command


@dataclass
class T:
    host: str = "x"


# argparse: the host's positionals, after the `--` argparse honors
argv = ["--", "--host", "y"]
parser = argparse.ArgumentParser()
parser.add_argument("rest", nargs="*")
populate_parser(T, parser, argv=argv)
ns = parser.parse_args(argv)
print("argparse", argv, "host:", {"rest": ns.rest}, "confarg:", merge_namespace(T, ns, argv=argv, env={}))


# click: the value of the host's own --name option, and the host's positionals after `--`
def run(argv: list[str]) -> None:
    def callback(name: str | None, rest: tuple[str, ...]) -> tuple:
        return {"name": name, "rest": rest}, merge_context(T, click.get_current_context(), argv=argv, env={})

    cmd = click.Command("cli", callback=callback, params=[click.Option(["--name"]), click.Argument(["rest"], nargs=-1)])
    populate_command(T, cmd, argv=argv)
    host, merged = cmd.main(argv, standalone_mode=False)
    print("click   ", argv, "host:", host, "confarg:", merged)


run(["--name", "--host", "x"])
run(["--", "--host", "y"])

# expected: confarg: {} on every line (the host bound those tokens; the CLI channel does not write host)
# actual (typer answers as click does):
#   argparse ['--', '--host', 'y'] host: {'rest': ['--host', 'y']} confarg: {'host': 'y'}
#   click    ['--name', '--host', 'x'] host: {'name': '--host', 'rest': ('x',)} confarg: {'host': 'x'}
#   click    ['--', '--host', 'y'] host: {'name': None, 'rest': ('--host', 'y')} confarg: {'host': 'y'}
```
