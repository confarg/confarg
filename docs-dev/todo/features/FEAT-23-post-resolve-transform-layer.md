# FEAT-23 — A post-resolve transform layer

**Where:** new `src/confarg/dicttransform/`, plus `src/confarg/_api.py`,
`src/confarg/dictexpr/_expressions.py`, `src/confarg/_defaults.py`, `src/confarg/exceptions.py` ·
**Filed:** 2026-09-27
**Effort:** XL · **Risk:** high · **Impact:** config

Every channel can only patch what it contributes — set a value, extend a list, remove a key. Nothing
rewrites the merged result itself. The case that motivates it is **read-modify-write**: reclassify a
value from its own current value plus a sibling field. A `car` longer than 10 becomes a `truck`; a
`warship` becomes a `destroyer` over 120, a `frigate` over 60, a `corvette` otherwise.

An expression cannot say that, for two independent reasons: a field referencing itself is a
`CircularReferenceError`, and `_deep_merge` replaces the very value an overlay expression would have
to read, so the prior value is gone before resolution runs. Read-modify-write therefore joins
addressing many nodes, changing a key, and conditional absence as the things `${...}` structurally
cannot express — which is the test that bounds this feature. A single-path conditional such as
`type: ${"truck" if length > 10 else "car"}` is *not* in scope: it works today, at the field it
governs, still overridable from the command line.

The design was settled with the maintainer on 2026-09-26. The contract, the rejected alternatives
and the phased plan are in
[../../plans/feat-23-transform-layer.md](../../plans/feat-23-transform-layer.md). In short: a stage
between resolution and construction; rules under a reserved `__transforms__` key — in the document,
in a rules-only file layered above it, or passed as `transforms=`; ops `set`, `move` and `remove`
over a `[*]` selector with a `when:` guard; one sequential pass; rules consumed by the stage that
applies them.

**Absorbs FEAT-11.** Its version chain and `confarg migrate` become a later phase, which needs a
*per-source, pre-merge* stage of its own — a post-resolve stage cannot emit a file that keeps its
`${...}`. Its lighter alias-only half moved to
[FEAT-6](FEAT-6-annotated-field-metadata.md), which needs no version key.

Related: [FEAT-3](FEAT-3-reserved-sentinel-key-registry.md) gains a reserved key;
[FEAT-4](FEAT-4-ordered-patch-op-stream.md) may share the op record;
[FEAT-8](FEAT-8-value-provenance.md) and [FEAT-10](FEAT-10-confarg-explain-command.md) become
load-bearing rather than optional, because a rule is the last word over an explicitly supplied value
and so must be traceable; [FEAT-19](FEAT-19-app-declared-defaults.md) is the composition half of the
same story. See
[pipeline/stages.md#the-pipeline](../../architecture/pipeline/stages.md#the-pipeline)
and [expressions/reference-anchoring.md#reference-anchoring](../../architecture/expressions/reference-anchoring.md#reference-anchoring).
