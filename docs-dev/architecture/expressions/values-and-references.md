# Values and references

## Value typing

A string that is exactly one `${expr}` keeps the expression's Python type (int, list, …).
Anything with surrounding text, including surrounding whitespace, is string interpolation.
`$${...}` is an escape producing the literal `${...}`.

## Referencing a whole subtree

A reference is a path, not a leaf selector: `_get_nested` returns whatever sits at that path,
so `${db}` is as valid as `${db.port}` and substitutes the entire node — dict, list or scalar.

**Value semantics, not identity.** Resolution finishes before construction begins
([pipeline](../pipeline/stages.md#the-pipeline)), so what a site references is raw data, never
an object. Construction then walks the resolved dict with no memo keyed by node identity, and
two sites referencing one node yield two objects that are equal and not identical. confarg
builds a value, not an object graph: sharing one instance between two fields is a
dependency-injection concern and stays out of scope, which is the same boundary that keeps the
library free of a container ([design decisions](../design-decisions/no-custom-types-required.md#no-custom-types-required)).

**The substituted node is the live sub-dict, not a copy.** `_get_nested` hands back the node
itself, so after `resolve()` the referencing path and the referenced path are one dict.
`build()` hides that — it constructs from the dict and drops it — but the three-step seam
([pipeline](../pipeline/api-seams.md#public-api-seams)) exposes it: mutating `resolved["db"]` in
place also mutates every path that referenced it. Copying on substitution would pay a deep copy
per reference to protect a caller the seam does not invite (its documented use is to inspect and
dump), so the aliasing stands as a limitation ([limitations](../limitations.md#expressions)) rather than a
defect.

**The union tag travels with the node.** A referenced struct carries its `class` key along, and
`_construct_struct_dispatch` honors a tag even on a non-union field
([types](../types/construction.md#union-construction)). The referencing field's *declared* type
therefore governs what is built: annotated with the tagged class it constructs, annotated with a
leaf type it is a coercion error — `${db.port}` is the reference for a single field.
