# Consuming values from argv

## Token consumption

- `--key=value` is normalized to `--key value`. The value half comes back wrapped in
  `_EqValue`, which is what makes `--key=--value` work: position already proved the token is
  a value, so no later shape test may take it back
  ([design decisions](../design-decisions/equals-escapes-a-dashed-value.md#the--form-is-the-escape-for-a-dashed-value)). The wrapper also
  makes the normalization idempotent, which the adapters need — `strip_argv_prefix` and the
  dynamic-flag scans normalize before `_parse_cli` normalizes again.
- A flag is `--` followed by a letter or `_`, so `-5` and `--3` are values. `_looks_like_flag`
  is the sole discriminator and the sole reader of `_EqValue`; every value-consumption site
  rewraps the token (`_StrToken`, `json.loads`, `Path`), so the marker never reaches a merged
  dict.
- Values run until the next flag: variable-length collections consume greedily and
  fixed-length ones consume exactly their arity. A value-taking flag always needs its value,
  struct flags included: `--db` with nothing after it is `Missing value for '--db'`
  ([design decisions](../design-decisions/a-whole-value-flag-needs-its-value.md#a-whole-value-flag-needs-its-value)). `_require_value` is the
  single guard: argv running out and the next token being another flag are one failure, and
  the fixed-arity branch asks it once per positional token, so a short token run is a missing
  value rather than a shorter tuple. Its usage line spells every position, so it never tells the
  user who passed one value to pass one value: `--pair <value> <value>` for a `tuple[X, Y]`, and
  a namedtuple's field names, `--pt <x> <y>` — the names its `--pt.x` sub-flags spell, as
  argparse spells a tuple metavar (`--pt X Y`); click and argparse name the count instead
  (`requires 2 arguments`). `_fixed_arity_usage` is the one spelling, which the adapters' spec
  carries as `FlagSpec.usage` for the front-end that refuses a bare occurrence before it parses
  (BUG-171). A key path below a dict that the walk types as nothing
  (`--d.a.b` on `dict[str, Any]`) is a value-taking flag too, so it asks the same guard rather
  than being dropped when bare (BUG-161). No declaration types that key, so it is typed as
  `Any` — the raw token it stores is what an `Any` field takes — and its append spelling
  (`--d.a.b+`) goes to the append handler, which refuses it as it refuses `--d.a+`: an `Any`
  value is no list, set or frozenset. It is no unknown field, since the plain spelling writes
  it (BUG-166).
- **Repeating** a multi-token flag extends it rather than replacing it: `--f x --f y` is a second
  spelling of `--f x y`, which is what the clicklike front-ends have no other way to write
  ([CLI adapters](../cli-adapters/list-syntax-divergence.md#list-syntax-divergence)). The occurrences are joined as *tokens*
  (`_ParseCtx.multi_tokens`, keyed by field path) and the accumulated list is shaped once, by
  `_varlen_value` for a varlen collection and by `_union_seq_value` for a union with a sequence
  variant. A fixed-arity flag takes one value and is not part of this: repeating it is last-wins.
- **Fixed-length** means `tuple[X, Y]` *or* a namedtuple: both are sequences of a known
  arity, so one function answers "how many tokens, of which types?" for both,
  `_types._fixed_seq_types` — and `_is_seq_variant` counts a namedtuple as sequence-shaped
  wherever a union variant is classified
  ([design decisions](../design-decisions/namedtuple-is-a-fixed-length-sequence.md#a-namedtuple-is-a-fixed-length-sequence)).
- A token starting with `{` or `[` is decoded as JSON when the field type accepts an object
  or a list. `_accepts_object_value` owns the object half, because the adapters must register
  and decode the same bare flags ([04](../cli-adapters/whole-value-flags.md#whole-value-flags)). The `{`-prefix
  guard runs *before* the arity path, so a namedtuple takes a whole object without ever
  competing with its own positional form.
- The `[` half is a **whole-value** spelling, so `_lone_json_array` grants it only to a flag
  carrying exactly one token: `--tags '["a","b"]'` decodes, and `--tags '["a","b"]' z` or a second
  occurrence makes every token an ordinary item. On a multi-token flag the question is therefore
  asked of the *accumulated* tokens
  ([CLI adapters](../cli-adapters/list-syntax-divergence.md#list-syntax-divergence)).
- Leaves are coerced eagerly with `_try_coerce` so the merged dict has the same types
  whichever channel supplied them (and so CLI numbers work inside expressions).
- Bool fields take an explicit value: `--verbose true` ([design decisions](../design-decisions/explicit-boolean-values.md#explicit-boolean-values)).
- A whole value already stored at a field is **opened, not overwritten**, when a later
  `--<field>.<sub>` has to descend through it. `--fn pkg.func` is the shorthand for
  `--fn.bind pkg.func`, so `--fn pkg.func --fn.sep -` refines the target the shorthand
  named; `_open_callable_shorthand` is the one place that decides it, called by this loop and
  by the env loop, so `FN=pkg.func` plus `FN__SEP=-` reads the same. A segment naming an
  *opener* is a second spelling of the target rather than a refinement, so it still replaces
  the shorthand outright — the rule that already makes an opener beat the blob beside it. A
  field with no shorthand has nothing to open and the deeper key replaces its scalar
  ([pipeline](../pipeline/deep-merge.md#scalar-intermediates)).
- A namedtuple's **positional list is the `__base__`** a later sub-flag patches beside,
  as a *varlen* collection's is: the generic `_set_nested` promotion turns `--pt 1 2
  --pt.y 9` into `{__base__: [1, 2], 'y': 9}`, and `build()` lays the patch over the positions
  by field name, the same shape the merge defers a file's list under a name patch to.
  Write order decides the shape: a later arity flag still replaces the whole field
  ([design decisions](../design-decisions/namedtuple-arity-flag-argv-order.md#a-namedtuples-arity-flag-and-its-sub-flags-merge-in-argv-order)).

## Unions with sequence variants

A union such as `str | list[str]` consumes tokens greedily and defers list/tuple/scalar
choice to `construct`. Two refinements:

- a **single** token is stored as a bare scalar when the union has a scalar variant (so
  `--input foo` stays `'foo'`), wrapped in `_UnionSeqToken` so that if no scalar variant
  accepts it, `construct` can still build a one-element list (`--input hello` for
  `bool | list[str]` → `['hello']`). Env and file scalars get no such fallback: they express
  lists explicitly, so they stay strict;
- a **single** none word is stored bare too, as the environment stores it, when the union
  counts `None`. An optional sequence (`list[int] | None`) is dispatched as such a union, so
  `--xs none` nulls it, whatever the element type. Whether the token is one is
  construction's `_construct._selects_none`, asked rather than repeated
  ([design decisions](../design-decisions/a-lone-none-word-nulls-an-optional-sequence.md#a-lone-none-word-nulls-an-optional-sequence));
- **no** token builds `[]` only if the union has a variable-length variant. For a
  fixed-tuple-only union an empty list can build nothing, so this is rejected at parse time —
  one of the few provable-at-parse-time errors.

## Callable paths

`--f.bind`, `--f.class`, `--f.call`, a nested target's `--f.bind.<key>` or `--f.call.<key>`,
the target's `--f.<p>`, a typed call's `--n.call` and its opened siblings, and their escaped
`_bind`/… forms are parsed
leniently as string leaves; whether a spec is well-formed is decided in `construct`
([callables](../callables.md)).
