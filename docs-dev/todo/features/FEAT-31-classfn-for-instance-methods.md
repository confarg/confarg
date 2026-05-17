---
filed: 2026-10-06
where:
  - src/confarg/_callable.py
effort: L
risk: medium
impact: config
severity: major
---
# FEAT-31 — `classfn:` names an instance method and takes the owner's constructor arguments

`{classfn: C.m, <init>}` builds `C(**init)` and returns its bound method `m`. Siblings of
`classfn` are constructor arguments. Under `call:` or `bind:`, siblings of the directive are
arguments of the method, so the two namespaces never meet.

`classmethod` and `staticmethod` targets need no owner. A plain path works (`call: C.cm`,
`bind: C.sm`), and `classfn:` is not needed for them. The bare-path case for an instance method
(auto-instantiation versus error) is open in FEAT-27 and decided here, with the default kept.

Replaces the removed `fn: C.m` with siblings, which built the owner the same way. FEAT-30
removed it ahead of this ticket, so until `classfn:` lands an owner that needs arguments has no
spelling but a `call:` of a factory. What that left to restore:

- The strict `xfail` tests marked `FEAT-31` in `tests/test_callables.py` and
  `tests/cli/test_backend_contract.py` (the escaped `_classfn` residual, owner arguments from a
  file and from the CLI, an unknown sibling under `bind: {classfn: …}`). They are written in the
  `classfn` spelling this ticket describes; drop the marker as each passes.
- The failed auto-instantiation message (`_callable._maybe_bind_method`) lists the owner's
  constructor and points to `call:`; it should point to `classfn:` with a ready-to-paste spec,
  as the removed `fn:` example did.
- `examples/18_callables` and `examples/19_bindings` lost their "method of an object that needs
  initialization parameters" sections (`--greet_fn.fn greetings.Greetings_printer.print
  --greet_fn.greetings Hi`, and `greet_fn_method_init_bound.yaml` with `greetings: Hi` beside
  `adjective: beautiful`). Restore them in the `classfn` spelling.
