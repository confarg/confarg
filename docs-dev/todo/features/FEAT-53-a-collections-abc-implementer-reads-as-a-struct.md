---
filed: 2026-10-18
where:
  - src/confarg/_types.py::_builtin_read_as
  - src/confarg/_types.py::_is_plain_class
  - src/confarg/typedload/_coerce.py::as_subclass
effort: M
needs_design: true  # which constructor shape is called (deque(iterable), ChainMap(*maps)), and a deque's maxlen
risk: medium
impact: config  # a file's list starts building a deque; --x.dict.a stops building a UserDict
severity: minor  # annotating the builtin, or registering the class, works
---

# FEAT-53 — A `collections.abc` implementer reads as a struct

A subclass of a builtin reads as that builtin ([a builtin's subclass is that builtin](../../architecture/design-decisions/a-builtins-subclass-is-that-builtin.md#a-builtins-subclass-is-that-builtin)), but a class that implements a collection ABC without subclassing a builtin does not: `deque[int]` is an unsupported leaf, and `UserDict` and `ChainMap` are structs of their constructors' parameters.

```text
deque[int], file x: [1, 2]  -> TypeCoercionError Unsupported leaf type collections.deque[int] at 'x'
UserDict, file x: {a: 1}    -> TypeCoercionError Unknown field(s) ['a'] for UserDict at 'x'. Valid fields: ['dict', 'kwargs']
ChainMap, file x: {a: 1}    -> TypeCoercionError Unknown field(s) ['a'] for ChainMap at 'x'. Valid fields: ['maps']
```

Reading them as their ABC's concrete collection needs a design: a constructor that takes no one collection (`ChainMap(*maps)`), a `deque`'s `maxlen`, and whether a user class registered with an ABC (`Mapping.register(C)`) counts.
`_is_plain_class` also refuses a class taking nothing whose instances hold C storage (`_types._holds_c_storage`, [design decisions](../../architecture/design-decisions/a-structs-members-are-its-constructors-parameters.md#a-class-taking-nothing-that-holds-c-storage-is-no-struct)): an implementer of that shape is an unsupported leaf before this reading is asked.
Precedents: pydantic validates `deque[int]` and builds the deque, and refuses `UserDict` and `ChainMap`; cattrs builds all three; msgspec refuses them (run, while settling BUG-253).
