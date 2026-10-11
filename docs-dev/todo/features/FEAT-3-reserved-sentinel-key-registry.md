---
filed: 2026-09-12
effort: S
risk: high
impact: config
severity: minor
needs_design: true  # the effort sizes the design pass; the implementation is not sized
---
# FEAT-3 — A registry of reserved sentinel keys

`__root__`, `__cast__`, `__value__`, `__include__`, `+`, `-`, `*`, `~` are recognised in
several places. One registry, plus a guard against user keys colliding with them, would harden
the plain-dict IR. Since BUG-170 no channel's parser writes a list-patch key from what the user
typed below a sequence, and `_merge._replace_base` refuses a `'*'` holding no list, so what is
left is a file writing the keys itself
([BUG-175](../bugs/BUG-175-a-files-list-delete-key-holding-no-index-list-escapes-as-a-typeerror.md)).
See [pipeline/deep-merge.md#deep-merge-semantics](../../architecture/pipeline/deep-merge.md#deep-merge-semantics).
