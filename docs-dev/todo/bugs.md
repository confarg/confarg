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

### BUG-19 — A subclass field is dropped when its class tag came from a config file

**Where:** `src/confarg/cli/_collect.py` (`_collect_ns_inheritance`) · **Filed:** 2026-09-15
**Effort:** M · **Risk:** medium

`_collect_ns_inheritance` descends into the tagged subclass only when the tag is in the *flat
CLI result*; a tag read from a `--config` file leaves the collector walking the base class, so
a subclass field typed on the CLI has nowhere to go and is silently dropped. Vanilla resolves
the same path through the type tree and keeps it. Found while fixing BUG-6, and independent of
it — it reproduces with a subclass that was imported all along. The tag is already collected
for registration by `_tags.collect_tags`, which is where the flat collector should read it
from too, rather than from `flat` alone.
See [04-cli-adapters.md#the-triad](../architecture/04-cli-adapters.md#the-triad).

```python
import argparse
from dataclasses import dataclass, field
from pathlib import Path

import confarg
from confarg.cli.argparse import from_namespace, populate_parser


@dataclass
class Handler:
    name: str = "base"


@dataclass
class FileHandler(Handler):
    path: str = "/var/log/a"


@dataclass
class Config:
    handler: Handler = field(default_factory=Handler)


Path("app.toml").write_text('[handler]\nclass = "__main__.FileHandler"\n')
argv = ["--config", "app.toml", "--handler.path", "/x"]

print("vanilla :", confarg.load(Config, argv=argv, env={}))
parser = argparse.ArgumentParser()
populate_parser(Config, parser, argv=argv)
print("argparse:", from_namespace(Config, parser.parse_args(argv), argv=argv, env={}))
# expected: vanilla : Config(handler=FileHandler(name='base', path='/x'))
#           argparse: Config(handler=FileHandler(name='base', path='/x'))
# actual:   vanilla : Config(handler=FileHandler(name='base', path='/x'))
#           argparse: Config(handler=FileHandler(name='base', path='/var/log/a'))
# click and cyclopts drop it identically.
```

### BUG-20 — A fixed-arity flag refuses in the adapters the whole-value token vanilla takes

**Where:** `src/confarg/cli/_build.py` (`_build_leaf_spec`, `_collect_namedtuple_specs`)
**Filed:** 2026-09-15 · **Effort:** M · **Risk:** medium

A `tuple[X, Y]` and a namedtuple register with the framework's exact token count, fixed before
argv is read, so the framework rejects the single whole-value token vanilla decodes —
`--pair '[13, 42]'` for either, and `--pair '{"x": 13}'` for the namedtuple. Not a namedtuple
property: both shapes lose the same spelling in the same three front-ends, which is why this is
one ticket. The `FlagSpec` vocabulary can express it (`nargs="*"` plus an arity check in
`cli/_collect.py`), but click renders `nargs="*"` as `multiple=True`, so that spelling would
cost click its `--pair 13 42` form and extend the approved list-syntax divergence
([04](../architecture/04-cli-adapters.md#list-syntax-divergence)) to fixed arity — a trade the
maintainer has to approve. An argv-scanned arity is the other candidate and contradicts
`build_static_flags`' promise that argv never changes the declared flag set.
See [04-cli-adapters.md#whole-value-flags](../architecture/04-cli-adapters.md#whole-value-flags).

```python
import argparse
from dataclasses import dataclass

import confarg
from confarg.cli.argparse import populate_parser


@dataclass
class Config:
    pair: tuple[int, int] = (0, 0)


argv = ["--pair", "[13, 42]"]
print("vanilla:", confarg.load(Config, argv=argv, env={}))
parser = argparse.ArgumentParser()
populate_parser(Config, parser, argv=argv)
print("argparse:", parser.parse_args(argv))
# expected: vanilla:  Config(pair=(13, 42))
#           argparse: Namespace(pair=[13, 42], ...)
# actual:   vanilla:  Config(pair=(13, 42))
#           argparse: r20.py: error: argument --pair: expected 2 arguments
#                     SystemExit: 2
```

### BUG-23 — A scalar whole value followed by a subkey crashes with a bare `TypeError`

**Where:** `src/confarg/_parse_cli.py` (`_consume_collection_or_scalar` → `_merge._set_nested`)
**Filed:** 2026-09-15
**Effort:** S · **Risk:** medium

`--<field> <scalar> --<field>.<sub> <v>` stores a `_StrToken` at the field path, then asks
`_set_nested` to descend through it, which raises Python's own `TypeError` out of the merge
core instead of a `ConfargError` naming the flag. Not type-specific: a dict field given a
non-JSON token and a callable field given the string shorthand fail identically, and the
adapters never reach it because their flat collector nests the paths itself. Either reject the
pair with a real error, or let the later subkey replace the scalar the way the adapters do
— that choice is the ticket. Found while fixing BUG-22.
See [03-cli-parsing.md#token-consumption](../architecture/03-cli-parsing.md#token-consumption).

```python
from collections.abc import Callable
from dataclasses import dataclass

import confarg


@dataclass
class Config:
    fn: Callable[[str], str] = str.upper


print(confarg.load(Config, argv=["--fn", "string.capwords", "--fn.bind.sep", "-"], env={}))
# expected: Config(fn=functools.partial(<function capwords ...>, sep='-'))
#           — what --fn.fn string.capwords --fn.bind.sep - already gives
# actual:   TypeError: '_StrToken' object does not support item assignment
# The same line on a dict field fails the same way:
#   confarg.merge(D, argv=["--d", "oops", "--d.c", "x"], env={})  # D.d: dict[str, str] | None
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

### BUG-21 — A union with a namedtuple variant cannot be built from a sequence

**Where:** `src/confarg/typedload/_construct.py` (`_construct_union_leaf`,
`_try_tuple_variants`) · **Filed:** 2026-09-15 · **Effort:** S · **Risk:** medium

`_construct_union_leaf` partitions the variants with `_is_tuple`, so a namedtuple variant lands
among the *scalar* leaves and is never offered the list. `str | tuple[int, int]` builds from
`[13, 42]`; `str | Point` refuses it, in every channel — this is below the parsers, so files,
env and CLI fail alike. The parse side already agrees with the tuple since a namedtuple became
sequence-shaped ([10](../architecture/10-design-decisions.md#a-namedtuple-is-a-fixed-length-sequence)),
which is what moved the failure down here. Fix direction: partition on
`_types._fixed_seq_types(...) is not None` rather than `_is_tuple`, in both the split and the
arity filter inside `_try_tuple_variants`, so the one function that answers "fixed arity, of
which types?" answers here too
([09](../architecture/09-invariants.md#delegate-to-the-canonical-function)).
See [05-types-and-construction.md#leaf-coercion](../architecture/05-types-and-construction.md#leaf-coercion).

```python
from dataclasses import dataclass
from typing import NamedTuple

import confarg


class Point(NamedTuple):
    x: int
    y: int


@dataclass
class Config:
    v: str | Point = "unset"


@dataclass
class Plain:
    v: str | tuple[int, int] = "unset"


print("tuple     :", confarg.build(Plain, {"v": [13, 42]}))
print("namedtuple:", confarg.build(Config, {"v": [13, 42]}))
# expected: tuple     : Plain(v=(13, 42))
#           namedtuple: Config(v=Point(x=13, y=42))
# actual:   tuple     : Plain(v=(13, 42))
#           namedtuple: TypeCoercionError: Cannot coerce list [13, 42] to str | Point at 'v'
```
