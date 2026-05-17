# Some quoted blocks stay hand-copied

Under `examples/`, a fenced `python` or `yaml` block is generated from a real file wherever
one exists — the `markdown-code-snippet` hook rewrites the block from it, so the two cannot
drift ([quoted code keeps the formatter's spacing](quoted-code-keeps-formatter-spacing.md#quoted-code-keeps-the-formatters-spacing)).
Three kinds of block stay hand-copied on purpose, each because no honest source exists to
quote:

- **A bare expression quoted out of a function.** `confarg.load(PostgreSQLConfig,
  env_prefix="MYAPP_")` in `1_three_input_sources`, `config.greet_fn("world")` in
  `18_callables`, the `merge()`/`dump_file()`/`build()` trio in `23_local_variables`, and
  the `register_leaf_type` calls in `4_leaf_types` (the second one is `main()`'s own line,
  unreachable by a selector). The hook quotes whole files or whole symbols; showing the
  whole `main()` to illustrate a one-liner trades teaching for generation, and inventing a
  file that only exists to be quoted adds dead example code.
- **A staged teaching variant.** `4_leaf_types` first registers `Int` without a `serialize`
  argument and introduces the serializer a page later, while the shipped
  `custom_leaf_type.py` registers with both. The block teaches the progression, and quoting
  the script would spoil it.
- **A file the run itself writes.** `22_variable_scopes` shows the `saved_config_*.yaml`
  files a `dump_file()` produces. They are `gitignore`d, so annotating them fails the hook
  on a clean checkout.

The two `type Config = …` blocks (`6_unions`, `9_child_configurations`) are not a decision:
their sources exist, and they move to annotations as soon as the hook names a `type`
statement — filed upstream as FEAT-6 in `markdown-code-snippet` — and a release carrying it
is pinned. The bare-expression kind would retire the same way if the upstream marker
regions (FEAT-1 there) landed; until then the drift risk these blocks carry is the price of
teaching prose, and nothing mechanical flags one that disagrees — which is how
`pair_of_ints.yaml` drifted before the hook existed (REF-59).

Why: the alternatives are worse. A fake source file rots invisibly the same way, but in a
file the reader can also open; and the docs' spacing rule
([quoted code keeps the formatter's spacing](quoted-code-keeps-formatter-spacing.md#quoted-code-keeps-the-formatters-spacing))
only holds because quoted code is real. Precedents: Sphinx's `literalinclude` reaches a
file at the same granularity — whole file or marker-delimited span — and its ecosystem
accepts hand-copied snippets where no marker exists. Cost: a sweep must know which blocks
are generated and which are authored, and a hand-copied block can silently disagree with
the code it describes.
