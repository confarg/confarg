---
filed: 2026-10-20
where:
  - src/confarg/typedload/_construct.py::read_union_leaf
  - src/confarg/_typed_read.py::_read_leaf
effort: S
risk: low  # behavior-preserving today: no dict value reaches the leaf reading
impact: none
severity: trivial
---

# REF-99 — `read_union_leaf` reads a union's variants under the default `union_tag`

`read_union_leaf` passes `_defaults.UNION_TAG` where construction passes the configuration's own tag to the same walk (`_first_scalar_variant_taking`), and `TypedReading` holds the union tag only to drop it: `_read_leaf` calls `read_union_leaf(tp, value)` and `read_as_object(tp, value)` with no tag of their own.

Nothing is wrong today because only a dict value reads the tag (`_construct_scalar`'s taggable-leaf branch and its tag-key refusal), and a dict never reaches `_read_leaf` — `_read` walks dicts and lists itself.
That is an accident of the callers, not a rule the reading states: a future caller handing `read_union_leaf` a dict silently gets the default tag's behavior, where construction gets the configuration's.

Fix direction: thread the union tag through `_typed_read` into `read_union_leaf` — and `read_as_object`, whose `_coerce_leaf` reaches no tag-reading branch today — so the reading spells the tag construction does ([a typed leaf reads as its object](../../architecture/expressions/values-and-references.md#a-typed-leaf-reads-as-its-object)).
