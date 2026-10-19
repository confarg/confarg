---
filed: 2026-10-14
where:
  - src/confarg/_parse_cli.py::_open_callable_shorthand  # opens the shorthand an opener restates; a restated spec or tag is left alone
  - src/confarg/_merge.py::_set_nested
effort: M
risk: medium
impact: behavior
severity: major  # a stale argument the new target accepts binds with no error; the other cases fail loudly
introduced_by: [PR-5]  # (inferred) every flag wrote its own key into one dict, with no notion of an opener; not reproduced at PR-5
---
# BUG-238 — A restated opener or tag in one source keeps what the first one took

Within one argv, or one environment, a second opener or union tag at a node that already holds one replaces only its own key: the arguments and fields written for the first target stay beside the second. `--fn.bind pkg.f --fn.args.a 1 --fn.bind pkg.g` builds `partial(g, a=1)`, and `--task.class pkg.Sub --task.extra 1 --task.class pkg.Task` fails on `extra`, a field of the class no longer named. A whole `{…}` value followed by an opener flag does the same. Across layers the same restatement starts the node afresh ([the type decides](../../architecture/design-decisions/the-type-decides-replace-or-refine.md#the-type-decides-whether-a-value-replaces-or-refines)); within one source it should too, by the same predicate (`typedload._construct.reads_as_new_value`). The first opener at a node stays order-free: `--task.retries 1 --task.class pkg.Sub` restates nothing, and keeps `retries`.

Origin: latent since the initial version (PR-5) *(inferred)*, where the CLI and environment loops wrote each flag's key into one dict with no notion of an opener. BUG-23 taught them to open a bare callable shorthand that an opener restates (`_open_callable_shorthand`), the one restatement it handled; a restated spec or tag was left to `_set_nested`, which overwrites the one key. Found settling BUG-231, the same restatement across layers.

```python
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import confarg


def f(a: int = 0) -> int:
    return a


def g(a: int = 0) -> int:
    return a + 7


@dataclass
class Task:
    retries: int = 0


@dataclass
class SubTask(Task):
    extra: int = 0


@dataclass
class Config:
    fn: Callable[..., Any] = g
    task: Task = field(default_factory=Task)


for argv in (
    ["--fn.bind", "__main__.f", "--fn.args.a", "1", "--fn.bind", "__main__.g"],  # expected: 7
    ["--fn", json.dumps({"bind": "__main__.f", "args": {"a": 1}}), "--fn.bind", "__main__.g"],  # expected: 7
    [
        "--task.class",
        "__main__.SubTask",
        "--task.extra",
        "1",
        "--task.class",
        "__main__.Task",
    ],  # expected: Task(retries=0)
):
    try:
        cfg = confarg.load(Config, argv=argv, env={})
        print(cfg.fn(), cfg.task)
    except confarg.exceptions.ConfargError as e:
        print(f"{type(e).__name__}: {e}")
```

Actual output, from the revision that filed this:

```text
8 Task(retries=0)
8 Task(retries=0)
TypeCoercionError: Unknown field(s) ['extra'] for Task at 'task'. Valid fields: ['retries']
```
