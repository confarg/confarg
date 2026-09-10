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

## Token consumption

- `--key=value` is normalized to `--key value`.
- A flag is `--` followed by a letter or `_`, so `-5` and `--3` are values.
- Values run until the next flag: variable-length collections consume greedily, fixed
  tuples consume exactly their arity, and a dataclass flag with no value means "use defaults".
- A token starting with `{` or `[` is decoded as JSON when the field type accepts an object
  or a list.
- Leaves are coerced eagerly with `_try_coerce` so the merged dict has the same types
  whichever channel supplied them (and so CLI numbers work inside expressions).
- Bool fields take an explicit value: `--verbose true` ([10](10-design-decisions.md#explicit-boolean-values)).

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
  cast; scalar casts have nothing to attach to.

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
| `--f+ v…` | append |
| `--f.N-` | delete element N |
| `--f.key v` / `--f.key-` | set / delete a dict key |
| `--f.N.sub v` | patch inside an element |

They accumulate into the sentinel vocabulary of [01](01-pipeline-and-contracts.md#deep-merge-semantics)
in argv order. After `--f+ {}`, a negative index (`--f.-1.sub x`) navigates into the item
just appended (`_navigate_append_spec`), so repeated append-then-fill sequences each patch
their own new item.

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

`cli_prefix` (require `--<prefix>.` on every flag) exists only in vanilla `load`/`merge`.
The adapters' `populate_*` functions own flag naming; a prefix given only at merge time
could silently disagree with what was registered, so it is not offered there. A side
effect: a non-struct (scalar) target can be set from the CLI only as `--<prefix> VALUE`,
so adapters have no CLI form for scalar roots ([11](11-limitations-and-directions.md#parity-gaps)).

## Callable paths

`--f.fn`, `--f.class`, `--f.call`, `--f.bind.<p>` and their escaped `_fn`/… forms are parsed
leniently as string leaves; whether a spec is well-formed is decided in `construct`
([06-callables.md](06-callables.md)).
