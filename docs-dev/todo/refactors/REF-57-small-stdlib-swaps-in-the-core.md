# REF-57 — Small stdlib swaps across the core

**Where:** `src/confarg/_pipeline.py`, `src/confarg/_files.py`, `src/confarg/_parse_env.py`,
`src/confarg/_types.py`, `src/confarg/cli/cyclopts/_register.py`,
`src/confarg/typedload/_coerce.py`, `src/confarg/typedload/_construct.py` ·
**Filed:** 2026-09-24
**Effort:** S · **Risk:** low · **Impact:** none

Independent one-site edits, grouped the way
[REF-52](REF-52-mechanical-collapses-in-the-type-machinery.md) groups its collapses: no design
question attached to any of them. Split across revisions if one turns out bigger than it looks.

- `_pipeline.py:220-223` — a two-level `setdefault` loop building an insertion-ordered union of
  keys is `dict.fromkeys(chain.from_iterable(dicts))`. Verified equal, order included; `names`
  is only ever iterated (line 224), so nothing depends on how it was built.
- `_files.py:187-188` — `lambda path: _load_csv(path, orient="rows")` and its `.tsv` twin are
  `functools.partial(_load_csv, orient="rows")`. `path` is `_load_csv`'s first positional
  parameter and the rest are keyword-only, so the binding is exact. A `partial` also reprs
  usefully in a traceback where `<lambda>` does not.
- `_parse_env.py:99-106` — `name_to_types.setdefault(fname, []).append(...)` is
  `collections.defaultdict(list)`. The variable is local to `_match_union_part` and never
  returned, so the auto-vivification a `defaultdict` adds cannot leak.
- `cli/cyclopts/_register.py:68` — three chained `.replace()` calls are one `str.maketrans`
  table plus `.translate()`. Verified equal today, because no replacement's output contains a
  later search character — which is exactly the cascade hazard a single-pass `translate` removes
  permanently, and the reason to make the swap before a fourth mapping is added.
- `typedload/_coerce.py:152-154` — `_steal_rank`'s `enumerate` scan over `_RANKED_LEAF_TYPES` is
  an O(1) lookup in a module-level `{tp: 3 + i for i, tp in enumerate(_RANKED_LEAF_TYPES)}`.
  Dict lookup on type objects is identity-based, so the `bool`-is-not-`int` behaviour the
  inline comment protects is preserved — **keep that comment**, it is the whole point of the loop.
- `types.NoneType` — `_types.py` already imports `types` and writes `types.UnionType` at line
  172, yet spells the sibling `type(None)` at lines 159, 196, 212 and 220, and again at
  `typedload/_coerce.py:135` and `typedload/_construct.py:590, 595, 711, 718, 761, 764`.
  Strictly equivalent (`types.NoneType is type(None)`); purely consistency.

**A lint question to settle in the same pass.** Two of these patterns are already known to ruff,
in preview only: `FURB118` reports `_pipeline.py:340`'s `lambda ec: ec[0]` as
`operator.itemgetter(0)`, and `PLW0717` flags four of the try clauses in
[REF-53](REF-53-contextlib-suppress-for-hand-rolled-try-except.md). Enabling them in
[`.ruff.toml`](../../../.ruff.toml) makes lint hold the line afterwards; hand-fixing without
enabling them means the pattern comes back. Decide which — the itemgetter site is deliberately
*not* listed above, because it should be fixed by whichever answer wins.
