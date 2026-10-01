# BUG-110 — The walk accepts a path that continues past the union tag

**Where:** `src/confarg/_parse_cli.py` (`_resolve_field_type`) · **Filed:** 2026-10-01
**Effort:** S · **Risk:** medium · **Impact:** behavior

When no member reaches a segment spelled like the tag, `_resolve_field_type` returns `str`
right away, without walking the segments after it. So `--leaf.class.junk X` resolves, and
vanilla merges a dict under the tag where a class-path string belongs. The adapters refuse
the same flag at parse time: `_names_tag_by_fallback` admits a tag only as the last segment.
Fix direction: let the fallback continue the walk at `str` (`tp = str; continue`), so a
segment after the tag finds nothing and vanilla raises its unknown-field error. See
[a tag is a replayed write](../../architecture/cli-adapters/collection-patch-parity.md#a-tag-is-a-replayed-write).

```python
from dataclasses import dataclass
import confarg
from confarg.cli.argparse import make_parser, merge_namespace

@dataclass
class Cfg:
    leaf: int = 0

argv = ["--leaf.class.junk", "X"]
try:
    print("vanilla :", confarg.merge(Cfg, argv=argv, env={}, config_flag=""))
except Exception as e:
    print("vanilla :", type(e).__name__, e)
try:
    parser = make_parser(Cfg, argv=argv, config_flag="")
    print("argparse:", merge_namespace(Cfg, parser.parse_args(argv), argv=argv, config_flag=""))
except SystemExit:
    print("argparse: parse-time rejection")

# expected: vanilla raises UnknownArgumentError for '--leaf.class.junk', as argparse refuses it
# actual:
#   vanilla : {'leaf': {'class': {'junk': 'X'}}}
#   argparse: parse-time rejection
```
