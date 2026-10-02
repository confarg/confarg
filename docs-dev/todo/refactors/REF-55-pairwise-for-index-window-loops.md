# REF-55 — An adjacent-pair loop written with indices instead of `itertools.pairwise`

**Where:** `src/confarg/cli/_spec.py` (`_get_field_docstrings`) · **Filed:** 2026-09-24
**Effort:** S · **Risk:** low · **Impact:** none

It walks a sequence looking at each element and its successor, and carries a bounds guard that
exists only to skip the final element — which is exactly what `pairwise` omits.

- `cli/_spec.py:117-129` enumerates `stmts`, `continue`s on `i + 1 >= len(stmts)`, then reads
  `stmts[i + 1]`. `for stmt, next_stmt in pairwise(node.body):` drops the `stmts` binding, the
  index and the guard together. `i` is used for nothing else.

Verified equal to the index form on empty, one-, two- and three-element inputs.
`itertools.pairwise` is 3.10+ and the floor is 3.12, so no guard is needed.
