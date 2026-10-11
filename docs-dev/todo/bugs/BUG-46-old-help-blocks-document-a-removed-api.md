---
filed: 2026-09-25
where:
  - examples/90_integration/README.md  # three `python` blocks under `## Old help`
effort: S
risk: low
impact: none
severity: minor  # the shipped scripts beside the README are correct
inferred: true  # from code reading, no test covers it
introduced_by: [PR-13, PR-28]  # PR-13 moved populate_parser and from_namespace out of confarg; PR-28 renamed args
---
# BUG-46 — The `90_integration` code blocks document an API that does not exist

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

Origin: regression. The three blocks are written against the initial version's API (PR-5), where
`confarg.populate_parser`, `confarg.from_namespace(namespace, Config)` and `confarg.load(args=…)`
existed. PR-13 moved the argparse functions out of `confarg`'s namespace and PR-28 renamed `args` to
`argv`. The README itself has no history on `origin/master`: it entered the repository only through
the local `wip` revision (jj `pxozrmwu`, author date 2026-05-17) stacked on PR-311, which names no
ticket or PR and adds 247 files. If that revision is dropped, this ticket and REF-81 go with it.

```console
$ uv run python -c "import confarg; confarg.populate_parser"
AttributeError: module 'confarg' has no attribute 'populate_parser'
```
