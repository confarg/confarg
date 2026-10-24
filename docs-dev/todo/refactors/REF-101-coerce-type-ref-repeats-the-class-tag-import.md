---
filed: 2026-10-20
where:
  - src/confarg/typedload/_coerce.py::_coerce_type_ref
  - src/confarg/_callable.py::_import_class_by_path
effort: S
risk: low
impact: none
severity: trivial
---

# REF-101 — `_coerce_type_ref` repeats the class-tag import step for step

`_callable._import_class_by_path` is the one reader of a class tag — a union's, a struct field's subclass tag, a `class:` spec's — and the move that made it so deleted `_construct`'s copy.
`_coerce_type_ref`, which reads a `type` / `type[X]` leaf, still walks the same four steps by hand: refuse a non-string, `_import_dotted`, turn `SymbolNotFoundError` into a `TypeCoercionError` naming the full-dotted-path remedy and re-raise any other `SymbolImportError` with the path, then refuse an object that is no class.
The two spell their messages differently (`'mypackage.MyClass'` against `'mypackage.mymodule.MyClass'`, "expected a class, got" against "must be a class path"), and both grew the not-found/import-failure split in the same range ([dotted-imports.md](../../architecture/types/dotted-imports.md#a-path-names-nothing-or-a-module-fails)).

Fix direction: `_coerce_type_ref` keeps its class-object branch and its `type[X]` constraint check and delegates the string branch to `_import_class_by_path`, which takes a word for what it reads (tag, `class:` key or type field) to keep each message's subject.
