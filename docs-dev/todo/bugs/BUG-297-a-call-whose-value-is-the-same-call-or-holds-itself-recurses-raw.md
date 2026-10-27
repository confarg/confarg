---
filed: 2026-10-27
where:
  - src/confarg/_callable.py::resolve_typed_call  # the value goes to construction unbounded
  - src/confarg/_depth.py::refuse_overflow
  - src/confarg/exceptions.py::ConfargError  # the cycle and chain refusals
effort: M  # one helper, two refusals and their messages, tests through the loader fixture
risk: medium  # a mistake refuses a legitimate chain loudly, or leaves the raw error
impact: config  # a self-holding value a typed field took as it is, a list[Any] holding itself, starts being refused
severity: minor  # invalid input answered with a raw RecursionError
introduced_by: [FEAT-28]  # resolve_typed_call, which hands a dict value back to construction
---

# BUG-297 — A call whose value is the same call, or holds itself, recurses to a raw `RecursionError`

A `call:` on a typed field hands a value its annotation does not accept back to construction, which reads a `call:` in it as a call again; nothing bounds that chain, and nothing checks the value with `_depth.refuse_overflow`, as `build()` data is checked where it enters ([a configuration nests at most 64 levels](../../architecture/design-decisions/a-configuration-nests-at-most-64-levels.md#where-it-is-counted)).
So a function returning its own spec, and a function returning a dict that holds itself under a recursive struct, recurse until Python's limit.

Fix, settled in [the plan](../plans/a-calls-value-is-read-by-construction.md#a-calls-value-is-bounded-where-it-enters): one helper in `_callable` owns a call's value at a node; it checks the value with `refuse_overflow` from the node's depth, refuses a spec equal to one already made at that node as a cycle naming its targets, and refuses a chain that never repeats once its links and the node's depth pass 64.
[FEAT-61](../features/FEAT-61-a-calls-value-is-configuration-on-an-any-and-a-callable-node.md) routes the `Any` and Callable call sites through the same helper.

Origin: latent since FEAT-28, which dispatched `call:` on every typed field and built a value `_accepts` refused through construction, where a `call:` key is read again; BUG-248 later listed every place a value enters for the nesting bound, and a call's value, computed during construction, was not among them.

```python
from dataclasses import dataclass

import confarg


@dataclass
class Node:
    child: "Node | None" = None


@dataclass
class C:
    n: int = 0
    node: Node | None = None


def again():
    return {"call": "__main__.again"}


def ring():
    d = {"child": None}
    d["child"] = d
    return d


for data in ({"n": {"call": "__main__.again"}}, {"node": {"call": "__main__.ring"}}):
    try:
        print(confarg.build(C, data))
    except RecursionError as e:
        print(f"{type(e).__name__}: {e}")

# expected: a ConfargError naming the cycle at 'n' (__main__.again's value is the call already made there),
#           then one naming 'node.child' as holding 'node'
# actual:   RecursionError: maximum recursion depth exceeded
#           RecursionError: maximum recursion depth exceeded
```
