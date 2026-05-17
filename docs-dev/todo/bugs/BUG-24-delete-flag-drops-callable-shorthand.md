# BUG-24 — A delete flag drops the callable shorthand it refines in the adapters

**Where:** `src/confarg/cli/_collect.py` (`_collect_callable_spec`) · **Filed:** 2026-09-15
**Effort:** M · **Risk:** high · **Impact:** behavior

A `--<field>.<sub>-` delete is a patch op, so it reaches the merged dict through
`_collect_cli_patch_ops`, not the flat collector. The collector therefore sees no sibling
flag beside the bare string, stores the shorthand alone, and the patch dict then deep-merges
over it — replacing the scalar instead of opening it, the way a whole value and its
refinement do everywhere else. Vanilla keeps both. The shorthand needs to survive the
deep merge with the patch ops, which is where the whole-value/patch split already bites
([04-cli-adapters.md#collection-patch-parity](../../architecture/04-cli-adapters.md#collection-patch-parity)).
Found while fixing BUG-23; the crash it grew out of is gone, this parity gap is not.

```python
import argparse
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import confarg
from confarg.cli.argparse import merge_namespace, populate_parser


def shout(name: str, punct: str = ".") -> str:
    return f"{name.upper()}{punct}"


@dataclass
class Config:
    fn: Callable[..., Any] = str.upper


argv = ["--fn", "__main__.shout", "--fn.bind-"]
print("vanilla: ", confarg.merge(Config, argv=argv, env={}))
parser = argparse.ArgumentParser()
populate_parser(Config, parser, argv=argv)
print("argparse:", merge_namespace(Config, parser.parse_args(argv), argv=argv, env={}))
# expected: vanilla:  {'fn': {'fn': '__main__.shout', 'bind': _DELETE_}}
#           argparse: {'fn': {'fn': '__main__.shout', 'bind': _DELETE_}}
# actual:   vanilla:  {'fn': {'fn': '__main__.shout', 'bind': _DELETE_}}
#           argparse: {'fn': {'bind': _DELETE_}}
```
