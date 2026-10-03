# A registered leaf is never a struct variant

A type in `_LEAF_COERCIONS` is not taken apart into fields by anything that *infers* it should
be: not by the construction and serialization dispatchers, and not by the union-variant filters
on either side. Only an explicit tag still opens it, and that is
[an explicit tag opts a leaf back in](an-explicit-tag-opts-a-leaf-back-in.md#an-explicit-tag-opts-a-leaf-back-in).
The one
predicate is `_is_struct_variant`
([types](../types/leaf-coercion.md#leaf-coercion)); asking `_is_struct` was the bug. The
exception is the whole-value predicate, which runs *before* construction and must ask
`_is_struct` — see
[an explicit tag opts a leaf back in](an-explicit-tag-opts-a-leaf-back-in.md#an-explicit-tag-opts-a-leaf-back-in).

The distinction has teeth because `_is_struct` is structural: a class with any `__init__`
parameter is a struct, and `UUID.__init__` takes seven, all with defaults. So a field typed
`Release | UUID` — where `Release` is a struct with a `version` field, a name `UUID.__init__`
also uses — read as a union of two structs. `build()` refused `{"version": 2}` with
`AmbiguousUnionError`, and `dump()` emitted a `class` tag for a union holding exactly one
struct. The two defects hid each other: the spurious tag is what kept `load(dump(x)) == x`
working, so fixing either alone would have broken the round trip
([pipeline](../pipeline/api-seams.md#public-api-seams)).

This narrows what `build()` rejects: data that used to be ambiguous now constructs the struct.
That is the intended direction — registration is a promise that the type is opaque, and a
promise that holds in one direction only is worse than none. A registered leaf still claims
the *scalar* form of the same union through the leaf path, so neither variant loses its
spelling.

Precedent: cattrs treats a type with a registered structure hook as opaque and never considers
it in union disambiguation, which only ever looks at attrs classes. The rejected alternative —
keep the registry out of the union filters and require an explicit tag on every union with a
registered leaf in it — pushes the cost of an introspection accident onto every user of such a
union, to spell out a variant that the leaf path already resolves on its own.
