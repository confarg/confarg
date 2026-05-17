# FEAT-3 — A registry of reserved sentinel keys

**Effort:** S *(design pass; implementation not sized)* · **Risk:** high · **Impact:** config

`__root__`, `__cast__`, `__value__`, `__include__`, `+`, `-`, `*`, `~` are recognised in
several places. One registry, plus a guard against user keys colliding with them, would harden
the plain-dict IR. See [01-pipeline-and-contracts.md#deep-merge-semantics](../../architecture/01-pipeline-and-contracts.md#deep-merge-semantics).
