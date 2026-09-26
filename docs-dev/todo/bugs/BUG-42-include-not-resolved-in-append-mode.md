# BUG-42 — `__include__` is not resolved for a file loaded in append mode

**Where:** `src/confarg/_files.py` (`_load_file_item`) · **Filed:** 2026-09-24
**Effort:** S · **Risk:** medium · **Impact:** config

`_load_any` ends with `return _resolve_node(data, path.parent, seen)`; `_load_file_item` — the
loader `--<config_flag>.<path>+` uses, via `_pipeline._load_cli_config` — returns `loader(path)`
raw. So an `__include__` in an appended file is never resolved, and a file-only dunder key
([02-files-and-env.md#reserved-file-only-keys](../../architecture/02-files-and-env.md#reserved-file-only-keys))
survives into the merged dict as ordinary user data, where it reaches `build()` as an unknown
field.

The two loaders are otherwise the same suffix dispatch plus the same `unsupported_format`
raise, written twice — so the missing call is exactly what the duplication hid. Fix direction:
one loader, with the list-tolerant root as a parameter; `_load_raw` stays the canonical "is this
root a configuration layer?" ([09-invariants.md](../../architecture/09-invariants.md)). Filed as
part of [REF-46](../refactors/REF-46-near-duplicate-helpers-in-the-merge-core.md).

```python
from dataclasses import dataclass, field
import pathlib, tempfile
import confarg

d = pathlib.Path(tempfile.mkdtemp())
(d / "part.yaml").write_text("host: inner\n")
(d / "item.yaml").write_text("__include__: part.yaml\n")


@dataclass
class C:
    items: list[dict] = field(default_factory=list)


print(confarg.merge(C, argv=["--config.items", str(d / "item.yaml")], env={}))
print(confarg.merge(C, argv=["--config.items+", str(d / "item.yaml")], env={}))

# expected: the include is resolved either way, so both name 'host'
#   {'items': {'host': 'inner'}}
#   {'items': {'+': [{'host': 'inner'}]}}
# actual:   the append form leaks the dunder key
#   {'items': {'host': 'inner'}}
#   {'items': {'+': [{'__include__': 'part.yaml'}]}}
```
