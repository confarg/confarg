# CLI adapters (argparse, click, typer, cyclopts)

A translation layer, never a second implementation: every adapter must produce exactly what
`confarg.load()` would ([invariants](../invariants.md#cross-channel-parity)). Implementation:
`cli/**`. What they translate *from* is [CLI parsing](../cli-parsing/README.md).

| Note | What it holds |
|---|---|
| [model.md](model.md) | why the adapters exist, the register/merge/build triple each one exports, and why framework defaults never enter |
| [clicklike-seam.md](clicklike-seam.md) | what click and typer share since typer forked click, and what each still supplies |
| [cli-prefix-boundaries.md](cli-prefix-boundaries.md) | the two boundaries `cli_prefix` is applied and removed at, and where each framework hides it |
| [flag-model.md](flag-model.md) | `FlagSpec`/`FieldMeta`, the framework-neutral contract between spec generation and the adapters |
| [static-and-dynamic-flags.md](static-and-dynamic-flags.md) | flags from the type walk, flags found by scanning argv, and why the second kind is best-effort |
| [whole-value-flags.md](whole-value-flags.md) | assigning an object in one token, fixed-arity flags and their bounds, and the namedtuple's two halves |
| [collection-patch-parity.md](collection-patch-parity.md) | the second parse over argv that recovers what a framework's parse result cannot express |
| [a-flag-that-stands-bare.md](a-flag-that-stands-bare.md) | flags legal with nothing after them, and the one marker with two readers that keeps them working |
| [parity.md](parity.md) | byte-identical merged dicts, and the choice gates that must let an expression through |
| [union-inheritance-and-cast-flags.md](union-inheritance-and-cast-flags.md) | registering a union tag and its variants' fields, and reading the same tag back |
| [framework-specifics.md](framework-specifics.md) | what each of the four frameworks spells its own way |
| [completion.md](completion.md) | shell completion per framework, and why it never raises |
| [list-syntax-divergence.md](list-syntax-divergence.md) | the approved spelling divergence, and what repeating a flag means in every front-end |
