# Include semantics

`__include__` accepts a path, a `{path: …, <format options>}` dict, or a list of either. So do
the other two mount routes, which read their value with the same parser ([mounting](mounting.md#mounting)).

- Paths are relative to the including document's own location, local or remote
  ([relative includes resolve within one origin](locations-and-schemes.md#relative-includes-resolve-within-one-origin)).
- A list is layered left to right into one value first, so the list form means the same in a
  dict node and in a list item. Dict entries deep-merge, mirroring repeated `--config`, and
  they deep-merge under `union_tag`, so a class tag in a later entry discards the earlier node
  exactly as it does across `--config` files
  ([design decisions](../design-decisions/class-tag-replaces.md#a-class-tag-replaces-not-merges)).
- A pure include (no sibling keys) may yield any type; with siblings the include must yield a
  dict, and siblings merge on top (they were written by the including file). They are resolved
  first, so a sibling that is itself an include wins over the included document as a plain value
  would: `{__include__: base.yaml, db: {__include__: db.yaml}}` keeps `db.yaml`'s `host` over
  `base.yaml`'s. Merged first and resolved after, the included document's keys would have become
  siblings of the inner include and won instead.
- In a list, an include lands as **one** element, whatever type it yields. Spreading a value
  over several elements is the `+` operator's job and nothing else's
  ([design decisions](../design-decisions/plus-is-a-merge-operator.md#the--suffix-is-a-merge-operator-not-a-list-spelling)), so
  `items+: {__include__: rows.yaml}` extends the list with the fragment's items while
  `items: [{__include__: rows.yaml}]` adds the fragment itself. `--config.items+ rows.yaml` is
  the first of those, in the CLI channel.
- A fragment whose whole content is one value names it under `__root__`. TOML has no list or
  scalar root, so that is the only way a TOML fragment carries one; only a lone `__root__`
  unwraps, and a *document* root never does, because there `__root__` is a non-struct target's
  value and `build()` is what reads it.
- `__include__` with a value it cannot use (`null`) raises in a dict node and in a list item
  alike: one key, one rule.
- Cycle detection: `seen` grows **per entry**, not across a list. Sibling entries are
  sequential layers, not nesting, so naming the same file twice is legal while a genuine
  cycle still raises.
