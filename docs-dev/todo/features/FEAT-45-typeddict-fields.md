---
filed: 2026-10-15
where:
  - src/confarg/_types.py::_is_struct
  - src/confarg/_parse_cli.py::_advance_field_type
  - src/confarg/typedload/_construct.py::construct
effort: L
needs_design: true  # a mapping with named keys: a struct to the walk, a dict to construction?
risk: high
impact: behavior
severity: minor  # refused loudly; a dataclass or a dict[str, X] is the workaround
---

# FEAT-45 — `TypedDict` fields

A `TypedDict` field is read as a plain class whose constructor is `dict.__init__`, so it has the `args` and `kwargs` fields that signature reads as, the shape [BUG-253](../bugs/BUG-253-a-dict-subclass-reads-as-a-struct-of-its-constructors-parameters.md) has for every `dict` subclass: `--td.a 3` is refused as unknown, and `--td '{"a": 3}'` as `Unknown field(s) ['a'] for TD at 'td'. Valid fields: ['args', 'kwargs']`.
A `TypedDict` is a mapping whose keys are named and typed, so the walk could list its keys as a struct's fields, and construction would build a plain `dict` checked against the declared keys (`total`, `Required`, `NotRequired`).
Precedents: pydantic and msgspec accept a `TypedDict` as a model field, building a `dict`; cattrs structures one since 23.1.
Found while checking delete spellings on struct-like types.
