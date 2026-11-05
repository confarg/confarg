# Construction

## Union construction

`_construct_union` tries, in order:

1. single non-None variant (with `none`/`null` tokens for Optional);
2. the **class key** (`class`): a full dotted class path, which must be a subclass of exactly one variant that `_is_struct` accepts — registered leaves included, since a tag is an explicit request to build from fields ([design decisions](../design-decisions/an-explicit-tag-opts-a-leaf-back-in.md#an-explicit-tag-opts-a-leaf-back-in)).
   A tag that is all the data asks the named class to build from nothing, and a `TypeError` out of that call is a `TypeCoercionError` naming the class and quoting Python's own text — the tag is supplied data, so the field is not missing (BUG-213), the shape the auto-bound owner of an instance method already takes ([callables](../callables.md#auto-binding)).
   No member can take the key's spelling, `class` being a Python keyword ([the class key is `class`](../design-decisions/the-class-key-is-class.md#the-class-key-is-class)).
   It is not the tag where it can select no variant and a variant reads a dict, which holds it as data ([below](#where-no-tag-selects-a-variant-that-reads-a-dict-holds-the-key-as-data));
3. **structural** matching for struct variants: required fields ⊆ provided keys ⊆ fields, a required field that construction builds from nothing read as optional ([below](#a-missing-field-built-from-nothing)), refined by value/type compatibility, a variant that demands its tag left out ([below](#a-variant-that-demands-its-tag-takes-no-untagged-value)); more than one match is an `AmbiguousUnionError` whose message lists each variant's fields and suggests the tag; zero matches falls back to trying each variant;
4. **leaf** variants: tuples (filtered by arity), then collections, then scalars (stealing rule), then the `_UnionSeqToken` one-element-list fallback, then `Any` ([below](#an-any-variant-is-tried-last)).
   A tuple is offered to the tuple and collection variants as a list is ([a tuple reads where a list reads](#a-tuple-reads-where-a-list-reads)).
   A built instance of a struct or an unsupported-leaf variant is taken by that variant first ([a built instance is taken as it is](#a-built-instance-is-taken-as-it-is)).

### A tag no variant takes

A union none of whose variants is a struct or reads a spec — `int | str`, `int | Path` — has nothing a tag could select, whatever class it names; one with a variant that reads a dict, `list[int] | str` or `int | dict[str, str]`, reads the key as that variant's data instead ([below](#where-no-tag-selects-a-variant-that-reads-a-dict-holds-the-key-as-data)).
It refuses the tag as a leaf field does, naming the union as written and the `call:` spec that computes a value the field accepts, with its own reason: a leaf is built from one value, not from keys (`datetime is built from one value, not from keys`), and no variant of the union is built from keys (`no variant of int | str is built from keys`).
The message says the tag "picks the class to build from the keys beside it", plain wording chosen after the user docs' own, which give a class's keys "alongside the `class` key" ([tutorial 18](../../../examples/18_callables/README.md)) and build a block as "whichever class its `class` key picks" (README); the phrase itself is no established vocabulary.
It used to say the type "accepts no struct", confarg's internal word for a class built from keys, which `docs/` and the examples never use; it read worst on a class leaf, `datetime` told it accepts no struct when the tag named `datetime` itself (BUG-280).
No user-facing message says "struct": `dump()`'s refusal of an unsupported leaf says `bytes is no leaf type confarg reads`, which it used to preface with `is no struct and`.
The refusal comes before the tag is imported, as on the leaf: no class it names would be taken, so the import could only run a module's code, or report a typo or a broken module the leaf does not report ([a bare word is never imported](dotted-imports.md#a-bare-word-is-never-imported)).
`TypeCoercionError.leaf_takes_no_tag` and `TypeCoercionError.union_takes_no_tag` spell it, one factory per reason, each called where construction knows its case (`_construct_scalar`, `_construct_union_by_tag`), and `_types._spell_type` names the type, so a union reads `int | str` on every Python, though its `__name__` is `Union` since 3.14.
Until BUG-252 the union imported the tag and listed the struct variants it could be a subclass of, which were none: "Expected a subclass of one of: []".
A union with a struct variant or a spec reader still imports the tag, which decides what is built.

#### Where no tag selects, a variant that reads a dict holds the key as data

The key is the tag only where it can select a variant: a struct, a registered leaf a tag opens, or a Callable or an `Any` reading the spec (`_construct.tag_selects_a_variant`).
Where it can select none, a variant that reads a dict reads it as data, as it does alone: `int | dict[str, str]` holds `{class: confidential}` as an entry, as a lone `dict[str, str]` does, and the merge lets `--labels.class confidential` add it beside a lower file's entries rather than replace them ([the type decides](../design-decisions/the-type-decides-replace-or-refine.md#the-type-decides-whether-a-value-replaces-or-refines)).
Only a union whose variants read no dict refuses the tag, as above.
`_construct.tag_reading` is the one answer, telling a variant's data, a tag refused and a tag that selects apart; construction, the merge's `reads_as_new_value` and its walk's `_union_child`, the walk's `_naming.named_variant`, the tag pre-import and the default layer all ask it.
Only a tag that selects a variant is imported, so no channel runs the module a dict entry spells, nor one a refused tag names: the pre-import used to import both, `--labels.class pkg.mod` on `int | dict[str, str]` as `--u.class pkg.mod` on `int | str`, and the default layer the first, since each asked only whether a member owned the spelling.

The type decides what the key is, as for a lone field, not whether some variant could hold `class`: `int | dict[int, str]` and `list[int] | str` read it as data their dict or sequence variant then refuses (`Cannot coerce str 'class' to int`), and the union's refusal is theirs, not the tag's.
Asking whether a variant's key type takes the spelling, so that only `dict[str, V]` held it and `int | dict[int, str]` refused the tag, was rejected: the tag refusal says no variant "is built from keys", which is false of a dict, and the merge would coerce the tag's spelling against each key type (maintainer-chosen).

Beside a variant a tag selects, the key stays the tag, a dict variant or not: `Job | dict[str, str]` imports `confidential` and refuses it, so the dict variant there cannot hold a `class` entry.
Reading the key as data whenever the tag does not import, as jsonargparse reads a `class_path` its `Union[Job, dict]` cannot import, was rejected: a misspelled class path would silently become a dict entry.
So was a dict variant owning the key as a real field owns it, which would have left no tag selecting a class in `Job | dict[str, str]`.
Precedents: pydantic's discriminated unions and msgspec's tagged ones refuse a dict variant beside a tag when the type is defined; without a tag, both read `{class: …}` on `int | dict` as data.

Until BUG-276 the union read the key as the tag whatever its variants were, so `int | dict[str, str]` refused a value its dict variant holds, and the merge replaced a lower layer's entries with it.

### A variant that demands its tag takes no untagged value

A struct with subclasses is built only through the class a tag names ([inheritance](#inheritance)), so structural matching never offers it a value carrying no tag: `{}` under `Base | AllDefaults`, where `Base` has a subclass, builds `AllDefaults`, and a value no other variant takes gets the union's refusal, whose line for `Base` says it wants the tag ([below](#a-union-refusal-names-each-variants-reason)).
One predicate, `_types._demands_tag`, answers whether a struct requires its tag, and construction (`_construct_struct_dispatch`), flag registration (`cli._build._collect_struct_specs`), the default layer (`_struct_built_from`) and the structural match (`_construct._builds_by_fields`) all ask it; the dump's `_needs_tag` asks the structural match, so an `AllDefaults` beside `Base` is written untagged, and a `Base` is tagged, its untagged `{}` matching `AllDefaults` alone ([serialization](serialization.md#serialization)).
The match asks it at every depth it reaches, a field's value included, so `{inner: {}}` tells `Holds(inner: Base)` from `Holds(inner: AllDefaults)`.

Until BUG-295 the match read such a struct by its own fields, so a base declaring none was ambiguous with every all-defaults variant over `{}`, and the remedy the ambiguity offered, `'class': 'Base'`, names the base exactly ([class names the type it builds](../design-decisions/class-names-the-type-it-builds.md#class-names-the-type-it-builds)), which is refused; latent since PR-63, which made construction demand the tag and left the match as it was.
Precedent: jsonargparse 4.52 reads `{}` under `Union[Base, AllDefaults]` as `AllDefaults(k=0)` (run), a subclass type taking only a `class_path`.

### An ambiguity met inside a variant ends the walk

An `AmbiguousUnionError` a variant meets while building its value is the value's refusal, not the variant's: it leaves the union as itself, at its own path, and no later variant is tried.
`list[Cat | Dog] | list[dict[str, str]]` refuses `[{name: Rex}]` with `Ambiguous union at 'pets[0]'`, as a lone `Cat | Dog` field refuses the item, and `list[Cat | Dog] | int` raises the same error, which a caller can catch by type.
Until BUG-288 the walk read it as one more refusal, so the next variant took the value (`[{'name': 'Rex'}]`, as dicts), and with no later variant it survived as one line of the union's `TypeCoercionError`; latent since PR-5, whose walk caught every `ConfargError`.

The rule holds wherever candidates are tried in turn, and `_construct._first_that_builds` is the one walk: the fixed-length, collection and struct-fallback rungs (`_first_constructible`) ask it, the one-item fallback of a lone token reaches it through the collection rung, and a tag's bindings ask it too (`_construct_bound_tag`), so `Box[list[Cat | Dog]] | Box[list[dict[str, str]]]` with a tag refuses the item as well.
The scalar walk builds no struct, so it meets none.

Declaration order still decides which variant is tried first, so the ambiguity is met only by a variant the walk reaches: `list[dict[str, str]] | list[Cat | Dog]` builds the dicts, and a tagged item builds the `Cat` under either order.
The cost is that a value the earlier variant finds ambiguous cannot reach a later one that would hold it ([limitations](../limitations.md#subclasses)): declare the variant that should win first, or tag the items.

Rejected:

- **Recording the ambiguity as a refusal, naming the variant that took the value**: a value the user's type cannot tell apart would still build as a variant the user did not choose, a warning-free pick of the kind the union's own position refuses.
- **Trying every variant and refusing where any meets an ambiguity, whatever the order**: `list[dict[str, str]] | list[Cat | Dog]` would refuse dicts its first variant takes, and a walk past the first success calls constructors it then throws away, where a class whose `__init__` has side effects should be called once.

Precedents (run) do not agree: pydantic's smart mode keeps `[{'name': 'Rex'}]` under either order, its `left_to_right` mode builds `Cat` for the `Cat`-first order, jsonargparse builds `Cat` under both, and cattrs and msgspec refuse the types themselves.
confarg keeps the refusal its union position already gives: a refusal of the type would refuse `Cat | Dog` outright, which builds whatever a tag names.

### A union refusal names each variant's reason

When no variant takes a value, the refusal names the field and the union, then each variant whose refusal says more than that, on a line of its own, in the union's order (FEAT-46):

```text
Cannot coerce str 'os.dubble' to Callable | Opts at 'f':
  Callable: cannot import 'os.dubble': module 'os' has no attribute 'dubble'
```

Every rung that tries a variant and catches its refusal keeps it (`_construct._Refusals`): the struct variants tried one by one when none matches structurally, the fixed-length and collection variants, the scalar walk and the one-item fallback of a lone token; each variant is named by the last refusal it gave.
The walk used to drop each one as it tried the next variant, so a typo'd import, an Enum's members, a field a struct does not declare or the bound of a `type[X]` were one lone-field load away.

Which refusals give a line is the error's to say, read by `exceptions._variant_reason`:

- **None, where it says only that the value is no value of the variant, or not of its shape** (`TypeCoercionError.cannot_coerce`, `wrong_shape`, `wrong_length` and `keys_not_indices` mark it `_plain` with the path and the value they refused).
  `int` refusing `'x'` repeats the union's line, a `Literal` lists its members in its own spelling already, and a struct handed a string, a fixed tuple a list of another length, a list a dict whose keys name no index, or a scalar leaf a dict or a list (`_construct._variant_reasons`, a registered leaf a tag opens among them), refused a shape the user did not mean, whatever its message says: a `datetime`'s format hint, the refusal of a `class` key it cannot take, or the tag a `UUID` would be built from fields by.
  A length is shape too, though it says how many: the union's line spells each tuple's arity, and a variant the length filter skips is never tried, so a line for some would be a line for a few.
- **Its own clause, where a factory says it apart** (`_reason`): an Enum's members, a registered leaf's format hint (`cannot_coerce_because`), the fields a struct does not declare, a class outside a `type[X]` bound, a `type` path that imports nothing or no class, a Callable's class whose instances are not what it returns, its spec resolving to nothing callable or its dict holding no opener, a branch confarg reads nothing as (`no leaf type confarg reads`, which the union used to append to its one line), and a missing field, named without the flag a remedy would spell, since only the front-end that parsed argv knows its `cli_prefix`.
- **Its message as a clause otherwise**, which covers a refusal inside the value, at its own path (`list[int]: cannot coerce str 'x' to int at 'u[0]'`), and a Python exception's text, a symbol's import failure among them, whose text names no path.

A refusal a variant raises at the union's own position is therefore made by a factory, which marks it through `ConfargError._refusal`, the one place the two markers are set: its message names the position the union's line names already, and given whole, it would repeat it (`type: cannot import class 'x' at 'v': …`), as the import, Callable and registered-leaf refusals first did.
The markers are relative to the value the union was handed, so `_plain` holds it and `_variant_reason` compares it: a refusal of another value at the same position, a base a patch carries, says more.

Two refusals are no union's, deliberately.
A struct the keys select alone (structural matching) fails as itself, its field named, since the keys chose it, as the tag would have.
A dict carrying a merge base (`__base__`) that no variant takes fails as the sequence variant it patches ([below](#an-optional-field-fails-as-its-variant), BUG-200), since the union's line would print the merge's internal key.

Where no line is left, the refusal is the one line it was; with lines, the none-word remedy closes them on one of its own.

The format follows the per-variant breakdown `AmbiguousUnionError` already gives, and pydantic v2, which lists one error per union member.
Listing every variant, as pydantic does, was rejected: `int: cannot coerce str 'x' to int` is the noise that hides the one line that matters.
So was giving the most specific reason alone, as msgspec does (`Invalid enum value 'x'`): with two informative variants, which one is dropped is a guess (maintainer-chosen).

### An optional field fails as its variant

`X | None` fails exactly as an `X` field does: same exception type, same message, same path.
A `{q: "notint"}` for `Inner | None` names `inner.q`, a `{}` missing a required field is the `MissingFieldError` naming it, and a callable spec's own refusal reaches the user.
The `None` variant adds one thing, and only where it could have applied: when the value is a [token](token-model.md#token-model), the one place a none word is read, the variant's error ends with the remedy (`… To set this field to None, pass 'none' or 'null'.`).
A dict, a list or a file's string could not have meant `None` — a file writes it as its own null, and its `"none"` stays a string — so there the remedy would only mislead (BUG-159).

A union of several variants and `None` follows the same rule when no variant accepts the
value: its "Cannot coerce … to int | float | None" gains the remedy for a token and for
nothing else (BUG-162).
One predicate, `_construct._reads_none_word`, answers whether the value could have been a none word, and every union site asks it: the single-variant union to select `None` and to offer the remedy, the scalar variants to rank `None` among them, the multi-variant refusal to offer the remedy.
Whether such a value does select `None` is `_construct._selects_none`, which the CLI parser asks too, before storing a lone none word bare rather than as a one-item list ([design decisions](../design-decisions/a-lone-none-word-nulls-an-optional-sequence.md#a-lone-none-word-nulls-an-optional-sequence)).

The rule also answers a multi-variant union offered a patch the merge deferred with its list base (`{__base__: base, **patch}`, [merge/build contract](../pipeline/merge-build-contract.md#merge-build-contract)): when no variant takes it, the refusal is the first sequence variant's own — the list's "Cannot patch … with non-integer key", the fixed tuple's "dict keys must be integer indices" — naming the key the user spelled, where the generic "Cannot coerce dict {'**base**': …}" would print the merge's internal base key (BUG-200).
First is the try order's own: a fixed-arity variant before a variable-length one.
The alternative the ticket offered, keeping the generic refusal but spelling the patch without its base, was not taken: it says what the value is not, not which key failed to place.

The remedy is appended to the variant's error rather than replacing it, so a token keeps what the variant had to say: a callable shorthand's arity refusal, the element of a list a whole-value token failed on (maintainer-chosen).
Replacing it with one generic "Cannot coerce … to X" for a token, as `_construct_single_variant_union` used to for every value, was rejected for that reason.
The suffix is spelled once in `exceptions.py` (`_append_none_remedy`), for this site and for `cannot_coerce`'s `none_sentinel`. pydantic reports an `Optional[Model]` failure the same way: at the inner location, as the plain model's, the nullable wrapper adding nothing.

### An `Any` variant is tried last

`Any` beside other variants takes only what every other variant refused (BUG-117).
It is the last rung of `_construct_union_leaf`, after the fixed-arity and collection variants, the scalars in stealing rank and the `_UnionSeqToken` fallback, for a token and a native value alike: `int | Any` reads `--x 3` as `3` and `--x abc` as `"abc"`, `int | Any | None` reads `none` as `None`, and `Path | Any` reads a file's `"a"` as a `Path` whichever side of the union `Any` is written on.
A more specific variant keeps what it can take, as `str`, the widest variant text can reach, comes last in the [stealing rule](stealing-rule.md#stealing-rule).
Giving `Any` a rank in `_steal_rank` would not do it: the rank orders the scalar variants only, and `Any` must also come after the fixed-arity and collection variants.

A tagged dict goes the tag's way first: a tag naming a struct variant selects it, and one naming no variant is the spec of the variant that reads one, a Callable or else the `Any`, which builds the class it names ([callables](../callables.md#an-any-node-reads-every-opener)); a tag that does not import is refused.
A dict holding another opener (`bind`, `classfn`) is read by that variant before any struct or dict variant, unless a struct variant owns the key, and a `call` is the union's to take ([a Callable beside another variant](../callables.md#a-callable-beside-another-variant)).

`_holding._holds_anything` is the one test of the variant.
`dump()` asks it too, looking for the variant that holds an instance among the others first ([serialization](serialization.md#serialization)).
Because `Any` holds every type, `_cast.holds_the_cast` admits every cast on a union holding it, as on a bare `Any`, so the `{__cast__, __value__}` escape hatch reaches the text a `Path` variant would steal ([stealing rule](stealing-rule.md#casting-a-stolen-leaf)).

The other direction the ticket offered, refusing a union with an `Any` variant on both sides, was rejected: `Any | None` is the only way to null an `Any` field from a token, `X | Any` reads "typed when it fits, raw otherwise", and such unions also arise unwritten, from aliases composed with `Any`.

### A union without `None` takes no `None`

`construct()` takes a `None` itself only where `_types._allows_none` says the type holds one, a union counting `None` among its variants included.
Any other `None` — a file's `null`, a YAML key left empty, a `from_dict()` value — meets a union's variants as any value does, and the union refuses it as a lone variant does: `int | str` refuses `null` as `str` does, `Cannot coerce NoneType None to int | str at 'a'`.
A variant that holds `None` takes it: an `Any`, on the leaf walk's last rung ([above](#an-any-variant-is-tried-last)), and a `Literal` listing `None`.
A token never meets this: a none word selects `None` only in a union counting it ([an optional field fails as its variant](#an-optional-field-fails-as-its-variant)), and `int | str` reads it as the text `'none'`.
A field default of `None` its annotation does not hold is no value read, so it still builds, and `dump()` writes it with the warning that it will not read back ([serialization](serialization.md#a-value-its-type-does-not-hold-dumps-as-an-any-node-holds-it)).

Until BUG-298 the union returned any `None` before asking a variant, a regression of PR-11, which turned the branch `if data is None and type(None) in all_args` into `if data is None`, its comment calling it unreachable since `construct()` takes a `None` first, which holds only for a union counting `None`.

## Inheritance

A struct field whose class has subclasses requires the class key naming the concrete class; without it construction fails rather than guessing, because the set of visible subclasses depends on what has been imported ([design decisions](../design-decisions/no-implicit-subclass-inference.md#no-implicit-subclass-inference)).
The tag must be a full dotted path so the class can be imported.
No field, the struct's own or a subclass's, can take the key's spelling away, since `class` is a Python keyword ([the class key is `class`](../design-decisions/the-class-key-is-class.md#the-class-key-is-class)).

Subclass discovery (`_struct_subclasses`) walks breadth-first and yields each class exactly once.
Both halves are settled decisions: a diamond subclass is reachable by two inheritance paths and used to be offered twice in the `--class` completer (BUG-44, closed), and the breadth-first order is load-bearing there — direct subclasses are offered before their descendants, which the contract suite asserts.
The depth-first walk the code used to run was an accident of `list.pop()`, contradicting a docstring that had promised BFS from the start; the stdlib splits on the alternative (`ast.walk` is breadth-first, `pkgutil.walk_packages` is depth-first), and BFS was picked to honor the documented contract.
The other caller, `_types._subclass_field_type`, only reduces the list to a common field type, so it is indifferent to both.

## Structs, collections and defaults

- A builtin's subclass is built as the builtin and then given to the class, `cls(value)`, a `defaultdict` with the factory its value type gives (`_coerce.as_subclass`, [design decisions](../design-decisions/a-builtins-subclass-is-that-builtin.md#a-subclass-is-built-by-its-constructor)).
- Unknown keys are errors (typo detection); missing required fields are `MissingFieldError` naming the CLI flag to set, as the CLI spells it ([below](#a-missing-fields-remedy-is-spelled-as-the-cli-spells-it)).
- A missing struct field whose class needs nothing is built from `{}` ([below](#a-missing-field-built-from-nothing)) — a registered leaf never is, however defaulted its `__init__` looks, so a missing one is a `MissingFieldError` rather than whatever its constructor raises for no arguments.
- That shortcut is a **guess**, and an unregistered class can defeat it: `_construct.builds_from_nothing` reads `__init__` parameter defaults, which is not the same question as "does `tp()` work" (a class taking one of two parameters, each defaulting to `None`, refuses an empty call, as an unregistered `UUID` did with seven).
  A `TypeError` out of the shortcut therefore means the guess was wrong, not that the caller gets a stdlib traceback out of `build()`: it is caught and the field is reported missing like any other.
  Catching it is preferred to asking the question up front — there is no way to ask short of calling the constructor, and a class whose `__init__` has side effects should be called once, not twice.
  Every missing field raises the one `MissingFieldError(path, type)`, so its type never changes the message ([invariants](../invariants.md#delegate-to-the-canonical-function)).
- The root takes the same rule (BUG-184): `build()` builds a struct root from the empty merged dict when no channel supplied anything, and a `TypeError` out of that call is the missing root — `MissingFieldError((), target)`, the error a scalar root nothing supplied raises, whose remedy is the root's own ([above](#a-missing-fields-remedy-is-spelled-as-the-cli-spells-it)).
  The catch sits in `build()` rather than at `_construct_struct`'s final `tp(**kwargs)`, because a tag or an opener reaches that call with an empty dict too (`--field.class x.S` and nothing else), and there the value *was* supplied, so "missing" would be wrong — that route refuses as a coercion instead ([below](#a-class-built-from-nothing)).
  And it is gated on nothing having been supplied at all, so a constructor's own `TypeError` about data a channel did supply still escapes as its own.
- A field default is the base a patch applies over, for every type: `build()` lays it under the data before construction, as a lower file holding it would be ([design decisions](../design-decisions/a-field-default-is-the-base-layer.md#a-field-default-is-the-base-layer)).
  A base the merge carried (`__base__`) replaces it, as it replaces a lower file's list.
- An append on a fixed tuple or a namedtuple applies over the `__base__` it carries, and the list it leaves is checked against the arity; with no base it is refused naming the op, as on a dict (BUG-221).
  A list delete is refused there either way, naming `{__unset__: true}`: a delete at a position unsets it in place, under a carried base too ([design decisions](../design-decisions/a-fixed-length-delete-unsets-a-position.md#a-fixed-length-delete-unsets-a-position)).
- A fixed tuple's position neither a base nor a patch filled is a missing field, `MissingFieldError` naming `t[0]` and its flag `--t.0`, as a namedtuple's field is; an Optional position is `None`.
  `unset_position` is the one answer to what an unset position holds, a namedtuple field's class default included, which the default layer asks too.
  A list shorter than the arity is still the arity refusal: it states its length.
- A `__base__` with an index patch beside it builds as the merge would have built it, had no index escaped the base: each patch value refines what the base holds at its position through `_merge._merge_existing_value`, and fills a slot past the base's end.
  So `--t.1 5` beside `--t.0.a 9` over a file's `t: [[1, 2]]` defers the patch without turning the refinement of `t[0]` into a replacement (BUG-164).
  A fixed tuple and a namedtuple lay their positions alike.
- Lists accept a list, a tuple or an index-keyed dict, whose keys are read once as integers, so a YAML `{0: 9}` and a flag's `"0"` are one index ([a tuple reads where a list reads](#a-tuple-reads-where-a-list-reads)).
  Index-keyed lists must be gap-free unless the element type is Optional.
  Deletes and negative indices need a base list; without one they are errors that say so.
- Negative indices count from the end wherever a sequence's length is known (`_indexed_dict_to_positions`), mirroring list patches.
- Namedtuples accept a list, a dict by field name, or a dict by index — and a `__base__` list with either kind of patch beside it, laid over the positions ([design decisions](../design-decisions/namedtuple-arity-flag-argv-order.md#build-reconciles-the-positions-with-the-patch)).
  A list is keyed by field name and built as the by-name dict, so a list shorter than the arity leaves the fields it stops before to their defaults and, for one with none, to the `MissingFieldError` the dict omitting it raises.
  It used to fill such a field with `None`, which failed as a coercion of a value nobody passed, or built silently for an `X | None` field (BUG-167).
  The stdlib agrees (`P._make([1])` is a `TypeError`, "Expected 2 arguments, got 1"), and so does pydantic, which reports `y` as a `missing_argument`.

### A tuple reads where a list reads

A list-kind node (`list[int]`, `Sequence[int]`, a `list` subclass) reads a tuple as the sequence it spells and builds its own list, as a tuple node already reads a list and a set node a tuple; a union offers a tuple to its tuple and collection variants as it offers a list, and a scalar variant's refusal of one says no more than of a list (FEAT-60).
No file, variable or flag spells a tuple; a caller's `build()` data and a `call:` value do, and a function returning a tuple under a `list[int]` field was refused.
A set stays refused under a list: it has no positions, and its order varies from run to run for strings, so the dump would not be reproducible.

Rejected:

- **A tuple taken only where the annotation holds one, and kept a tuple** (pydantic): a second, type-checker-shaped reading inside construction, which reads `Sequence` as `list` everywhere else ([a builtin's subclass is that builtin](../design-decisions/a-builtins-subclass-is-that-builtin.md#a-builtins-subclass-is-that-builtin)).
- **List nodes reading a list only**: a call returning a tuple under `Sequence[int]`, which a field took as it is, would be refused once a call's value is read by construction (BUG-293).
- **Sets too** (pydantic lax, msgspec, cattrs): for the reproducibility above.

Precedent (run): `list[int]` given `(1, 2)` is `[1, 2]` in pydantic lax, msgspec and cattrs, refused in pydantic strict; `Sequence[int]` given `(1, 2)` is `[1, 2]` in msgspec, kept a tuple in pydantic and cattrs.

### A built instance is taken as it is

A node takes a value that is already what it names, as it is, in a caller's `build()` data and in a call's value alike: a file, a variable and a flag spell no such value, so the merge never meets one ([a call's value is read by construction](../design-decisions/a-calls-value-is-read-by-construction.md#construction-takes-a-built-instance-of-what-its-node-names)).

- **A struct node** (`_construct_struct_dispatch`) takes a value that is no dict when `typedload._holding._holds` holds it, before the tag or the subclass dispatch is asked: an instance of the class or of a subclass, and for a generic struct one whose members hold their bound types.
  It refuses any other naming the value's class and the struct (`TypeCoercionError.no_instance_of`), a file's `'abc'` included, or, for an instance of a generic struct, the first member in declaration order whose value does not hold (`typedload._holding.unheld_member`, `TypeCoercionError.unheld_member`).
  The instance is the field: not copied, and a non-generic class's members not read again, its constructor being its own contract.
- **An unsupported leaf** (`_coerce._unsupported_leaf_instance`) takes an instance of its class, by the same `_holds`, and refuses every other value as `Unsupported leaf type`: no text reads as one, and `dump()` still refuses to write one ([an unsupported leaf is refused both ways](serialization.md#an-unsupported-leaf-is-refused-both-ways)).
- **A union** (`_instance_variant`, the first rung of `_construct_union_leaf`) hands a value that is no dict, list or tuple to the variant the dump would write it by (`typedload._holding.first_holding_variant`), when that variant is a struct or an unsupported leaf; a leaf with a coercion takes what its coercion takes, in the leaf walk.
  A built instance takes no part in structural matching, which reads dicts: its class answers what a tag would.
- A leaf with a coercion, a namedtuple, a tuple, a set, a Callable and a `type[X]` read a built value as they did.

A Protocol class that is not `@runtime_checkable` holds no value for `_holds`, since `isinstance` raises for it (`typedload._holding._isinstance_answers`): construction refuses a value under it as it refuses any other a struct does not hold, and the dump writes one as foreign, with its warning, until the Protocol's conformance answers the question ([FEAT-57](../../todo/features/FEAT-57-protocol-typed-fields.md)).
Raising `isinstance`'s own `TypeError` was rejected: once construction asked `_holds` of every value that is no dict, a file's `5` under `P | int` raised it, where it had read as the `int`.

### A class built from nothing

Five routes ask a class to build from no key at all: a missing defaulted struct field, a struct root no channel supplied, a union's tag with nothing beside it, a struct field's subclass tag with nothing beside it (`--opt.class x.Sub` on a `Base | None` field takes this route, not the union's), and a `class:` or `classfn:` opener with no argument.
All five call `_construct.build_from_nothing`, the one reader of the refused empty call, because what the refusal means differs only by whether the user supplied the value.
Nothing supplied — the field, the root — reads as the missing value, `MissingFieldError(path, type)`.
A tag or an opener named the class, so the value was supplied: the refusal is a `TypeCoercionError` naming the class as written, quoting Python's own text, and saying the fields go beside the tag or the opener (`TypeCoercionError.refused_empty_call`).

BUG-213 put the supplied reading at the union route alone, the site its reproduction reached, which left the struct field's tag route — the common `Base | None` shape — and the two openers letting the constructor's bare `TypeError` out of `build()` (BUG-215).
Routing every route through one function is what keeps a sixth from being missed the same way.

### A missing field built from nothing

`_construct.builds_from_nothing` answers whether a missing required field is built rather than missing: a struct variant whose required fields all build from nothing in turn (`_construct._struct_needs` names those that do not), so `Deep(o: Outer)` over `Outer(inner: Inner)` over `Inner(a: int = 0)` builds from `{}`.
Construction (`_construct_struct`), the default layer (`_default_layer._struct`, so a reference reads what the field builds to), the union's structural match (`_structurally_matches`) and its ambiguity breakdown (`_ambiguous_union_msg`) all ask it, so none can read such a field differently from what construction does with it.

Two kinds never build from nothing:

- **A class reaching itself on its own path**, `Chain(next: Chain)`, whose build would never end.
  The walk carries the classes it is inside as a per-path stack rather than a global visited set, so a class reached twice side by side, `Pair(a: Inner, b: Inner)`, still builds.
- **A struct that demands its tag** ([inheritance](#inheritance)), which `{}` is refused for, so a missing field of that type is a `MissingFieldError`, the default layer lays nothing there, and the match counts it as required.
  The answer is read afresh on every call rather than cached, as `_types._demands_tag` is: a subclass can appear when a module is imported.

So the match reads `inner` in `N1(inner: Inner) | N2(inner: Inner)` as optional, and `{}` is ambiguous between them as `{inner: {}}` is, and between `N1` and `Other(x: int = 0)` too, whose message lists the field as optional because that is why `{}` matched.
A guess that fails stays the known divergence ([above](#structs-collections-and-defaults)): a class whose `__init__` refuses the empty call its defaults promise is read as optional by the match, then reported as the `MissingFieldError` construction gives.

Until BUG-304 the question was shallow and asked by two of the four: `_types._all_have_defaults`, which construction and the default layer asked, read only whether the class's own fields had defaults, not whether a required one built in turn, and nothing about its tag, and the match counted the field as required.
So `{}` matched no variant, and the fallback that tries each one built the first, where `{inner: {}}` was refused: giving less data avoided the refusal; latent since PR-5.
`Deep` was a `MissingFieldError` naming `o`, and a missing field of a struct demanding its tag was built as the base, untagged, which `{inner: {}}` refused.

Rejected:

- **The fallback building every variant and refusing where two build**: it leaves the match and construction answering two questions, and calls constructors whose objects it throws away, where a class whose `__init__` has side effects should be called once.
- **Never building a required field from nothing**, as pydantic refuses `N1 | N2` over `{}` for the missing `inner`: every configuration relying on a defaulted nested section would have to spell it.

Precedents (run): jsonargparse builds a missing section recursively too, and picks `N1` over `{}`; pydantic refuses it as missing; cattrs and msgspec refuse the union's type.

### A missing field's remedy is spelled as the CLI spells it

A `MissingFieldError` names the field by its construction path and the remedy by the flag the CLI accepts for it.
The two spell a sequence element differently: the path writes it as `[0]`, like an expression (`${items[0].size}`) and `dump()`'s errors, while the CLI writes the index as one more dotted segment.
So `items[0].size` is reported missing with the remedy `--items.0.size`, which every front-end accepts; `--items[0].size` was refused as an unknown argument (BUG-165).
`MissingFieldError.__str__` is the one site that spells the remedy, so every missing field below a list, a fixed or variable tuple, or a nested sequence gets it right.

The error holds the path as its segments ([below](#a-construction-path-is-a-sequence-of-segments)), and the flag writes each one as a dotted CLI segment, so a dict key literally spelled `x[0]` keeps its spelling: `--d.x[0].size`, the flag that addresses it.
The remedy used to be spelled by rewriting each `[N]` of the path string, which turned that key into `--d.x.0.size` (BUG-169).
The field name itself keeps the `[0]` spelling, so the message's two halves read the same path two ways rather than every construction error changing its spelling.

The flag also lives under the `cli_prefix`, which `build()` never sees: it turns a dict into an object and knows no command line.
So the error carries the field's path and type, and spells its message when it is shown rather than when it is raised.
`load()` and the adapters' `from_*` build through `_api._build_for_cli`, which sets on a `MissingFieldError` the prefix the merge resolved and re-raises it, traceback intact: under `cli_prefix="app"` the remedy is `--app.port`, a flag the CLI accepts, where `--port` was refused as outside the prefix (BUG-168).
A field inside a non-struct target's value has no flag of its own, since such a root is [set whole](../cli-parsing/cli-prefix.md#a-non-struct-root-is-set-whole).
`build()` marks the error so, and its remedy names the root cast that sets the whole value, `--app.json <json>` (`--json <json>` with no prefix), where it had offered `--0.size`, which reads as a positional (BUG-172).
The target itself, a scalar root, has the same error with an empty path: its remedy is the bare `--app`, and with no prefix, which leaves the bare flag no spelling ([CLI parsing](../cli-parsing/cli-prefix.md#cli_prefix)), the root cast `--json`.
It used to offer the literal placeholder `--<prefix>`. click spells a missing option the same way: `MissingParameter` holds the parameter and builds its hint in `format_message()`, not when it is raised.

Rejected: a `cli_prefix` keyword on the public `build()`, threaded through `construct()` down to the error.
It would let `merge()` then `build()` spell the prefixed flag when the caller repeats the prefix, but it puts a CLI presentation concern on the dict-to-object step, and every recursive `construct()` call would carry one more argument.
Also rejected: a context variable that `load()` sets around `build()`, which is hidden global state.
The cost of the chosen shape is that `build()` called directly, after `merge(cli_prefix=...)` or on a hand-built dict, still offers the unprefixed flag (maintainer-chosen).

### A construction path is a sequence of segments

Construction carries the position it builds as a tuple, one segment per step: a field or a dict key by name, a sequence element by its integer index (`("items", 0, "size")`), the way pydantic carries its `loc` and the expression engine its positions ([expressions](../expressions/values-and-references.md#a-position-is-a-sequence-of-segments)).
Text is spelled only for a message, by one function, `exceptions._spell_field_path`: each key after a dot, each index in brackets, the first key bare.
Construction, the callable specs built below it and `dump()`'s diagnostics all name a path through it, and `MissingFieldError` holds the tuple itself, since its remedy spells the same segments as a flag.
A call out to a helper that only words a message (`_coerce_leaf`, the merge's list operations, the `TypeCoercionError` factories) is handed the spelled text.

A path string threaded through construction and appended to at each step could not tell a key holding `[0]` from an index (BUG-169), and gave a field below a dict or namedtuple target a leading dot (`'.x.size'`), since only the struct step special-cased the empty root path.
The public `construct(path=...)` takes the tuple too, `()` for the target itself: a string would have to be split back into segments, which is the loss the tuple removes (maintainer-chosen).
A dict key enters the path as `str(k)`, so an integer segment is always a sequence index.

The message spelling stays lossy where a key is not a plain name: the key `a.b` reads as nesting (`d.a.b`) and the key `x[0]` as an index (`d.x[0]`).
Spelling such a key as the expression engine does (`d['x[0]']`) was rejected to keep every message's spelling unchanged (maintainer-chosen); the segments, and so the remedy's flag, are exact either way.
