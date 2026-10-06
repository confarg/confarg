---
filed: 2026-10-05
where:
  - src/confarg/_parse_cli.py::_is_collection_patch_path
effort: S
risk: low
impact: none
severity: trivial
---
# REF-86 — The collection-patch question stops at a callable for nothing

`_is_collection_patch_path` stops a branch when it stands on a callable, but that stop never
changes the answer. Past a callable the walk stands on nothing but `str`
(`_advance_field_type` returns `str` for any key of a spec, and a bind key opens a `str`
subtree). A callable also holds no namespace, since `_locals_keys_nested` answers only for
structs and namedtuples. With the stop deleted, the full suite still passes. The question
then reads like `_addresses_callable_key`: does any stone of any branch stand on a
collection or enter a namespace. Since BUG-157 the callable is the only stop left.
[One walk, many questions](../../architecture/cli-parsing/type-guided-parsing.md#one-walk-many-questions)
uses that per-branch stop to argue why the walk yields branches rather than a stream of
nodes, and to reject a callback. When the stop goes, restate that argument from what still
needs branches (`_field_types` reads each branch's end) or drop it.
