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

### BUG-6 — The subclass selector flag is registered only for subclasses already imported

**Where:** `src/confarg/cli/argparse/_build.py` (`tp.__subclasses__()`) · **Filed:** 2026-09-12
**Effort:** L · **Risk:** medium

`_collect_struct_specs` registers the `--<field>.<union_tag>` selector only when
`tp.__subclasses__()` is non-empty at parser-build time, so a plugin subclass that has not been
imported yet leaves the host parser with no way to name it. The subclass's own field flags do
arrive — the argv scan imports the class named by `--<field>.class` and registers them — so the
selector is the single missing flag, and the same keys in a config file succeed because
`build()` imports the tagged class itself. The same import dependence is why subclass inference
was rejected ([10-design-decisions.md#no-implicit-subclass-inference](../architecture/10-design-decisions.md#no-implicit-subclass-inference));
here it leaks into the CLI channel.
See [04-cli-adapters.md#union-inheritance-and-cast-flags](../architecture/04-cli-adapters.md#union-inheritance-and-cast-flags).

```python
# handlers.py
from dataclasses import dataclass

@dataclass
class Handler:
    name: str = "base"
```

```python
# plugins.py — a plugin module the application does not import
from dataclasses import dataclass
from handlers import Handler

@dataclass
class FileHandler(Handler):
    path: str = "/var/log/a"
```

```python
# app.py
import argparse
from dataclasses import dataclass, field
from handlers import Handler
from confarg.cli.argparse import populate_parser, from_namespace

@dataclass
class Config:
    handler: Handler = field(default_factory=Handler)

argv = ["--handler.class", "plugins.FileHandler", "--handler.path", "/var/log/a"]
parser = argparse.ArgumentParser()
populate_parser(Config, parser, argv=argv)
print(from_namespace(Config, parser.parse_args(argv), argv=argv))
# expected: Config(handler=FileHandler(name='base', path='/var/log/a'))
#           — what the same keys in a file already build:
#           confarg.build(Config, {"handler": {"class": "plugins.FileHandler",
#                                              "path": "/var/log/a"}})
# actual:   app.py: error: unrecognized arguments: --handler.class plugins.FileHandler
#           (--handler.path was registered; only the selector is missing)
```

### BUG-16 — A NamedTuple takes a whole `{...}` token in the environment but not on the CLI

**Where:** `src/confarg/_parse_cli.py` (`_accepts_object_value`) · **Filed:** 2026-09-14
**Effort:** S · **Risk:** medium

`_parse_env` tests `_is_namedtuple` in both its direct and its union arm; `_accepts_object_value`
tests `_is_dc`, which a NamedTuple is not, so neither `NT` nor `NT | None` qualifies and the CLI
stores the token raw. Fixing it means adding the arm *and* checking it against the fixed-tuple
consumption path a NamedTuple field also has
([03-cli-parsing.md#token-consumption](../architecture/03-cli-parsing.md#token-consumption)),
which the `{`-prefix guard should keep out of the way.
See [10-design-decisions.md#optionality-does-not-change-what-a-whole-value-accepts](../architecture/10-design-decisions.md#optionality-does-not-change-what-a-whole-value-accepts).

```python
from dataclasses import dataclass
from typing import NamedTuple
import confarg

class NT(NamedTuple):
    a: int
    b: int = 2

@dataclass
class Config:
    nt: NT = NT(1)

print("env:", confarg.load(Config, argv=[], env={"MYAPP_NT": '{"a": 5}'}, env_prefix="MYAPP_"))
print("cli:", confarg.load(Config, argv=["--nt", '{"a": 5}']))
# expected: env: Config(nt=NT(a=5, b=2))
#           cli: Config(nt=NT(a=5, b=2))
# actual:   env: Config(nt=NT(a=5, b=2))
#           cli: TypeCoercionError: Cannot construct NT at 'nt': expected list, tuple,
#                or dict, got _StrToken '{"a": 5}'
```

### BUG-17 — `Callable | None` does not accept the whole-spec token that `Callable` does

**Where:** `src/confarg/_parse_cli.py` (`_accepts_object_value`),
`src/confarg/_parse_env.py` (`_store_env_value`) · **Filed:** 2026-09-14
**Effort:** S · **Risk:** medium

A whole-spec token decodes on a `Callable[...]` field and is kept raw on the optional one, in
both channels, so it reaches the importer as if it were a symbol name. Same shape as the dict
case, and the rule is already recorded — optionality is not a statement about syntax — so this
is applying it, not deciding it. Both channels move together, as they did there: the callable
arms are `_is_callable` in `_accepts_object_value` and in `_parse_env._store_env_value`'s
`accepts_obj`, and neither union arm asks about callables. Watch the spec/bind merge in
`cli/_collect.py` (`_whole_value` → `_merge_blob_into_spec`), which the raw path never reaches
today.
See [10-design-decisions.md#optionality-does-not-change-what-a-whole-value-accepts](../architecture/10-design-decisions.md#optionality-does-not-change-what-a-whole-value-accepts).

```python
from collections.abc import Callable
from dataclasses import dataclass
import confarg

@dataclass
class Plain:
    fn: Callable[[str], str] = str.upper

@dataclass
class Opt:
    fn: Callable[[str], str] | None = None

spec = '{"fn": "string.capwords"}'
print("plain:", confarg.load(Plain, argv=["--fn", spec]).fn)
print("opt  :", confarg.load(Opt, argv=["--fn", spec]).fn)
# expected: plain: <function capwords ...>
#           opt  : <function capwords ...>
# actual:   plain: <function capwords ...>
#           opt  : SymbolImportError: Cannot import '{"fn": "string.capwords"}':
#                  no importable module found in path
# The env channel fails identically, with env={"MYAPP_FN": spec}, env_prefix="MYAPP_".
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
