---
filed: 2026-10-14
where:
  - src/confarg/_files.py::_load_includes
  - src/confarg/_files.py::_unwrap_root_key
  - src/confarg/_files.py::_load_mount
effort: S
risk: low
impact: behavior
severity: minor  # loud; a key beside __root__ (`locals: {}`) is the workaround
introduced_by: [PR-209]  # every channel's root file went through the include layering, which unwraps a fragment's __root__
---
# BUG-242 — A lone `__root__` in a root configuration file is unwrapped as a fragment's

At a document root, `__root__` holds a non-struct target's value, which `build()` reads; only a mounted fragment's lone `__root__` is its whole content, which `_files._unwrap_root_key` unwraps ([reserved keys](../../architecture/config-files/reserved-keys.md#reserved-file-only-keys)). A file passed by `files=`, `--config` or the environment's config pointer is a document root, yet it is layered by `_load_includes`, which unwraps it like a fragment: a scalar or a list is then refused as a non-mapping root, a dict loses the key `build()` reads, and so does an append to a list root. A key beside `__root__` stops the unwrap, which is why `locals:` beside it works. Fix direction: unwrap a fragment where it is mounted at a node, never at the root (`_load_mount`'s empty subpath), as `_unwrap_root_key`'s docstring already says.

Origin: regression from PR-209, which mounted a file the same way from every channel by routing the root files through `_load_mount_value` and `_load_includes`, the include layering that unwraps a fragment's `__root__`. Before it, each of the three reproductions below loaded.

```python
import tempfile
from pathlib import Path

import confarg

d = Path(tempfile.mkdtemp())
for tp, text in ((int, "__root__: 5\n"), (dict[str, int], "__root__: {a: 1}\n"), (list[int], "__root__: [1, 2]\n")):
    path = d / "c.yaml"
    path.write_text(text)
    try:
        print(tp, "->", confarg.load(tp, files=[str(path)], argv=[], env={}))
    except Exception as e:
        print(tp, "->", type(e).__name__, str(e)[:60])

# expected: 5, {'a': 1}, [1, 2]
# actual:
#   <class 'int'> -> InvalidConfigFileError Root config file must be a mapping, got int: C:\…
#   dict[str, int] -> MissingFieldError No value provided for target type dict[str, int]. Pr
#   list[int] -> InvalidConfigFileError Root config file must be a mapping, got list: C:\…
```
