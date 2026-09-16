# BUG-3 — A root-level JSON cast is refused in the environment

**Where:** `src/confarg/_parse_env.py` (`_apply_env_json_cast`) · **Filed:** 2026-09-12
**Effort:** M · **Risk:** high · **Impact:** behavior

CLI `--json '{…}'` injects a whole configuration; `<PREFIX>JSON` is declined at the root, then
warned about as an unknown field and dropped, so the configuration silently keeps its defaults.
The fix belongs in the canonical cast path rather than in a second special case in `_parse_env`.

```python
from dataclasses import dataclass
import confarg

@dataclass
class Config:
    host: str = "localhost"
    port: int = 8080

blob = '{"host": "db", "port": 5432}'
print("cli:", confarg.load(Config, argv=["--json", blob]))
print("env:", confarg.load(Config, argv=[], env={"MYAPP_JSON": blob}, env_prefix="MYAPP_"))
# expected: cli: Config(host='db', port=5432)
#           env: Config(host='db', port=5432)
# actual:   cli: Config(host='db', port=5432)
#           ConfargWarning: Environment variable 'MYAPP_JSON' has no matching field
#           (segment 'json' not found in Config). Known fields: ['host', 'port'].
#           The variable will be ignored.
#           env: Config(host='localhost', port=8080)
```
