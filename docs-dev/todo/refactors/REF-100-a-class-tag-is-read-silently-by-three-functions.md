---
filed: 2026-10-20
where:
  - src/confarg/_naming.py::_class_named
  - src/confarg/_naming.py  # _UNREADABLE
  - src/confarg/_default_layer.py::_tagged_class
  - src/confarg/_tags.py::_tag_named_struct
effort: S
risk: medium
impact: none
severity: trivial
---

# REF-100 — A class tag is read silently by three functions, one of them past the canonical one

"Which struct does a class tag name, if any?" is `_tags._tag_named_struct` in the [canonical table](../../architecture/invariants.md#delegate-to-the-canonical-function).
`_default_layer._tagged_class` asks it behind an `isinstance(str)` / `contains_expression` guard, and so did `_typed_merge._class_named` until the one naming moved into `_naming` (BUG-233, BUG-236); its replacement, `_naming._class_named`, repeats the guard but calls `_import_dotted` itself and checks `isinstance(cls, type)`, leaving the struct test to each caller.
The guard is now spelled twice and the import three times, with three exception sets: `_tag_named_struct` catches `SymbolImportError` and four builtins, `_typed_merge._UNREADABLE` seven named classes, and `_naming._UNREADABLE = (Exception,)` everything.

That last constant is a blanket `except Exception` the linter cannot see: ruff's BLE001 matches the bare name, not a tuple bound to it, whereas every other broad catch in the package spells `except Exception:  # noqa: BLE001  # <reason>` (`_pipeline.below_argv`).
It also shares its name with `_typed_merge._UNREADABLE`, which means something narrower.

Fix direction: one guarded reader, `_tags._tag_named_struct` taking the guard in, which `_naming`, `_default_layer` and argparse completion call; `_naming`'s other `_UNREADABLE` uses (`_spec_child`, `_member`, `arguments_of`) either name the exceptions a signature or an import raises, as `_typed_merge` does, or spell the broad catch with its `noqa` and reason.
See [a-node-types-its-keys-by-the-class-it-names.md](../../architecture/design-decisions/a-node-types-its-keys-by-the-class-it-names.md#a-node-types-its-keys-by-the-class-it-names).
