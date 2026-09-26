# REF-54 — Three hand-written scan loops in `dictexpr` the stdlib writes in one line

**Where:** `src/confarg/dictexpr/_expressions.py` (`_map_expressions`, `_resolve_single`,
`_line_starts`) · **Filed:** 2026-09-24
**Effort:** S · **Risk:** low · **Impact:** none

- `_map_expressions` (lines 1023-1032) is `re.sub` written out: a `finditer` loop appending
  `value[last : m.start()]`, tracking `last`, and joining at the end. It collapses to a single
  `_EXPR_RE.sub(lambda m: m.group(0) if m.group(1) is None else "${" + fn(m.group(1)) + "}", value)`
  — ten lines to two. Strictly equivalent, and the usual trap does not apply: when `repl` is a
  **callable**, `re.sub` uses the returned string literally, with no backslash or group-reference
  processing.
- `_resolve_single` (lines 607-629), in its interpolation branch, is the same `last_end` /
  `result_parts` loop over the same regex with evaluation inside, and reduces to the same one
  call. Its pure-expression fast path (lines 600-605) must stay — that one returns a *typed*
  value, not a string.
- `_line_starts` (lines 732-737) is a prefix sum:
  `list(accumulate(map(len, text.splitlines(keepends=True)), initial=0))`. Verified equal on
  `""`, `"a"`, `"a\nb"`, `"a\nb\n"`, `"\n\n"` and `"x\r\ny"` — including the empty string, where
  both give `[0]`.

`itertools` and `re` are stdlib, so engine independence
([07-expressions.md#engine-independence](../../architecture/07-expressions.md#engine-independence))
holds, as it does for [REF-49](REF-49-graphlib-replaces-hand-written-kahn.md).

This sharpens one bullet of [REF-52](REF-52-mechanical-collapses-in-the-type-machinery.md),
which notes that `_resolve_single` and `_map_expressions` are "the same `finditer` accumulate
loop differing only in escape handling". REF-52 names the duplication; this names the answer to
both halves — after the `sub` rewrite there is little left to share. Close that bullet here.
