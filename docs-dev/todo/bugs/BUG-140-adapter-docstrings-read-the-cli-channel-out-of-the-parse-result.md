# BUG-140 — The `from_namespace` / `from_context` docstrings still read the CLI channel out of the parse result

**Where:** `src/confarg/cli/argparse/_namespace.py` (`from_namespace`) ·
`src/confarg/cli/click/_context.py` / `src/confarg/cli/typer/_context.py` (`from_context`) ·
`src/confarg/cli/argparse/_register.py` (`populate_parser`) · **Filed:** 2026-10-03
**Effort:** S · **Risk:** low · **Impact:** behavior

Since REF-72, argv is the only writer: the CLI channel is vanilla's loop over the argv the
framework parsed, and the parse result is only *checked* — a confarg flag it holds that argv
does not spell is refused (`_require_argv_spells`), and its values are never read. The adapters'
docstrings still describe the pre-REF-72 flow: `from_namespace` says "then CLI arguments from
the Namespace" and "Only fields registered by `populate_parser` are consumed from `ns`", the
click and typer `from_context` say "then CLI arguments from the Context" and "Options absent
from the Context … fall back", and `populate_parser` says "type coercion happens in
`from_namespace`". A reader concludes the parse result's values feed the merge, so a doctored or
hand-built Namespace should carry values in. Fix direction: say the CLI channel is read off argv
by vanilla's loop and the parse result only has to agree with it, in all four docstrings, see
[model.md#argv-is-the-only-writer](../../architecture/cli-adapters/model.md#argv-is-the-only-writer).

```python
from dataclasses import dataclass

from confarg.cli.argparse import make_parser, merge_namespace


@dataclass
class Config:
    tags: list[str]


parser = make_parser(Config)
ns = parser.parse_args(["--tags", "a", "--tags", "b"])
ns.tags = ["HACKED"]  # the value from_namespace's docstring says the CLI channel comes from
print(merge_namespace(Config, ns, argv=["--tags", "a", "--tags", "b"], env={}))
# docstring ("CLI arguments from the Namespace"): {'tags': ['HACKED']}
# actual:                                  {'tags': ['a', 'b']}
```
