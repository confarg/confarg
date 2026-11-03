# One class key in every role

One key names the class to build from the keys beside it: a union's variant, a struct field's subclass, a registered leaf the key opens, and the class a Callable's or an `Any`'s spec instantiates ([callables](../callables.md#the-openers)).
That key is `class` ([the class key is `class`](the-class-key-is-class.md#the-class-key-is-class)): `{class: pkg.Mul, factor: 3}` builds the instance at a lone Callable field, at a lone `Any`, and at a union's Callable or `Any` variant, as it selects a variant or a subclass at a typed field.

`_callable.OPENERS` is the one answer to "which keys open a spec": construction (`_spec_parts`, `holds_an_opener`), the merge's replace-or-refine (`reads_as_new_value`), the walk that types a key below a node (`_naming`), the CLI loop and registration (`_parse_cli`, `cli._build`), and `dump()` all ask it, so every channel reads and writes the same key ([BUG-305](../callables.md#a-callable-beside-another-variant)).
A key the user writes beside the class key is read as it is everywhere: `{call: pkg.f, class: pkg.Sub}` is no typed call, but the class key naming `Sub`, `call` one of its fields.

Why: before BUG-305, a custom spelling of the key, configurable then, renamed the selector of a typed field but not the opener, so `class` stayed the opener wherever it was not the tag, and the tag reached a Callable or an `Any` only as a union's.
There, `int | Any` imported the class `{kind: collections.OrderedDict}` names and held the dict as it was, since the spec reader opened on `class` alone, and `int | Callable` refused it, saying the dict must hold `class`.
On the command line, `--x.kind pkg.J --x.parts a b` typed no key below the tag, so `parts` took one token.

Precedents: Hydra's `_target_` and jsonargparse's `class_path` are one key for every role they play.

Rejected:

- **The tag stands for `class` only where a union hands it to its Callable or `Any` variant**, the ticket's first direction, a lone Callable or `Any` reading `class` alone.
  The fewest changes, but one dict, `{kind: pkg.Mul}`, built an object at `int | Any` and stayed a dict at `Any`, and `class` kept meaning the opener beside a tag spelling the same role: two rules side by side.
- **A custom tag never reaches a spec reader**: it selects struct variants alone, and only `class` opens a spec.
  A lone node and a union agreed, but a tag naming no struct variant at `int | Any` became a dict entry, the silent typo [an `Any` node reads every opener](an-any-node-reads-every-opener.md) rejects.

Cost: a constructor parameter spelled `classfn` cannot sit beside the class key; it is reached under the `args` of a `bind:` or a `call:` of the class, and `dump()` refuses a callable holding a field of that spelling, which no spec spells, and writes a struct an `Any` holds with one untyped, with a warning naming the field ([callables](../callables.md#an-openers-word-is-never-an-argument), [serialization](../types/serialization.md#an-any-node-dumps-the-spec-that-rebuilds-it)).
