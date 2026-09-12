# Local variables (the reserved `locals` namespace)

`locals:` holds scratch values that expressions reference as `${locals.<name>}` but that
are not fields of the target. They are stripped before construction.

## Work at the edges

The expression engine resolves paths against the whole merged dict, so it needs no change.
The work is spread over the edges:

| Where | Responsibility |
|---|---|
| `_parse_cli._locals_keys` / `_locals_keys_nested` / `_locals_keys_at` | which names address a namespace, at a given node |
| `_parse_cli._walk_target`, `_locals_walk_root` | let `--locals.x` resolve like a `dict[str, Any]` field at the root |
| `_parse_cli._resolve_field_type` | step through a nested namespace as `dict[str, Any]` |
| `_parse_env._parse_env` | store `PFX_DB__LOCALS__X` raw, without the unknown-field warning |
| `_build.build_static_flags` | register `--config.<locals>` (declaring from the CLI) |
| `_pipeline._apply_locals_layer` and helpers | declared-ness, types, add/remove refusal |
| `_api._strip_locals` | drop every namespace in `build()` / `from_dict()` |

## Derived name

The name is not configurable. `_locals_keys(target)` returns whichever of
`("locals", "_locals")` is **not** a real member of the target, using
`_segment_names_real_field` — the same "real field wins" predicate as the `.json` cast
([03](03-cli-parsing.md#real-field-wins)). A target with a `locals` field keeps it and uses
`_locals`; a target owning both has no namespace; declaring under both spellings raises
`LocalsError.ambiguous`. A dict-typed root has no namespace (every name is a real key); a
scalar (`__root__`) root keeps it.

It is a **pure function of the target** on purpose: `build()`/`from_dict()` see no
`config_flag`, so any other input could make them strip different keys than `merge()`
produced. A `config_flag` equal to a live locals name is rejected in `_merge_sources`,
because the config flag is intercepted before field lookup and `--<flag>.<name>` could never
reach a local.

`_locals`, not `__locals__`: the env separator is `__`, so `PFX___LOCALS____X` splits into
`['LOCALS', '', 'X']` and a dunder name is inexpressible in the env channel. The namespace
must work in every channel, unlike the file-only dunder keys.

## Per-node namespaces

A file's root — and its `locals:` block — lands wherever the file is mounted, so a
namespace can sit at any struct-like node, not only the root. Every consumer asks
`_locals_keys_at(target, path)` at each node. Only struct-like nodes can hold one (a dict
treats every name as data; lists address children by index). With anchoring
([07](07-expressions.md#reference-anchoring)), a mounted fragment reads its own variables
with the same bare `${locals.x}` it would use standing alone.

## Declare in files, modify anywhere

- **Declaring** a local (introducing a name) is a config-file privilege, because a local has
  no annotation: its type is whatever its file format produced. Only self-describing formats
  carry a type, so CSV/TSV cells (`_StrToken`) are rejected in a namespace; otherwise
  `${locals.n + 1}` would concatenate. One walk (`_check_locals_are_typed`) covers every
  route a data file can take into a namespace.
- **Modifying** a declared local has full parity across env and CLI. The override is coerced
  to the declared value's runtime type with `_coerce_leaf` (not `_try_coerce`, which would
  swallow a failure), so `${locals.n * 2}` keeps multiplying and a type-changing override is a
  `TypeCoercionError`. Containers may only be replaced by containers.
- Writing an undeclared name is a `LocalsError` (typo detection). Adding or removing locals
  (`+`, `-` markers, `DICT_DELETE`) from env/CLI is refused: which locals exist belongs to
  the declaring files. Assigning the whole namespace from env/CLI is refused too.
- Expression tokens are exempt from override coercion ([07](07-expressions.md#deferral-rule)).

**Why these checks live in the pipeline, not in the parsers**: config files are loaded
*after* argv and env are parsed, so at parse time neither "is it declared?" nor "what type?"
is answerable; an undeclared local is not provable wrong at parse time
([01](01-pipeline-and-contracts.md#merge-build-contract)). The parsers accept `locals.*`
permissively. `_iter_namespace_nodes` walks the union of the three sources' key structures
(not the merged result), so a namespace written only on the CLI is still checked against
the declarations.

## Walk-target graft

At the root, the parser resolves paths against `target | _LocalsRoot` (a synthetic
dataclass with one `dict[str, Any]` field per locals name), so nested paths and indices ride
the machinery real dict fields already use — including adapter patch-flag registration.

- The graft is used **only for path resolution**. The real target is kept to classify the
  root (scalar vs struct) and for the config-flag conflict check: a union is struct-like, so
  grafting would misclassify a scalar root.
- **Only graft the names `_locals_keys` returns.** The graft is a union and the type walk
  searches every variant, so grafting a name that is also a real field silently routes
  `--<name>.x` to the synthetic dict instead of the field — the one mistake here that changes
  parsing without any error.

## Stripping

`_strip_locals` copies rather than pops, and only where something is dropped:
`resolve_expressions` returns the caller's own dict when there are no expressions, so
mutating would strip the namespace out of the caller's data.

## Gap

`--locals VALUE` (whole namespace) is rejected everywhere, but only vanilla reports a
`LocalsError`; adapters register no flag for a whole dict, so their framework rejects the
token first — the same pre-existing gap as a bare `--<dictfield>`.
