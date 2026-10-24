# The stealing rule and its escape hatches

## Stealing rule

When a value meets a union of leaf types, the **highest-ranked** variant that accepts it "steals" it, a token and a file's value alike ([a union ranks every value](../design-decisions/a-union-ranks-every-value.md#a-union-ranks-every-value)).
The rank is fixed; the order the union happens to be declared in decides nothing (maintainer-confirmed, and what `examples/7_stealing_rule/README.md` teaches):

```text
custom (registered) leaf type > Enum > every other leaf kind > Callable > float > int > bool > None > str
```

`_coerce._steal_rank` is the one place that order is written down and `_steal_order` sorts by it, stably — so declaration order still breaks ties *within* a rank, and nowhere else ([invariants](../invariants.md#delegate-to-the-canonical-function)).
Two callers ask: the scalar-variant walk of a union (`_construct._ranked_scalar_variants`, walked by `_first_scalar_variant_taking`) and the members of a `Literal` (`_coerce._coerce_literal_value` and `_match_literal_str_token`, ranking each member by the type of its value).
The union walk is also what an expression reads a union's leaf through (`_construct.read_union_leaf`), so `${v}` reads the variant construction builds ([values and references](../expressions/values-and-references.md#a-typed-leaf-reads-as-its-object)).

A Callable ranks on its own below them, since it takes anything callable, classes included ([a Callable beside another variant reads its spec](../design-decisions/a-callable-beside-another-variant-reads-its-spec.md#a-string-meets-the-callable-in-rank-just-below-type-references-and-literal)).
The kinds the rule does not name — type references (`type`, `type[X]`), `Literal`, a `bytes` Literal member — share the one rank below `Enum`, ahead of the numbers ([design decisions](../design-decisions/stealing-rule-for-text-in-unions.md#stealing-rule-for-text-in-unions)).

Details that are intended:

- the order applies to every value, but only a token is *converted*: a file's `"5"` meets `int | str` as text, which `int` refuses, so it is the string.
  A file's string is *recognized* by a variant that names it — a type reference, an `Enum` member, a `Literal` member, a registered leaf — exactly as the same text on the CLI is;
- `bool` ranks below `int`, so a numeric token is a number and a bool word is a bool: `1` is `1` and `yes` is `True` for `bool | int`.
  No case handles this: the rank does;
- `None` is ranked like the rest rather than taken first, so an `Enum` member or a registered leaf that accepts `none` outranks it.
  Only a token's none *words* select the `None` variant, never the empty token `_coerce_leaf` would also accept for a bare `None` target — `str | None` must keep `""` a string;
- scalar variants are tried through `_construct_scalar`, the canonical single-value constructor, **not** `_coerce_leaf`: `_coerce_leaf` cannot build `type`/`type[X]`, and calling it let `str` always steal a type-ref variant;
- escape hatches: `.str`/`.int`/… casts on CLI/env, `__cast__` in files.

## Cast pinning in files

`{__cast__: <type name>, __value__: <raw>}` is the file-side escape hatch.
The dict must have **exactly** these two keys, so a real struct with those fields plus others is never hijacked.
The type name is a scalar cast name or the `__name__` of a registered leaf, and it must name one of the types the field's annotation holds — the CLI's `.str`/`.int` casts ask the same admission, `_cast.holds_the_cast`, so both spellings of the escape hatch read alike and neither ever places a value the field's type does not accept (BUG-210, [design decisions](../design-decisions/a-cast-names-a-type-the-field-holds.md#a-cast-names-a-type-the-field-holds)).
A string `__value__` re-enters coercion as a token; a native value does not.
`_cast` owns both directions of that vocabulary — `type_for_cast_name` reads a name, `cast_name_for_type` writes one — so the reader and the writer cannot drift apart.
The reader needs the leaf registry, which lives in `typedload._coerce`, and imports it inside the function: `typedload`'s package init reaches `_cast` through `_construct`, so the import at module level would be a cycle.

It is also the spelling a `_Pinned` **leaves** by.
A `.str`/`.int`/… cast on the CLI stores a `_Pinned` in the merged dict, and no writer can represent one, so `_serialize_untyped` emits the file form instead — `cast_name_for_type` naming the type, `_serialize_untyped` itself unwrapping the `_StrToken` in `__value__` so no token reaches a writer.
Writing the *coerced* value, as a coerced leaf beside it does, would be lossy: it is enough while the pin only separates scalars, because a file is self-describing and its values are never re-interpreted, but as soon as a non-scalar leaf variant precedes the scalar the bare form is stolen back on the way in — `Color | str` reads `v = "red"` as `Color.RED`, so `--v.str red` would stop round-tripping at the built object ([design decisions](../design-decisions/dump-round-trips-at-the-built-object.md#dump-round-trips-at-the-built-object)).
`_serialize_untyped` is type-blind and cannot tell the two apart, so it keeps the pin in every case.
A `__cast__` dict that came from a file is already in this form and re-dumps unchanged, so the emission is idempotent.
Only the untyped path is affected: `dump(instance)` serializes a constructed object, which no longer holds a pin — it reaches the same spelling by the typed route below, and both go through `_serialize._cast_dict` so the two keys are written in one place ([invariants](../invariants.md#delegate-to-the-canonical-function)).

## Casting a stolen leaf

`dump()` knows the declared type, so — unlike the type-blind path above — it can tell whether a bare scalar comes back as the value that produced it.
`_serialize_union` asks `_reads_back` for every **leaf** variant and, when the answer is no, writes the `{__cast__, __value__}` spelling instead: `Color | str` holding `"FOO"` dumps `{__cast__: str, __value__: "FOO"}`, because the bare `"FOO"` re-reads as `Color.FOO` (BUG-15, closed).

`_reads_back` answers by **running the reader** — `construct(tp, data)`, then a same-type-and-equal comparison (`is` first, so a `float('nan')` that passes through unchanged still counts).
Re-deriving the answer, by mirroring the stealing rule, would be a second model of `_construct_union` that drifts the moment the first one changes ([invariants](../invariants.md#delegate-to-the-canonical-function)).
The same function vets the cast before it is written, so a cast that would not read back either is never emitted.

A union with one variant beside `None` is not read back at all: only a token selects `None`, and a dump holds no token, so nothing can take the dump from its variant.
Running the reader there would only rebuild the value, and compare it by an equality that a partial, a bound method or a callable instance does not have: an `Optional[Callable]` warned on every such value, and built it again inside `dump()`, which otherwise builds nothing ([callables](../callables.md#a-path-is-written-only-when-it-reads-back)).

An `Any` variant writes what a bare `Any` field writes ([serialization](serialization.md#an-any-node-dumps-the-spec-that-rebuilds-it)), so what the union must read back is what a bare `Any` reads that dump back as, and its cast names the dump's own type: `Path | Any` holding `"a"` dumps `{__cast__: str, __value__: "a"}`, since the bare `"a"` reads back as a `Path`.
A value the union reads back as a bare `Any` does is written bare ([construction](construction.md#an-any-variant-is-tried-last)).

A struct variant is unaffected: it is disambiguated by the class tag (`_needs_tag`) as before, and `tag_policy` stays a class-tag policy — `"always"` tags structs and never casts leaves ([design decisions](../design-decisions/a-stolen-leaf-dumps-with-its-cast.md#a-stolen-leaf-dumps-with-its-cast)).

When no cast can name the variant — an unregistered `Enum` losing its scalar to another `Enum` of its rank that shares the value, the case `__cast__`'s vocabulary cannot spell — the bare value is written and a `ConfargWarning` names the path ([limitations](../limitations.md#callables-and-serialization)).
