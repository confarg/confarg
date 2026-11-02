# The union tag is the class key in every role

One key names the class to build from the keys beside it: a union's variant, a struct field's subclass, a registered leaf a tag opens, and the class a Callable's or an `Any`'s spec instantiates ([callables](../callables.md#the-openers)).
That key is the union tag, `class` by default, so `union_tag="kind"` renames it in every role at once: `{kind: pkg.Mul, factor: 3}` builds the instance at a lone Callable field, at a lone `Any`, and at a union's Callable or `Any` variant, and `class` is an ordinary key there, a dict entry an `Any` holds or an unknown field a class refuses.
`classfn`, `bind`, `call` and `args` keep their spelling under any tag.

`_callable.openers(union_tag)` is the one answer to "which keys open a spec": construction (`_spec_parts`, `holds_an_opener`), the merge's replace-or-refine (`reads_as_new_value`), the walk that types a key below a node (`_naming`), the CLI loop and registration (`_parse_cli`, `cli._build`), and `dump()` all ask it, so every channel reads and writes the same key ([BUG-305](../callables.md#a-callable-beside-another-variant)).
A key the user writes beside the tag is read as it is beside `class` under the default: `{call: pkg.f, kind: pkg.Sub}` is no typed call, but the tag naming `Sub`, `call` one of its fields.

Why: the glossary already says "the `union_tag` option names another key for the role", and a custom tag exists for a file format whose discriminator is spelled otherwise, which spells its class opener the same way (maintainer-chosen).
Until BUG-305, `class` stayed the opener wherever it was not the tag, and the tag reached a Callable or an `Any` only as a union's: there, `int | Any` imported the class `{kind: collections.OrderedDict}` names and held the dict as it was, since the spec reader opened on `class` alone, and `int | Callable` refused it, saying the dict must hold `class`.
On the command line, `--x.kind pkg.J --x.parts a b` typed no key below the tag, so `parts` took one token.

Precedents: Hydra's `_target_` and jsonargparse's `class_path` cannot be renamed; pydantic's and msgspec's discriminators are named per union, and select among the union's members only, never a class a spec instantiates.

Rejected:

- **The tag stands for `class` only where a union hands it to its Callable or `Any` variant**, the ticket's first direction, a lone Callable or `Any` reading `class` alone.
  The fewest changes, but one dict, `{kind: pkg.Mul}`, built an object at `int | Any` and stayed a dict at `Any`, and `class` kept meaning the opener beside a tag spelling the same role: two rules side by side.
- **A custom tag never reaches a spec reader**: it selects struct variants alone, and only `class` opens a spec.
  A lone node and a union agreed, but a tag naming no struct variant at `int | Any` became a dict entry, the silent typo [an `Any` node reads every opener](an-any-node-reads-every-opener.md) rejects.
- **`classfn` follows the tag**, spelled `kindfn`.
  The pair stays visibly related, but the word is coined, no user would guess it, and `dump()` would write it.

Cost: under a custom tag, an `Any` reads a dict holding the tag's key, at any depth, as a spec, so `union_tag="type"` imports what a `type` entry names wherever an `Any` holds one ([limitations](../limitations.md#callables-and-serialization)).
A constructor parameter spelled like the tag cannot sit beside it, as one named `classfn` cannot; it is reached under the `args` of a `bind:` or a `call:` of the class, and `dump()` refuses a callable holding a field of that spelling, which no spec spells, and writes a struct an `Any` holds with one untyped, with a warning naming the field ([callables](../callables.md#an-openers-word-is-never-an-argument), [serialization](../types/serialization.md#an-any-node-dumps-the-spec-that-rebuilds-it)).

## A tag spelling another role is refused

Every entry point taking a `union_tag` refuses, with a `ValueError` before reading anything, a tag that would merge two roles into one key or that no channel can spell (`_defaults.check_union_tag`): `bind`, `call` and `classfn`, the other openers; `args`, which holds a computation's arguments; a key the merge or `build()` reads as its own (`_defaults.RESERVED_KEYS`); a name of the local-variables namespace, stripped before construction; the empty key; and a key holding the `.` a flag's path is split on.
`merge()`, `load()` and the adapters check it where their options are resolved (`_defaults._Options`), `build()`, `from_dict()`, `resolve()`, `dump()` and `dump_file()` on entry.
Before BUG-305 nothing was checked: `union_tag="bind"` selected a subclass by a `bind` key while a Callable read the same key as its target, and `union_tag="a.b"` was a key no flag could write.
A `ValueError`, not the `TypeError` an unknown option raises: the argument is of the right type and names a value the option refuses.

Rejected: **refusing only the other openers**, which this decision makes collide.
The reserved keys, the namespace and the unspellable keys were as broken before it, and one check names every role a key may already have.
