---
filed: 2026-11-03
where:
  - src/confarg/_defaults.py::MergeOptions  # the union_tag key
  - src/confarg/_defaults.py::check_union_tag
  - src/confarg/_defaults.py::UNION_TAG  # becomes CLASS_KEY
  - src/confarg/_callable.py::openers  # becomes a constant
  - src/confarg/_callable.py::object_openers
  - src/confarg/_types.py::_union_tag_shadowed
  - src/confarg/exceptions.py::ConfargWarning  # tag_shadowed_by_member
  - src/confarg/typedload/_construct.py
  - src/confarg/_api.py
  - src/confarg/_serialize.py
  - src/confarg/_parse_cli.py
  - src/confarg/_parse_env.py
  - src/confarg/_naming.py
  - src/confarg/_tags.py
  - src/confarg/_typed_merge.py
  - src/confarg/_default_layer.py
  - src/confarg/_pipeline.py
  - src/confarg/_typed_read.py
  - src/confarg/_merge.py
  - src/confarg/_types.py
  - src/confarg/cli/
  - docs-dev/architecture/
  - tests/
effort: L  # every channel and front-end, three decision notes, a sweep of the test suite
risk: low  # the deleted branches are dead under `class`, which the whole suite already runs on
impact: api  # the union_tag keyword goes from every entry point
severity: trivial
---

# REF-121 — Drop the `union_tag` option: the class key is always `class`

`union_tag` is the one reserved key a caller can rename: `classfn`, `bind`, `call`, `args`, `__include__`, `__cast__`, `__value__`, `__root__`, the list ops and the locals namespace are all fixed.
Since BUG-305 it renames one opener of four, so `union_tag="kind"` writes `{kind: pkg.Mul}` beside an unrenamed `classfn`.
It is also threaded through every layer per call, and every collision between the tag and a field (BUG-92, 97, 102, 106, 276, 285, 303, 305) exists only because a custom tag can be spelled like a field.
`class` is a keyword, so no struct confarg reads can own it, and `_union_tag_shadowed` always answers `False` under it.

The design is settled in [the class key is `class`](../plans/the-class-key-is-class.md): the keyword goes from every entry point, the key is `_defaults.CLASS_KEY`, the shadowed-tag machinery goes with it, and "union tag" becomes "class key" in the code and the notes.
It closes BUG-285 and REF-95, whose tests and warning it deletes.
