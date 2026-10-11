# Construction

## Union construction

`_construct_union` tries, in order:

1. single non-None variant (with `none`/`null` tokens for Optional);
2. the **union tag** (`class` by default): a full dotted class path, which must be a subclass
   of exactly one variant that `_is_struct` accepts — registered leaves included, since a tag is
   an explicit request to build from fields
   ([design decisions](../design-decisions/an-explicit-tag-opts-a-leaf-back-in.md#an-explicit-tag-opts-a-leaf-back-in)).
   A tag that is all the data asks the named class to build from nothing, and a `TypeError` out
   of that call is a `TypeCoercionError` naming the class and quoting Python's own text — the
   tag is supplied data, so the field is not missing (BUG-213), the shape the auto-bound owner
   of an instance method already takes ([callables](../callables.md#auto-binding)).
   The key is the tag only when no member — no variant's own field, nor a variant's
   subclass-only field — owns its spelling; a member that does owns the key, the union falls
   through to structural matching, and the key counts as provided data there (BUG-102,
   BUG-103, [CLI parsing](../cli-parsing/casts-and-reserved-words.md#real-field-wins));
3. **structural** matching for struct variants: required fields ⊆ provided keys ⊆ fields,
   refined by value/type compatibility; more than one match is an `AmbiguousUnionError`
   whose message lists each variant's fields and suggests the tag; zero matches falls back
   to trying each variant;
4. **leaf** variants: tuples (filtered by arity), then collections, then scalars (stealing
   rule), then the `_UnionSeqToken` one-element-list fallback.

### An optional field fails as its variant

`X | None` fails exactly as an `X` field does: same exception type, same message, same path.
A `{q: "notint"}` for `Inner | None` names `inner.q`, a `{}` missing a required field is
the `MissingFieldError` naming it, and a callable spec's own refusal reaches the user. The
`None` variant adds one thing, and only where it could have applied: when the value is a
[token](token-model.md#token-model), the one place a none word is read, the variant's error
ends with the remedy (`… To set this field to None, pass 'none' or 'null'.`). A dict, a list
or a file's string could not have meant `None` — a file writes it as its own null, and its
`"none"` stays a string — so there the remedy would only mislead (BUG-159).

A union of several variants and `None` follows the same rule when no variant accepts the
value: its "Cannot coerce … to int | float | None" gains the remedy for a token and for
nothing else (BUG-162). One predicate, `_construct._reads_none_word`, answers whether the
value could have been a none word, and every union site asks it: the single-variant union to
select `None` and to offer the remedy, the scalar variants to rank `None` among them, the
multi-variant refusal to offer the remedy. Whether such a value does select `None` is
`_construct._selects_none`, which the CLI parser asks too, before storing a lone none word
bare rather than as a one-item list
([design decisions](../design-decisions/a-lone-none-word-nulls-an-optional-sequence.md#a-lone-none-word-nulls-an-optional-sequence)).

The rule also answers a multi-variant union offered a patch the merge deferred with its list
base (`{__base__: base, **patch}`, [merge/build
contract](../pipeline/merge-build-contract.md#merge-build-contract)): when no variant takes it, the
refusal is the first sequence variant's own — the list's "Cannot patch … with non-integer key",
the fixed tuple's "dict keys must be integer indices" — naming the key the user spelled, where the
generic "Cannot coerce dict {'__base__': …}" would print the merge's internal base key (BUG-200).
First is the try order's own: a fixed-arity variant before a variable-length one. The alternative
the ticket offered, keeping the generic refusal but spelling the patch without its base, was not
taken: it says what the value is not, not which key failed to place.

The remedy is appended to the variant's error rather than replacing it, so a token keeps
what the variant had to say: a callable shorthand's arity refusal, the element of a list a
whole-value token failed on (maintainer-chosen). Replacing it with one generic "Cannot
coerce … to X" for a token, as `_construct_single_variant_union` used to for every value,
was rejected for that reason. The suffix is spelled once in `exceptions.py`
(`_append_none_remedy`), for this site and for `cannot_coerce`'s `none_sentinel`. pydantic
reports an `Optional[Model]` failure the same way: at the inner location, as the plain
model's, the nullable wrapper adding nothing.

## Inheritance

A struct field whose class has subclasses requires the union tag naming the concrete class;
without it construction fails rather than guessing, because the set of visible subclasses
depends on what has been imported
([design decisions](../design-decisions/no-implicit-subclass-inference.md#no-implicit-subclass-inference)). The tag must be a full dotted
path so the class can be imported. One of the struct's own fields may take the tag's
spelling away — the field owns the key, and the base then builds from its fields, with no
tag able to dispatch to a subclass (BUG-102,
[CLI parsing](../cli-parsing/casts-and-reserved-words.md#real-field-wins)). A subclass-only
field may take it too (BUG-103): the key is then field data, and the subclass that owns the
spelling is selected structurally, the union's answer — several matches or none fail loudly,
never a silent pick or a stripped value. Where a tag could have dispatched, consuming a
shadowed tag-shaped key emits a `ConfargWarning` naming that
([design decisions](../design-decisions/a-shadowed-tag-warns-on-use.md#a-shadowed-tag-warns-on-use)).

Subclass discovery (`_dataclass_subclasses`) walks breadth-first and yields each class exactly
once. Both halves are settled decisions: a diamond subclass is reachable by two inheritance
paths and used to be offered twice in the `--<union_tag>` completer (BUG-44, closed), and the
breadth-first order is load-bearing there — direct subclasses are offered before their
descendants, which the contract suite asserts. The depth-first walk the code used to run was an
accident of `list.pop()`, contradicting a docstring that had promised BFS from the start; the
stdlib splits on the alternative (`ast.walk` is breadth-first, `pkgutil.walk_packages` is
depth-first), and BFS was picked to honor the documented contract. The other caller,
`_types._subclass_field_type`, only reduces the list to a common field type, so it is
indifferent to both.

## Structs, collections and defaults

- Unknown keys are errors (typo detection); missing required fields are `MissingFieldError`
  naming the CLI flag to set, as the CLI spells it
  ([below](#a-missing-fields-remedy-is-spelled-as-the-cli-spells-it)).
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
  not twice. Every missing field raises the one `MissingFieldError(path, type)`, so its type never changes
  the message ([invariants](../invariants.md#delegate-to-the-canonical-function)).
- The root takes the same rule (BUG-184): `build()` builds a struct root from the empty merged dict when no channel supplied anything, and a `TypeError` out of that call is the missing root — `MissingFieldError((), target)`, the error a scalar root nothing supplied raises, whose remedy is the root's own ([above](#a-missing-fields-remedy-is-spelled-as-the-cli-spells-it)). The catch sits in `build()` rather than at `_construct_struct`'s final `tp(**kwargs)`, because the union tag reaches that call with an empty dict too (`--field.class x.S` and nothing else), and there the field *was* supplied, so "missing" would be wrong — that route refuses as a coercion instead ([above](#union-construction)). And it is gated on nothing having been supplied at all, so a constructor's own `TypeError` about data a channel did supply still escapes as its own.
- An index-keyed dict for a tuple field with a default patches the default in place, unless
  the merge layer carried a base (`__base__`), which wins.
- A `__base__` with an index patch beside it builds as the merge would have built it, had no
  index escaped the base: each patch value refines what the base holds at its position through
  `_merge._merge_existing_value`, and fills a slot past the base's end. So `--t.1 5` beside
  `--t.0.a 9` over a file's `t: [[1, 2]]` defers the patch without turning the refinement of
  `t[0]` into a replacement (BUG-164). A fixed tuple and a namedtuple lay their positions alike.
- Lists accept a list or an index-keyed dict. Index-keyed lists must be gap-free unless the
  element type is Optional. Deletes and negative indices need a base list; without one they
  are errors that say so.
- Negative indices count from the end wherever a sequence's length is known
  (`_indexed_dict_to_positions`), mirroring list patches.
- Namedtuples accept a list, a dict by field name, or a dict by index — and a `__base__` list
  with either kind of patch beside it, laid over the positions
  ([design decisions](../design-decisions/namedtuple-arity-flag-argv-order.md#build-reconciles-the-positions-with-the-patch)).
  A list is keyed by field name and built as the by-name dict, so a list shorter than the
  arity leaves the fields it stops before to their defaults and, for one with none, to the
  `MissingFieldError` the dict omitting it raises. It used to fill such a field with `None`,
  which failed as a coercion of a value nobody passed, or built silently for an `X | None`
  field (BUG-167). The stdlib agrees (`P._make([1])` is a `TypeError`, "Expected 2
  arguments, got 1"), and so does pydantic, which reports `y` as a `missing_argument`.

### A missing field's remedy is spelled as the CLI spells it

A `MissingFieldError` names the field by its construction path and the remedy by the flag the
CLI accepts for it. The two spell a sequence element differently: the path writes it as
`[0]`, like an expression (`${items[0].size}`) and `dump()`'s errors, while the CLI writes
the index as one more dotted segment. So `items[0].size` is reported missing with the remedy
`--items.0.size`, which every front-end accepts; `--items[0].size` was refused as an unknown
argument (BUG-165). `MissingFieldError.__str__` is the one site that spells the remedy, so
every missing field below a list, a fixed or variable tuple, or a nested sequence gets it right.

The error holds the path as its segments
([below](#a-construction-path-is-a-sequence-of-segments)), and the flag writes each one as a
dotted CLI segment, so a dict key literally spelled `x[0]` keeps its spelling:
`--d.x[0].size`, the flag that addresses it. The remedy used to be spelled by rewriting each
`[N]` of the path string, which turned that key into `--d.x.0.size` (BUG-169). The field name
itself keeps the `[0]` spelling, so the message's two halves read the same path two ways
rather than every construction error changing its spelling.

The flag also lives under the `cli_prefix`, which `build()` never sees: it turns a dict into
an object and knows no command line. So the error carries the field's path and type, and
spells its message when it is shown rather than when it is raised. `load()` and the adapters'
`from_*` build through `_api._build_for_cli`, which sets on a `MissingFieldError` the prefix
the merge resolved and re-raises it, traceback intact: under `cli_prefix="app"` the remedy is
`--app.port`, a flag the CLI accepts, where `--port` was refused as outside the prefix
(BUG-168). A field inside a non-struct target's value has no flag of its own, since such a root
is [set whole](../cli-parsing/cli-prefix.md#a-non-struct-root-is-set-whole). `build()` marks
the error so, and its remedy names the root cast that sets the whole value, `--app.json <json>`
(`--json <json>` with no prefix), where it had offered `--0.size`, which reads as a positional
(BUG-172). The target itself, a scalar root, has the same error with an empty path: its remedy
is the bare `--app`, and with no prefix, which leaves the bare flag no spelling
([CLI parsing](../cli-parsing/cli-prefix.md#cli_prefix)), the root cast `--json`. It used to
offer the literal placeholder `--<prefix>`. click spells a missing option the same way:
`MissingParameter` holds the parameter and builds its hint in `format_message()`, not when
it is raised.

Rejected: a `cli_prefix` keyword on the public `build()`, threaded through `construct()`
down to the error. It would let `merge()` then `build()` spell the prefixed flag when the
caller repeats the prefix, but it puts a CLI presentation concern on the dict-to-object step,
and every recursive `construct()` call would carry one more argument. Also rejected: a
context variable that `load()` sets around `build()`, which is hidden global state. The cost
of the chosen shape is that `build()` called directly, after `merge(cli_prefix=...)` or on a
hand-built dict, still offers the unprefixed flag (maintainer-chosen).

### A construction path is a sequence of segments

Construction carries the position it builds as a tuple, one segment per step: a field or a
dict key by name, a sequence element by its integer index (`("items", 0, "size")`), the way
pydantic carries its `loc` and the expression engine its positions
([expressions](../expressions/values-and-references.md#a-position-is-a-sequence-of-segments)).
Text is spelled only for a message, by one function, `exceptions._spell_field_path`: each key
after a dot, each index in brackets, the first key bare. Construction, the callable specs
built below it and `dump()`'s diagnostics all name a path through it, and
`MissingFieldError` holds the tuple itself, since its remedy spells the same segments as a
flag. A call out to a helper that only words a message (`_coerce_leaf`, the merge's list
operations, the `TypeCoercionError` factories) is handed the spelled text.

A path string threaded through construction and appended to at each step could not tell a
key holding `[0]` from an index (BUG-169), and gave a field below a dict or namedtuple target
a leading dot (`'.x.size'`), since only the struct step special-cased the empty root path.
The public `construct(path=...)` takes the tuple too, `()` for the target itself: a string
would have to be split back into segments, which is the loss the tuple removes
(maintainer-chosen). A dict key enters the path as `str(k)`, so an integer segment is always
a sequence index.

The message spelling stays lossy where a key is not a plain name: the key `a.b` reads as
nesting (`d.a.b`) and the key `x[0]` as an index (`d.x[0]`). Spelling such a key as the
expression engine does (`d['x[0]']`) was rejected to keep every message's spelling unchanged
(maintainer-chosen); the segments, and so the remedy's flag, are exact either way.
