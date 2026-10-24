---
filed: 2026-10-20
where:
  - src/confarg/_serialize.py::_open
  - src/confarg/_serialize.py::_serialize
  - src/confarg/_serialize.py::_serialize_any
effort: S
risk: low
impact: none
severity: trivial
---

# REF-116 — The dump opens and closes an instance by hand, twice

BUG-248 gave `dump()` its depth and self-containment check: `_serialize._open` enters an instance at its position, and the caller removes it from `opts.open_at` when it leaves.
`_serialize` and `_serialize_any` each spell that as `opened = _open(...)`, `try:`, the body, `finally: if opened: del opts.open_at[id(instance)]` — the enter and the exit of one scope, written apart at two sites.

Fix direction: make `_open` a `contextlib.contextmanager` (`with _opened(instance, path, opts):`), so the release lives beside the entry it undoes.
See [a-configuration-nests-at-most-64-levels.md](../../architecture/design-decisions/a-configuration-nests-at-most-64-levels.md#a-value-that-holds-itself-is-refused-as-one).
