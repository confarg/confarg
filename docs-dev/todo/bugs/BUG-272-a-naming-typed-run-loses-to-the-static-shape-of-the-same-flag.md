---
filed: 2026-10-22
where:
  - src/confarg/cli/_build.py::_collect_loop_typed_specs  # builds a spec a loader then drops
  - src/confarg/cli/_build.py::bound_runs  # counts the dropped spec as a bound run
effort: M
risk: medium
impact: behavior
severity: minor  # valid input refused by every adapter, accepted by merge()
introduced_by: [BUG-233, BUG-236, BUG-110, BUG-114]  # the naming-typed registration family
---

# BUG-272 — A flag a naming types as a run loses to the static shape of the same name

A statically registered flag whose declared shape is one token, but which a node's naming types as a multi-token run, keeps its static shape on every adapter: `_collect_loop_typed_specs` builds the wider `FlagSpec` (the guard only skips a name whose widest naming type *equals* the declared one), and each loader's first-wins skip drops it, because the static flags were loaded first.
Vanilla's loop consumes the run, the framework binds one token, so the token after it is an unrecognized argument (argparse, cyclopts) or an unexpected extra one (click, typer).
`bound_runs` reads the spec lists as built, not as loaded, so it also records the dropped spec as a run the framework never bound.

```python
from dataclasses import dataclass, field
import tempfile, os

from confarg import merge
from confarg.cli.argparse import make_parser


@dataclass
class Base:
    x: int = 0


@dataclass
class Sub(Base):
    x: list[int] = field(default_factory=list)  # a subclass widens the base's annotation


@dataclass
class Config:
    db: Base | None = None


fd, path = tempfile.mkstemp(suffix=".yaml")
with os.fdopen(fd, "w") as f:
    f.write("db:\n  class: __main__.Sub\n")

argv = ["--db.x", "1", "2"]
print(merge(Config, argv=argv, files=[path]))
# expected: {'db': {'class': '__main__.Sub', 'x': [1, 2]}}

parser = make_parser(Config, files=[path], argv=argv)
try:
    parser.parse_args(argv)
except SystemExit:
    print("refused")
# actual: error: unrecognized arguments: 2
```

`merge()` accepts the same argv on click and typer too ("Got unexpected extra argument (2)"), and the same one-token-vs-run mismatch would reach the merge's stray check wherever the host has a positional to swallow the extra token.

Fix direction: a loop-typed spec for a name the static walk already registered must *replace* the registered shape when it is wider (`_arity_rank` is the ranking to compare), in every loader, so the framework binds at least what vanilla takes — and `bound_runs` must then read what was loaded (or the loaders must return what they kept), so the stray check does not believe in a run the framework never bound.
[a-node-types-its-keys-by-the-class-it-names.md#the-adapters](../../architecture/design-decisions/a-node-types-its-keys-by-the-class-it-names.md#the-adapters)

Origin: regression from the fix for BUG-233, BUG-236, BUG-110 and BUG-114, which typed the flags below a node by the class a layer names and let registration follow through `_collect_loop_typed_specs`.
That family assumed every naming-typed flag is one the static walk did not register: where the subclasses *disagree* about a field's annotation, the static walk registers the fold (the base's one token) while the naming types the subclass's run, and the wider spec is silently discarded by the loaders' first-wins skip.
Before it, vanilla typed the flag by the base's annotation too and refused the run, so both sides agreed.
