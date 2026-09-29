# BUG-67 — A plain fixed tuple's index patch lands as the applied value in the adapters, as a list-op dict in vanilla

**Where:** `src/confarg/cli/_collect.py` (`_merge_from_flat`, the patch-scan deep merge) ·
**Filed:** 2026-09-29
**Effort:** M · **Risk:** medium · **Impact:** behavior

Found while fixing BUG-66 (closed); the namedtuple's merge shapes were settled there, and the
plain `tuple[X, Y]` beside it turned out to disagree on the same argv.

`--pair 1 2` stores a plain list on both sides, and `--pair.0 5` is a collection patch on both.
Vanilla's `_set_nested` promotes the stored list to the `LIST_REPLACE_BASE_KEY` base so the
index patch rides along in one list-op dict — the shape `build()` applies. The adapters deep-merge
the patch scan over the collected list, and `_deep_merge` applies the index patch on the spot,
so the merged dict holds the *result* (`[5, 2]`) rather than the operation
(`{'*': [1, 2], '0': 5}`). Both build the same tuple, so only the
[byte-identical](../../architecture/cli-adapters/parity.md#byte-identical-merged-dicts) rule is
broken — and a lower-priority source (`--config` file, env) can no longer see the base list the
operation was meant to apply against, which is the point of the list-op shape.

```python
from dataclasses import dataclass

import confarg
from confarg.cli.argparse import make_parser, merge_namespace


@dataclass
class T:
    pair: tuple[int, int] = (0, 0)


argv = ["--pair", "1", "2", "--pair.0", "5"]
parser = make_parser(T, argv=argv)
print("argparse:", merge_namespace(T, parser.parse_args(argv), argv=argv, env={}))
print("vanilla :", confarg.merge(T, argv=argv, env={}))

# expected: the two merged dicts are equal
# actual:
#   argparse: {'pair': [5, 2]}
#   vanilla : {'pair': {'*': [1, 2], '0': 5}}
```
