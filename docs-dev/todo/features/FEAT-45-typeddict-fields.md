---
filed: 2026-10-15
where:
  - src/confarg/_types.py::_is_struct
  - src/confarg/_types.py::_tagged_struct  # issubclass on a TypedDict variant
  - src/confarg/_parse_cli.py::_advance_field_type
  - src/confarg/typedload/_construct.py::construct
effort: L
needs_design: true  # a mapping with named keys: a struct to the walk, a dict to construction?
risk: high
impact: behavior
severity: minor  # refused loudly; a dataclass or a dict[str, X] is the workaround
---

# FEAT-45 — `TypedDict` fields

A `TypedDict` field is read as a plain class whose constructor is `dict.__init__`, so it has the `args` and `kwargs` fields that signature reads as, the shape every `dict` subclass had before it read as a dict ([a builtin's subclass is that builtin](../../architecture/design-decisions/a-builtins-subclass-is-that-builtin.md#a-builtins-subclass-is-that-builtin), which leaves a `TypedDict` out so that its keys stay typed one by one): `--td.a 3` is refused as unknown, and `--td '{"a": 3}'` as `Unknown field(s) ['a'] for TD at 'td'. Valid fields: ['args', 'kwargs']`.
A `TypedDict` is a mapping whose keys are named and typed, so the walk could list its keys as a struct's fields, and construction would build a plain `dict` checked against the declared keys (`total`, `Required`, `NotRequired`).
Precedents: pydantic and msgspec accept a `TypedDict` as a model field, building a `dict`; cattrs structures one since 23.1.
Found while checking delete spellings on struct-like types.

As a union's variant beside a struct with subclasses, it fails with a raw `TypeError: TypedDict does not support instance and class checks` from `_types._tagged_struct`'s `issubclass` once a class key names a subclass (`v: A | T` given `{class: pkg.B}` or `--v.class pkg.B`, run on 3.12), instead of a confarg error.

The design pass also decides what a key spelled `class` means in one, `TypedDict("T", {"class": str})` being the only struct that can own the class key ([the class key is `class`](../../architecture/design-decisions/the-class-key-is-class.md#the-class-key-is-class)): refused, as Hydra and jsonargparse reserve their key everywhere, or the member's, which brings back the real-field-wins rule REF-121 deletes.
