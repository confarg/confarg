# The stealing rule and its escape hatches

## Stealing rule

When a token meets a union of leaf types, the **highest-ranked** variant that accepts it
"steals" it. The rank is fixed; the order the union happens to be declared in decides nothing
(maintainer-confirmed, and what `examples/7_stealing_rule/README.md` teaches):

```
custom (registered) leaf type > Enum > every other leaf kind > float > int > bool > None > str
```

`_coerce._steal_rank` is the one place that order is written down and `_steal_order` sorts by
it, stably — so declaration order still breaks ties *within* a rank, and nowhere else
([invariants](../invariants.md#delegate-to-the-canonical-function)). Two callers ask: the scalar-variant
loop of a union (`_construct._coerce_scalar_variants`) and the members of a `Literal`
(`_coerce._match_literal_str_token`, ranking each member by the type of its value).

The kinds the rule does not name — type references (`type`, `type[X]`), `Literal`, a `bytes`
Literal member — share the one rank below `Enum`, ahead of the numbers
([design decisions](../design-decisions/stealing-rule-for-text-in-unions.md#stealing-rule-for-text-in-unions)).

Details that are intended:

- the order applies only to tokens; native file values keep declaration order;
- `bool` ranks below `int`, so a numeric token is a number and a bool word is a bool: `1` is
  `1` and `yes` is `True` for `bool | int`. No case handles this: the rank does;
- `None` is ranked like the rest rather than taken first, so an `Enum` member or a registered
  leaf that accepts `none` outranks it. Only the none *words* select the `None` variant, never
  the empty token `_coerce_leaf` would also accept for a bare `None` target — `str | None` must
  keep `""` a string;
- scalar variants are tried through `_construct_scalar`, the canonical single-value
  constructor, **not** `_coerce_leaf`: `_coerce_leaf` cannot build `type`/`type[X]`, and calling
  it let `str` always steal a type-ref variant;
- escape hatches: `.str`/`.int`/… casts on CLI/env, `__cast__` in files.

## Cast pinning in files

`{__cast__: <type name>, __value__: <raw>}` is the file-side escape hatch. The dict must have
**exactly** these two keys, so a real struct with those fields plus others is never
hijacked. The type name is a scalar cast name or the `__name__` of a registered leaf. A
string `__value__` re-enters coercion as a token; a native value does not.

It is also the spelling a `_Pinned` **leaves** by. A `.str`/`.int`/… cast on the CLI stores a
`_Pinned` in the merged dict, and no writer can represent one, so `_serialize_untyped` emits the
file form instead — `cast_name_for_type` naming the type, `_serialize_untyped` itself unwrapping
the `_StrToken` in `__value__` so no token reaches a writer. Writing the *coerced* value, as a
coerced leaf beside it does, would be lossy: it is enough while the pin only separates scalars,
because a file is self-describing and its values are never re-interpreted, but as soon as a
non-scalar leaf variant precedes the scalar the bare form is stolen back on the way in —
`Color | str` reads `v = "red"` as `Color.RED`, so `--v.str red` would stop round-tripping at
the built object ([design decisions](../design-decisions/dump-round-trips-at-the-built-object.md#dump-round-trips-at-the-built-object)).
`_serialize_untyped` is type-blind and cannot tell the two apart, so it keeps the pin in every
case. A `__cast__` dict that came from a file is already in this form and re-dumps unchanged,
so the emission is idempotent. Only the untyped path is affected: `dump(instance)` serializes a
constructed object, which no longer holds a pin — it reaches the same spelling by the typed
route below, and both go through `_serialize._cast_dict` so the two keys are written in one
place ([invariants](../invariants.md#delegate-to-the-canonical-function)).

## Casting a stolen leaf

`dump()` knows the declared type, so — unlike the type-blind path above — it can tell whether a
bare scalar comes back as the value that produced it. `_serialize_union` asks `_reads_back` for
every **leaf** variant and, when the answer is no, writes the `{__cast__, __value__}` spelling
instead: `Color | str` holding `"FOO"` dumps `{__cast__: str, __value__: "FOO"}`, because the
bare `"FOO"` re-reads as `Color.FOO` (BUG-15, closed).

`_reads_back` answers by **running the reader** — `construct(tp, data)`, then a
same-type-and-equal comparison (`is` first, so a `float('nan')` that passes through unchanged
still counts). Re-deriving the answer, by mirroring the stealing rule or the declaration order
native values keep, would be a second model of `_construct_union` that drifts the moment the
first one changes ([invariants](../invariants.md#delegate-to-the-canonical-function)). The same function
vets the cast before it is written, so a cast that would not read back either is never emitted.

A struct variant is unaffected: it is disambiguated by the class tag (`_needs_tag`) as before,
and `tag_policy` stays a class-tag policy — `"always"` tags structs and never casts leaves
([design decisions](../design-decisions/a-stolen-leaf-dumps-with-its-cast.md#a-stolen-leaf-dumps-with-its-cast)).

When no cast can name the variant — an unregistered `Enum` losing its scalar to a `str` variant,
the case `__cast__`'s vocabulary cannot spell — the bare value is written and a `ConfargWarning`
names the path ([limitations](../limitations.md#callables-and-serialization)).
