# BUG-29 — A bind subkey's delete flag is registered as if it took a value

**Where:** `src/confarg/cli/_build.py` (`_collect_callable_bind_argv_specs`) · **Filed:** 2026-09-17
**Effort:** S · **Risk:** medium · **Impact:** config

Bind subkeys are registered from the *path* (BUG-25), but the scan reads the raw argv key
without asking `_parse_flag_mode` what mode it is in, so `--f.bind.<key>-` still matches
`_addresses_callable_bind` and is registered with a value and claimed in `existing_names`.
The value-less delete spec `_collect_patch_argv_specs` would have produced never gets its
turn, and all three adapters demand an argument for a flag that takes none. Strip the mode
suffix before the predicate, the way the patch scan does
([04-cli-adapters.md#static-and-dynamic-flags](../../architecture/04-cli-adapters.md#static-and-dynamic-flags)).
Found while fixing BUG-24.

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


argv = ["--fn.fn", "__main__.shout", "--fn.bind.punct-"]
print("vanilla: ", confarg.merge(Config, argv=argv, env={}))
parser = argparse.ArgumentParser()
populate_parser(Config, parser, argv=argv)
try:
    print("argparse:", merge_namespace(Config, parser.parse_args(argv), argv=argv, env={}))
except SystemExit as e:
    print("argparse: SystemExit", e)
# expected: vanilla:  {'fn': {'fn': '__main__.shout', 'bind': {'punct': _DELETE_}}}
#           argparse: {'fn': {'fn': '__main__.shout', 'bind': {'punct': _DELETE_}}}
# actual:   vanilla:  {'fn': {'fn': '__main__.shout', 'bind': {'punct': _DELETE_}}}
#           argparse: SystemExit 2
#             (error: argument --fn.bind.punct-: expected one argument)
```
