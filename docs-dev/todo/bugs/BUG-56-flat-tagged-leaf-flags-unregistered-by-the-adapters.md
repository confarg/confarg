# BUG-56 — The flat spelling of the tagged-leaf hatch reaches no adapter

**Where:** `src/confarg/cli/_build.py` (`_specs_for_field`), `src/confarg/cli/_collect.py`
(`_collect_ns_fields`) · **Filed:** 2026-09-29
**Effort:** M · **Risk:** medium · **Impact:** behavior

An explicit `class` tag opens a registered leaf and builds it from its `__init__` parameters
([10-design-decisions.md#an-explicit-tag-opts-a-leaf-back-in](../../architecture/10-design-decisions.md#an-explicit-tag-opts-a-leaf-back-in)).
The hatch has two spellings, and only one of them crosses the adapter seam. BUG-39 fixed the
whole-value one (`--id '{"class": …, "hex": …}'`); the *flat* one — `--id.class uuid.UUID
--id.hex …`, what `ID__CLASS` / `ID__HEX` says in the environment — still works in vanilla only.
Both `_build.py` and `_collect.py` take their `_is_registered_leaf` branch before the
`_is_struct` one and stop there, so no `--<field>.class` or `--<field>.<param>` flag is ever
registered and the four frameworks reject the tokens at parse time. An unapproved gap in
[#cross-channel-parity](../../architecture/09-invariants.md#cross-channel-parity).

Fix direction: the whole-value branch already reaches past the leaf; the flat one has to as
well. `_build.py` needs the leaf's tag selector and parameter flags registered — statically like
a struct's, or argv-scanned the way an escaped opener is, since they clutter `--help` for a field
whose ordinary spelling is a scalar — and `_collect.py` needs to descend into the leaf's fields
when they are present, still coercing the plain scalar when they are not. Which of the two
registration routes it takes is the one open question, and `--help` noise is the reason it is
open.

```python
from dataclasses import dataclass
from uuid import UUID
import confarg
from confarg.cli.argparse import make_parser, from_namespace

confarg.register_leaf_type(UUID, UUID)


@dataclass
class Cfg:
    id: UUID = UUID(int=0)


argv = ["--id.class", "uuid.UUID", "--id.hex", "12345678123456781234567812345678"]
print(confarg.load(Cfg, argv=argv, env={}))
print(confarg.load(Cfg, argv=[], env={"P_ID__CLASS": "uuid.UUID", "P_ID__HEX": "1" * 32}, env_prefix="P_"))

parser = make_parser(Cfg)
print(from_namespace(Cfg, parser.parse_args(argv)))

# expected: all three build the UUID the tag names
# actual:
#   vanilla : Cfg(id=UUID('12345678-1234-5678-1234-567812345678'))
#   env     : Cfg(id=UUID('11111111-1111-1111-1111-111111111111'))
#   argparse: usage: repro.py [-h] [--id UUID] [--config [FILE ...]] ...
#             repro.py: error: unrecognized arguments: --id.class uuid.UUID
#             --id.hex 12345678123456781234567812345678
#             (click and typer exit the same way; cyclopts says
#              "Unknown option: --id.class.")
```
