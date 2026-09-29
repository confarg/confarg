# BUG-70 — A union-of-structs field is a mount point with no `--config.<field>` entry

**Where:** `src/confarg/cli/_build.py` (`_collect_subconfig_specs`) · **Filed:** 2026-09-29 ·
*(found while fixing BUG-50, which narrowed this skip to unions)*
**Effort:** S · **Risk:** low · **Impact:** behavior

`_collect_subconfig_specs` emits a `--<config_flag>.<subpath>` help entry for a struct field
and, since BUG-50, for a dict field — but still skips a union of structs (`_unwrap_optional`
leaves it a union, and neither `_is_struct` nor `_is_dict` matches it). Mounting there works:
the fragment names its variant with the class tag, and the BUG-50 check accepts the path because
`_resolve_field_type` resolves a union field. So the one mount point whose fragment *needs* a
tag to make sense is also the one `--help` does not show.

Fix direction: admit a union whose variants are struct-like, and say in the entry's help text
that the file's top level must name the variant with the tag — the reader cannot guess that
from the field's flags alone, which are per-variant.

```python
from dataclasses import dataclass, field
import pathlib

import confarg
from confarg.cli import build_static_flags

frag = pathlib.Path("frag.yaml")
frag.write_text("kind: A\na: 5\n")


@dataclass
class A:
    kind: str = "A"
    a: int = 0


@dataclass
class B:
    kind: str = "B"
    b: int = 1


@dataclass
class Holder:
    db: "A | B" = field(default_factory=A)


flags = sorted(
    f.name
    for f in build_static_flags(Holder, union_tag="kind", config_flag="config")
    if f.name.startswith("config")
)
print(flags)
print(confarg.merge(Holder, argv=["--config.db", str(frag)], env={}))

# expected: 'config.db' registered, and the mount succeeds
#   ['config', 'config._locals', 'config.db', 'config.locals']
#   {'db': {'kind': 'A', 'a': 5}}
# actual:   the mount succeeds but the flag is not discoverable
#   ['config', 'config._locals', 'config.locals']
#   {'db': {'kind': 'A', 'a': 5}}
```
