# BUG-92 — The adapters reject a root tag on a subclass-less struct root that vanilla accepts

**Where:** `src/confarg/cli/_build.py` (`build_static_flags`, `_collect_leaf_tag_argv_specs`) ·
**Filed:** 2026-09-30
**Effort:** S · **Risk:** medium · **Impact:** behavior

Vanilla's `union_tag` rule answers the tag segment whatever the target, so
``--<prefix>.class <path>`` is accepted at the root of any struct target and reaches
`build()`, which raises the subclass complaint for a path that names no subclass — the
construction-side refusal BUG-56's route relies on ("the flag is the adapter's to accept
and the kwarg is construction's to judge"). The adapters register the root tag only when
the walk can see a subclass (`_collect_struct_specs` adds it when `__subclasses__()` is
non-empty, which `import_tagged_classes` feeding the walk covers for a tag naming a real
subclass) or when the target is a registered leaf (BUG-71); a subclass-less struct root
gets nothing, so its framework rejects the flag at parse time and the user sees
`unrecognized arguments` instead of the named complaint. An unapproved gap in
[invariants.md#cross-channel-parity](../../architecture/invariants.md#cross-channel-parity);
the noise-averse fix is argv-scanned, like the tagged-leaf flags.

```python
from dataclasses import dataclass
import confarg
from confarg.cli.argparse import make_parser, from_namespace

@dataclass
class Cfg:
    a: int = 0

argv = ["--v.class", "decimal.Decimal"]

try:
    confarg.load(Cfg, argv=argv, cli_prefix="v")
except Exception as e:
    print("vanilla :", type(e).__name__, e)

try:
    parser = make_parser(Cfg, argv=argv, cli_prefix="v")
    from_namespace(Cfg, parser.parse_args(argv), cli_prefix="v")
except SystemExit:
    print("argparse: parse-time rejection (see stderr)")

# expected: both print the same complaint — TypeCoercionError: Class 'decimal.Decimal'
#           at '' is not a subclass of __main__.Cfg.
# actual:
#   vanilla : TypeCoercionError Class 'decimal.Decimal' at '' is not a subclass of
#             __main__.Cfg.
#   argparse: usage: bug92.py [-h] [--v.a INT] ... error: unrecognized arguments:
#             --v.class decimal.Decimal  (parse-time rejection)
```
