---
filed: 2026-10-10
where:
  - src/confarg/_types.py::_init_fields
  - src/confarg/_types.py::_struct_fields
  - src/confarg/_types.py::_dataclass_subclasses
  - src/confarg/_parse_cli.py::_locals_keys_at
effort: S
risk: medium  # an ordinary wrong answer fails the suite; a stale cache after class mutation stays silent
impact: none
severity: minor  # slowed, not stopped
---
# REF-92 — Class introspection is recomputed for every locals-namespace query

The type walk answers "is this segment a real field?" at every config-tree node
([locals.md#per-node-namespaces](../../architecture/locals.md#per-node-namespaces)), and for a
struct member the answer goes through the subclass scan
([casts-and-reserved-words.md#real-field-wins](../../architecture/cli-parsing/casts-and-reserved-words.md#real-field-wins)):
`_locals_keys_at` → `_struct_member_type` → `_subclass_field_type` → `_dataclass_subclasses`,
a BFS that calls `_struct_fields` on every subclass, each call re-running
`inspect.signature` and `typing.get_type_hints` on `__init__`. Nothing is memoized, so a
target with a field typed against a wide plain-class tree — albumentations'
`BasicTransform` in kitzen's example config, ~200 subclasses — re-inspects the same classes
hundreds of times per run: one `merge`+`build` made 10,915 `_init_fields` calls and 42,827
forward-ref `eval`s under cProfile.

Measured against kitzen's installed confarg with its `example/tst_time.py`: `merge` 1.16 s +
`build` 1.38 s. Wrapping `functools.lru_cache` around `_struct_fields`, `_init_fields`,
`_is_plain_class` and `_dataclass_subclasses` drops the same run to 0.067 s (~15x), so the fix
direction is to memoize the pure per-class helpers — and `_locals_keys`, whose docstring
already pins it to "target and union_tag only". Prefer a `WeakKeyDictionary` or a documented
invalidation point over `lru_cache`'s strong references, so dynamically created classes stay
collectable. Precedents: `dataclasses.fields()` serves the cached `__dataclass_fields__`,
and pydantic and attrs build and cache one schema per class.
