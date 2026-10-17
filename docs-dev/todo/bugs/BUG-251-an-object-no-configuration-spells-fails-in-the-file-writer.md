---
filed: 2026-10-17
where:
  - src/confarg/_api.py::dump_file
  - src/confarg/_serialize.py::_serialize_held_object
effort: S
needs_design: true  # refuse at dump_file naming the path, or let the writer fail and wrap its error
risk: low
impact: behavior
severity: minor  # loud, though the writer's own exception; dump() warned first
introduced_by: [PR-5]  # dump_file hands the serialized dict to the format writers as it stands
---

# BUG-251 — An object no configuration spells fails in the file writer, with the writer's own error

An `Any` node holding an object no spec rebuilds, such as a lock, is written untyped by `dump()`, with a `ConfargWarning` saying it will not read back ([an Any node dumps the spec that rebuilds it](../../architecture/types/serialization.md#an-any-node-dumps-the-spec-that-rebuilds-it)).
`dump_file()` then hands it to the format writer, which refuses it with its own exception: PyYAML's `RepresenterError`, `json`'s and `tomli_w`'s `TypeError`, none naming the path and none a `ConfargError`.
Fix direction: `dump_file()` refuses a value the writer cannot hold with a `ConfargError` naming its path, either before writing or by wrapping the writer's refusal.
A typed field holding such a value is refused by `dump()` itself since FEAT-14 ([an unsupported leaf is refused both ways](../../architecture/types/serialization.md#an-unsupported-leaf-is-refused-both-ways)); [BUG-245](BUG-245-dumping-a-non-string-key-to-toml-or-json-escapes-as-a-raw-typeerror.md) is the same symptom for a dict key, from the same origin, and [BUG-194](BUG-194-a-bind-keyword-built-as-a-struct-dumps-as-the-instance.md) for a `bind:` keyword built as a struct.

Origin: latent since the initial version (PR-5), whose `dump_file` writes the dict `dump()` returns through each format's writer with no check.
FEAT-42 added the warning to `dump()`, and left the object in the dict.

```python
import tempfile
import threading
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import confarg


@dataclass
class Config:
    lock: Any = field(default_factory=threading.Lock)


warnings.simplefilter("ignore", confarg.exceptions.ConfargWarning)
tmp = Path(tempfile.mkdtemp())
for name in ("out.yaml", "out.json", "out.toml"):
    try:
        confarg.dump_file(Config(), tmp / name)
        print(name, "-> written")
    except Exception as e:
        print(name, "->", f"{type(e).__name__}: {e}")

# expected: a ConfargError naming 'lock' for each format
# actual:
#   out.yaml -> RepresenterError: ('cannot represent an object', <unlocked _thread.lock object at 0x...>)
#   out.json -> TypeError: Object of type lock is not JSON serializable
#   out.toml -> TypeError: Object of type 'lock' is not TOML serializable
```
