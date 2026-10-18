---
filed: 2026-10-18
where:
  - src/confarg/_files.py::_toml_holds
  - src/confarg/_api.py::dump_file
effort: M
needs_design: true  # omit a None the reload gives back, a cast to spell one, or a none word a file reads
risk: medium  # a dump that reloads differently is silent
impact: behavior
severity: minor  # refused with a ConfargError naming the path; YAML and JSON hold it
---

# FEAT-54 — A TOML file spells a `None`

TOML has no null, so `dump_file()` refuses a `None` to a TOML file, naming its path ([a written file holds what its reader reads back](../../architecture/design-decisions/a-written-file-holds-what-its-reader-reads-back.md#a-written-file-holds-what-its-reader-reads-back)).
A configuration with an optional field left at `None`, the commonest optional field there is, cannot be dumped to TOML at all.
No TOML spelling reads back as `None` today: a file's `"none"` stays a string ([the token model](../../architecture/types/token-model.md#token-model)) and `__cast__` names no `NoneType`.

Directions to weigh:

- Omit a `None` where the reload gives it back: a typed dump knows a field whose default is `None`; a `None` with another default, a list item or a value a raw `merge()` dict holds stays refused, as an omitted key in an overlay leaves the base where `null` set the field.
- A cast that spells it, `{__cast__: None}`, read by every format.
- Let a TOML file's none word select `None` on an optional field, as a token does.

Precedents: the Rust `toml` crate omits a `None` struct field and refuses a `None` in an array; Python's `toml` drops every `None`; `tomli_w` and `tomlkit` refuse it; pydantic users dump with `exclude_none=True` first.
