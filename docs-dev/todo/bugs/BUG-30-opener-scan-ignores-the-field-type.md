# BUG-30 — The argv opener scan reads a struct field named `fn` as a callable opener

**Where:** `src/confarg/cli/_build.py` (the argv scan behind `build_dynamic_flags`) · **Filed:** 2026-09-17
**Effort:** M · **Risk:** medium · **Impact:** config

`--<path>.fn <dotted>` is taken as an opener naming a callable at `<path>` without asking
whether `<path>` is callable-typed, so a plain struct with a field literally called `fn`
(or `class`, or `call`) also buys that target's bind flags. The scan is not type-guided,
which is the very thing the whole-value blob walk avoids by feeding a type-guided walk
instead of pattern-matching argv
([04-cli-adapters.md#whole-value-flags](../../architecture/04-cli-adapters.md#whole-value-flags)).
argparse and click only register flags nobody will type; cyclopts fails outright, because
the spurious specs carry a group named after the struct and described as bind arguments,
which collides with the struct's own group. Found while fixing BUG-24.

```python
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import cyclopts

import confarg
from confarg.cli import build_dynamic_flags
from confarg.cli.cyclopts import merge_app, populate_app


def shout(name: str, punct: str = ".") -> str:
    return f"{name.upper()}{punct}"


@dataclass
class Inner:
    """A struct whose field is spelled like a callable opener."""

    fn: Callable[..., Any] = str.upper


@dataclass
class Config:
    inner: Inner = field(default_factory=Inner)


argv = ["--inner.fn", "__main__.shout"]
print("dynamic:", [s.name for s in build_dynamic_flags(Config, argv)])
print("vanilla:", confarg.merge(Config, argv=argv, env={}))
app = cyclopts.App()
populate_app(Config, app, argv=argv)
try:
    print("cyclopts:", merge_app(Config, app, argv=argv, env={}))
except Exception as e:
    print("cyclopts:", type(e).__name__, e)
# expected: dynamic: ['inner.fn.bind.name', 'inner.fn.bind.punct']
#           vanilla: {'inner': {'fn': '__main__.shout'}}
#           cyclopts: {'inner': {'fn': '__main__.shout'}}
# actual:   dynamic: ['inner.fn.bind.name', 'inner.fn.bind.punct', 'inner.bind.name', 'inner.bind.punct']
#           vanilla: {'inner': {'fn': '__main__.shout'}}
#           cyclopts: ValueError Cannot register 2 distinct Group objects with same name.
```
