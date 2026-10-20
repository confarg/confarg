---
filed: 2026-10-20
where:
  - src/confarg/_typed_read.py::_read
  - src/confarg/_serialize.py::written_form
  - src/confarg/_api.py::_strip_locals_node
  - src/confarg/_pipeline.py::_LayerReading
  - src/confarg/_default_layer.py::_copied_if_changed
effort: S
risk: low
impact: none
severity: trivial
---

# REF-98 — `_typed_read._read` and `_serialize.written_form` are one walk spelled twice

Both walk a dict or a list, recurse into each child, and return the original value when every child came back as itself — the "copy only where a leaf changed" walk — spelled once with a `TypedAt` threaded to each child and once without.
Both were added by the typed-leaf reading (BUG-246, FEAT-51's `written_form` side).

The same "hand back the original when every child came back as itself" test is written by hand in two more walks: `_api._strip_locals_node` (lists) and `_pipeline._LayerReading.read` (lists and dicts) — seven spellings in all, counting the four here — while `_default_layer._copied_if_changed` already is that test as a function, for dicts and lists alike.
Whatever the collapse decision for the two walks, the test itself has one home to move to.

Whether to collapse is the call [look-alike code that behaves differently stays apart](../../architecture/design-decisions/look-alike-code-that-behaves-differently-stays-apart.md#look-alike-code-that-behaves-differently-stays-apart) governs: the two differ only in what each child is handed, so one walker taking a `Callable[[key, child], Any]` is close to that note's `_rewrite_spans` precedent; if the collapse is declined, the refusal belongs in that note so the pair is not re-filed.
