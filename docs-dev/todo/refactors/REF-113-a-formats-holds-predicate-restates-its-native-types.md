---
filed: 2026-10-20
where:
  - src/confarg/_files.py::_toml_holds
  - src/confarg/_files.py::_yaml_holds
  - src/confarg/_files.py::_json_holds
  - src/confarg/_files.py::_Format
effort: S
risk: low
impact: none
severity: trivial
---

# REF-113 — A format's `holds` predicate restates its native types

Each `_files._Format` carries `natives`, the registered leaf types its writer holds (`YAML_NATIVE_TYPES`, `TOML_NATIVE_TYPES`, `JSON_NATIVE_TYPES`), and a `holds` predicate saying which values its reader reads back.
The three predicates spell the natives again as literals — `(*_SCALARS, date, datetime)` in `_yaml_holds` and `_toml_holds` — so a type added to a format's natives is written as an object `_writable` then refuses.
What differs between formats is small and stated: a null (YAML, JSON), and TOML's local `time`.

Fix direction: one `holds(value, fmt)` reading `type(value) in (*_SCALARS, *fmt.natives)`, with `nullable` and an `extra` predicate on `_Format` for the two exceptions.
See [a-written-file-holds-what-its-reader-reads-back.md](../../architecture/design-decisions/a-written-file-holds-what-its-reader-reads-back.md#a-written-file-holds-what-its-reader-reads-back).
