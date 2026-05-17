# BUG-146 — The alternative-directive notes in `19_bindings` exercise two of the five front-ends

**Where:** `examples/19_bindings/README.md` · **Filed:** 2026-10-03
**Effort:** S · **Risk:** low · **Impact:** none

The two `> [!NOTE]` callouts about the `_`-prefixed directive set (`_fn`/`_bind`, `_class`)
carry a visible vanilla block and one hidden argparse block, while every other command on
the page shows all five front-ends. Console blocks are the subprocess replay that covers
the example commands
([testing.md#examples-and-documentation](../../architecture/testing.md#examples-and-documentation)),
so the alternative directives are never exercised on click, cyclopts or typer anywhere in
the docs. Add the three hidden blocks to each note — the replay suite then covers them,
which is also what catches a wrong one.

## Reproduction

```console
$ grep -n "_fn greetings.print_greetings" examples/19_bindings/README.md
63:> $ uv run print_greetings.py --greet_fn._fn greetings.print_greetings --greet_fn._bind.greetings Hi
71:> $ uv run print_greetings_argparse.py --greet_fn._fn greetings.print_greetings --greet_fn._bind.greetings Hi
# expected: five blocks, one per front-end (vanilla, argparse, click, cyclopts, typer),
#           as for the un-prefixed `--greet_fn.fn` command at lines 13-37
# actual:   two — the same for `_class` at lines 175 and 183
```
