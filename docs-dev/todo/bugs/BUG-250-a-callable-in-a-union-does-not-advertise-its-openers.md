---
filed: 2026-10-17
where:
  - src/confarg/cli/_build.py::_specs_for_field  # the `_is_callable(core)` branch, which a union never reaches
effort: S
risk: medium  # registration is shared by the four adapters; a static flag can collide with a struct variant's field
impact: behavior
severity: minor  # the flags parse in every front-end once typed; only --help leaves them out
introduced_by: [PR-13]  # the earliest revision `_build_callable_fn_specs` appears in (log search on the symbol)
---
# BUG-250 — A Callable in a union does not advertise its openers

An adapter registers a lone Callable field's four openers statically, so `--help` lists `--f.bind`, `--f.call`, `--f.class` and `--f.classfn`. For a Callable beside another variant, `Callable[[int], int] | Level`, it lists only `--f.class`, which it registers as the union tag, and the struct variant's fields. The other openers parse in all five front-ends, and are registered once argv types them (BUG-234 made the union build them), but a user reading `--help` cannot discover them. The static branch of `_specs_for_field` tests `_is_callable` on the field's type with only an optional unwrapped. Fix direction: register a Callable variant's openers as a lone Callable's are, unless a struct variant owns the opener's name, the rule construction applies ([callables](../../architecture/callables.md#a-callable-beside-another-variant)).

Origin: latent since the first registration of a Callable's opener flags (PR-13, the earliest revision the log search finds `_build_callable_fn_specs` in), which keyed them on a field that unwraps to a Callable. A union holding one was never built before BUG-234, so its flags were never missed.

```python
import argparse
from collections.abc import Callable
from dataclasses import dataclass, field

import confarg.cli.argparse as cap


@dataclass
class Level:
    level: int = 0


@dataclass
class Lone:
    f: Callable[[int], int] = abs


@dataclass
class InUnion:
    f: Callable[[int], int] | Level = field(default_factory=Level)


for target in (Lone, InUnion):
    parser = argparse.ArgumentParser()
    cap.populate_parser(target, parser, config_flag="")
    print(target.__name__, sorted(o for a in parser._actions for o in a.option_strings if o.startswith("--f")))

# expected: InUnion lists --f.bind, --f.call, --f.class and --f.classfn as Lone does
# actual:
#   Lone ['--f', '--f.bind', '--f.call', '--f.class', '--f.classfn']
#   InUnion ['--f', '--f.class', '--f.level']
```
