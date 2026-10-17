---
filed: 2026-10-17
where:
  - src/confarg/typedload/_coerce.py::_LEAF_COERCIONS
  - src/confarg/typedload/_coerce.py::_LEAF_SERIALIZERS
effort: S
needs_design: true  # what each type reads from a file's native value, and which text spellings
risk: low
impact: behavior
severity: minor  # refused loudly both ways; register_leaf_type is the workaround
---

# FEAT-51 — The date and time types as built-in leaves

`Decimal` and `UUID` are built-in leaves beside `Path` ([Decimal and UUID are built-in leaves](../../architecture/design-decisions/decimal-and-uuid-are-built-in-leaves.md)); `datetime.date`, `datetime.datetime`, `datetime.time` and `datetime.timedelta` are not, so a field typed by one is an unsupported leaf until the application registers it: `--when 2021-02-03` and a YAML `when: 2021-02-03` are both refused (`Unsupported leaf type <class 'datetime.date'>`), and `dump()` refuses the field.

The design pass decides what each type reads, since files hold some of them natively: YAML parses `2021-02-03` as a `date` and TOML has native dates, datetimes and times, while JSON and every token are text.
It also settles the text spelling (`fromisoformat` alone, as pydantic accepts ISO 8601 alongside Unix timestamps), a `datetime` beside a `date` (a `datetime` is a `date` subclass, so a `date` field's pass-through would let one in), how `timedelta` is spelled (pydantic writes ISO 8601 durations), and whether the dump writes the native value a TOML or YAML writer holds or the ISO text.
