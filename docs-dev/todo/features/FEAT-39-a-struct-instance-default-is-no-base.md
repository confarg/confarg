---
filed: 2026-10-10
where:
  - src/confarg/_default_layer.py::_merged_form
effort: M
risk: medium
impact: none
severity: minor
needs_design: true
blocked_by: [FEAT-38]  # whether build() may run a factory decides whether it may build an instance
---

# FEAT-39 — A struct instance default is no base layer

Since FEAT-37 a field default is the layer below every source, but a default that is a struct instance — `sub: Sub = field(default_factory=Sub)`, a frozen dataclass instance, a namedtuple of instances — is not laid ([tier 1](../../architecture/design-decisions/a-field-default-is-the-base-layer.md#tier-1-defaults-read-without-running-code)).
So `${sub.a}` misses unless a source names `sub`, and then it reads `Sub`'s class default rather than the instance's.
Laying it means building the instance (running `__init__` and `__post_init__`) and serializing it back into merged-dict form; `dump()` refuses a plain class whose state does not mirror its constructor's parameters, and OmegaConf refuses a plain-class field outright.

Once laid, the instance is also the last layer a key delete meets: today `--sub.p-` over `sub = field(default_factory=lambda: Sub(p=5))` deletes nothing, so `p` stays 5 rather than falling back to `Sub`'s own default ([a delete meets the defaults last](../../architecture/design-decisions/a-field-default-is-the-base-layer.md#a-delete-meets-the-defaults-last)).

A delete a source already met is spent there and never reaches the defaults: over a file's `d: {x: 2}`, `--d.x-` removes the file's `x`, and a laid default holding `x` would fill it again.
A fixed-length position keeps its delete for the default below so that it does not ([a fixed-length delete unsets a position](../../architecture/design-decisions/a-fixed-length-delete-unsets-a-position.md#the-delete-removes-the-position-from-the-default-too), BUG-243).
Whether a laid instance default follows that rule, or lets a key a source deleted come back from the default, is part of this design.
