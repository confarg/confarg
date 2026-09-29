# Command-line parsing (vanilla)

`_parse_cli.py` is the vanilla argv parser used by `confarg.merge()`. The adapters reuse
parts of it (the `--config` scan, the patch-only mode, the type walk); see
[04-cli-adapters.md](04-cli-adapters.md).

## Type-guided parsing

Argv is not parsed as generic `key=value` pairs: each dotted path is resolved against the
target type (`_resolve_field_type`) to decide whether a segment names a field, indexes a
sequence, keys a dict, enters a callable spec, or is a cast. That is what lets
`--db.hosts.0.port 5432` produce the right nested structure and what lets values be coerced
eagerly. Env parsing walks the same type tree ([02](02-files-and-env.md#environment-parsing)).

An unknown flag is an error (`UnknownArgumentError`); an unresolvable path under a dict is
accepted as a dict key.

The one path not resolved *while* it is parsed is the config flag's subpath: the flag is
intercepted before field lookup
([10](10-design-decisions.md#the-mount-keyword-is-spelled-per-channel)), so the check runs
once the interception is over (`_check_mount_subpath`, one walk shared with the environment
channel and the adapters' rescan). A subpath that names no node — a misspelled field, or a
descent through a scalar — is an error at parse time, not a silent mount at an invented key
that surfaces much later as an unknown-field error from `build()` (BUG-50, closed). What the
node *holds* is still not the scan's question: a path is accepted at any depth it resolves to,
because whether the fragment fits is the mount's call.

## Token consumption

- `--key=value` is normalized to `--key value`. The value half comes back wrapped in
  `_EqValue`, which is what makes `--key=--value` work: position already proved the token is
  a value, so no later shape test may take it back
  ([10](10-design-decisions.md#the--form-is-the-escape-for-a-dashed-value)). The wrapper also
  makes the normalization idempotent, which the adapters need — `strip_argv_prefix` and the
  dynamic-flag scans normalize before `_parse_cli` normalizes again.
- A flag is `--` followed by a letter or `_`, so `-5` and `--3` are values. `_looks_like_flag`
  is the sole discriminator and the sole reader of `_EqValue`; every value-consumption site
  rewraps the token (`_StrToken`, `json.loads`, `Path`), so the marker never reaches a merged
  dict.
- Values run until the next flag: variable-length collections consume greedily and
  fixed-length ones consume exactly their arity. A value-taking flag always needs its value,
  struct flags included: `--db` with nothing after it is `Missing value for '--db'`
  ([10](10-design-decisions.md#a-whole-value-flag-needs-its-value)). `_require_value` is the
  single guard: argv running out and the next token being another flag are one failure, and
  the fixed-arity branch asks it once per positional token, so a short token run is a missing
  value rather than a shorter tuple.
- **Repeating** a multi-token flag extends it rather than replacing it: `--f x --f y` is a second
  spelling of `--f x y`, which is what the clicklike front-ends have no other way to write
  ([04](04-cli-adapters.md#list-syntax-divergence)). The occurrences are joined as *tokens*
  (`_ParseCtx.multi_tokens`, keyed by field path) and the accumulated list is shaped once, by
  `_varlen_value` for a varlen collection and by `_union_seq_value` for a union with a sequence
  variant. A fixed-arity flag takes one value and is not part of this: repeating it is last-wins.
- **Fixed-length** means `tuple[X, Y]` *or* a namedtuple: both are sequences of a known
  arity, so one function answers "how many tokens, of which types?" for both,
  `_types._fixed_seq_types` — and `_is_seq_variant` counts a namedtuple as sequence-shaped
  wherever a union variant is classified
  ([10](10-design-decisions.md#a-namedtuple-is-a-fixed-length-sequence)).
- A token starting with `{` or `[` is decoded as JSON when the field type accepts an object
  or a list. `_accepts_object_value` owns the object half, because the adapters must register
  and decode the same bare flags ([04](04-cli-adapters.md#whole-value-flags)). The `{`-prefix
  guard runs *before* the arity path, so a namedtuple takes a whole object without ever
  competing with its own positional form.
- The `[` half is a **whole-value** spelling, so `_lone_json_array` grants it only to a flag
  carrying exactly one token: `--tags '["a","b"]'` decodes, and `--tags '["a","b"]' z` or a second
  occurrence makes every token an ordinary item. On a multi-token flag the question is therefore
  asked of the *accumulated* tokens, which is what a framework's own collection already hands
  `_collect._json_array_override` ([04](04-cli-adapters.md#list-syntax-divergence)).
- Leaves are coerced eagerly with `_try_coerce` so the merged dict has the same types
  whichever channel supplied them (and so CLI numbers work inside expressions).
- Bool fields take an explicit value: `--verbose true` ([10](10-design-decisions.md#explicit-boolean-values)).
- A whole value already stored at a field is **opened, not overwritten**, when a later
  `--<field>.<sub>` has to descend through it. `--fn pkg.func` is the shorthand for
  `--fn.fn pkg.func`, so `--fn pkg.func --fn.bind.sep -` refines the target the shorthand
  named; `_open_callable_shorthand` is the one place that decides it, called by this loop and
  by the env loop, so `FN=pkg.func` plus `FN__BIND__SEP=-` reads the same. A segment naming an
  *opener* is a second spelling of the target rather than a refinement, so it still replaces
  the shorthand outright — the rule that already makes an opener beat the blob beside it. A
  field with no shorthand has nothing to open and the deeper key replaces its scalar
  ([01](01-pipeline-and-contracts.md#scalar-intermediates)).
- A namedtuple's **positional list is re-keyed under its field names** before a sub-flag
  descends into it: `_promote_namedtuple_positional` turns the `--pt 1 2` list into
  `{'x': 1, 'y': 2}` for `--pt.y 9` to join, where the generic `_set_nested` promotion
  would have wrapped it in `LIST_REPLACE_BASE_KEY` — the shape a *varlen* collection's
  index patches ride on, and one a namedtuple cannot build. Write order decides the
  shape: a later arity flag still replaces the whole field
  ([10](10-design-decisions.md#a-namedtuples-arity-flag-and-its-sub-flags-merge-in-argv-order)).

## Unions with sequence variants

A union such as `str | list[str]` consumes tokens greedily and defers list/tuple/scalar
choice to `construct`. Two refinements:

- a **single** token is stored as a bare scalar when the union has a scalar variant (so
  `--input foo` stays `'foo'`), wrapped in `_UnionSeqToken` so that if no scalar variant
  accepts it, `construct` can still build a one-element list (`--input hello` for
  `bool | list[str]` → `['hello']`). Env and file scalars get no such fallback: they express
  lists explicitly, so they stay strict;
- **no** token builds `[]` only if the union has a variable-length variant. For a
  fixed-tuple-only union an empty list can build nothing, so this is rejected at parse time —
  one of the few provable-at-parse-time errors.

## Force casts

`.str`, `.int`, `.float`, `.bool` and `.json` suffixes pin how a value is interpreted,
bypassing the type-directed coercion (notably the stealing rule,
[05](05-types-and-construction.md#stealing-rule)).

- `_cast.py` owns **what** the cast names are and **what value** each produces, so vanilla,
  adapters and env produce byte-identical results. `detect_force_cast` owns **whether** a
  trailing segment is a cast, because that needs the type walk.
- Scalar casts store a `_Pinned` (deferred single-type coercion). `.json` decodes eagerly and
  hard-errors on invalid JSON: an explicit request deserves a loud failure, not a fallback.
- JSON-decoded values are stored raw (not tokens), so their elements are exempt from the
  stealing rule (`"yes"` stays a string) and `null` becomes expressible inside a list.
- Root `--json` injects a whole config. It is folded in **under** the per-field flags (field
  flags refine it); with several `--json`, the later wins. At the root only `--json` is a
  cast; scalar casts have nothing to attach to. The environment has the same root form,
  `<PREFIX>JSON` ([02](02-files-and-env.md#environment-parsing)).

## Real field wins

A reserved word never shadows a real member: a field named `json` beats the `.json` cast, a
field named `locals` beats the locals namespace. One predicate decides it everywhere,
`_segment_names_real_field`: structs, namedtuples and (recursively) union variants are
checked for the name; dicts accept any key so the name is always real there; lists, sets,
tuples, callables and scalars have no named members, so the word is reserved.

Keep this predicate canonical: casts, the locals name derivation, the env `__json` cast and
the adapters' `_find_json_cast`/`apply_root_json` all rely on it answering identically.

## Collection patch operations

| Syntax | Effect |
|---|---|
| `--f.N v`, `--f.-1 v` | replace element N (negative from the end) |
| `--f+ v…` | append ([10](10-design-decisions.md#the--suffix-is-a-merge-operator-not-a-list-spelling)) |
| `--f.N-` | delete element N |
| `--f.key v` / `--f.key-` | set / delete a dict key |
| `--f.N.sub v` | patch inside an element |

They accumulate into the sentinel vocabulary of [01](01-pipeline-and-contracts.md#deep-merge-semantics)
in argv order. After `--f+ {}`, a negative index (`--f.-1.sub x`) navigates into the item
just appended (`_navigate_append_spec`), so repeated append-then-fill sequences each patch
their own new item.

A varlen `--f` is absent from the table because it is not a patch: it replaces the whole list,
and with no token at all it clears it — the other flag family that stands bare
([04](04-cli-adapters.md#a-flag-that-stands-bare)). Repeating it extends the list it is building rather than
appending to the lower-priority sources, so it is still exactly one replacement however many
occurrences spell it; a plain occurrence therefore discards the patch ops recorded before it, which
is what makes `--f --f+ x` a reset followed by an append.

Three spellings therefore clear a list, and they are not interchangeable:

| Spelling | What it does |
|---|---|
| `--f a b` | replaces the lower-priority list outright — the ordinary "start over" |
| `--f` | replaces it with `[]` |
| `--f-` | drops the key, so the field falls back to its **default** rather than to `[]` |

`--f-` is the only one every front-end spells, because a delete registers value-less. It also ends
the list being built, so it resets the token accumulation: `--f x --f- --f a` is `['a']`, not
`['x', 'a']`. An *index* delete (`--f.1-`) is a patch inside the list and leaves the accumulation
alone. The adapters re-assert a delete after the merge, so there `--f- --f a` is `[]` and not
`['a']` ([04](04-cli-adapters.md#a-patch-op-joins-the-values-the-framework-collected)) — an open
gap, not this rule.

`_is_collection_patch_path` answers "does this path index a list/tuple/set or key a dict?".
It is the dividing line between what a framework's flat parse result can represent and what
needs the argv-order patch scan ([04](04-cli-adapters.md#collection-patch-parity)).

## Config file flags

`--<config_flag>[.subpath][+] FILE…` is intercepted **before** field lookup, so a field with
the same name as `config_flag` could never be set; that shadowing is rejected up front by
`_check_reserved_key_conflict`, the one canonical shadow check for reserved top-level
names. `_addresses_key` is the one canonical test for "this token belongs to a reserved
namespace", shared by the config flag and the locals namespace across CLI and env.

`_collect_config_file_pairs` is a lenient re-scan used by the adapters to recover argv
order after the framework already consumed the paths; it never raises.

## cli_prefix

`cli_prefix` requires `--<prefix>.` on every flag, so configuration arguments stay
distinguishable from the host application's own — the case the adapters exist for. All four
front-ends support it ([04](04-cli-adapters.md#the-cli_prefix-boundaries)).

The adapters take it on `populate_*`, which owns flag naming, and **record** it there; the
merge step recovers it, so `merge_*`/`from_*` need not repeat it. Passing one that disagrees
with what was registered raises rather than silently matching no flag — the objection that
once kept the prefix out of the adapters, answered instead of avoided.

Vanilla owns the whole command line, so a flag outside the prefix is an
`UnknownArgumentError`. An adapter does not: there, a flag outside the prefix belongs to the
host framework and is left alone. That is not a divergence in the prefix but the adapter
model itself — it holds with or without one.

A non-struct (scalar) target has no field name to address, so `--<prefix> VALUE` is its only
CLI spelling, handled by `_handle_scalar_root` and mirrored for the adapters in
`cli/_collect.py`. Without a prefix it has no CLI spelling at all, in any front-end.
`--<prefix>.json` reaches the same root through the root cast above.

## Callable paths

`--f.fn`, `--f.class`, `--f.call`, `--f.bind.<p>` and their escaped `_fn`/… forms are parsed
leniently as string leaves; whether a spec is well-formed is decided in `construct`
([06-callables.md](06-callables.md)).
