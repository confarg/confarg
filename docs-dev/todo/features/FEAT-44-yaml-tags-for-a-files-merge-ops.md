---
filed: 2026-10-14
where:
  - src/confarg/_files.py::_load_yaml_item
  - src/confarg/_files.py::_dump_yaml
effort: M
needs_design: true
risk: medium
impact: none
severity: trivial  # every op has a spelling in a YAML file already, as a reserved key
---

# FEAT-44 — YAML tags for a file's merge ops

A YAML file spells a merge op as a reserved key of the value ([a file spells an op in its value](../../architecture/design-decisions/a-file-spells-an-op-in-its-value.md#a-file-spells-an-op-in-its-value)): `xs: {__append__: [3]}`, `name: {__unset__: true}`.
Docker Compose marks the value with a YAML tag instead (`!reset`, `!override`), which reads shorter: `xs: !append [3]`, `name: !unset`.
A tag is YAML's alone, so TOML and JSON would keep the reserved keys and the two spellings would coexist.
The design pass decides whether that is worth a second spelling, which tags exist (one per op, or `!unset` alone), how a tag combines with keys beside it (`sec: !unset {a: 1}`), and whether `dump_file` writes tags or keys, given that `yaml.safe_load` refuses an unknown tag and so needs a loader of confarg's own.
