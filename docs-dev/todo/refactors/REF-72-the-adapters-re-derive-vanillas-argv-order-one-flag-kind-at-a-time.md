# REF-72 — The adapters re-derive vanilla's argv order one flag kind at a time

**Where:** `src/confarg/cli/_collect.py`, `src/confarg/cli/_argv.py`,
`src/confarg/_parse_cli.py` (`patch_only` scan) · **Filed:** 2026-10-01
**Effort:** XL · **Risk:** high · **Impact:** none

The adapters build the CLI channel in two halves. The flat collector walks the framework's
parse result, which has no order, and the `patch_only` scan replays vanilla's own loop for
patches. The two are then joined with `_deep_merge`. Every bug fix in which argv order matters
added a new reader that recovers one piece of vanilla's sequential loop:

- latest writer: `_arity_flag_writes_last`, `_last_flag_occurrence`, `_last_leaf_cast_spelling`
- token runs: `_fixed_arity_occurrence_runs`, `_union_seq_occurrence_writes`,
  `_tokens_past_whole_field_delete`, `bare_only_flag_names`
- repairs at the join: `_pop_nested` in the scan, `_promote_patched_lists`,
  `_restore_patch_deletes`

Each new reader cites the previous one as its precedent. Most of them match `--flag` and
`--flag=` by hand instead of going through `_normalize_eq_args` and `_parse_flag_mode`. Each
also models less than the loop does, and the gaps are bugs: BUG-111 (interleaving), BUG-87 (key
order), BUG-95 (`.json` cast order).

The canonical decision-maker already exists: vanilla's loop. BUG-92 / BUG-106 already route
union tags through it (`_is_replayed_path`), and that replaced a scan written only for the
adapters. Fix direction: make the scan the only writer for the adapters' CLI channel. It walks
the argv as typed. The framework's parse result keeps the jobs only it can do: validation,
`--help`, completion. The readers and join repairs above then disappear, along with the parts
of REF-65 that mirror token shaping. This needs a decision note in
`../../architecture/cli-adapters/`, superseding
[collection-patch-parity.md](../../architecture/cli-adapters/collection-patch-parity.md)'s
split, and the
[namedtuple-arity-flag-argv-order](../../architecture/design-decisions/namedtuple-arity-flag-argv-order.md)
mechanism. Risk is high because it changes how every adapter assembles its merged dict;
[parity.md#byte-identical-merged-dicts](../../architecture/cli-adapters/parity.md#byte-identical-merged-dicts)
is the contract, and the contract suite is what must catch a regression.
