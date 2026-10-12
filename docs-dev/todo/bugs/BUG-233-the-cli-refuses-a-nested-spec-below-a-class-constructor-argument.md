---
filed: 2026-10-12
where:
  - src/confarg/_parse_cli.py::_advance_field_type  # a Callable answers str for one segment only
  - src/confarg/cli/_build.py::_callable_argument_targets
effort: M
risk: medium
impact: behavior
severity: major  # a configuration files and the environment accept is refused on the CLI
introduced_by: [PR-11]  # the walk's per-segment refactor
---
# BUG-233 — The CLI refuses a nested spec below a `class:` constructor argument

A `class:` spec's constructor arguments are its other keys ([spec grammar](../../architecture/callables.md#spec-grammar)), and one of them may be a Callable that takes a spec of its own: `{class: Wrap, inner: {class: Mul, factor: 4}}`. A file and the environment (`APP_F__INNER__FACTOR=4`) both build it, but the CLI refuses `--f.inner.factor` as an unknown argument, though it accepts `--f.inner.class`. The CLI walk answers `str` for any segment below a Callable field, so `f.inner` is a string and nothing lies below it. A `bind:` target is reachable at any depth only because `bind`, `call` and `args` open a subtree (`_opens_spec_subtree`). Cross-channel parity breaks ([invariants](../../architecture/invariants.md#cross-channel-parity)). The fix has to decide how deep a path below a Callable stays open, without the opener, which a path does not see. The adapters register a flag on the same walk, so they refuse it too *(inferred: only vanilla was run)*.

Origin: PR-11 refactored `_resolve_field_type` into a per-segment `_advance_field_type`. Before it, a non-opener segment below a Callable returned `str` for the whole remaining path, so a constructor argument's own keys were accepted at any depth. After it, `str` holds for one segment only, and the next one walks from `str` and finds nothing. It is a regression: the reproduction prints `4` at PR-5 and up to the revision before PR-11, and fails from PR-11 on (bisected).

```python
from collections.abc import Callable
from dataclasses import dataclass

import confarg


class Mul:
    def __init__(self, factor: int) -> None:
        self.factor = factor

    def __call__(self, x: int) -> int:
        return x * self.factor


class Wrap:
    def __init__(self, inner: Callable[[int], int]) -> None:
        self.inner = inner

    def __call__(self, x: int) -> int:
        return self.inner(x)


@dataclass
class Config:
    f: Callable[[int], int]


env = {"APP_F__CLASS": "__main__.Wrap", "APP_F__INNER__CLASS": "__main__.Mul", "APP_F__INNER__FACTOR": "4"}
print(confarg.load(Config, argv=[], env=env, env_prefix="APP_").f(1))
# 4
argv = ["--f.class", "__main__.Wrap", "--f.inner.class", "__main__.Mul", "--f.inner.factor", "4"]
print(confarg.load(Config, argv=argv, env={}).f(1))
# expected: 4
# actual:   confarg.exceptions.UnknownArgumentError: Unknown argument: '--f.inner.factor' (field 'f.inner.factor' not found)
```
