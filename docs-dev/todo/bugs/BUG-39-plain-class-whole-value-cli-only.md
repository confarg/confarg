# BUG-39 — A plain class takes a whole `{…}` value from env and files, but not from the CLI

**Where:** `src/confarg/_parse_cli.py` (`_accepts_object_value`), `src/confarg/_parse_env.py`
(`_accepts_json_for`) · **Filed:** 2026-09-24
**Effort:** S · **Risk:** high · **Impact:** config

`_accepts_object_value` is the canonical "does this field take a whole `{…}` token?" predicate
([04-cli-adapters.md#whole-value-flags](../../architecture/04-cli-adapters.md#whole-value-flags)),
and it tests `_is_dc`. The environment channel does not call it: `_accepts_json_for` asks the
same question again with `_is_struct` (= `_is_dc or _is_plain_class`). So a plain class takes
the blob from env and from a file, and the CLI is the only channel that refuses it — an
unapproved cross-channel divergence
([09-invariants.md#cross-channel-parity](../../architecture/09-invariants.md#cross-channel-parity)).

Fix direction: delete the second answer. Route env through `_accepts_object_value` and let the
canonical predicate use `_is_struct` — two of three channels already accept the token, plain
classes are structs everywhere else in construction, and the predicate is documented as
deciding for the vanilla parser, static registration *and* the flat collector at once, so
whichever way it goes all five front-ends follow. That also removes most of
`_accepts_json_for`: its `[` branch re-derives `_types._is_seq_variant` plus a hand-written
union-arm `any(...)` that `_accepts_object_value` already does in one line, so the fix and the
refactor are one change (see [REF-43](../refactors/REF-43-parse-cli-path-walk-copies.md) for
the same pattern elsewhere in the walk).

```python
from dataclasses import dataclass, field
import json, pathlib, tempfile
import confarg


class Plain:  # a plain class: _is_struct is True, _is_dc is False
    def __init__(self, host: str = "h", port: int = 1) -> None:
        self.host, self.port = host, port

    def __repr__(self) -> str:
        return f"Plain({self.host!r}, {self.port})"


@dataclass
class Cfg:
    db: Plain = field(default_factory=Plain)


blob = '{"host": "x", "port": 9}'
path = pathlib.Path(tempfile.mkdtemp()) / "c.json"
path.write_text(json.dumps({"db": {"host": "x", "port": 9}}))

print(confarg.load(Cfg, argv=[], env={"P_DB": blob}, env_prefix="P_"))
print(confarg.load(Cfg, argv=[], env={}, files=[path]))
print(confarg.load(Cfg, argv=["--db", blob], env={}))

# expected: all three print Cfg(db=Plain('x', 9))
# actual:
#   env : Cfg(db=Plain('x', 9))
#   file: Cfg(db=Plain('x', 9))
#   cli : confarg.exceptions.TypeCoercionError: Cannot construct Plain at 'db':
#         expected dict, got str '{"host": "x", "port": 9}'
```
