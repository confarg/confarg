# BUG-7 — Typer integration is claimed, never tested, and currently broken

**Where:** `src/confarg/cli/click/_register.py`, `tests/cli/click/` · **Filed:** 2026-09-12
**Effort:** L *(XL if typer becomes a supported front-end)* · **Risk:** medium · **Impact:** behavior

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
([12-testing.md](../../architecture/12-testing.md)); if it is merely "click underneath, at your
own risk", the two documentation claims must say so. Either way the claim and the test suite
have to agree.
See [04-cli-adapters.md](../../architecture/04-cli-adapters.md).

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
