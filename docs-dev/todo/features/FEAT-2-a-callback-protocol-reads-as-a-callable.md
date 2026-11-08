---
filed: 2026-09-12
where:
  - src/confarg/_types.py::_is_callable
  - src/confarg/_types.py::_is_plain_class  # so _KIND_ORDER's STRUCT row does not claim it first
  - src/confarg/_callable.py::_check_callable_signature
  - src/confarg/_types.py::_expected_call_signature  # the expected signature's one home, answering __call__'s
  - src/confarg/_callable.py::_unproducible_return
effort: M  # the decision is taken; the work is the Callable predicate, the expected signature and their tests
risk: high  # a callback Protocol changes kind in every channel and front-end at once
impact: behavior
severity: minor  # annotating Callable[..., R] instead works
blocked_by: [FEAT-57]
---

# FEAT-2 — A callback Protocol reads as a Callable

A Protocol whose only member is `__call__` (PEP 544's richer spelling of a `Callable`) reads today as a plain class whose fields are `*args, **kwargs`: `f: Scorer` refuses `pkg.linear` with `expected dict, got str`, and `{bind: pkg.linear}` with `Unknown field(s) ['bind']`.

Settled in [the Protocol plan](../plans/protocol-typed-fields.md#a-callback-protocol-reads-as-a-callable): such a Protocol is a Callable whose expected signature is `__call__`'s without `self`, so every Callable spec reaches it (a dotted path, `bind:`, `call:`, a `class:` instance), each resolved value goes through the Callable's [call-shape check](../../architecture/callables.md#a-callable-is-checked-by-its-call-shape), `_unproducible_return` reads `__call__`'s return annotation, and the dump writes it as a Callable.
A Protocol with another member beside `__call__` stays struct-like.
Precedent: jsonargparse takes a function for a Protocol only when `__call__` is its single member.
See [callables](../../architecture/callables.md).

The `**kwargs` half of what this ticket used to hold is [FEAT-58](FEAT-58-a-kwargs-parameter-takes-extra-keys-typed-by-its-annotation.md).
