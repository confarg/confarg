---
filed: 2026-10-18
where:
  - src/confarg/_files.py::_load_json_item
  - src/confarg/_files.py::_load_toml
  - src/confarg/_files.py::_load_yaml_item
effort: M
needs_design: true  # a hook per parser, and what the warning names without a field path
risk: medium  # every file's float goes through the hook
impact: behavior
severity: minor  # the value is right, only the warning is missing
---

# FEAT-52 — A file's float literal that overflows reads as `inf` silently

A finite number too large for a float reads as `inf` and warns with `FloatOverflowWarning` wherever confarg converts it: a file's integer, a CLI or environment token ([a float reads an int as its digits](../../architecture/design-decisions/a-float-reads-an-int-as-its-digits.md#a-number-too-large-for-a-float-reads-as-infinity)).
A file's float literal (`1e400` in JSON or TOML, `1.0e+400` in YAML) does not warn: its parser makes it `inf` before confarg sees it, indistinguishable from a deliberate `Infinity` or `.inf`.
`json.loads` and `tomllib.loads` take a `parse_float` that receives the text (`'1e400'`), and PyYAML a float constructor, so each loader could spot the overflow; but no type is known yet, so the warning would name the file and not the field, and it would fire for an `Any` or a `str | float` field too.
Precedents: msgspec refuses JSON `1e400` ('Number out of range'); pydantic reads it as `inf` without a warning.
