---
filed: 2026-10-06
where:
  - src/confarg/dictexpr/_expressions.py
  - src/confarg/_api.py
effort: L
risk: high
impact: behavior
severity: minor
---
# FEAT-35 — Let `${...}` read a `call:` result

Expressions resolve over the merged dict before construction, so an expression cannot read a
value a `call:` spec produces. Put `call:` nodes into the expression dependency graph
(`_dependency_graph`, `_topological_sort`), so a call and an expression that reads it are ordered
together, and a cycle through a call is a `CircularReferenceError`. The decision is recorded in
[resolution.md § Calls and expressions share one graph](../../architecture/expressions/resolution.md#calls-and-expressions-share-one-graph).

Open within it: whether an expression reads a call result typed or raw.
