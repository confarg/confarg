# BUG-91 — Vanilla silently drops the bare prefix flag's value on a struct-like root

**Where:** `src/confarg/_parse_cli.py` (`_consume_typed_arg` at an empty path) ·
**Filed:** 2026-09-30
**Effort:** S · **Risk:** medium · **Impact:** behavior

For a struct-like root (a dataclass, a plain class — a registered leaf included), the bare
``--<cli_prefix> VALUE`` flag resolves to an empty path, and the parse loop consumes the
value only to hand it to `_set_nested(ctx.data, [], value)`, a no-op: the token is accepted
without error and vanishes from the merged dict. `_handle_scalar_root` is never reached —
it serves only a root that is *not* struct-like — and the adapters register no bare flag
either (`_scalar_root_spec` covers non-struct roots only), so the four adapters reject the
flag at parse time while vanilla accepts and drops it. Both halves are wrong, in different
ways:

- the loud refusal the adapters give is arguably the right answer for a struct root, whose
  whole-value spelling is the root `--v.json` cast, not the bare flag;
- for a registered leaf as the root the eaten spelling is the leaf's *ordinary* one:
  `--v <uuid text>` fails in `build()` with `Cannot coerce dict {} to UUID ... pass a value
  it coerces from` — advice the user already followed
  ([an-explicit-tag-opts-a-leaf-back-in.md](../../architecture/design-decisions/an-explicit-tag-opts-a-leaf-back-in.md#an-explicit-tag-opts-a-leaf-back-in)).
  Whether that spelling should work (a scalar root flag for a leaf root) or be refused
  loudly is a maintainer call; silent acceptance is the one answer that cannot be right.

Found while closing BUG-71.

```python
from dataclasses import dataclass
import confarg

@dataclass
class Cfg:
    a: int = 0

print(confarg.load(Cfg, argv=["--v", "5"], cli_prefix="v"))
# expected: a loud error naming '--v' (the adapters' parse-time rejection, or vanilla's
#           no_such_field) — nothing about '--v 5' names a field of Cfg
# actual:   Cfg(a=0) — the value 5 accepted, then silently dropped
```
