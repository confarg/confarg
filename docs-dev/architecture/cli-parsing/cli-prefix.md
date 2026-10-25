# cli_prefix

`cli_prefix` requires `--<prefix>.` on every flag, so configuration arguments stay distinguishable from the host application's own — the case the adapters exist for.
All four front-ends support it ([CLI adapters](../cli-adapters/cli-prefix-boundaries.md#the-cli_prefix-boundaries)).

The adapters take it on `populate_*`, which owns flag naming, and **record** it there; the merge step recovers it, so `merge_*`/`from_*` need not repeat it.
Passing one that disagrees with what was registered raises rather than silently matching no flag — the objection that once kept the prefix out of the adapters, answered instead of avoided.

Vanilla owns the whole command line, so a flag outside the prefix is an `UnknownArgumentError`.
An adapter does not: there, a flag outside the prefix belongs to the host framework and is left alone.
That is not a divergence in the prefix but the adapter model itself — it holds with or without one.

A non-struct (scalar) target has no field name to address, so `--<prefix> VALUE` is its only CLI spelling, on the adapters too.
Without a prefix it has no CLI spelling at all, in any front-end.
The bare flag takes what a field flag of the root's type takes (BUG-177): vanilla's loop consumes it through the field's own handlers, at the empty path, which `_ParseCtx.write` lands under `__root__`, and the adapters register the spec a field of that type gets.
So `--app 1 2` sets a `list[int]` root, `--app 1 a` a `tuple[int, str]` one, `--app '{"a": 1}'` a dict one, a bare `--app` builds an empty list, and repeated occurrences join their runs; the bare `<PREFIX>` variable is read as a field variable of the root's type is (`APP_='[1, 2]'` decodes as `APP_XS='[1, 2]'` does).
Until then the flag took exactly one token whatever the root collected, a scalar's, and construction refused that string on every collection root, so the flag a missing root's remedy offers never set one.
`--<prefix>.json` reaches the same root through the [root cast](casts-and-reserved-words.md#force-casts).

A **struct** root (dataclass, plain class — a registered leaf included), or a union of structs alone, refuses the bare flag instead (BUG-91); a union of a struct and another variant takes it ([below](#a-mixed-root-is-set-whole-or-by-field)): nothing about `--<prefix> VALUE` names a field, and a value consumed for the empty path would be silently dropped — the adapters had refused it at parse time all along, so vanilla's `UnknownArgumentError` is the refusal the five front-ends share.
A registered leaf as the root keeps its flat tagged spelling (`--<prefix>.class uuid.UUID --<prefix>.hex …`), the one [a registered leaf is opted back in with](../design-decisions/an-explicit-tag-opts-a-leaf-back-in.md#an-explicit-tag-opts-a-leaf-back-in).

## The bare prefix names the root

The bare `--<prefix>` and the bare `<PREFIX>` variable both name the root, and every mistake made with them is told that it is about the root, in one text per cause that both channels share (`exceptions._bare_value_on_a_struct_root`, `exceptions._merge_suffix_on_the_root`): the CLI refuses with it, and the environment warns with it, as it warns wherever the CLI refuses.

- **A value on a struct-like root** (BUG-91, BUG-183): `--app 8080` and `APP_=8080` on a dataclass are told the bare prefix sets a root whole and this root is set field by field, and offered a field, `--app.<field>` or `APP_<FIELD>`.
  The environment used to warn about it as the failed lookup of an empty segment, `segment '' not found in Cfg`.
- **A merge suffix on any root** (BUG-178): `--app+`, `--app-`, `APP_+` and `APP_-` patch nothing, since a struct-like root is patched one field at a time and any other root is set whole.
  The remedy follows the root's kind: a field with the suffix kept (`--app.<field>+`) on a struct root, the root cast (`--app.json <json>`, `APP_JSON`) on a non-struct one, the one spelling that sets every such root in one token, and both on a [mixed root](#a-mixed-root-is-set-whole-or-by-field).
  `--app+` used to be refused as a flag outside the prefix, which is false about the token it quotes, and `APP_+` warned about as a segment `+` below the root.

One predicate tells the merge suffix on the root, `_parse_cli._merge_suffix_on_root`, asked of the key left once the prefix is stripped: `_strip_cli_prefix` strips `app+` to `+`, as the environment's key for `APP_+` already is.
It is recognized at the refusal site only, the way `_addresses_key` intercepts the mistake `--config+` as one about that flag: `_in_cli_prefix` still answers that `app+` is outside the namespace, so the pre-scans step over it and the host-mode skip leaves it to an adapter's framework, which refuses a flag it never registered, as it refuses the bare `--app` on a struct root.
A message names the root as "the root", not by its type: the target has one, and a type is named by what confarg reads ([design decisions](../design-decisions/a-message-names-a-type-by-what-confarg-reads.md#a-message-names-a-type-by-what-confarg-reads)), which says nothing of where the value sits.

## A non-struct root is set whole

`build()` reads a non-struct root from `__root__` alone, so no flag addresses a path below it (BUG-172): `--app.0.size` on a `list[Item]` root, `--app.k` on a dict root, `--app.x` on a namedtuple root and the tag `--app.class` on an `int` root are all `UnknownArgumentError`.
Vanilla had written each at the top of the merged dict, beside `__root__`, where the value was dropped without a word.
The adapters refused the element flags they never registered, and accepted the ones the walk let them register.
Such a root is spelled whole: the bare `--<prefix>` or the [root cast](casts-and-reserved-words.md#force-casts) `--<prefix>.json`, and a missing field below it names that cast as its remedy ([construction](../types/construction.md#a-missing-fields-remedy-is-spelled-as-the-cli-spells-it)).

One decision-maker settles it: `_walk_target`, which every dotted path is resolved against — vanilla's loop, the adapters' patch-flag registration, the host-mode skip, the mount check and the environment, whose variables it reaches as a flag's path ([environment parsing](../environment-parsing.md#environment-parsing), BUG-115).
For a non-struct root it is the [locals graft](../locals.md#walk-target-graft) alone, so the namespace beside the root value stays addressable (`--app.locals.n`), and nothing else does.
Four consequences follow from that one answer:

- A dict root's `--<prefix>.json` (and `--json` without a prefix, and `<PREFIX>JSON`) is the root cast, not a key named `json`: no key of that dict is a CLI member, so the [real field wins](casts-and-reserved-words.md#real-field-wins) rule has nothing to yield to.
- A config file mounted below the root (`--app.config.0`, `APP_CONFIG__0`) is refused with the error that says so.
  A root config file writes the value under `__root__` instead.
- With no prefix, an adapter's host owns every dotted flag on such a root, locals aside, since the host-mode skip asks the same walk.
- Only the bare `<PREFIX>` and `<PREFIX>JSON` set the root from the environment; any other variable under the prefix is warned about and ignored, as an unknown field of a struct root is, since the environment warns where the CLI refuses.

Writing the path under `__root__` as a patch was rejected.
It is a feature, not a fix: the four adapters would have to register element flags of a collection root, and the environment would need `APP_0__SIZE` for parity, the opposite of the direction BUG-115 took for it.
A list root without a prefix would still have no spelling, since `--0.size` reads as a positional.
Hydra wants a mapping as its primary config, and pydantic-settings and simple_parsing want a model or a dataclass at the root. tyro is the exception: it registers `--0.x` below a tuple of dataclasses.

## A mixed root is set whole or by field

A root union of a struct variant and a variant that is none, `int | A` or `A | None`, is both kinds of root at once (BUG-266): the bare `--<prefix>`, the root cast `--<prefix>.json`, the bare `<PREFIX>` variable, its `<PREFIX>JSON` cast and a root file's `__root__` set it whole, as they set a non-struct root, and its struct variants' fields stay addressable, `--app.a 3` and `APP_A=3`, as on a struct root.
A JSON object the root cast decodes still folds in as the fields it holds, below the flags beside it, a whole value among them: `--app 5 --app.json '{"a": 3}'` builds `5` in either order, as `--app.a 4 --app.json '{"a": 3}'` keeps `a=4` on a struct root; `_cast.root_cast_folds` is the one answer to where a decoded root cast goes, for the CLI and the environment.
A root with a dict variant, `dict[str, int] | A`, has no root cast: `json` is a key of that variant, as on a [dict field](../design-decisions/real-field-wins.md), so `--app.json '{"x": 1}'` writes the key `json`, and the bare `--app '{"x": 1}'` sets the dict whole.
`_types._root_kind` is the one answer to how a root is set, a `RootKind`: `STRUCT` field by field, `WHOLE` under `__root__`, or `MIXED`, either; it is asked by the CLI loop, the environment, registration (`cli._build._whole_root_spec`, whose bare flag is the whole-value flag a field of the union's type registers, `--app JSON`), the merge, `build()` and the default layer, and `RootKind.held_whole` answers whether a merged dict holds the root whole.
One value, where two booleans, has fields and is set whole, could also spell a root that is neither.
A union is mixed when a variant is no struct, `None` included: `_is_struct_like` drops `None` to ask whether a union has fields, but `None` is a value the root is set to whole, so `A | None` is mixed while `A | B` is a struct root.

The whole value and the fields meet as a whole value and a subkey meet at a field ([whole value then subkey](../design-decisions/whole-value-then-subkey.md)): within a source the last written wins, `--app 5 --app.a 3` building `A(a=3)` and `--app.a 3 --app 5` building `5`, and across layers the higher one does, a flag's `--app 5` over a file's `a: 3` building `5`.
The environment has no argv order, and applies the broader variable first ([environment parsing](../environment-parsing.md#the-broader-variable-applies-first)), so `APP_=5` beside `APP_A=3` builds `A(a=3)`.
A field's delete is a write like any other: `--app 5 --app.a-` drops the whole value and builds the struct from nothing, `A()`, as `--f 5 --f.a-` leaves a field of type `int | A` to its default.
The merge's position at such a root, `_typed_merge._MixedRootAt`, says what of a dict stands beside the keys written over it (`MergeAt.left_beside`): the fields go where `__root__` is written, `__root__` where a field is, and the locals namespace stands beside either; `_deep_merge` asks it between layers and `_set_nested` within a source, so every writer keeps the two apart; the environment's root writes, the bare variable and its cast, go through `_set_nested` too, so its sort order is not what keeps them apart.
A dict that holds both is refused by `build()` and `from_dict()` naming the fields: nothing in it says which was written last (`TypeCoercionError.whole_root_beside_fields`, maintainer-chosen).
No flag or variable leaves one, but a root file can, `__root__: 5` beside `a: 3`, as can a dict handed to `build()`; neither is ordered, so neither says which was written last either, and both are refused alike.
`None` is such a variant, so `--app none` nulls an `A | None` root, which nothing spelled before; with nothing supplied, the struct is built, as before.

The alternative, recording the case in [limitations](../limitations.md) as the registered leaf root is, was rejected: the same union as a field took either variant, so a root had a gap no field had.
Writing the struct variant's fields under `__root__` too was not taken, since a root file for `A | B` would then need `__root__` where it writes the fields at its top today.
Precedents: pydantic's `RootModel[int | A]` validates `5` and `{"a": 3}` alike; tyro makes each variant a subcommand, `int 5` or `a --a 3`.
Dumping such a root's non-struct value is [FEAT-55](../../todo/features/FEAT-55-dumping-a-configuration-whose-root-is-no-struct.md)'s, as for every root that is no struct; `dump_file(merge(...))` writes its `__root__`.
