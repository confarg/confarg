# Quoted code keeps the formatter's spacing

Between a Markdown block and the prose around it, one blank line. Inside a fenced `python`
block, whatever `ruff format` gives that code: two blank lines around a top-level `def` or
`class`, one between statements. A blank-line sweep of the docs collapses the runs outside
code blocks and leaves the interiors alone — REF-80 was closed this way, its "collapse
each" having overstated the rule: the two blank lines in `examples/11_include/README.md`
(between two top-level dataclasses) and `examples/4_leaf_types/README.md` (after
`serialize_int`, before the `register_leaf_type` call) stay.

Why: the docs quote real, formatter-clean files — the `markdown-code-snippet` hook
regenerates the annotated blocks from them, and mkdocstrings renders the code it quotes
verbatim (observed: a double blank line inside a docstring's code block survives the build).
Collapsing an interior run makes the block disagree with the code it quotes, and a reader
who copies the snippet into a file gets a reformat diff: given the same code with one blank
line after a top-level `def`, `ruff format` re-expands it to two. Precedents: PEP 8 and every
Python formatter require the two blank lines; the sibling decision is
[line endings pinned in `.gitattributes`](line-endings-pinned-in-gitattributes.md) — the
convention is written down because no hook checks it. Cost: a docs sweep must know which
side of the fence it is on, and nothing mechanical flags a wrongly collapsed interior.
