# No implicit subclass inference

A base-class field is resolved through the union tag alone; confarg never picks a subclass by
looking at which keys the input supplies. Inference existed (PR #58) and was removed (PR #63)
because a subclass is only discoverable once it has been imported: the candidate set would be
whatever `__subclasses__()` happens to hold at resolution time, so the same configuration would
build different objects depending on which modules were loaded first. Making it deterministic
means requiring users to import every candidate subclass before resolving — a constraint confarg
does not want to impose. Structural matching is unaffected
([types](../types/construction.md#union-construction)): the variants of a `Union[...]` are named
in the annotation, so they are imported by construction. Any later attempt at subclass inference,
including `Annotated` hints, inherits the same import problem and must answer it first.

Precedents: pydantic requires an explicit discriminator for tagged unions and never scans
`__subclasses__()`; cattrs exposes subclass handling only as an opt-in strategy
(`include_subclasses`) applied when hooks are registered, which pins the candidate set at a
moment the user controls.
