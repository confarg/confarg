---
filed: 2026-11-08
where:
  - src/confarg/_types.py::_spell_type  # unwraps an alias, then spells a generic's arguments the same way
  - src/confarg/_types.py::_spell_argument
effort: S
risk: low  # TestARecursiveAlias covers the alias; a refusal test beside it closes it
impact: behavior  # a refusal that crashes names the type
severity: minor  # invalid input answered with a raw exception
introduced_by: unknown  # bisected to the revision bookmarked fix/errmsg, "fix: Spell a missing field's type, a Literal and a generic's arguments as every message names a type", which closes no ticket and is not merged
---

# BUG-316 — A refusal at a recursive type alias raises `RecursionError`

Every refusal at a field typed by a recursive alias, `type Json = int | str | list[Json] | dict[str, Json]`, raises `RecursionError` instead of its `TypeCoercionError`: the message spells the type, `_spell_type` unwraps the alias and spells `list[Json]`'s argument by unwrapping the alias again, without end.
A value that builds is unaffected; only the message is.
[A message names a type by what confarg reads](../../architecture/design-decisions/a-message-names-a-type-by-what-confarg-reads.md#a-message-names-a-type-by-what-confarg-reads) unwraps an alias so a message names what confarg tried, which a recursive one never finishes.

Fix direction: spell an alias met again while spelling it by its own name (`int | str | list[Json] | dict[str, Json]`), as REF-97 did before arguments were unwrapped.

Origin: a regression from the revision that spelled a generic's arguments through `_spell_type` (`_spell_argument`), unwrapping a nested alias; REF-97 named it by its own name, and the same refusal read `Cannot coerce float 1.5 to int | str | list[Json] | dict[str, Json] at 'j'`.
Found by BUG-312, whose first draft spelled the type of every dict it built.

```python
from dataclasses import dataclass

import confarg

type Json = int | str | list[Json] | dict[str, Json]


@dataclass
class T:
    j: Json = 0


try:
    confarg.build(T, {"j": 1.5})
except RecursionError:
    print("RecursionError")
# expected: TypeCoercionError: Cannot coerce float 1.5 to int | str | list[Json] | dict[str, Json] at 'j'
# actual:   RecursionError
```
