# Serialization

`_serialize` is the inverse of construction for `dump()`; `_serialize_untyped` is its counterpart for the raw dict `dump_file()` accepts, walking containers and routing every leaf through the same `_serialize_leaf` — plus what only a raw dict holds: a force-cast `_Pinned` ([cast pinning in files](stealing-rule.md#cast-pinning-in-files)), a pending list op, written by its reserved key, and a delete, written as a file's node delete, `{__unset__: true}` for a key delete and `__unset__: true` beside the keys of a node whose base is deleted ([a file spells an op in its value](../design-decisions/a-file-spells-an-op-in-its-value.md#the-node-delete)).
Until BUG-202 a delete reached the writer, which raised its own error.

- `tag_policy="auto"` emits the class key only when `_needs_tag` shows that structural disambiguation of the serialized data would not select exactly the instance's variant on the way back in; `"always"` tags every struct union member.
  A variant that demands its tag matches no untagged value, so its instance is tagged; until BUG-302 `_needs_tag` asked only that one variant match, so a `Base` beside an all-defaults `AllDefaults` was written `{}`, which reads back silently as `AllDefaults` ([construction](construction.md#a-variant-that-demands-its-tag-takes-no-untagged-value)).
  A subclass of the declared type is always tagged, with its own class: `_written_struct` answers which struct an instance is written as, through `_tagged_struct`, and the struct's own tag and a union's both name that class, so a union whose variants need the tag does not name its variant over the subclass, which would read back as the variant exactly ([class names the type it builds](../design-decisions/class-names-the-type-it-builds.md#class-names-the-type-it-builds)) and refuse the subclass's fields (BUG-301, closed).
  A struct field whose type demands its tag tags an instance of its own class too, which construction builds only through the tag; until BUG-302 it was written `{}`, which the reload refused.
  One function writes the tag, `_write_tag`, for a struct field and a union alike.
- Which union variant an instance belongs to is `_variant_holds`, asked once per variant in declaration order, `Any` last: it holds every instance, so it is asked after every other variant, as construction offers it a value only after every other variant refused it ([construction](construction.md#an-any-variant-is-tried-last)).
  It dispatches on the same `_type_kind` as `_serialize_by_type` ([shape dispatch](introspection.md#shape-dispatch)), so the variant it picks is the one that then serializes the value, and each shape answers with the concrete class construction builds for it — `list` for `Sequence[X]`, `dict` for `Mapping[K, V]` — before a second pass widens it to what a type checker accepts ([below](#a-value-its-type-does-not-hold-dumps-as-an-any-node-holds-it)), and among the variants those two passes name, the first holding the value whole is taken ([below](#a-collection-variant-is-picked-by-what-it-holds)).
  A bare `isinstance` cannot ask the question at all: a parameterized generic and a `Literal` both refuse to be its second argument, so every union holding one — `list[str] | str`, `Literal["fast", "slow"] | str` — used to raise a `TypeError` out of `dump()` while loading fine (BUG-31, closed).
  A `Literal` answers by membership on the member's own type, so `True` is not a value of `Literal[1]`; its members are plain values, and `_serialize_leaf` already writes them as such, reading the value rather than the declared type.
- A **leaf** union member is written as `{__cast__, __value__}` when the bare scalar would be read back as another variant, under either policy ([casting a stolen leaf](stealing-rule.md#casting-a-stolen-leaf)).
- Enums dump as values, registered leaf types through their registered serializer (`Path` being the first of them, written as `as_posix()`, so a relative path dumped on Windows reads back on any OS; an absolute one still names its drive, `C:/Users/x`, which no POSIX system resolves), types as dotted paths when the path imports back ([dotted imports](dotted-imports.md#a-dotted-path-is-written-only-when-it-imports-back)), sets sorted by `(type name, str)` so output is deterministic.
  These rules read the *value*, not the declared type, which is why the untyped path can share them; only widening an `int` to a `float` needs a type, so it never happens on a raw dict ([pipeline](../pipeline/api-seams.md#public-api-seams)).
  An instance of a builtin's subclass is written as the builtin, whatever the field's type, since PyYAML's writer refuses a subclass, and it reads back as the subclass where the field is one ([design decisions](../design-decisions/a-builtins-subclass-is-that-builtin.md#a-subclass-is-built-by-its-constructor)).
  The `_StrToken` unwrap comes before the registry lookup, so a token cannot be captured by a serializer registered for `str`.
  A registered leaf is written by the serializer of its most specific registered type (`_coerce._registered_leaf_of`), so a `datetime` by `datetime.isoformat`, not `date`'s ([design decisions](../design-decisions/the-date-and-time-types-are-built-in-leaves.md#an-instance-is-its-most-specific-registered-type)).
- A registered leaf whose type `native_types` names is written as the object it is, for a writer that holds it: `dump_file()` passes its format's set, a `date` and a `datetime` for YAML and TOML, none for JSON.
  `_DumpOptions` carries the set and the tag policy down every serializer, and `_serialize_untyped` takes the set too ([design decisions](../design-decisions/the-date-and-time-types-are-built-in-leaves.md#a-writer-may-hold-a-date-natively)).
- A dataclass is written as the fields it stores, an `init=False` one included and an `InitVar` never; a plain class as its constructor's parameters, each read from the same-named attribute, slot or property the instance holds, never from a plain class attribute ([the object dump is forensic](../design-decisions/the-object-dump-writes-state.md#the-object-dump-is-forensic)).
- `_serialize` writes the state of the built object: resolved values, and never the `call:` that produced one ([design decision](../design-decisions/the-object-dump-writes-state.md#the-object-dump-writes-state)).
  Callables dump as what they are ([callables](../callables.md#round-trip)), and leave through `_serialize_untyped`, since a partial's keywords carry no declared type.
  A callable instance and a bound method's owner are serialized as structs, their fields typed ([callables](../callables.md#an-object-dumps-the-state-it-holds)).

## An unsupported leaf is refused both ways

A value typed by a leaf construction does not build — no struct, no type reference, and none of the leaves `_coerce._is_coercible_leaf` names, as `complex` is until registered — is refused by `dump()` with a `ConfargError` naming the path and `register_leaf_type`, the type construction refuses as `Unsupported leaf type` (`_serialize._refuse_an_unsupported_leaf`).
One predicate answers both directions, so a value `dump()` writes is one construction can read back.
Construction takes an instance of such a type from a caller's data or a call's value, the one reading it has, so `{call: threading.Lock}` builds a lock as a default factory does; no text reads as one, and `dump()` refuses it still ([construction](construction.md#a-built-instance-is-taken-as-it-is)).
A dict's key type is asked the same, by `_coerce._is_coercible_leaf` alone since construction coerces a key as a leaf: a `dict[tuple[int, int], V]` or a `dict[int | None, V]` holding a key is refused, as construction refuses its key (`Unsupported leaf type`), where `dump()` used to write a dict that did not load back.
A `Literal` holding a member PEP 586 forbids is refused by both with the same error, and a value that is a `bytes` member of a `Literal` is refused as a `bytes` field's is ([design decisions](../design-decisions/a-literal-member-is-what-pep-586-allows.md#a-literal-member-is-what-pep-586-allows)).
`dump()` used to pass such a value through, untouched and unwarned, and the format writer then failed with its own error (`Object of type date is not JSON serializable`) or wrote a value the reload refused.
`date` reached that path only once a class whose signature does not read stopped being a struct ([which signature is read](../design-decisions/a-structs-members-are-its-constructors-parameters.md#which-signature-is-read)); before, it was a struct with `object.__init__`'s `args` and `kwargs`, which `dump()` refused as not held.
It is a built-in leaf since ([the date and time types](../design-decisions/the-date-and-time-types-are-built-in-leaves.md#the-date-and-time-types-are-built-in-leaves)).

An `Any` node still writes what it holds untyped, with a warning, since an `Any` node holds every type ([below](#an-any-node-dumps-the-spec-that-rebuilds-it)).

## An `Any` node dumps the spec that rebuilds it

An `Any` node reads every opener ([callables](../callables.md#an-any-node-reads-every-opener)), so `_serialize._serialize_any` writes what one holds by its runtime type, as the spec that rebuilds it: a dict and a list walked, each item an `Any` node in turn; a struct as `{class: <its path>, <fields>}`, its fields serialized as their types say; a callable as a Callable field writes it ([callables](../callables.md#round-trip)), with a bare path opened into `{bind: <path>}`, since an `Any` node reads a bare string as text; a leaf through `_serialize_leaf`.
`_held_object_form` is the one place that picks the form of a value that is no container.

A form is kept only if an `Any` node reads it back as the value it came from, which `_reads_back` decides by running the reader.
An object that does not compare equal to the one rebuilt — a plain class with no `__eq__`, a bound method, a partial — is the same value when the rebuilt one dumps back as the same form: it holds the same state ([an object dumps the state it holds](../callables.md#an-object-dumps-the-state-it-holds)).
Any other value is written untyped (`_serialize_untyped`), with a `ConfargWarning` naming its path and the reason: a `Path` that reads back as text, an `Enum` that reads back as its value, a `datetime`, an object no spec spells, such as a closure or a class that keeps an argument under another name.
A value of a leaf construction does not build, a `complex`, a `bytes`, an `object()` or a lock, is refused by `_held_object_form` with the refusal a field of its type gets (`_refuse_an_unsupported_leaf`, [above](#an-unsupported-leaf-is-refused-both-ways)), so it warns too.
Until BUG-268 it was handed back untouched and kept, unwarned: an `Any` node passes an object through, so the reader rebuilt it from itself.
A dict holding an opener key reads back as the spec it spells, and a tuple or a set as a list, so they warn too.
A struct with a field spelled `classfn`, an object opener, is refused by `_held_object_form` as a callable instance is (`_callable.refuse_a_field_spelling_an_object_opener`), so the warning names the field: the field would read back as a second opener; until BUG-305 the read-back check caught it, with a warning naming no field.
What a struct's fields warn is said only when the struct's spec is kept, so a plain class no spec rebuilds, such as one holding every alternative its constructor takes, warns once, not once per attribute.

In a union, the `Any` variant's form is what a bare `Any` reads back; the union must read it back the same way, or it is written with its own type's cast, as a stolen leaf is ([stealing rule](stealing-rule.md#casting-a-stolen-leaf)).
An object only `Any` holds beside a struct variant is written with its `class:` tag, which names no variant and so is the `Any` variant's spec.

Before FEAT-42 an `Any` node wrote what it held untouched, and only Python code could put an object in one: `dump_file()` then failed with the writer's own error, even after a plain `load()` of a field whose default is an object.
Writing every object untyped with a warning was rejected: the object still reaches the writer ([design decision](../design-decisions/an-any-node-reads-every-opener.md)).
It still reaches `dump_file()`, which refuses it with a `ConfargError` naming its path before anything is written ([a written file holds what its reader reads back](../design-decisions/a-written-file-holds-what-its-reader-reads-back.md#a-written-file-holds-what-its-reader-reads-back)); until BUG-251 the writer raised its own error, into a file it had already truncated.

## A value its type does not hold dumps as an `Any` node holds it

A value its declared type does not hold — a `Bar` in a field typed `Empty`, a `3` in a struct field, `'abc'` in an `int` field, a `None` in a field that lists no `None`, a three-item tuple in a `tuple[int, int]`, the class `int` in a `type[Base]` — is written as an `Any` node writes it, by its runtime type ([above](#an-any-node-dumps-the-spec-that-rebuilds-it)), with a `ConfargWarning` naming the path, the value's class and the declared type (`_serialize._serialize_foreign`, BUG-267); a value that is itself a class is named as one, "its class int", not by its metaclass.
The object dump is forensic, so it records what the object holds rather than refusing it ([the object dump is forensic](../design-decisions/the-object-dump-writes-state.md#the-object-dump-is-forensic)), and the warning says that the dump will not read back.
A value no spec spells is written untyped.

Whether the type holds the value is `typedload._holding._holds`, the predicate construction asks of a built instance too ([construction](construction.md#a-built-instance-is-taken-as-it-is)), asked before anything else of the value, and answered by the predicate that already picks a union's variant (`_variant_holds`), widened to what a type checker accepts for the annotation: an abstract collection holds any instance of its abstract class (a tuple in a `Sequence[int]`, a `frozenset` in an `AbstractSet[int]`, a `MappingProxyType` in a `Mapping[str, int]`), a str or bytes apart for a sequence, and a `float` holds an int, PEP 484's numeric tower.
A `type[X]` holds a class its bound admits, by the predicate construction reads it with ([leaf coercion](leaf-coercion.md#a-type-reference-takes-a-subclass-of-its-bound)).
A union holds what one of its variants holds, an exact holder preferred over a widened one, so `float | int` still writes `1` as the int it is.
A type construction does not build at all is still refused first, whatever the value ([above](#an-unsupported-leaf-is-refused-both-ways)).

A plain class's `*args` member is typed as the tuple Python hands the constructor, `tuple[T, ...]`, when the dump reads what the instance holds, where it is a `list[T]` as a member every channel sets (`_types._struct_state_fields`): `self.items = items` keeps that tuple.

Before, each shape answered differently, and none warned: a struct field read its declared fields off whatever it held, so a field-less one wrote `{}` for any value and a `tuple[int, int]` holding three items wrote two; a union handed the value back untouched, a live object that only `dump_file()` refused; a leaf was written as it was.
Refusing at `dump()` was rejected for the forensic reason above; a field-less struct's `{}` is what a descriptor-typed dataclass field dumped as, read as its descriptor class.

## A key that does not read back is written with a warning

A key reads back from its text, as a token, as its key type reads every key ([which keys are one key](../pipeline/deep-merge.md#which-keys-are-one-key)).
So most keys round-trip, `1` and `'a'` of a `dict[int | str, V]`, `None` of a `dict[int | None, V]` (written `null`), but the text `'1'`, which only code builds, reads back as the int.
No `__cast__` spells a key, so `dump()` writes it and warns (`_serialize._warn_an_unread_key`), as it writes a leaf no cast can pin with a warning: the dump is forensic ([the object dump is forensic](../design-decisions/the-object-dump-writes-state.md#the-object-dump-is-forensic)).
`Key '1' at 'm' will not read back as str: int reads its text as 1.` says what comes back, and `Key 'x' at 'm' will not read back as str: int refuses its text.` that nothing does; one sentence serves every key type.

A key reads back when its key type holds it (`_holding._holds`) and reads its text as an equal value (maintainer-chosen).
Both halves are needed: `1` of a `dict[bool, V]` reads as `True`, which equals it, though `bool` does not hold it, and `True` of a `dict[int, V]` is held, though no text reads as it.
So a `str` subclass, an `IntEnum` member of a `dict[int, V]` and an int of a `dict[float, V]` are silent, as the same values are in a field.
Pydantic warns of the same keys and spares the same ones; cattrs and msgspec write them silently.

A key with no key type is asked the same, on a `dict[Any, V]`, a bare `dict` and a dict an `Any` node holds: every file writes a key as its text, so `{1: 'a'}` loads as `{'1': 'a'}` and `d[1]` is gone (maintainer-chosen).
Sparing the keys JSON spells, because the merge treats `1` and `"1"` as one key, was rejected: that is what the merge meets, not what the program reads back.
A dict `_serialize_foreign` writes has already warned as a whole, so its keys are not asked, and a raw `dump_file(merge(...))` dict has no type to ask.

Until BUG-314 only a union key type was asked, and by `type(read) is type(key)`, so a `str` subclass of a `dict[int | str, V]` warned though nothing was lost.

Refusing a key that does not read back, as two keys written alike are refused, was weighed and not taken: the dict holds the state the object has, and the merged dict that produced it keeps its text (maintainer-chosen).

A union holding a variant no key is read as, `int | tuple[int, int]`, is refused both ways, as such a key type alone is: construction refuses the key type (`_construct.read_key`) and `dump()` the dict.
Until BUG-261 every union key type was: each key went through the leaf coercion, which takes no union.

## Two keys written as one are refused

Two keys of one dict that are written alike, `Path('a')` and `'a'` of a `dict[Path, V]`, or `Color.RED` and `'red'`, are refused by `dump()`, naming both (`_serialize._written_dict`, BUG-314, maintainer-chosen).
The written dict cannot hold both, so the dump could only record one of them, and before this it kept the last with no sign of it.
A dict's own two keys that stay apart in Python, `1` and `'1'`, are kept by `dump()`, and refused by the writer of a file that spells them alike ([a key is written as the text it is met by](../design-decisions/a-written-file-holds-what-its-reader-reads-back.md#a-key-is-written-as-the-text-it-is-met-by)).
A warning that keeps the last was rejected: it would still lose state a forensic dump exists to record.
A dict `_serialize_foreign` writes falls back to the untyped form on this refusal as on any other, its keys kept as they stand.

## A collection variant is picked by what it holds

A collection's class does not tell `list[int]` from `list[str]`, so among the variants holding a value by its class, `first_holding_variant` takes the first holding it whole (`_holding._holds_whole`), and otherwise the first by its class, whose items then warn where they are.
So `list[int] | list[str]` writes `['a']` by its `list[str]` where it used to warn of `f[0]`, though the dump read back equal (BUG-307).
The answer covers every container kind at every depth: items, a dict's keys and values, a tuple's positions, a generic struct's members (maintainer-chosen).
Every variant holding the value by its class competes, a widened one and `Any` included, in the order they are asked, so `tuple[int, ...] | Sequence[str]` writes `('a',)` by the `Sequence` and `list[int] | Any` writes `['a']` by the `Any`.
An int counts as held by a `float` item, as a type checker reads it, so `list[float] | list[int]` writes `[1]` as `[1.0]`: preferring the exact item would need a second predicate and gains nothing, since `[1]` reads back as `[1.0]` either way, the list's first variant taking it (maintainer-chosen).

`_holds` stays by the class: a plain `list[int]` holding `['a']` still warns of `f[0]` rather than of the whole list, and construction of a built instance is unchanged ([a built instance is taken as it is](construction.md#a-built-instance-is-taken-as-it-is)).
The walk runs only where two variants hold the value, so `type Json = int | str | list[Json] | dict[str, Json]` costs nothing.
It treats a value it is already inside, or one past `MAX_DEPTH`, as held, so the dump's own refusal is what such a value meets, and it does not walk a one-shot iterator, whose items the dump still has to write.

Precedents: pydantic's union serializer tries each variant strictly over the whole value before warning, and writes `['a']` silently; msgspec refuses such a union at definition (`Type unions may not contain more than one array-like`).

## A widened value reads back as its variant reads it

A value a union variant holds only widened, an int in a `float`, a tuple in a `Sequence`, a `frozenset` in an `AbstractSet`, reads back as that variant reads the dump, as a float or a list.
`_serialize_union` therefore expects what a field of that variant reads (`_serialize._variant_reading`), as it does of an `Any` variant, and warns only if the union reads something else.
Until BUG-307 it demanded the value's own class, so `float | str` holding `1` warned that another variant took the float, though none had, while `float | None` was silent, returning before the question.
