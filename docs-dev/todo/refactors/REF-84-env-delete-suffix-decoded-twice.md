---
filed: 2026-10-04
where:
  - src/confarg/_parse_env.py::_handle_env_delete
  - src/confarg/_parse_cli.py::_parse_flag_mode
effort: S
risk: low
impact: none
severity: trivial
---
# REF-84 — The delete suffix and its list index are decoded twice

Both channels decide "is this a delete, and does it name a list index?" with code of their
own. `_parse_cli._parse_flag_mode` strips a trailing `-` from the last segment and calls
`int()` on the rest, and `_parse_env._handle_env_delete` strips the same `-` and calls `int()`
again. They agree today, but which spellings count as an index (`int()` takes `+1`, `01` and
`1_0`, where the expressions and the namedtuple walk accept only what `str()` of an integer
writes, BUG-97, BUG-133) is a decision that would have to change at both sites. Fix
direction: one decoder of the last segment, `(name, index | None)`, which both channels call,
following [delegate to the canonical function](../../architecture/invariants.md#delegate-to-the-canonical-function).

Since BUG-170 the walk refuses a non-canonical index below a sequence before either `int()` runs
(`--xs.01-`, `APP_XS__01-`), so the two decoders now differ only where no sequence is walked: on
a dict, where both take `1-` for a list delete
([BUG-174](../bugs/BUG-174-an-index-delete-on-a-dict-writes-the-list-delete-key.md)).
