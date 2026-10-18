---
filed: 2026-10-13
where:
  - src/confarg/_parse_cli.py::_advance_field_type  # a Callable and an Any answer one untyped segment, whatever class the spec names
  - src/confarg/_parse_cli.py::_walk_path
  - src/confarg/_parse_env.py::_accepts_json_for
  - src/confarg/cli/_build.py::_collect_callable_factory_specs
effort: M  # the design pass: how the type walk learns the class a sibling key names
needs_design: true
risk: high  # the CLI walk every front-end shares; a wrong arity silently takes or leaves a token
impact: behavior
severity: minor  # refused loudly; the `.json` cast reaches it on the CLI and in the environment
introduced_by: [PR-5]  # the walk has always typed a key below a Callable as one str token
---
# BUG-236 — A list argument of a class named below a Callable or an `Any` takes one token

A `class:` spec's other keys are the named class's constructor arguments ([spec grammar](../../architecture/callables.md#spec-grammar)), but the CLI walk types every key below a Callable field as `str`, and every key below an `Any` field as `Any`, without reading the class the spec names. So an argument the class declares as a list takes one token: `--f.class pkg.Joiner --f.parts a b` refuses `b` as a stray positional, where a list field anywhere else takes the run. The environment has the same blind spot: `APP_F__PARTS='["a","b"]'` stays text below a Callable, though it decodes on a field typed `list[str]` ([type-guided parsing](../../architecture/cli-parsing/type-guided-parsing.md)). The adapters register `--f.parts` from the class's signature, typed as a list (`_collect_callable_factory_specs`), while vanilla's loop, which writes their CLI channel, takes one token, so the front-ends fail differently: vanilla refuses `b`, argparse and cyclopts bind it to the flag and `build()` then refuses the one token as no list (`Cannot construct list at 'f.parts': expected list or dict with integer keys, got str 'a'`), and click and typer exit with a usage error (status 2). FEAT-42 gave an `Any` field the same walk, so `--x.class pkg.Joiner --x.parts a b` fails the same way ([limitations](../../architecture/limitations.md#callables-and-serialization)).

The `.json` cast reaches the list on both channels (`--f.parts.json '["a","b"]'`, `APP_F__PARTS__JSON`). The index spelling does not below a Callable, `--f.parts.0 a` being refused as an unknown field: that is BUG-233, the same root, since the walk cannot see the class at that path either. A fix has to type a path by the class a sibling key names, which only argv and the merged data know, and which `import_tagged_classes` already does for a struct's union tag.

Origin: latent since the initial version (PR-5); the reproduction fails the same way there and at every release since. The walk has always typed a key below a Callable as one `str` token, leaving the class's own types to construction, which comes after the tokens are consumed.

```python
import sys
from collections.abc import Callable
from dataclasses import dataclass

import confarg


class Joiner:
    def __init__(self, parts: list[str]) -> None:
        self.parts = parts

    def __call__(self) -> str:
        return "-".join(self.parts)


sys.modules["b236"] = sys.modules[__name__]
Joiner.__module__ = "b236"


@dataclass
class Config:
    f: Callable[[], str] | None = None


try:
    print(confarg.load(Config, argv=["--f.class", "b236.Joiner", "--f.parts", "a", "b"], env={}).f())
except Exception as e:
    print(f"{type(e).__name__}: {e}")

# expected: a-b
# actual:   UnknownArgumentError: Unexpected positional argument: 'b'. All arguments must be named flags (e.g. --fieldname value).
```
