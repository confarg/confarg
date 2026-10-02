# BUG-46 — The `90_integration` code blocks document an API that does not exist

**Where:** `examples/90_integration/README.md` (three `python` blocks under `## Old help`) ·
**Filed:** 2026-09-25 · *(inferred — from code reading, no test covers it)*
**Effort:** S · **Risk:** low · **Impact:** none

The three python blocks call `confarg.load(Config, args=ctx.args)`,
`confarg.populate_parser(Config, parser)` and `confarg.from_namespace(namespace, Config)`.
None of those exist: the shipped scripts beside the README use
`confargclick.from_context(Config, ctx)` and `confargclick.populate_command(Config, run)`
(`myapp_click.py`), and `confarg_ap.make_parser(Config)` with
`confarg_ap.from_namespace(Config, namespace)` (`myapp_argparse.py`) — note the reversed
argument order. A reader copying these blocks gets an `AttributeError`.

The blocks sit in prose, not in a `console` block, so `pytest-markdown-console` never replays
them and nothing catches this. Fix direction: rewrite the three blocks against the real scripts
and annotate them with `<!-- snippet: myapp_click.py#run -->` and friends, so the
`markdown-code-snippet` hook keeps them honest. The remaining unannotated blocks are tracked in
[../refactors/REF-59-example-code-blocks-not-generated.md](../refactors/REF-59-example-code-blocks-not-generated.md).

```console
$ uv run python -c "import confarg; confarg.populate_parser"
AttributeError: module 'confarg' has no attribute 'populate_parser'
```
