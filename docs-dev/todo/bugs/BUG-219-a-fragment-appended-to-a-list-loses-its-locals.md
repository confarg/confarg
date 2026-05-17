---
filed: 2026-10-10
where:
  - src/confarg/_pipeline.py::_iter_namespace_nodes
  - src/confarg/_api.py::_strip_locals_node
  - src/confarg/_parse_cli.py::_locals_keys_at
effort: M  # inferred: the expression resolver's anchoring may need the same fix as the two walkers
risk: high
impact: behavior
severity: major  # a valid mount fails loudly; inlining the variables is the only way around it
introduced_by: [PR-105]  # per-node namespaces walked the merged dict's keys as field names
---

# BUG-219 — A fragment appended to a list loses its `locals`

A fragment mounted at a struct field (`--config.one frag.yaml`) reads its own `${locals.n}`, as [per-node namespaces](../../architecture/locals.md#per-node-namespaces) promise.
The same fragment appended to a list of structs (`--config.items+ frag.yaml`) fails: its `${locals.n}` finds no namespace.

The append records the item below the list's `ListOp.APPEND` marker ([deep merge](../../architecture/pipeline/deep-merge.md#no-channel-types-an-op)), and the walkers that look for a namespace (`_iter_namespace_nodes`, `_strip_locals_node`) skip what a pending op holds, so the appended item is never seen as a node that may hold a namespace.
Before `ListOp` was an enum they descended into the marker as the field `__append__`, which found nothing either: `_locals_keys_at(Cfg, ["items", "__append__", "0"])` returns `()` where `["items", "0"]` returns `('locals', '_locals')`.
Fix direction: a walker reaching an op marker reads its value by the list it builds (an append's items as list elements) rather than as a field.

Origin: latent since locals were introduced (PR-105), whose per-node lookup walks the merged dict's keys as path segments; `--config.<f>+` already stored its fragment under the append op then.
It reproduces unchanged at PR-105.

```python
import pathlib
import tempfile
from dataclasses import dataclass, field

import confarg


@dataclass
class Item:
    name: str = ""


@dataclass
class Cfg:
    items: list[Item] = field(default_factory=list)
    one: Item = field(default_factory=Item)


frag = pathlib.Path(tempfile.mkdtemp()) / "frag.yaml"
frag.write_text("locals: {n: b}\nname: '${locals.n}'\n")
for argv in (["--config.one", str(frag)], ["--config.items+", str(frag)]):
    try:
        print(argv[0], "->", confarg.load(Cfg, argv=argv, env={}))
    except Exception as e:
        print(argv[0], "->", type(e).__name__, e)

# expected: --config.items+ -> Cfg(items=[Item(name='b')], one=Item(name=''))
# actual:
#   --config.one -> Cfg(items=[], one=Item(name='b'))
#   --config.items+ -> MissingReferenceError Field 'locals' not found in configuration
```
