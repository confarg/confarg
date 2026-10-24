# A call spec yields to data the annotation can hold

A `call:` key dispatches on any typed field, not only on a Callable: `n: {call: pkg.f, args: {x: 4}}` fills an `int`, and a dataclass field takes its function's value.
The key stops being a spec where the annotation could hold it as data: a `dict` type and a struct with a member named `call` keep the value as written.
`Any` was on this list until FEAT-42, which made an `Any` node read every opener ([an `Any` node reads every opener](an-any-node-reads-every-opener.md)).
The decision is taken per construction, so the same key means a call on one field and data on another.

Why: a `call:` spec on a field that takes a plain value is the function-returns-the-value form the redesign of the openers needs for every type ([callables](../callables.md#spec-grammar)), and it is additive, because the key was an error on those fields before.
Precedent: Hydra marks any config node to be instantiated with `_target_`, whatever its type.

Rejected:

- **Dispatch only on Callable fields** (the old rule).
  Keeps every typed field free of the key, but `call:` cannot produce an `int` or a dataclass, so the redesign would need a second spelling for the same thing.
- **Dispatch everywhere, with no yield.**
  A dataclass with a field named `call` would lose it, and a `dict[str, str]` holding a `call` key would be read as a spec.
  Both are real data that already load today.

Cost: a struct member named `call` and a dict-typed field can never be a call spec.
They keep the data they hold, and a user who wants a call on such a field has to use a field name other than `call`.
`class:` is not affected: it is the union tag, which already selects a struct ([union tag](union-tag-defaults-to-class.md)).
