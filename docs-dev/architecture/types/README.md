# Types, coercion and construction

Everything below the channels: what the annotations say, how untyped text becomes a typed
value, and how the typed value gets back out. Implementation: `_types.py`, `typedload/**`,
`_serialize.py`, `_import.py`.

| Note | What it holds |
|---|---|
| [introspection.md](introspection.md) | what a plain annotation is read to mean, with no base class or field marker, and the one shape every walk dispatches on |
| [token-model.md](token-model.md) | `_StrToken`, `_UnionSeqToken`, `_Pinned` — which values are text a channel carried, and why they must not leak |
| [leaf-coercion.md](leaf-coercion.md) | the leaf registry, the eager/raising split, and what counts as a struct on the way in |
| [stealing-rule.md](stealing-rule.md) | which variant of a union takes a token, and the `{__cast__, __value__}` escape hatch on both sides |
| [construction.md](construction.md) | union dispatch, subclasses through the tag, and how structs, collections and defaults are built |
| [serialization.md](serialization.md) | the inverse of construction, typed and untyped |
| [dotted-imports.md](dotted-imports.md) | the one reader and the one writer of a dotted path |
