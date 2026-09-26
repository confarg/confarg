# BUG-45 — An unimportable class tag silently vanishes from the adapters' merged dict

**Where:** `src/confarg/cli/_collect.py` (`_collect_ns_inheritance`) · **Filed:** 2026-09-25
**Effort:** S · **Risk:** medium · **Impact:** behavior

Vanilla stores `--<path>.<union_tag> VALUE` as a raw string and lets `construct` raise the
import error naming the bad path. The flat collector's inheritance branch imports the class
first and writes the tag back only if the import succeeded and the class verifies as a struct,
so a path with a typo in it disappears without a trace —
[byte-identity with vanilla](../../architecture/04-cli-adapters.md#byte-identical-merged-dicts)
broken, and the user hears a misleading complaint ("no 'class' discriminator was provided")
about a discriminator they did provide. The union-field branch
(`_collect_ns_union_field`) writes the tag *before* importing, matches vanilla, and the two
branches of one collector disagree — only the older one is right.

Confirmed on argparse and click; typer and cyclopts follow through the same `_merge_from_flat`
tail. A field-level tag loses more than the tag: with `db: Base` and a bad `--db.class`, the
whole `db` key is absent from the adapter's merged dict, because the recursion into the subclass
fields is skipped along with the tag.

Fix direction: write the tag before the import, exactly as `_collect_ns_union_field` does —
or extract the shared "resolve tag → import → descend" step so the two branches cannot drift;
it is written twice in `_collect.py` and a third time (under a deliberately broader `except`)
in `argparse/_completion.py`, so the fix and that small refactor are one change.

```python
from dataclasses import dataclass

import confarg
from confarg.cli.argparse import make_parser, merge_namespace


@dataclass
class Base:
    x: int = 1


@dataclass
class Sub(Base):
    y: int = 2


ARGV = ["--class", "no.such.module.Class"]

for label, merged in (
    ("vanilla", confarg.merge(Base, argv=ARGV, env={})),
    ("argparse", merge_namespace(Base, make_parser(Base, argv=ARGV).parse_args(ARGV), argv=ARGV, env={})),
):
    print(f"{label} merged: {merged!r}")
    try:
        confarg.build(Base, merged)
    except Exception as e:  # noqa: BLE001
        print(f"{label} build:  {type(e).__name__}: {e}")

# expected: both front-ends merge {'class': 'no.such.module.Class'} and both
#           build() errors name the bad import path
# actual:
#   vanilla merged: {'class': 'no.such.module.Class'}
#   vanilla build:  TypeCoercionError: Cannot import class 'no.such.module.Class' from
#                   'class' tag at '': Cannot import 'no.such.module.Class': no importable
#                   module found in path. The value must be a full dotted path, e.g.
#                   'mypackage.mymodule.MyClass'.
#   argparse merged: {}
#   argparse build: TypeCoercionError: Cannot construct 'Base' at '': it has subclasses
#                    (__main__.Sub) but no 'class' discriminator was provided. Add a 'class'
#                    field with the fully-qualified class name.
```
