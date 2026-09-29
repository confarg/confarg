# Leaf coercion

`_coerce_leaf` converts to bool, int, float, str, None, `Final[T]`, `Literal`, `Enum` and
registered leaf types. Policies:

- bool words: true/1/yes/on, false/0/no/off (case-insensitive); None words: none/null, and
  the empty string for a `None` target;
- `int(text, 0)`: `0x10`, `0o7`, `0b1`, `1_000` accepted (so `08` is rejected);
- a real `bool` is never accepted as an int or float;
- Enum: member name first, then `str(value)`;
- tokens only: a native value from a file must already have the right type.

**Registry**: `_LEAF_COERCIONS` maps a type to a coerce function and `_LEAF_SERIALIZERS` maps
it to the inverse; `register_leaf_type` writes both, and `Path` is simply the first entry of
each (`Path: Path`, `Path: str`), so built-in and user leaf types are one mechanism. A
registered type is treated as a leaf even if it looks like a struct, in **both** directions:
construction skips the struct branch for it (`_construct_typed`) and so does serialization
(`_serialize_by_type`). The one way back in is an explicit class tag: `_is_taggable_leaf` marks a
struct-shaped registered type, and `_construct_scalar` hands a dict carrying the tag to
`_construct_struct_dispatch` and rejects one without it
([design decisions](../design-decisions/an-explicit-tag-opts-a-leaf-back-in.md#an-explicit-tag-opts-a-leaf-back-in)). `_is_struct_variant` is the one function that answers "does this type
get taken apart into fields?" — `_is_struct` minus the registry — and both dispatchers and both
union-variant filters (`_construct_union`'s `dc_vars` and its complement in
`_construct_union_leaf`, `_serialize._needs_tag`) go through it
([invariants](../invariants.md#delegate-to-the-canonical-function)). Asking `_is_struct` directly is
the mistake: a registered leaf may have an `__init__` — `UUID` has one with a default for every
parameter — so a `Release | UUID` field otherwise looks like a union of two structs and is
neither ambiguous on the way in nor in need of a tag on the way out
([design decisions](../design-decisions/registered-leaf-is-never-a-struct-variant.md#a-registered-leaf-is-never-a-struct-variant)).
`_construct_union_leaf` then splits what is left three ways, each bucket decided by a canonical
function rather than by a type test spelled out in place: **fixed-arity sequences**
(`_fixed_seq_types(...) is not None` — `tuple[X, Y]` *and* a namedtuple), tried first and
filtered on the arity that same function reports; **variable-length collections and dicts**
(`_is_varlen_collection` or `_is_dict`, which is where `tuple[X, ...]` belongs, not with the
fixed ones); and the **scalar leaves**, whatever is left. Asking `_is_tuple` for the first
bucket is the mistake it used to make: a namedtuple is a tuple subclass, not a `tuple[...]`
generic alias, so `str | Point` landed among the scalars and refused the list
`str | tuple[int, int]` accepts — in every channel, since this is below the parsers
([design decisions](../design-decisions/namedtuple-is-a-fixed-length-sequence.md#a-namedtuple-is-a-fixed-length-sequence)).

Coerce functions may raise `ValueError`, `TypeError` or `OSError`;
`serialize` defaults to `str` and must return something a config writer accepts and `coerce`
reads back ([design decisions](../design-decisions/registered-leaf-serializer.md#registered-leaf-types-dump-through-a-registered-serializer)).

`_try_coerce` (eager, used by parsers) never raises: it coerces only unambiguous targets and
returns the token unchanged otherwise, leaving the decision to `construct`. `_coerce_leaf`
raises. Pick deliberately: overrides of locals use `_coerce_leaf` because a failure must be
an error there ([locals](../locals.md#declare-in-files-modify-anywhere)). Expression tokens are
skipped by rule ([expressions](../expressions/deferral-rule.md#deferral-rule)). The two share one predicate for
"is this leaf type coerced eagerly?" — `_is_eagerly_coercible`, the eager subset of
`_coerce_leaf`'s domain (str and `Final` excluded) — and diverge only on raise-vs-return
([invariants](../invariants.md#delegate-to-the-canonical-function)).
