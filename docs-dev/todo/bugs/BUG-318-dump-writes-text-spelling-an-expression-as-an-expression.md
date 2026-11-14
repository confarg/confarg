---
filed: 2026-11-09
where:
  - src/confarg/_serialize.py::_serialize_leaf  # every string an object dump writes passes here
  - src/confarg/dictexpr/_expressions.py::escape_expressions  # the canonical spelling
effort: M  # keys, tags and Any nodes write strings too, and the read-back check meets the escaped text
risk: medium  # every string of every object dump goes through it; a raw merged dict must stay verbatim
impact: behavior  # such text is written escaped, and loads back as the text it was
severity: critical  # with a field named x, the reload silently computes another value
introduced_by: [PR-5]
---

# BUG-318 — `dump()` writes text spelling `${...}` as an expression, which the reload evaluates

A `str` value holding `${x}` is written as it stands, so reloading the dump evaluates it: it fails on a missing reference, or silently reads whatever `x` holds.
The read-back that asks every leaf ([a leaf is asked whether it reads back](../../architecture/types/serialization.md#a-leaf-is-asked-whether-it-reads-back)) does not see it, since it runs `construct`, which resolves no expression.
The escape exists: `$${x}` reads as the text `${x}`, and `dictexpr.escape_expressions` spells it ([invariants](../../architecture/invariants.md)), which the default layer lays a default string with.

Fix direction: an object dump writes each string through `escape_expressions`, keys and the strings in a tag or an `Any` node included, and the read-back compares against the unescaped text, or it warns falsely on every such string.
A raw dict stays verbatim: `dump_file(merge(...))` writes its expressions on purpose ([api seams](../../architecture/pipeline/api-seams.md#public-api-seams)).
Whoever reads the dump, or passes it to `construct` directly, then sees `$${x}`: the design pass weighs that against the forensic dump ([the object dump is forensic](../../architecture/design-decisions/the-object-dump-writes-state.md#the-object-dump-is-forensic)).
OmegaConf's plain `to_yaml` writes `\${x}`, which reloads as the text; with `resolve=True` it has this bug, and the reload raises `InterpolationKeyError` (run).

Origin: latent since the initial version (PR-5), which brought the object dump and expressions together, its `_serialize` writing a string as it stood.

```python
from dataclasses import dataclass

import confarg


@dataclass
class C:
    f: str = ""


dumped = confarg.dump(C("${x}"))
print(dumped)
print(confarg.build(C, dumped))
# expected: {'f': '$${x}'}
#           C(f='${x}')
# actual:   {'f': '${x}'}
#           MissingReferenceError: Field 'x' not found in configuration
```
