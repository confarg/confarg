# A stolen leaf dumps with its cast

`dump()` writes `{__cast__, __value__}` for a union **leaf** whose bare scalar another variant
would take back — the typed sibling of the pin `_serialize_untyped` already writes
([types](../types/stealing-rule.md#casting-a-stolen-leaf)). `Color | str` holding `"FOO"` dumped
`"FOO"` and rebuilt as `Color.FOO`, breaking the one round trip the library promises
([pipeline](../pipeline/api-seams.md#public-api-seams); BUG-15, closed).
The cast is emitted only where the bare form fails to read back, so every dump that round-tripped
before is unchanged.

Rejected alternatives:

- **Cast every leaf union member.** Uniform and cheap to decide, but it turns every `int | str`
  field into a two-key dict in a file a human reads and edits; the file spelling earns its
  ugliness by being the exception. `tag_policy="always"` was the obvious lever for it and stays
  a *class-tag* policy for the same reason — a leaf has no class to name.
- **Re-read file values by declared type**, so the bare scalar selects the right variant on the
  way in. Rejected once already, by
  [dump round-trips at the built object](dump-round-trips-at-the-built-object.md#dump-round-trips-at-the-built-object):
  it breaks the token model, in which a self-describing
  file is never re-interpreted ([types](../types/token-model.md#token-model)).
- **Decide by mirroring the stealing rule** rather than by calling `construct`. That is a second
  model of variant selection, and wrong for native values — which keep declaration order — on
  the day it is written ([invariants](../invariants.md#delegate-to-the-canonical-function)).

The cost is one `construct()` call per leaf union value at dump time, and two where a cast is
emitted, since the cast is vetted the same way before it is written. `dump()` is not a hot path,
and the alternative is a rule that can be wrong in silence.

A variant `__cast__` cannot name — an unregistered `Enum` beside a `str`, a collection
variant — gets a `ConfargWarning` and the bare value, rather than an error or a cast no reader accepts:
`dump()` of a working object must not start raising, and the value stays correct for every consumer
that does not feed it back into `build()`. A `Literal` over `Enum` members no longer joins them: its
bare value (the `Enum` member's value) reads back as the member, because the native branch of
`_coerce_literal_value` matches it the way the token branch already did — one `_match_literal_member`
answers for both channels (BUG-32, closed) — so no cast is needed. Widening `__cast__` to dotted
paths would close the `Enum` half ([FEAT-16](../../todo/features/FEAT-16-dotted-cast-names.md)); the
warning outlives that for a collection variant, which has no dotted name.

Precedents: YAML emitters tag a scalar (`!!str 5`) exactly when the plain form would resolve to
another type, and leave it bare otherwise. pydantic warns
(`PydanticSerializationUnexpectedValue`) instead of raising when `model_dump` meets a value its
serializer cannot represent faithfully.
