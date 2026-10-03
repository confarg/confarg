# BUG-77 — An index delete below a whole-field delete crashes the patch scan

**Where:** `src/confarg/_parse_cli.py` (`_accumulate_list_delete`, reached from
`_handle_delete_token`) · **Filed:** 2026-09-30
**Effort:** S · **Risk:** high · **Impact:** behavior

A whole-field delete records its `_DeleteSentinel` at the path, and every later op at or
below the path replaces the node it finds there wholesale — an index set (`--users.0 x`),
an append, a dict subkey below a whole dict delete. Except the list *index* delete:
`_accumulate_list_delete` reads the node with `.get` without guarding the sentinel, so
`--users- --users.0-` crashes with an `AttributeError` instead of recording the op. The
crash is in the vanilla loop, so all five front-ends hit it — the adapters run the same
scan in `patch_only` mode. Found while probing the BUG-76 neighborhood.

Fix direction: the index delete is the later writer at the path, so it replaces the
sentinel like every other op below a whole delete does — the argv-order rule BUG-53
settled for plain occurrences. Recorded, the op then behaves exactly as a lone
`--users.0-` does: applied against the field's default at the merge, and dying with the
node a later plain occurrence replaces.

[cli-parsing/collection-patches.md#collection-patch-operations](../../architecture/cli-parsing/collection-patches.md#collection-patch-operations) ·
[cli-adapters/collection-patch-parity.md#a-plain-occurrence-erases-the-ops-before-it](../../architecture/cli-adapters/collection-patch-parity.md#a-plain-occurrence-erases-the-ops-before-it)

```python
from dataclasses import dataclass, field

import confarg


@dataclass
class Config:
    users: list[str] = field(default_factory=list)


print(confarg.merge(Config, argv=["--users-", "--users.0-"], env={}))

# expected: {'users': {'-': [0]}} — the index delete is the later writer at the
#           path, and every other op after a whole-field delete replaces the
#           sentinel (an index set does: --users- --users.0 x is {'users': {'0': 'x'}})
# actual:   AttributeError: '_DeleteSentinel' object has no attribute 'get'
#           (in _accumulate_list_delete: existing = node.get(delete_key))
```
