---
filed: 2026-10-07
where:
  - src/confarg/cli/_build.py::_collect_patch_argv_specs  # the subkey or element branch
effort: S
risk: low
impact: config  # `--pairs.a '[1, 2]'` parses on click today, and a field flag's exact count declines it
severity: minor  # the whole-value token is the workaround
introduced_by: [PR-72]  # fix: Close CLI-adapter parity gaps, which registered element flags nargs="*"
---
# BUG-198 — A fixed-arity element flag takes one token on click and typer

A subkey or element flag addressing a fixed-arity type (`--pairs.a` on a
`dict[str, tuple[int, int]]`, `--pairs.0` on a `list[tuple[int, int]]`) registers `nargs="*"`,
which click and typer map to `multiple=True`, one token per occurrence. So on click and typer
`--pairs.a 1 2` is refused with `Got unexpected extra argument (2)`, while the field flag of the
same type registers the exact count and takes `--pair 1 2`. The element flag accepts the
whole-value token `'[1, 2]'` that the field flag declines, the reverse of the approved
divergence
([whole-value flags](../../architecture/cli-adapters/whole-value-flags.md#whole-value-flags)).
Fix direction: register the element flag the way `_build_leaf_spec` registers the field flag of
that type, `nargs=<n>` and `whole_value=True`. argparse and cyclopts already register
`whole_value` greedily, so they keep taking both spellings and only click and typer change.

Origin: latent since PR-72, a bug fix that closed the adapters' parity gaps. Before it no adapter
registered a dict-subkey or list-element flag, and click refused `--pairs.a` with `No such option`
in either spelling (bisected with the reproduction). PR-72 registered every such flag `nargs="*"`
whatever type it addresses, which gave click the whole-value spelling and not the positional
one. BUG-180 shares this origin.

```python
from dataclasses import dataclass, field

import click

import confarg
from confarg.cli.click import from_context, populate_command


@dataclass
class Cfg:
    pair: tuple[int, int] = (0, 0)
    pairs: dict[str, tuple[int, int]] = field(default_factory=dict)


def run(argv):
    @click.command()
    @click.pass_context
    def cmd(ctx):
        print("click:  ", from_context(Cfg, ctx, argv=argv))

    populate_command(Cfg, cmd, argv=argv)
    print("vanilla:", confarg.load(Cfg, argv=argv, env={}))
    try:
        cmd.main(argv, standalone_mode=False)
    except click.UsageError as e:
        print("click:  ", type(e).__name__, e)


for argv in (["--pair", "1", "2"], ["--pairs.a", "1", "2"], ["--pairs.a", "[1, 2]"]):
    run(argv)

# expected: click takes `--pairs.a 1 2` as it takes `--pair 1 2` (typer alike)
# actual:
#   vanilla: Cfg(pair=(1, 2), pairs={})
#   click:   Cfg(pair=(1, 2), pairs={})
#   vanilla: Cfg(pair=(0, 0), pairs={'a': (1, 2)})
#   click:   UsageError Got unexpected extra argument (2)
#   vanilla: Cfg(pair=(0, 0), pairs={'a': (1, 2)})
#   click:   Cfg(pair=(0, 0), pairs={'a': (1, 2)})
```
