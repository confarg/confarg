# A field default is the base layer

A field default is the layer below every source.
`build()`, `resolve()` and `from_dict()` lay the target's defaults under the data they are given (`_default_layer.lay_defaults`), through the merge's own combiner (`_merge._merge_existing_value`), before expressions resolve.
So a default behaves as a lower configuration file holding the same value would:

- an expression reads a default nobody set: with `n: int = 42`, a file's `m: '${n}'` builds `m == 42`, where it was a `MissingReferenceError`;
- a patch the merge left pending applies over the default: `--v+ 3` on `v: tuple[int, ...] = (0, 1)` builds `(0, 1, 3)`, `--v.0-` builds `(1,)`, and `--pt.y 5` on a namedtuple defaulting to `Pt(1, 2)` builds `Pt(1, 5)` (BUG-109);
- a patch that does not fit the default is refused as it would be over the file: a file's `t: {__append__: [1]}` on `t: tuple[int, int] = (0, 0)` overruns it, "expected 2 elements, got 3" (BUG-221), and a stray `t: {foo: 1}` is refused as with no default.

`merge()` is untouched: it is still "save as written" ([api seams](../pipeline/api-seams.md#public-api-seams)), so `dump_file(merge(...))` never freezes a class default into a saved configuration, and a later change to the class still reaches it.

Until then only the tuple was patched over its default, by `_construct._resolve_tuple_partial`, which skipped any key it read no index in.
That skip dropped BUG-209's plain op spelling, BUG-210's cast pin and BUG-221's op marker in turn, three bugs at one spot; every other type ignored its default under a patch (a namedtuple raised `MissingFieldError` for the field the patch left out).
The function is gone: the default layer is the one place a default meets a patch, for every type.

## Tier 1: defaults read without running code

Only a value the class declares is laid: a dataclass field's `default` and a plain class's `__init__` parameter default (`_types._struct_declared_defaults`), and a namedtuple's own defaults, when the value is a leaf (`None`, `bool`, `int`, `float`, `str`, an enum member, a registered leaf type) or a tuple of them at a sequence-typed field, laid as the positional list a file writes.
Reading these calls nothing: the defaults stay the class's business, confarg reads them and never makes them.

- A `default_factory` is not called and its value not laid, so a list, dict or set default is no base: `list[int]` defaulting to `[0]` with `--xs+ 1` builds `[1]`.
  Making it one changes what an append means on every collection field, and runs user code at build time; it is its own ticket.
- A struct instance default (`sub: Sub = field(default_factory=Sub)`, a frozen instance) is not laid either: laying it means building the instance and serializing it back into merged-dict form.
- A struct field with no default whose class defaults every field is laid as its class's defaults, since construction builds it from `{}` anyway; one with a required field is not, so no `MissingFieldError` moves from `db` to `db.host`.
- A fixed-length node a source spells by key gets, at each position it leaves unset, what construction fills it with (`typedload._construct.unset_position`): a namedtuple field's class default, a fixed tuple's `None` where its type takes it.
  So `${pt.x}` reads 1 under `--pt.y 5` whatever the field default, as `pt.x` builds to, and a position a delete unset reads its class default ([a fixed-length delete unsets a position](a-fixed-length-delete-unsets-a-position.md#how-each-stage-carries-it)).
  Until BUG-243 such a node got no default laid inside it.
- Below a node, the defaults laid are those of the class construction will build there: the class a `class:` tag names (`_tags._tag_named_struct`, as construction dispatches), the one non-`None` variant of an optional, the variant a tag selects in a union.
  Where that is not certain — a tag that is an expression, a union a structural match decides, a struct with subclasses and no tag — nothing is laid below.
- A node that replaces what lies below is never combined with a default: one carrying its own `__base__`, a cast pin, or one construction reads as naming what it builds, a union tag or a typed `call:` (`typedload._construct.reads_as_new_value`).

## A delete meets the defaults last

The defaults are the last layer a key delete can meet.
One no layer met, the defaults included, deletes nothing: `lay_defaults` drops it, and with it every dict it alone filled, before laying a default where it stood (`_default_layer._kept`).
So the data reads as if no source had spelled it: `--data.x-` with no base builds the field's own default, `--sub.p-` builds `Sub`'s `p`, `--opt.p-` on `opt: Sub | None = None` leaves `opt` at `None`, `--a.k-` on an `Any` leaves `a` as it was, and `${data.x}` misses as with no flag.
A dict a source wrote empty stays.
It once reached construction as the merge's sentinel, which a typed field refused as `Cannot coerce _DeleteSentinel _DELETE_` (BUG-98), an `Any` built into its value, and an expression read.

- **Only a key delete.**
  An index delete with no base list is still refused, "requires a base list" ([limitations](../limitations.md#collections)): an index names a position, and nothing below gives it one.
  A bare delete at a list's index key is construction's to refuse as FEAT-43 decided ([a file spells an op in its value](a-file-spells-an-op-in-its-value.md#where-a-delete-has-no-meaning)).
  One at a fixed-length position unsets it, the default's included, and the layer lays there what construction fills the position with ([a fixed-length delete unsets a position](a-fixed-length-delete-unsets-a-position.md#the-delete-removes-the-position-from-the-default-too)).
- **Below a node no type settles**, an `Any`, a callable's spec, a union neither a single variant nor a tag decides, every unmet key delete is dropped the same way, untyped: there, a file's baseless `"0": {__unset__: true}` under a list one variant holds builds without FEAT-43's refusal.
- **`merge()` keeps it.**
  It is "save as written", so a dumped merge still writes the delete as `{__unset__: true}` and deletes what a lower file holds when it is layered over one (BUG-202).
  `resolve()` and `from_dict()` lay the defaults, so they drop it.
- **A default that is not laid is not met.**
  A `default_factory` or an instance default is no base yet ([FEAT-38](../../todo/features/FEAT-38-a-factory-default-is-no-base.md), [FEAT-39](../../todo/features/FEAT-39-a-struct-instance-default-is-no-base.md)), so `--d.x-` over `d = field(default_factory=lambda: {"x": 1})` keeps `x`; it starts meeting it once those defaults are laid.

Rejected: **refusing a baseless key delete**, as Hydra's `~key` and RFC 6902's `remove` refuse a missing member, which is what the ticket first expected.
A key delete over a base that lacks the key was already a no-op, so the error would have turned on whether some layer had written the dict at all (`d: {}` in a file silencing it).
Followed: RFC 7396 (JSON Merge Patch) and Helm, where `null` for an absent member deletes nothing.

## Untouched defaults are taken out again

Every tier-1 default is laid so an expression can read it, and each one no source touched is recorded and taken out once expressions are resolved (`drop_untouched`), before construction.
Construction then applies it from the class (`_construct_struct`'s `defs`), as it always did.
Building it through `construct()` instead would refuse defaults that work today — `x: int = None` — would change others — `x: float = 1` would build `1.0` where the class wrote `1` ([a float reads an int as its digits](a-float-reads-an-int-as-its-digits.md#a-float-reads-an-int-as-its-digits)) — and would replace the class's own object with a copy.
`resolve()` therefore returns the patched defaults (`{"v": [0, 1, 3]}`) and leaves out the untouched ones, so `from_dict(T, resolve(T, raw))` builds what `build(T, raw)` builds.

## A default string stays text

A default is the class's value, never an expression: `s: str = "${HOME}"` builds `"${HOME}"`, and `${s}` reads that text.
The layer lays a string escaped (`dictexpr.escape_expressions`, which inserts one `$` before every `${...}` and every `$${...}` escape), and resolution gives the string back byte for byte.
`from_dict()`, which resolves nothing, lays nothing it would have to escape: it only combines the pending patches with their defaults.

## Rejected

- **A layer in `merge()`, below the files.**
  Every seam would have seen the defaults with no API change, as OmegaConf's `structured()` puts them in the tree that Hydra composes on and jsonargparse starts parsing from.
  It was refused for what it does to `merge()`: its output would gain every defaulted field, a saved merge would freeze the class's defaults, and the merge, type-unaware by contract ([merge build contract](../pipeline/merge-build-contract.md#merge-build-contract)), would have to walk the target to read them.
  The cost of the chosen site is that `resolve()` takes the target.
- **Defaults as the class's business alone**: no type patched over its default, `_resolve_tuple_partial` deleted outright.
  Consistent, but it leaves an expression unable to read a default, which is what settled the question.
- **Laying the defaults through `_deep_merge`** at the root.
  It normalizes reserved keys on both sides, so a hand-built dict's plain `"__append__"` would become an op (BUG-209's contract), and a tagged override discards what lies below, the tagged class's defaults included.
  `_merge_existing_value` is the combiner for one field, and it normalizes nothing.
- **Materializing untouched defaults** in `resolve()`'s output, to show the effective configuration: `from_dict(resolve())` would then build them through `construct()`, which refuses some that work (above).
- **Evaluating a default's `${...}`**, as a Hydra structured config does: a default the class declares is its value, and a configuration that wants a derived value writes the expression itself.

## Precedents

OmegaConf `structured()` materializes a dataclass's defaults as nodes, calling each `default_factory` and reading back what a nested instance's `__post_init__` computed, and refuses a field typed by a plain class; interpolation reads those nodes.
Hydra composes on that tree, and jsonargparse starts from the parser's defaults, its `omegaconf+` mode resolving over the merged result. pydantic-settings ranks defaults lowest and has no patch operations or references. confarg follows them on what a reference and a patch see, and departs on where: the defaults enter at `build()`, and only what is read without running code.
