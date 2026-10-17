---
filed: 2026-10-16
where:
  - src/confarg/dictexpr/_expressions.py::_eval_expr
  - src/confarg/exceptions.py::_in_expression
effort: S
risk: low
impact: behavior
severity: minor  # loud, with a misleading reason
introduced_by: [PR-5]  # the initial evaluator reported an operator's failure as str(exc)
---

# BUG-247 — A decimal signal fails an expression with a list of classes

An expression's runtime failure ends with Python's own text ([an evaluation failure names its expression](../../architecture/expressions/resolution.md#an-evaluation-failure-names-its-expression)).
A `decimal` signal carries no text, only the list of signals raised, so `${d ** 10 ** 9}` on a `Decimal` reads `[<class 'decimal.Overflow'>]`.
Fix direction: when an exception's text names no cause, as a `decimal.DecimalException`'s does, name the exception instead (`decimal Overflow`).

Origin: latent since the initial version (PR-5), whose evaluator raised `ExpressionEvalError(str(exc))` for any operator failure; BUG-135 kept Python's own text after the quoted expression.

```python
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import confarg
from confarg.exceptions import ConfargError


@dataclass
class Config:
    d: Decimal = Decimal("1.1")
    v: Any = None


try:
    confarg.load(Config, argv=["--v", "${d ** 10 ** 9}"], env={})
except ConfargError as exc:
    print(exc)
# expected: the failure named in words, e.g. a decimal overflow
# actual:   Error in expression '${d ** 10 ** 9}': [<class 'decimal.Overflow'>]
```
