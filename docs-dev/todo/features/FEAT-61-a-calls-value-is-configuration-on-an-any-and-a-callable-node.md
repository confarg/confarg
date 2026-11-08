---
filed: 2026-10-27
where:
  - src/confarg/_callable.py::resolve_held_spec  # the call branch, under an Any
  - src/confarg/_callable.py::_resolve_call_spec  # under a Callable
effort: M  # two call sites onto BUG-297's helper, and one recorded sentence amended
risk: high  # an Any's call value holding an opener key changes meaning in every channel, silently
impact: config  # a call under an Any whose value holds an opener key builds what it spells instead of keeping the dict
severity: minor  # returning the built object instead of its spec works
blocked_by: [BUG-293]  # the typed path reads a call's value through construction first
---

# FEAT-61 — A call's value is configuration on an `Any` and a Callable node

A typed field reads a dict in a `call:` value as configuration written in its place (a tag, a nested opener, a pin), but an `Any` field keeps the value as it is, and a Callable field refuses any value that is not already callable: `a: {call: f}` keeps `{'call': 'pkg.nine'}` as a dict, and `f: {call: g}` refuses `'pkg.inc'` with `returned 'str', which is not callable`.

Settled in [the plan](../plans/a-calls-value-is-read-by-construction.md#a-calls-value-is-configuration-written-in-its-place-on-every-node): `resolve_held_spec`'s `call` branch and `_resolve_call_spec` hand their value to construction through the helper BUG-297 introduced, `_callable._call_value`, so an `Any` reads every opener in it (a bare dotted string staying text) and a Callable reads a path or a spec, signature-checked.
It amends "`call:` takes its target's value as it is" in [an `Any` node reads every opener](../../architecture/design-decisions/an-any-node-reads-every-opener.md) to "as configuration written in its place".
