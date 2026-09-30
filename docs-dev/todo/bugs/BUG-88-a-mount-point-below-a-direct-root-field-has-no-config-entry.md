# BUG-88 — A mount point below a direct root field has no `--config.<path>` entry

**Where:** `src/confarg/cli/_build.py` (`_collect_subconfig_specs`) · **Filed:** 2026-09-30
**Effort:** L · **Risk:** medium · **Impact:** behavior

`_check_mount_subpath` accepts a mount at whatever depth it resolves — dict keys and sequence
indices included
([type-guided-parsing](../../architecture/cli-parsing/type-guided-parsing.md#type-guided-parsing))
— but `_collect_subconfig_specs` walks only the root's direct fields, so every mount point
below the first level is accepted at parse time and invisible in `--help`. The same shape as
BUG-50 (closed) and BUG-70 (closed), one level down: `--config.<mount point>` is a projection
of the configuration tree onto filenames
([mount-keyword-per-channel](../../architecture/design-decisions/mount-keyword-per-channel.md#the-mount-keyword-is-spelled-per-channel)),
and this projection stops at depth 1.

Fix direction: recurse into struct fields — the dead `prefix` parameter of
`_collect_subconfig_specs` (its only caller passes `""`) is the natural hook, and should be
removed instead if the decision is not to recurse. The decision to record first is the noise
trade-off: full recursion adds one entry per struct node, where `config_subkeys=False` gates
only the root's entries today; a depth gate is the middle option.

```python
from dataclasses import dataclass, field
import pathlib

import confarg
from confarg.cli import build_static_flags


@dataclass
class DbA:
    kind: str = "A"
    a: int = 0


@dataclass
class DbB:
    kind: str = "B"
    b: int = 1


@dataclass
class Inner:
    db: "DbA | DbB" = field(default_factory=DbA)


@dataclass
class Outer:
    inner: Inner = field(default_factory=Inner)


frag = pathlib.Path("frag.yaml")
frag.write_text("kind: A\na: 5\n")

flags = sorted(
    f.name
    for f in build_static_flags(Outer, union_tag="kind", config_flag="config")
    if f.name.startswith("config")
)
print(flags)
print(confarg.merge(Outer, argv=["--config.inner.db", str(frag)], env={}, union_tag="kind"))

# expected: 'config.inner.db' registered beside 'config.inner', and the mount succeeds
#   ['config', 'config._locals', 'config.inner', 'config.inner.db', 'config.locals']
#   {'inner': {'db': {'kind': 'A', 'a': 5}}}
# actual:   the mount succeeds but the flag is not discoverable
#   ['config', 'config._locals', 'config.inner', 'config.locals']
#   {'inner': {'db': {'kind': 'A', 'a': 5}}}
```
