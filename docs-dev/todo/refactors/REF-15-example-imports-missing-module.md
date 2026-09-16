# REF-15 — `examples/17_removing_items/myapp.py` imports a module that does not exist

**Where:** `examples/17_removing_items/myapp.py` · **Filed:** 2026-09-13
**Effort:** S · **Risk:** low · **Impact:** behavior

`from configs.deletion import Config` — `examples/configs/src/configs/` has no `deletion.py`,
so the script dies with `ModuleNotFoundError` on import. Nothing catches it: the example's
`README.md` never invokes `myapp.py`, so `pytest-markdown-console` does not replay it, and the
only signal is a `ty check` `unresolved-import`. Point it at a real config module or delete it.
