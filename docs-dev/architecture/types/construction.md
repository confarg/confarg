# Construction

## Union construction

`_construct_union` tries, in order:

1. single non-None variant (with `none`/`null` tokens for Optional);
2. the **union tag** (`class` by default): a full dotted class path, which must be a subclass
   of exactly one variant that `_is_struct` accepts — registered leaves included, since a tag is
   an explicit request to build from fields
   ([design decisions](../design-decisions/an-explicit-tag-opts-a-leaf-back-in.md#an-explicit-tag-opts-a-leaf-back-in)).
   The key is the tag only when no struct variant owns its spelling as a field; a field that
   does owns the key, the union falls through to structural matching, and the key counts as
   provided data there (BUG-102,
   [CLI parsing](../cli-parsing/casts-and-reserved-words.md#real-field-wins));
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
([design decisions](../design-decisions/no-implicit-subclass-inference.md#no-implicit-subclass-inference)). The tag must be a full dotted
path so the class can be imported. One of the struct's own fields may take the tag's
spelling away — the field owns the key, and the base then builds from its fields, with no
tag able to dispatch to a subclass (BUG-102,
[CLI parsing](../cli-parsing/casts-and-reserved-words.md#real-field-wins)).

Subclass discovery (`_dataclass_subclasses`) walks breadth-first and yields each class exactly
once. Both halves are settled decisions: a diamond subclass is reachable by two inheritance
paths and used to be offered twice in the `--<union_tag>` completer (BUG-44, closed), and the
breadth-first order is load-bearing there — direct subclasses are offered before their
descendants, which the contract suite asserts. The depth-first walk the code used to run was an
accident of `list.pop()`, contradicting a docstring that had promised BFS from the start; the
stdlib splits on the alternative (`ast.walk` is breadth-first, `pkgutil.walk_packages` is
depth-first), and BFS was picked to honor the documented contract. The other caller,
`_parse_cli._subclass_field_type`, only reduces the list to a common field type, so it is
indifferent to both.

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
  the message ([invariants](../invariants.md#delegate-to-the-canonical-function)).
- An index-keyed dict for a tuple field with a default patches the default in place, unless
  the merge layer carried a base (`"*"`), which wins.
- Lists accept a list or an index-keyed dict. Index-keyed lists must be gap-free unless the
  element type is Optional. Deletes and negative indices need a base list; without one they
  are errors that say so.
- Negative indices count from the end wherever a sequence's length is known
  (`_indexed_dict_to_positions`), mirroring list patches.
- Namedtuples accept a list, a dict by field name, or a dict by index.
