# FEAT-5 — Optional structural validation right after `merge()`

**Effort:** S *(design pass; implementation not sized)* · **Risk:** low · **Impact:** behavior

Errors would surface earlier and closer to their source, without changing the
merge/build contract (`merge()` stays unvalidated by default).
See [pipeline/merge-build-contract.md#merge-build-contract](../../architecture/pipeline/merge-build-contract.md#merge-build-contract).
