# BUG-71 — The flat tagged-leaf hatch on a scalar root reaches no adapter

**Where:** `src/confarg/cli/_build.py` (`_collect_leaf_tag_argv_specs`, `build_static_flags`),
`src/confarg/cli/_collect.py` (`_collect_ns_fields`) · **Filed:** 2026-09-29
**Effort:** S · **Risk:** medium · **Impact:** behavior

BUG-56 taught the adapters the flat spelling of the tagged-leaf hatch
([design-decisions/an-explicit-tag-opts-a-leaf-back-in.md#an-explicit-tag-opts-a-leaf-back-in](../../architecture/design-decisions/an-explicit-tag-opts-a-leaf-back-in.md#an-explicit-tag-opts-a-leaf-back-in))
for a *field*, by scanning argv for a flag whose path descends below a registered leaf.
A registered leaf as the **root** target has no field to descend from: with `cli_prefix="v"`
the tag flag is `--v.class`, whose only segment is the tag, so the scan finds no leaf at a
proper prefix of the path and registers nothing — while vanilla accepts it, because its
type walk answers the tag segment through the `union_tag` rule whatever the target. An
unapproved gap in
[invariants.md#cross-channel-parity](../../architecture/invariants.md#cross-channel-parity).

Two side observations for whoever picks this up:

- `_collect_struct_specs` walks the scalar root structurally (a registered leaf is
  struct-shaped), so the leaf's `__init__` params are *already* in `--help`
  (`--v.hex ANY`, …) — statically, the very noise BUG-56's argv-scanned route avoided for
  fields. The tag flag alone is missing (`name == union_tag` is skipped in the field loop).
- On the merge side, the non-struct-root branch of `_collect_ns_fields` never writes a tag
  back, so even a registered tag flag would still need collector work.

```python
from uuid import UUID
import confarg
from confarg.cli.argparse import make_parser, merge_namespace

confarg.register_leaf_type(UUID, UUID)

argv = ["--v.class", "uuid.UUID", "--v.hex", "12345678123456781234567812345678"]
print(confarg.load(UUID, argv=argv, env={}, cli_prefix="v"))

parser = make_parser(UUID, argv=argv, cli_prefix="v")
print(merge_namespace(UUID, parser.parse_args(argv), argv=argv, cli_prefix="v"))

# expected: both print 12345678-1234-5678-1234-567812345678
# actual:
#   vanilla : 12345678-1234-5678-1234-567812345678
#   argparse: usage: - [-h] [--v.hex ANY] [--v.bytes ANY] [--v.bytes_le ANY]
#             [--v.fields ANY] [--v.int ANY] [--v.version ANY] [--v.is_safe ANY]
#             [--v.config [FILE ...]] [--v.config.locals [FILE ...]]
#             [--v.config._locals [FILE ...]]
#             -: error: unrecognized arguments: --v.class uuid.UUID
#             (click, typer and cyclopts exit the same way; only the message differs)
```
