# FEAT-14 — Dataclass fields that are not `__init__` parameters

**Where:** `src/confarg/_types.py` (`_dc_fields`, `_dc_defaults`) · **Filed:** 2026-09-13
**Effort:** L *(M for the `init=False` half alone)* · **Risk:** high · **Impact:** behavior

`_dc_fields` and `_dc_defaults` use `dataclasses.fields()` as a proxy for the `__init__` signature,
but the two sets differ in **both** directions, and construction ends in `tp(**kwargs)`
(`typedload/_construct.py`):

- `field(init=False)` is in `fields()` but not in `__init__`. Its default is collected and passed
  anyway, so a dataclass carrying `derived: int = field(init=False, default=0)` fails with a bare
  `TypeError: __init__() got an unexpected keyword argument 'derived'` — **even when no channel
  mentions `derived`**. Such a field cannot exist on a confarg target at all, and the failure
  escapes confarg's own exception hierarchy.
- `InitVar` is in `__init__` but not in `fields()`, so it cannot be set from any channel:
  `TypeCoercionError: Unknown field(s) ['seed'] for C at ''. Valid fields: ['n']` — an error that
  names the wrong problem.

Filtering `_dc_fields` and `_dc_defaults` on `f.init` closes the first half and is mechanical; the
second needs a decision on whether `InitVar` becomes a settable key, which is what makes this `L`.
Both bite a user who wrote an ordinary dataclass, which sits badly with
[10-design-decisions.md#no-custom-types-required](../../architecture/10-design-decisions.md#no-custom-types-required):
requiring users to *avoid* a stdlib field option is a field marker in reverse.
See [05-types-and-construction.md#structs-collections-and-defaults](../../architecture/05-types-and-construction.md#structs-collections-and-defaults).
