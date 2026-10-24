---
filed: 2026-10-10
where:
  - src/confarg/_default_layer.py::_merged_form
  - src/confarg/_types.py::_struct_declared_defaults
effort: M
risk: medium
impact: behavior  # an append on a list field with a non-empty default would keep the default
severity: minor
needs_design: true
---

# FEAT-38 — A `default_factory` default is no base layer

Since FEAT-37 a field default is the layer below every source, but only a value the class declares is laid ([tier 1](../../architecture/design-decisions/a-field-default-is-the-base-layer.md#tier-1-defaults-read-without-running-code)).
A `default_factory` is never called to be laid, so a list, dict or set default is no base and no expression reads it: `xs: list[int] = field(default_factory=lambda: [0])` with `--xs+ 1` builds `[1]`, where a file's `xs: [0]` under the same flag builds `[0, 1]`, and `${xs}` misses.
A plain class's mutable `__init__` default (`xs=[0]`) is left out the same way, to keep the two class kinds alike.

Laying them means calling the factory at `build()`, as OmegaConf's `structured()` does, and deciding whether construction then reuses that object or calls the factory again (`_types._dc_defaults` calls every factory on each construction today).
It also changes what `+` means on every collection field with a non-empty default, which is the decision this ticket is for.

Once laid, such a default is also the last layer a key delete meets: today `--d.x-` over `d = field(default_factory=lambda: {"x": 1})` meets no laid default and deletes nothing, so the default keeps `x` ([a delete meets the defaults last](../../architecture/design-decisions/a-field-default-is-the-base-layer.md#a-delete-meets-the-defaults-last)).

A delete a source already met is spent there and never reaches the defaults: over a file's `d: {x: 2}`, `--d.x-` removes the file's `x`, and a laid default holding `x` would fill it again.
A fixed-length position keeps its delete for the default below so that it does not ([a fixed-length delete unsets a position](../../architecture/design-decisions/a-fixed-length-delete-unsets-a-position.md#the-delete-removes-the-position-from-the-default-too), BUG-243).
Whether a laid factory default follows that rule, or lets a key a source deleted come back from the default, is part of this design.
