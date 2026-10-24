---
filed: 2026-10-20
where:
  - src/confarg/typedload/_coerce.py::_format_offset
effort: S
risk: low
impact: none
severity: trivial
---

# REF-115 — `_format_offset` slices an `isoformat()` string where `strftime("%:z")` says it

The serializer of a registered `timezone` writes its UTC offset by formatting `datetime.min` with the zone and cutting the first 19 characters off the result: `datetime.min.replace(tzinfo=value).isoformat()[len("0001-01-01T00:00:00"):]`.
Since Python 3.12, the floor `pyproject.toml` declares, `strftime` spells exactly that with `%:z`; on `UTC`, `+02:00`, `-05:30`, `+00:00:30` and a microsecond offset the two give identical text (checked 2026-10-20 on 3.12.11).

Fix direction: `datetime.min.replace(tzinfo=value).strftime("%:z")`.
See [a-timezone-is-an-iso-8601-offset](../../architecture/design-decisions/the-date-and-time-types-are-built-in-leaves.md#a-timezone-is-an-iso-8601-offset).
