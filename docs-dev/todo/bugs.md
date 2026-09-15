# Bugs

Defects, unapproved divergences between front-ends or channels, and code that deviates from
the documented intent. See [README.md](README.md) for the ticket format, including the
[reproduction snippet](README.md#reproduction) every entry here carries.

## Parity gaps

Cross-channel parity is mandatory
([09-invariants.md#cross-channel-parity](../architecture/09-invariants.md#cross-channel-parity));
every entry here is a violation nobody has approved, not a design choice.

### BUG-3 — A root-level JSON cast is refused in the environment

**Where:** `src/confarg/_parse_env.py` (`_apply_env_json_cast`) · **Filed:** 2026-09-12
**Effort:** M · **Risk:** high

CLI `--json '{…}'` injects a whole configuration; `<PREFIX>JSON` is declined at the root, then
warned about as an unknown field and dropped, so the configuration silently keeps its defaults.
The fix belongs in the canonical cast path rather than in a second special case in `_parse_env`.

```python
from dataclasses import dataclass
import confarg

@dataclass
class Config:
    host: str = "localhost"
    port: int = 8080

blob = '{"host": "db", "port": 5432}'
print("cli:", confarg.load(Config, argv=["--json", blob]))
print("env:", confarg.load(Config, argv=[], env={"MYAPP_JSON": blob}, env_prefix="MYAPP_"))
# expected: cli: Config(host='db', port=5432)
#           env: Config(host='db', port=5432)
# actual:   cli: Config(host='db', port=5432)
#           ConfargWarning: Environment variable 'MYAPP_JSON' has no matching field
#           (segment 'json' not found in Config). Known fields: ['host', 'port'].
#           The variable will be ignored.
#           env: Config(host='localhost', port=8080)
```

### BUG-24 — A delete flag drops the callable shorthand it refines in the adapters

**Where:** `src/confarg/cli/_collect.py` (`_collect_callable_spec`) · **Filed:** 2026-09-15
**Effort:** M · **Risk:** low

A `--<field>.<sub>-` delete is a patch op, so it reaches the merged dict through
`_collect_cli_patch_ops`, not the flat collector. The collector therefore sees no sibling
flag beside the bare string, stores the shorthand alone, and the patch dict then deep-merges
over it — replacing the scalar instead of opening it, the way a whole value and its
refinement do everywhere else. Vanilla keeps both. The shorthand needs to survive the
deep merge with the patch ops, which is where the whole-value/patch split already bites
([04-cli-adapters.md#collection-patch-parity](../architecture/04-cli-adapters.md#collection-patch-parity)).
Found while fixing BUG-23; the crash it grew out of is gone, this parity gap is not.

```python
import argparse
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import confarg
from confarg.cli.argparse import merge_namespace, populate_parser


def shout(name: str, punct: str = ".") -> str:
    return f"{name.upper()}{punct}"


@dataclass
class Config:
    fn: Callable[..., Any] = str.upper


argv = ["--fn", "__main__.shout", "--fn.bind-"]
print("vanilla: ", confarg.merge(Config, argv=argv, env={}))
parser = argparse.ArgumentParser()
populate_parser(Config, parser, argv=argv)
print("argparse:", merge_namespace(Config, parser.parse_args(argv), argv=argv, env={}))
# expected: vanilla:  {'fn': {'fn': '__main__.shout', 'bind': _DELETE_}}
#           argparse: {'fn': {'fn': '__main__.shout', 'bind': _DELETE_}}
# actual:   vanilla:  {'fn': {'fn': '__main__.shout', 'bind': _DELETE_}}
#           argparse: {'fn': {'bind': _DELETE_}}
```

### BUG-25 — An escaped `_bind` beside a plain opener is vanilla-only

**Where:** `src/confarg/cli/_build.py` (`_escaped_opener_specs`) · **Filed:** 2026-09-15
**Effort:** S · **Risk:** low

Dynamic registration adds escaped flags only for the escaped *openers* actually typed, so a
`--<field>._bind.<param>` next to a *plain* opener is never registered and all three
adapters reject the flag outright. Vanilla accepts it and stores `_bind` as ordinary data —
the documented reading, since the opener's form alone selects the mode
([06-callables.md#plain-and-escaped-directives](../architecture/06-callables.md#plain-and-escaped-directives)).
Neither half is obviously right: the pair is very likely a user who meant `--<field>.bind`,
so the fix may be to register it and let construction raise on the stray kwarg, or to
reject it in vanilla too. Pre-existing, and the bare-string shorthand behaves exactly like
the explicit opener shown here; found while fixing BUG-23.

```python
import argparse
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import confarg
from confarg.cli.argparse import merge_namespace, populate_parser


def shout(name: str, punct: str = ".") -> str:
    return f"{name.upper()}{punct}"


@dataclass
class Config:
    fn: Callable[..., Any] = str.upper


argv = ["--fn.fn", "__main__.shout", "--fn._bind.punct", "!"]
print("vanilla: ", confarg.merge(Config, argv=argv, env={}))
parser = argparse.ArgumentParser()
populate_parser(Config, parser, argv=argv)
print("argparse:", merge_namespace(Config, parser.parse_args(argv), argv=argv, env={}))
# expected: both front-ends agree, whichever way the pair is settled
# actual:   vanilla:  {'fn': {'fn': '__main__.shout', '_bind': {'punct': '!'}}}
#           argparse: error: unrecognized arguments: --fn._bind.punct !
#                     SystemExit: 2
```

## Intent versus implementation

### BUG-4 — Stealing order does not match the documented rule

**Where:** `src/confarg/typedload/_coerce.py` (`_steal_order`) · **Filed:** 2026-09-12
**Effort:** M · **Risk:** high

Intended (confirmed by the maintainer, and what the tutorial in `examples/7_stealing_rule/`
teaches): `registered leaf > Enum > [float, int, bool, None] > str`. Implemented:
`Enum > other non-str types in declaration order > str`, with `None` and bool-vs-int handled
first — so the declaration order of the union decides what the documented rule fixes. Fix the
code, not the tutorial.
See [05-types-and-construction.md#stealing-rule](../architecture/05-types-and-construction.md#stealing-rule).

```python
from dataclasses import dataclass
from decimal import Decimal
import confarg

confarg.register_leaf_type(Decimal, Decimal)

@dataclass
class A:
    v: int | Decimal = 0

@dataclass
class B:
    v: Decimal | int = 0

print("A:", repr(confarg.load(A, argv=["--v", "5"]).v))
print("B:", repr(confarg.load(B, argv=["--v", "5"]).v))
# expected: A: Decimal('5')   — a registered leaf outranks int whatever the order
#           B: Decimal('5')
# actual:   A: 5              — declaration order wins
#           B: Decimal('5')
# The documented float-before-int rule goes the same way: `int | float` gives 5,
# `float | int` gives 5.0.
```

### BUG-7 — Typer integration is claimed, never tested, and currently broken

**Where:** `src/confarg/cli/click/_register.py`, `tests/cli/click/` · **Filed:** 2026-09-12
**Effort:** L *(XL if typer becomes a supported front-end)* · **Risk:** medium

`README.md` and `docs/index.md` both promise confarg "can integrate with your favorite argument
parser library such as `argparse`, `click`, `typer` or `cyclopts`". Nothing verifies the typer
half: `typer` is in the `dev` dependency group (`pyproject.toml:37`) but no test, example or
module imports it, and the four front-ends behind the `loader` fixture are argparse, click,
cyclopts and vanilla only.

Registration is fine — every expected option, subkeys included, lands on the `TyperCommand` —
but invocation dies, because typer supplies its own `Context` from its vendored click shim
while the adapter registers real `click.Option` instances. Isolated from confarg: appending a
bare `click.Option` to a typer command reproduces it identically (typer 0.27.2, click 8.5.0),
so the fix direction is a seam letting the option class be `typer.core.TyperOption` when the
command is a typer command, rather than anything in the merge path.

Decide the scope first, since it sets the parity obligation: if typer is a supported
front-end it needs the shared `loader`-fixture contract like the other three
([12-testing.md](../architecture/12-testing.md)); if it is merely "click underneath, at your
own risk", the two documentation claims must say so. Either way the claim and the test suite
have to agree.
See [04-cli-adapters.md](../architecture/04-cli-adapters.md).

```python
from dataclasses import dataclass
import typer
from confarg.cli.click import populate_command, from_context

@dataclass
class Config:
    host: str = "localhost"

app = typer.Typer()

@app.command()
def main(ctx: typer.Context) -> None:
    print(from_context(Config, ctx))

command = typer.main.get_command(app)
populate_command(Config, command, argv=["--host", "db"])
command(["--host", "db"], standalone_mode=False)
# expected: Config(host='db')
# actual:   AttributeError: 'Context' object has no attribute '_param_default_explicit'
#           raised from click/core.py, Parameter.handle_parse_result
```

### BUG-15 — `dump()` drops a leaf a union variant will steal back

**Where:** `src/confarg/_serialize.py` (`_serialize_union`) · **Filed:** 2026-09-13
**Effort:** L · **Risk:** medium

`load(dump(x)) != x`, the one round trip
[01-pipeline-and-contracts.md#public-api-seams](../architecture/01-pipeline-and-contracts.md#public-api-seams)
does promise. Native file values are matched in declaration order, so any `Enum`, `Literal`,
registered leaf or type-ref variant ahead of the scalar steals the bare scalar on the way back
in; `Path | str` holding a plain `str` goes the same way. No `_Pinned` is involved — this is the
typed sibling of the pin `_serialize_untyped` now writes back
([05](../architecture/05-types-and-construction.md#cast-pinning-in-files)), and unlike that
type-blind path the typed one knows the declared type and can decide. Fix direction: a
`_needs_cast` check on leaf variants mirroring `_needs_tag` on struct variants — emit `{__cast__, __value__}` only when re-reading the bare scalar would not
select the variant that produced it. Precedent: YAML emitters tag a scalar (`!!str 5`) exactly
when the plain form would resolve to another type. It changes `dump()` output, so it needs a
decision recorded in [10-design-decisions.md](../architecture/10-design-decisions.md).
See [05-types-and-construction.md#serialization](../architecture/05-types-and-construction.md#serialization).

```python
from dataclasses import dataclass
from enum import Enum
import confarg

class Color(Enum):
    FOO = 1

@dataclass
class Config:
    v: Color | str = Color.FOO

original = Config(v="FOO")
blob = confarg.dump(original)
print("dump  :", blob)
print("reload:", confarg.build(Config, blob))
# expected: dump  : {'v': {'__cast__': 'str', '__value__': 'FOO'}}
#           reload: Config(v='FOO')      — equal to `original`
# actual:   dump  : {'v': 'FOO'}
#           reload: Config(v=<Color.FOO: 1>)
```
