---
filed: 2026-11-07
where:
  - src/confarg/dictexpr/_expressions.py::_dependency_graph  # orders a reference only after expressions its spelled path reaches
  - src/confarg/dictexpr/_expressions.py::_eval_path_or  # reads the base whole when the path misses
effort: M  # the ordering is one rule; the design pass is whether a base read from inside it is a cycle
needs_design: true
risk: high  # the expression engine's ordering, shared by every channel
impact: behavior  # a value read before it resolved becomes the resolved one, or a cycle error
severity: critical  # q holds '${x}' where it should hold 1, with no error, depending on key order alone
introduced_by: [BUG-121]  # PR-280, which made a constant subscript spell a path segment, and fell back on Python's subscript when it misses
---

# BUG-311 — A subscript indexing its base reads a sibling expression before it resolves

A reference whose path the data does not answer, as `${a[0].p}` on an integer key `0`, depends on no expression, yet evaluation falls back on indexing its base read whole ([spelling a path](../../architecture/expressions/values-and-references.md#spelling-a-path)), which may still hold expressions yet to resolve: `q: ${a[0].p}` reads `p: ${x}` as its text `'${x}'` when `q` comes first, and `1` when `p` does.
[A reference reads everything its path reaches](../../architecture/expressions/resolution.md#a-reference-reads-everything-its-path-reaches) holds for the path spelled, not for the base the fallback reads.
The two spellings of one read also disagree on a reference from inside its base: a computed key, `${svc[k]}` inside `svc`, depends on `svc` and is a cycle, while `${m[0]}` inside `m` resolves.
BUG-310 made the typed reading read a pending position as written, so no coercion runs on that text; the value read stays the text.

Fix direction, for the design pass: order a reference whose path misses after every expression below the base the fallback reads, and settle whether the reading expression itself, held in that base, is a cycle (as a computed key's is today) or only a read reaching it is (OmegaConf resolves lazily, so it only meets a cycle where a read reaches the node being resolved).

Origin: latent since BUG-121, which made a constant subscript spell a path segment for the dependency graph and kept Python's subscript as the fallback when the path misses; before it, `${m[0]}` depended on `m` whole *(inferred from the diff: `_collect_names` walked a subscript's children)*.

```python
import confarg

print(confarg.resolve(dict, {"x": 1, "a": {0: {"p": "${x}", "q": "${a[0].p}"}}}))
print(confarg.resolve(dict, {"x": 1, "a": {0: {"q": "${a[0].p}", "p": "${x}"}}}))
# expected: {'x': 1, 'a': {0: {'p': 1, 'q': 1}}}
#           {'x': 1, 'a': {0: {'q': 1, 'p': 1}}}
# actual:   {'x': 1, 'a': {0: {'p': 1, 'q': 1}}}
#           {'x': 1, 'a': {0: {'q': '${x}', 'p': 1}}}
```
