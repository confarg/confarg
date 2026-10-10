---
filed: 2026-10-11
where:
  - src/confarg/cli/_build.py::_collect_struct_specs
effort: L  # how deep a recursive type's flags register is a decision to record first
risk: medium
impact: behavior
severity: major  # an adapter cannot register the target at all, with a raw RecursionError
introduced_by: [PR-5]  # _walk_struct recursed into every struct field with no cycle guard
---
# BUG-224 — A self-referential type crashes flag registration with a `RecursionError`

`build_static_flags` recurses into every struct field (`_collect_struct_specs` through `_specs_for_field`) with nothing to stop it, so a type that holds itself (`child: Node | None`) recurses until Python's limit. Every `populate_*` and `build_static_flags` call on such a target raises `RecursionError`, while vanilla `load()` reads `--child.child.a` at any depth, so all four adapters are left out of a target vanilla handles.

Fix direction: stop the static walk at a struct already on the path, as the mount-point listing does ([every mount point has a help entry](../../architecture/design-decisions/every-mount-point-has-a-help-entry.md#every-mount-point-has-a-help-entry)), and register the deeper paths when argv types them ([static and dynamic flags](../../architecture/cli-adapters/static-and-dynamic-flags.md#static-and-dynamic-flags)). Which paths stay static and which become dynamic is the decision to record first, since a `--child.child.a` the framework does not register is refused before vanilla's loop sees it.

Origin: latent since PR-5. The initial version's `_walk_struct` recursed into every struct field, `Optional` unwrapped, with no cycle guard, and PR-13 carried that recursion into the framework-neutral `_collect_struct_specs` unchanged. No other open bug names PR-5 for this walk.

```python
from __future__ import annotations

import argparse
from dataclasses import dataclass

import confarg
from confarg.cli.argparse import populate_parser


@dataclass
class Node:
    a: int = 0
    child: Node | None = None


print(confarg.load(Node, argv=["--child.child.a", "5"], env={}))
try:
    populate_parser(Node, argparse.ArgumentParser(), argv=[])
except RecursionError as e:
    print(f"RecursionError: {e}")

# expected: populate_parser registers Node's flags, as vanilla load() reads them
#   Node(a=0, child=Node(a=0, child=Node(a=5, child=None)))
# actual:   vanilla reads the path, populate_parser crashes
#   Node(a=0, child=Node(a=0, child=Node(a=5, child=None)))
#   RecursionError: maximum recursion depth exceeded
```
