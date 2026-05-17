# FEAT-2 — Protocol-typed callables and `**kwargs`

**Where:** `src/confarg/_callable.py` · **Filed:** 2026-09-12
**Effort:** L · **Risk:** medium · **Impact:** behavior

Callable specs bind against a concrete signature. A field typed as a `Protocol` with
`__call__`, or a target accepting `**kwargs`, has no story yet: decide whether extra keys bind
as keyword arguments and how they are validated.
See [06-callables.md](../../architecture/06-callables.md).
