---
filed: 2026-10-06
where:
  - src/confarg/_parse_cli.py::_merge_append_ops
  - src/confarg/_merge.py::_apply_append_key
effort: S
risk: medium
impact: none
severity: trivial
---
# REF-87 — An append is combined with what its path holds in two functions

The CLI's `--key+` (`_parse_cli._merge_append_ops`) and a file's `key+:`
(`_merge._apply_append_key`) each decide what an append does with what the same source already
wrote at its path. Since BUG-116 both open a whole-field delete through `_merge._open_for_ops`,
but the rest still differs: the CLI keeps a whole list as the `'*'` base beside the append where
the file concatenates it, and the file keeps only the `'+'` of a node already holding one,
dropping its other keys, where the CLI keeps them. Fix direction: one combiner in `_merge`,
built on `_open_for_ops`, that both call
([delegate to the canonical function](../../architecture/invariants.md#delegate-to-the-canonical-function)).
