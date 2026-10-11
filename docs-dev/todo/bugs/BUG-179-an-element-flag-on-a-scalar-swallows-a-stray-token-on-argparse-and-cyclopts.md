---
filed: 2026-10-06
where:
  - src/confarg/cli/_build.py::_collect_patch_argv_specs  # the subkey or element branch
effort: M
risk: medium
impact: config
---
# BUG-179 — An element flag on a scalar swallows a stray token on argparse and cyclopts

`_collect_patch_argv_specs` registers every dict-subkey and list-element flag `nargs="*"`, even
when the type it addresses takes one token. So `--d.a 2 1` on a `dict[str, int]` hands argparse
and cyclopts both tokens as the flag's value, while vanilla's loop, the only writer
([adapter parity](../../architecture/cli-adapters/collection-patch-parity.md#collection-patch-parity)),
reads `2` and leaves `1` to the host, as a host positional. The `1` is dropped in silence.
Vanilla refuses it as a stray positional and click and typer refuse it at parse. A field flag
of the same type registers a scalar arity. The fix direction is to derive the element flag's
`nargs` from the type it addresses, as its `stands_bare` already is.

```python
from dataclasses import dataclass, field

import argparse

import cyclopts

import confarg
from confarg.cli.argparse import from_namespace, populate_parser
from confarg.cli.cyclopts import from_app, populate_app
from confarg.exceptions import ConfargError


@dataclass
class Cfg:
    d: dict[str, int] = field(default_factory=dict)
    xs: list[int] = field(default_factory=lambda: [0])


for argv in (["--d.a", "2", "1"], ["--xs.0", "2", "1"]):
    try:
        print("vanilla:", confarg.load(Cfg, argv=argv, env={}))
    except ConfargError as e:
        print("vanilla:", type(e).__name__, e)
    parser = argparse.ArgumentParser()
    populate_parser(Cfg, parser, argv=argv)
    print("argparse:", from_namespace(Cfg, parser.parse_args(argv), argv=argv))
    app = cyclopts.App()
    populate_app(Cfg, app, argv=argv)
    print("cyclopts:", from_app(Cfg, app, argv=argv))

# expected: argparse and cyclopts refuse the stray `1`, as vanilla (and click, typer) do
# actual:
#   vanilla: UnknownArgumentError Unexpected positional argument: '1'. All arguments must be named flags (e.g. --fieldname value).
#   argparse: Cfg(d={'a': 2}, xs=[0])
#   cyclopts: Cfg(d={'a': 2}, xs=[0])
#   vanilla: UnknownArgumentError Unexpected positional argument: '1'. All arguments must be named flags (e.g. --fieldname value).
#   argparse: Cfg(d={}, xs=[2])
#   cyclopts: Cfg(d={}, xs=[2])
```
