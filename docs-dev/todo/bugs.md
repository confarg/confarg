# Bugs

Defects, unapproved divergences between front-ends or channels, and code that deviates from
the documented intent. See [README.md](README.md) for the ticket format.

## Parity gaps

Cross-channel parity is mandatory (CLAUDE.md); every entry here is a violation nobody has
approved, not a design choice.

### BUG-1 — Bare whole-dict flags behave differently in the adapters

**Where:** `src/confarg/_parse_cli.py`, `src/confarg/cli/argparse/_build.py` · **Filed:** 2026-09-12

`--locals VALUE` and `--<dictfield> VALUE` (assigning a whole mapping in one token): vanilla
`load()` reports a confarg error naming the real problem, while the adapters register no such
flag, so the framework rejects the token with its own unrelated message. The diagnosis, not
just the rejection, should be the same across front-ends.
See [08-locals.md#gap](../architecture/08-locals.md#gap).

### BUG-2 — Adapters cannot set a scalar root from the CLI

**Where:** `src/confarg/cli/` · **Filed:** 2026-09-12

A non-struct target is set from argv as `--<cli_prefix> VALUE`, but `cli_prefix` is
vanilla-only, so the adapters have no spelling for it. Environment variables and config files
set a scalar root in every front-end; the CLI does not.
See [03-cli-parsing.md#cli_prefix](../architecture/03-cli-parsing.md#cli_prefix).

### BUG-3 — A root-level JSON cast is refused in the environment

**Where:** `src/confarg/_parse_env.py` (`_apply_env_json_cast`) · **Filed:** 2026-09-12 ·
*(inferred — from code reading, no test covers it)*

CLI `--json '{…}'` injects a whole configuration, but `<PREFIX>JSON` is declined at the root
and then reported as an unknown field. Confirm with a test first: if it reproduces, the fix
belongs in the canonical cast path rather than a second special case in `_parse_env`.

### BUG-6 — Subclass flags are registered only for subclasses already imported

**Where:** `src/confarg/cli/argparse/_build.py` (`tp.__subclasses__()`) · **Filed:** 2026-09-12 ·
*(inferred — from code reading, no test covers it)*

Flag registration for a base-class field enumerates `__subclasses__()` at parser-build time, so
a subclass that has not been imported yet contributes no flags. Since unknown CLI flags are
errors, `--f.class=pkg.Sub --f.only_in_sub=1` would fail where the same keys in a file succeed —
`build()` imports the tagged class itself. The same import dependence is why subclass inference
was rejected ([10-design-decisions.md#no-implicit-subclass-inference](../architecture/10-design-decisions.md#no-implicit-subclass-inference));
here it leaks into the CLI channel. Confirm with a test first.
See [04-cli-adapters.md#union-inheritance-and-cast-flags](../architecture/04-cli-adapters.md#union-inheritance-and-cast-flags).

## Intent versus implementation

### BUG-4 — Stealing order does not match the documented rule

**Where:** `src/confarg/typedload/_coerce.py` (`_steal_order`) · **Filed:** 2026-09-12

Intended (confirmed by the maintainer, and what the tutorial in `examples/7_stealing_rule/`
teaches): `registered leaf > Enum > [float, int, bool, None] > str`. Implemented:
`Enum > other non-str types in declaration order > str`, with `None` and bool-vs-int handled
first. Fix the code, not the tutorial.
See [05-types-and-construction.md#stealing-rule](../architecture/05-types-and-construction.md#stealing-rule).

### BUG-7 — Typer integration is claimed, never tested, and currently broken

**Where:** `src/confarg/cli/click/_register.py`, `tests/cli/click/` · **Filed:** 2026-09-12

`README.md` and `docs/index.md` both promise confarg "can integrate with your favorite argument
parser library such as `argparse`, `click`, `typer` or `cyclopts`". Nothing verifies the typer
half: `typer` is in the `dev` dependency group (`pyproject.toml:37`) but no test, example or
module imports it, and the four front-ends behind the `loader` fixture are argparse, click,
cyclopts and vanilla only.

Probed, and it does not work. Registration is fine — `populate_command(Config,
typer.main.get_command(app), ...)` on a `TyperCommand` registers every expected option,
subkeys included — but invocation dies in `click.core.Parameter.handle_parse_result` with
`AttributeError: 'Context' object has no attribute '_param_default_explicit'`, because typer
supplies its own `Context` from its vendored click shim while the adapter registers real
`click.Option` instances. Isolated from confarg: appending a bare `click.Option` to a typer
command reproduces it identically (typer 0.27.2, click 8.5.0), so the fix direction is a seam
letting the option class be `typer.core.TyperOption` when the command is a typer command,
rather than anything in the merge path.

Decide the scope first, since it sets the parity obligation: if typer is a supported
front-end it needs the shared `loader`-fixture contract like the other three
([12-testing.md](../architecture/12-testing.md)); if it is merely "click underneath, at your
own risk", the two documentation claims must say so. Either way the claim and the test suite
have to agree.
See [04-cli-adapters.md](../architecture/04-cli-adapters.md).

## Error handling

### BUG-5 — `build_dynamic_flags` swallows every error

**Where:** `src/confarg/cli/argparse/_build.py` · **Filed:** 2026-09-12

Dynamic flag registration catches everything, so a genuine failure inside it is invisible: the
only symptom is the framework later rejecting a flag that should exist. At minimum the
swallowed exception should surface as a `ConfargWarning`.
