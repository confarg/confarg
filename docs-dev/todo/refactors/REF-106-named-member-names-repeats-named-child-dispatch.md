---
filed: 2026-10-20
where:
  - src/confarg/_naming.py::named_member_names
  - src/confarg/_naming.py::named_child
effort: S
risk: medium
impact: none
severity: trivial
---

# REF-106 — `named_member_names` repeats `named_child`'s dispatch, and has drifted from it

`named_member_names` is described as "the listing view of `named_child`", for the environment, which matches a segment's spelling case-insensitively against a list of names.
It does not derive the class from `named_child`'s decision but re-dispatches on its own: by the union tag on a struct or a taggable leaf, by `class:` / `classfn:` on a Callable or an `Any`.
The two have drifted already: `named_child` refuses a tag naming a class that is no subclass of the field's type (`issubclass(cls, tp)`), `named_member_names` lists that class's members anyway, so the environment spells a segment by a class the walk then declines to type by.
The visible effect is small today — the walk falls back to the declared type and construction refuses the tag — but it is the drift the [one naming](../../architecture/design-decisions/a-node-types-its-keys-by-the-class-it-names.md#a-node-types-its-keys-by-the-class-it-names) exists to prevent.

Fix direction: one `_named_class(tp, node, union_tag)` returning the class a node names, or None, which both `named_child` (for a key's type) and `named_member_names` (for the list) read.
