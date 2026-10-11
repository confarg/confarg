---
filed: 2026-10-05
where:
  - src/confarg/typedload/_construct.py::_missing_field_error
  - src/confarg/_api.py::load
  - src/confarg/cli/_collect.py::_construct_from_merged
effort: L
risk: medium
impact: behavior
---
# BUG-168 — A missing field's remedy omits the CLI prefix

Under a `cli_prefix`, `_missing_field_error` still offers `--<path>`, a flag the CLI refuses
because every flag must start with `--<cli_prefix>.`. Every front-end shows it: vanilla's
`load()` and the adapters' `from_*` both reach `build()`, which knows nothing of the prefix.
The remedy is spelled at one site
([construction](../../architecture/types/construction.md#a-missing-fields-remedy-is-spelled-as-the-cli-spells-it)),
so the fix is deciding how the prefix reaches it: a keyword on the public `build()`, or
`load()` and `_construct_from_merged` respelling the error. Either way the remedy must stay
spelled at that one site, and the test belongs in `TestMissingFieldRemedyContract`.

```python
from dataclasses import dataclass

import confarg


@dataclass
class Cfg:
    host: str
    port: int


for argv in (["--app.host", "h"], ["--app.host", "h", "--port", "1"]):
    try:
        confarg.load(Cfg, argv=argv, env={}, cli_prefix="app")
    except Exception as e:
        print(type(e).__name__, e)

# expected: the remedy names a flag the CLI accepts, --app.port
# actual:
#   MissingFieldError Missing required field 'port' of type <class 'int'>. Set it via CLI (--port), environment variable, or config file.
#   UnknownArgumentError Unknown argument: '--port'. Expected arguments to start with --app.
```
