# Types, coercion and construction

## Type introspection

All type knowledge is derived at runtime from ordinary annotations (`_types.py`), because
confarg requires no base class, decorator or field marker
([10](10-design-decisions.md#no-custom-types-required)).

- `TypeAliasType` and `Annotated` are unwrapped everywhere (`_resolve_type`).
- Abstract collection types map to concrete ones: `Sequence`/`Iterable`/`Collection` → list,
  `AbstractSet`/`MutableSet` → set, `Mapping`/`MutableMapping` → dict.
- A **struct** is a dataclass or a *plain class* whose `__init__` takes parameters. Builtins,
  `Enum`, `PurePath` and tuple subclasses are never plain classes. `*args` becomes
  `list[T]`, `**kwargs` becomes `dict[str, T]`, both with empty defaults (never required).
- Since Python 3.11 `typing.Any` is a subclassable class and would pass the plain-class
  test; `_is_plain_class` and `_construct_typed` both guard it explicitly.
- `_unwrap_optional` returns Python `None` (not `NoneType`) to mean "multi-variant union";
  callers must handle that sentinel.

## Token model

- `_StrToken` (a `str` subclass) marks **untyped text from a channel that carries no types**:
  CLI, environment, CSV/TSV cells. Only tokens are coerced from text. A plain `str` came from
  a self-describing file and is never re-interpreted, so YAML's `"yes"` stays a string (no
  "Norway problem" for files).
- `_UnionSeqToken` (a `_StrToken`) marks a lone CLI token for a scalar+sequence union; it
  alone may fall back to a one-element list ([03](03-cli-parsing.md#unions-with-sequence-variants)).
- `_Pinned(tp, value)` carries an explicitly cast value through the merge dict; `construct`
  honors it before anything else, including `None` handling.
- Tokens must never leak out: error messages print them as `str` (`_src_type`), the dump path
  unwraps them in `_serialize_leaf` with `isinstance(v, _StrToken)`, and `dictexpr._map_strings`
  preserves the subclass when rewriting expressions. The test is `isinstance`, not an exact
  type test, so it covers the whole token hierarchy — `_UnionSeqToken` included, and any token
  type added later. Other `str` subclasses stay untouched all the same: `_StrToken` is private,
  so nothing a caller writes — a registered `str` leaf type included — can inherit from it, and
  the registry loop below the unwrap stays reachable for it.

## Leaf coercion

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
([10](10-design-decisions.md#an-explicit-tag-opts-a-leaf-back-in)). `_is_struct_variant` is the one function that answers "does this type
get taken apart into fields?" — `_is_struct` minus the registry — and both dispatchers and both
union-variant filters (`_construct_union`'s `dc_vars` and its complement in
`_construct_union_leaf`, `_serialize._needs_tag`) go through it
([09](09-invariants.md#delegate-to-the-canonical-function)). Asking `_is_struct` directly is
the mistake: a registered leaf may have an `__init__` — `UUID` has one with a default for every
parameter — so a `Release | UUID` field otherwise looks like a union of two structs and is
neither ambiguous on the way in nor in need of a tag on the way out
([10](10-design-decisions.md#a-registered-leaf-is-never-a-struct-variant)).
`_construct_union_leaf` then splits what is left three ways, each bucket decided by a canonical
function rather than by a type test spelled out in place: **fixed-arity sequences**
(`_fixed_seq_types(...) is not None` — `tuple[X, Y]` *and* a namedtuple), tried first and
filtered on the arity that same function reports; **variable-length collections and dicts**
(`_is_varlen_collection` or `_is_dict`, which is where `tuple[X, ...]` belongs, not with the
fixed ones); and the **scalar leaves**, whatever is left. Asking `_is_tuple` for the first
bucket is the mistake it used to make: a namedtuple is a tuple subclass, not a `tuple[...]`
generic alias, so `str | Point` landed among the scalars and refused the list
`str | tuple[int, int]` accepts — in every channel, since this is below the parsers
([BUG-21](../todo/bugs/README.md), closed;
[10](10-design-decisions.md#a-namedtuple-is-a-fixed-length-sequence)).

Coerce functions may raise `ValueError`, `TypeError` or `OSError`;
`serialize` defaults to `str` and must return something a config writer accepts and `coerce`
reads back ([10](10-design-decisions.md#registered-leaf-types-dump-through-a-registered-serializer)).

`_try_coerce` (eager, used by parsers) never raises: it coerces only unambiguous targets and
returns the token unchanged otherwise, leaving the decision to `construct`. `_coerce_leaf`
raises. Pick deliberately: overrides of locals use `_coerce_leaf` because a failure must be
an error there ([08](08-locals.md#declare-in-files-modify-anywhere)). Expression tokens are
skipped by rule ([07](07-expressions.md#deferral-rule)).

## Stealing rule

When a token meets a union of leaf types, the **highest-ranked** variant that accepts it
"steals" it. The rank is fixed; the order the union happens to be declared in decides nothing
(maintainer-confirmed, and what `examples/7_stealing_rule/README.md` teaches):

```
custom (registered) leaf type > Enum > every other leaf kind > float > int > bool > None > str
```

`_coerce._steal_rank` is the one place that order is written down and `_steal_order` sorts by
it, stably — so declaration order still breaks ties *within* a rank, and nowhere else
([09](09-invariants.md#delegate-to-the-canonical-function)). Two callers ask: the scalar-variant
loop of a union (`_construct._coerce_scalar_variants`) and the members of a `Literal`
(`_coerce._match_literal_str_token`, ranking each member by the type of its value).

The kinds the rule does not name — type references (`type`, `type[X]`), `Literal`, a `bytes`
Literal member — share the one rank below `Enum`, ahead of the numbers
([10](10-design-decisions.md#stealing-rule-for-text-in-unions)).

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
the built object ([10](10-design-decisions.md#dump-round-trips-at-the-built-object)).
`_serialize_untyped` is type-blind and cannot tell the two apart, so it keeps the pin in every
case. A `__cast__` dict that came from a file is already in this form and re-dumps unchanged,
so the emission is idempotent. Only the untyped path is affected: `dump(instance)` serializes a
constructed object, which no longer holds a pin.

## Union construction

`_construct_union` tries, in order:

1. single non-None variant (with `none`/`null` tokens for Optional);
2. the **union tag** (`class` by default): a full dotted class path, which must be a subclass
   of exactly one variant that `_is_struct` accepts — registered leaves included, since a tag is
   an explicit request to build from fields
   ([10](10-design-decisions.md#an-explicit-tag-opts-a-leaf-back-in));
3. **structural** matching for struct variants: required fields ⊆ provided keys ⊆ fields,
   refined by value/type compatibility; more than one match is an `AmbiguousUnionError`
   whose message lists each variant's fields and suggests the tag; zero matches falls back
   to trying each variant;
4. **leaf** variants: tuples (filtered by arity), then collections, then scalars (stealing
   rule), then the `_UnionSeqToken` one-element-list fallback.

## Inheritance

A struct field whose class has subclasses requires the union tag naming the concrete class;
without it construction fails rather than guessing, because the set of visible subclasses
depends on what has been imported
([10](10-design-decisions.md#no-implicit-subclass-inference)). The tag must be a full dotted
path so the class can be imported.

## Structs, collections and defaults

- Unknown keys are errors (typo detection); missing required fields are `MissingFieldError`
  naming the CLI flag to set.
- A missing struct field whose type has all-default fields is built from `{}` — a registered
  leaf never is, however defaulted its `__init__` looks, so a missing one is a
  `MissingFieldError` rather than whatever its constructor raises for no arguments.
- That shortcut is a **guess**, and an unregistered class can defeat it: `_all_have_defaults`
  reads `__init__` parameter defaults, which is not the same question as "does `tp()` work"
  (`UUID` defaults all seven of its parameters and still refuses an empty call). A `TypeError`
  out of the shortcut therefore means the guess was wrong, not that the caller gets a stdlib
  traceback out of `build()`: it is caught and the field is reported missing like any other.
  Catching it is preferred to asking the question up front — there is no way to ask short of
  calling the constructor, and a class whose `__init__` has side effects should be called once,
  not twice. Every missing field goes through `_missing_field_error`, so its type never changes
  the message ([09](09-invariants.md#delegate-to-the-canonical-function)).
- An index-keyed dict for a tuple field with a default patches the default in place, unless
  the merge layer carried a base (`"*"`), which wins.
- Lists accept a list or an index-keyed dict. Index-keyed lists must be gap-free unless the
  element type is Optional. Deletes and negative indices need a base list; without one they
  are errors that say so.
- Negative indices count from the end wherever a sequence's length is known
  (`_indexed_dict_to_positions`), mirroring list patches.
- Namedtuples accept a list, a dict by field name, or a dict by index.

## Serialization

`_serialize` is the inverse of construction for `dump()`; `_serialize_untyped` is its
counterpart for the raw dict `dump_file()` accepts, walking containers and routing every leaf
through the same `_serialize_leaf` — plus the one thing only a raw dict holds, a force-cast
`_Pinned` ([cast pinning in files](#cast-pinning-in-files)).

- `tag_policy="auto"` emits the union tag only when `_needs_tag` shows that structural
  disambiguation of the serialized data would not select exactly one variant on the way
  back in; `"always"` tags every struct union member. A subclass of the declared type is
  always tagged.
- Enums dump as values, registered leaf types through their registered serializer (`Path`
  being the first of them, hence a string), types as dotted paths, sets sorted by
  `(type name, str)` so output is deterministic. These rules read the *value*, not the
  declared type, which is why the untyped path can share them; only widening an `int` to a
  `float` needs a type, so it never happens on a raw dict
  ([01](01-pipeline-and-contracts.md#public-api-seams)). The `_StrToken` unwrap comes before
  the registry loop, so a token cannot be captured by a serializer registered for `str`.
- Plain classes must store every `__init__` parameter as a same-named attribute to be
  serializable.
- Callables dump via their stored spec ([06](06-callables.md#round-trip)).

## Dotted imports

`_import_dotted` tries the longest importable module prefix, then `getattr` for the rest,
then falls back to `builtins` so `int`, `str`, … need no prefix (this is what makes
`--value int` work for `str | type`). It assumes no builtin name collides with an
importable module name.

A failure raised *inside* an importable module is kept distinct from "this prefix is not
a module": only a `ModuleNotFoundError` whose `name` is the prefix itself or one of its
ancestors means the prefix is simply not importable (try a shorter one). Any other failure
raised while loading the module — a broken transitive dependency, a failed
`from x import y`, a circular import — comes from a module that does exist and is surfaced
as `SymbolImportError` rather than swallowed and masked as a typo'd path. The discriminator
is `ModuleNotFoundError.name`, because `ImportError` is the shared base of "module not
found" and "module found but its imports failed".
