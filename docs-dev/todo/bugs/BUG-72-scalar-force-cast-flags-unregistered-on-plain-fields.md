# BUG-72 — Scalar force-cast flags on non-union fields reach no adapter

**Where:** `src/confarg/cli/_build.py` (`_specs_for_field`, `_collect_patch_argv_specs`) ·
**Filed:** 2026-09-29
**Effort:** S · **Risk:** medium · **Impact:** behavior

Vanilla's `detect_force_cast` accepts a scalar cast (`--f.str`, `.int`, `.float`, `.bool`)
on *any* field: the cast applies whenever the trailing segment names no real member of the
type ([cli-parsing/casts-and-reserved-words.md#real-field-wins](../../architecture/cli-parsing/casts-and-reserved-words.md#real-field-wins)),
and a plain scalar field has no members. The adapters register cast flags only where the
stealing rule is non-obvious — statically on enum/str unions
([cli-adapters/union-inheritance-and-cast-flags.md#union-inheritance-and-cast-flags](../../architecture/cli-adapters/union-inheritance-and-cast-flags.md#union-inheritance-and-cast-flags)),
dynamically when the cast lands on a collection element — so the same flags on a plain
field are refused by the framework at parse time. `.json` is registered for every field
already, so the gap is the four scalar casts alone. An unapproved gap in
[invariants.md#cross-channel-parity](../../architecture/invariants.md#cross-channel-parity).

Fix direction: either the argv scan registers the typed scalar cast flags on plain fields
(the BUG-56 route, accepting exactly what vanilla's `detect_force_cast` accepts), or vanilla
stops accepting a cast that disambiguates nothing on a single-variant field — a maintainer
call, since the second halves of both spellings are harmless no-ops (`--host.str` on a
`str` field re-spells the value it would coerce to anyway).

```python
from dataclasses import dataclass
import confarg
from confarg.cli.argparse import make_parser, merge_namespace


@dataclass
class Cfg:
    host: str = "h"
    port: int = 1


argv = ["--host.str", "myhost", "--port.int", "42"]
print(confarg.load(Cfg, argv=argv, env={}))

parser = make_parser(Cfg, argv=argv)
print(merge_namespace(Cfg, parser.parse_args(argv), argv=argv))

# expected: both halves build Cfg(host='myhost', port=42)
# actual:
#   vanilla : Cfg(host='myhost', port=42)
#   argparse: usage: - [-h] [--host STR] [--port INT] [--config [FILE ...]]
#             [--config.locals [FILE ...]] [--config._locals [FILE ...]]
#             -: error: unrecognized arguments: --host.str myhost --port.int 42
#             (click, typer and cyclopts exit the same way; only the message differs)
```
