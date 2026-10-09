---
filed: 2026-10-01
where:
  - src/confarg/_parse_cli.py::_walk_path
effort: S
risk: medium
impact: behavior
severity: minor
introduced_by: [PR-5]  # the tag fallback reads every segment after the tag as a str
---
# BUG-110 — The walk accepts a path that continues past the union tag

When no member reaches a segment spelled like the tag, `_walk_path` reads every segment
after it as a `str`, as it does below a callable's bind key, without walking them. So `--leaf.class.junk X` resolves, and
vanilla merges a dict under the tag where a class-path string belongs. The adapters refuse
the same flag at parse time: `_names_tag_by_fallback` admits a tag only as the last segment.
Fix direction: let the fallback continue the walk at `str` as an ordinary step
(`str_subtree=False`), so a segment after the tag finds nothing and vanilla raises its
unknown-field error. See
[a tag is a replayed write](../../architecture/cli-adapters/collection-patch-parity.md#a-tag-is-a-replayed-write).

Origin: latent since the initial version (PR-5): the reproduction merges the same dict there,
spelled `merge(args=…)`. The adapters refuse the flag at parse time both before and after BUG-97's
fix, which gave them `_names_tag_by_fallback`.

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
