# REF-49 — `graphlib.TopologicalSorter` replaces the hand-written Kahn loop

**Where:** `src/confarg/dictexpr/_expressions.py` (`_topological_sort`) · **Filed:** 2026-09-24
**Effort:** S · **Risk:** low · **Impact:** behavior

`_topological_sort` is Kahn's algorithm with an explicit reverse adjacency list and in-degree
counts, about 34 lines where the stdlib does it in nine. The node sets match exactly, because the
dependency map is built as `refs & expr_paths`, so every dependency is also a key — which is the
precondition `TopologicalSorter` needs. Verified equal on the same graph:

```python
from graphlib import TopologicalSorter
from confarg.dictexpr._expressions import _topological_sort

g = {"a": {"b"}, "b": {"c"}, "c": set(), "d": set()}
print(_topological_sort(dict(g)))                    # ['c', 'd', 'b', 'a']
print(list(TopologicalSorter(g).static_order()))     # ['c', 'd', 'b', 'a']
```

`dictexpr` may import it: `graphlib` is the standard library, so engine independence
([07-expressions.md#engine-independence](../../architecture/07-expressions.md#engine-independence))
holds — the rule is stdlib plus `confarg.exceptions`, nothing about which stdlib modules.

Why **behavior**: `CycleError` is raised by `prepare()` before anything is yielded, so the
`CircularReferenceError` message widens from "the nodes that could not be released" to every
expression node in the graph. Nothing asserts that text today — a grep over `tests/`, `docs/` and
`docs-dev/` for the message finds nothing, and the cycle tests in
`tests/dictexpr/test_expressions.py` check only the exception type — but it is user-visible, so
the resolution algorithm note
([07-expressions.md#resolution-algorithm](../../architecture/07-expressions.md#resolution-algorithm))
needs a line saying which nodes the message names. If naming only the unreleasable nodes is worth
keeping, `prepare()` plus `get_ready()` in a loop preserves it and still deletes the in-degree
bookkeeping.
