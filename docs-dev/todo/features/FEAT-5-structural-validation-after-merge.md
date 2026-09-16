# FEAT-5 — Optional structural validation right after `merge()`

**Effort:** S *(design pass; implementation not sized)* · **Risk:** low · **Impact:** behavior

Errors would surface earlier and closer to their source, without changing the
merge/build contract (`merge()` stays unvalidated by default).
See [01-pipeline-and-contracts.md#merge-build-contract](../../architecture/01-pipeline-and-contracts.md#merge-build-contract).
