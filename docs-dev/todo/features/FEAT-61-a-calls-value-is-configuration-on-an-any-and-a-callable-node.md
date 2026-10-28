---
filed: 2026-10-27
where:
  - src/confarg/_callable.py::_resolve_call_spec  # under a Callable
  - src/confarg/_callable.py::resolve_held_spec  # its call branch, which no route reaches (inferred)
effort: S  # one call site onto _call_value, and the Callable's spec reading
risk: medium  # a call returning a string under a Callable starts importing it
impact: behavior  # a call whose value is a path or a spec fills a Callable field, where it was refused
severity: minor  # returning the function itself instead of its path or spec works
---

# FEAT-61 — A call's value is configuration on an `Any` and a Callable node

A typed field and an `Any` read a dict in a `call:` value as configuration written in its place (a tag, a nested opener, a pin), but a Callable field refuses any value that is not already callable: `f: {call: g}` refuses `'pkg.inc'` with `returned 'str', which is not callable`, and `{'bind': 'pkg.inc'}` with `returned 'dict'`.

Settled in [the plan](../plans/a-calls-value-is-read-by-construction.md#a-calls-value-is-configuration-written-in-its-place-on-every-node): `_resolve_call_spec` hands its value to construction through `_callable._call_value`, so a Callable reads a path or a spec, signature-checked, as it reads one a file writes.
The `Any` half landed with BUG-293, whose deletion of `_accepts` sent an `Any`'s call value through construction ([a call's value is read by construction](../../architecture/design-decisions/a-calls-value-is-read-by-construction.md#a-calls-value-is-configuration-written-in-its-place)).
`resolve_held_spec`'s `call` branch still takes its value as it is, but no route reaches it *(inferred: `_is_typed_call` takes every `call` an `Any` holds but one beside a `class`, which `_spec_parts` reads as the `class`)*; it goes, or goes through the helper, with this change.
