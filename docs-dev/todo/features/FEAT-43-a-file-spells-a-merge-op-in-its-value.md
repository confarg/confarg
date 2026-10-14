---
filed: 2026-10-14
where:
  - src/confarg/_merge.py::_normalize_merge_ops
  - src/confarg/_merge.py::_apply_append_key
  - src/confarg/_files.py::_resolve_dict
  - src/confarg/_files.py::_require_layer
  - src/confarg/_defaults.py
  - src/confarg/_serialize.py::_serialize_untyped
  - src/confarg/typedload/
  - examples/11_include/README.md
  - examples/16_appending_items/
  - docs-dev/architecture/
effort: L
risk: high  # the file reader every configuration document goes through
impact: config  # every file spelling `key+:`, `key-:` or `"N-":` changes meaning
severity: minor  # a dict key ending in + or - reaches a dict from argv or the environment as JSON, never from a file
---
# FEAT-43 — A file spells a merge op in its value, never in its key

A configuration file spells a merge op in a key, `xs+:`, `name-:` and `"0-":`, so a file key is a path and a datum at once. No file can give a dict a key ending in `+` or `-`, a dict that holds one does not survive `dump_file` and a reload, a file's dict has to be read exactly once because reading is not idempotent, and a merged key delete has no spelling a dump could write that a data key could not also mean ([limitations](../../architecture/limitations.md#collections), [a decoded value is data](../../architecture/design-decisions/a-decoded-value-is-data.md#a-decoded-value-is-data)). The ops move into the value, as dunder keys: `xs: {__append__: [3]}`, `xs: {__delete__: [0]}` and the new `name: {__unset__: true}`, and every other key of a file is data. Argv and the environment keep their suffixes, which sit on a path.

The settled design is in [the plan](../plans/feat-43-a-file-spells-a-merge-op-in-its-value.md).
