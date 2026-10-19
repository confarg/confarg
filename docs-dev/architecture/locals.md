# Local variables (the reserved `locals` namespace)

`locals:` holds scratch values that expressions reference as `${locals.<name>}` but that are not fields of the target.
They are stripped before construction.

## Work at the edges

The expression engine resolves paths against the whole merged dict, so it needs no change.
The work is spread over the edges:

| Where | Responsibility |
|---|---|
| `_parse_cli._locals_keys` / `_locals_keys_nested` / `_locals_keys_reached` | which names address a namespace, at a given node |
| `_parse_cli._step_states` | step a walker over data from a node to its child |
| `_parse_cli._walk_target`, `_locals_walk_root` | let `--locals.x` resolve like a `dict[str, Any]` field at the root |
| `_parse_cli._resolve_field_type` | step through a nested namespace as `dict[str, Any]` |
| `_parse_env._parse_env` | store `PFX_DB__LOCALS__X` raw, without the unknown-field warning |
| `_build.build_static_flags` | register `--config.<locals>` (declaring from the CLI) |
| `_pipeline._apply_locals_layer` and helpers | declared-ness, types, add/remove refusal, each layer read by `_LayerReading` |
| `_default_layer._with_namespaces_applied` | apply a list op a namespace holds before resolution |
| `_api._strip_locals` | drop every namespace in `build()` / `from_dict()` |

## Derived name

The name is not configurable.
`_locals_keys(target)` returns whichever of `("locals", "_locals")` is **not** a real member of the target, using `_segment_names_real_field` — the same "real field wins" predicate as the `.json` cast ([CLI parsing](cli-parsing/casts-and-reserved-words.md#real-field-wins)).
A target with a `locals` field keeps it and uses `_locals`; a target owning both has no namespace; declaring under both spellings raises `LocalsError.ambiguous`.
A dict-typed root has no namespace (every name is a real key); a scalar (`__root__`) root keeps it.

It is a **pure function of the target** on purpose: `build()`/`from_dict()` see no `config_flag`, so any other input could make them strip different keys than `merge()` produced.
A `config_flag` equal to a live locals name is rejected in `_merge_sources`, because the config flag is intercepted before field lookup and `--<flag>.<name>` could never reach a local.

`_locals`, not `__locals__`: the env separator is `__`, so `PFX___LOCALS____X` splits into `['LOCALS', '', 'X']` and a dunder name is inexpressible in the env channel.
The namespace must work in every channel, unlike the file-only dunder keys.

## Per-node namespaces

A file's root — and its `locals:` block — lands wherever the file is mounted, so a namespace can sit at any struct-like node, not only the root.
Only struct-like nodes can hold one (a dict treats every name as data; lists address children by index), and a name is a namespace there only where no class the node may build owns it, whatever its tag names ([real field wins](cli-parsing/casts-and-reserved-words.md#every-class-a-node-may-build-counts)).

A walker over data, the strip in `build()` and the checks in `merge()`, carries the walk down the data with it: it steps from each node to its child (`_step_states`, the walk's own step), by the class the node names, and asks the names of what it reached (`_locals_keys_reached`).
Each way the walk reaches a node is kept once, so a union met at every level never forks it again; the environment's `_locals_segment_index` folds the same steps along one path.
The strip reads the class each node names, as construction builds it; the checks the class the highest layer naming the node names, else its own layer's, since a higher layer's tag replaces the node below it.
Before, every walker asked `_locals_keys_at` at each node, which walked the type from the root again, naming nothing, so a union met at every level forked it into 2^depth branches per node: a 20-level tagged chain took 45 seconds to build (BUG-258).
With anchoring ([expressions](expressions/reference-anchoring.md#reference-anchoring)), a mounted fragment reads its own variables with the same bare `${locals.x}` it would use standing alone.

## A namespace in an item a list op holds

An item a list op holds is a node like any other, so its namespace is found, checked and stripped as a mounted fragment's is (BUG-219).
`build()` applies the op before resolution ([design decisions](design-decisions/a-pending-list-op-is-applied-before-resolution.md#a-pending-list-op-is-applied-before-resolution)), so the item reads its own `${.locals.n}` at the index it lands at, and its bare `${locals.n}` too, which the loader spells as that dot run ([reference anchoring](expressions/reference-anchoring.md#a-document-a-list-op-holds-is-anchored-by-dot-runs)); `_strip_locals` then meets the item as a list element.

The checks in `merge()` run before any op is applied, so `_apply_locals_layer` reads each layer through `_LayerReading`: a node of ops is the list it makes over the layers below that layer, the lower layers' items standing as placeholders the layer says nothing of.
So an item appended by a file (`--config.items+`, `CONFIG__ITEMS+`, a file's `__append__`) is at the position `build()` gives it, after the base below: its namespace is a declaration, and the typed-formats check covers a CSV row appended there.
An index patch addresses the same position, so `--items.0.locals.n c` overrides the local of a fragment `--config.items+` appended with no base, as construction applies the append before the patch.
An item appended on argv or in the environment is new, and a namespace in it declares nothing: `--items+ '{"locals": {…}}'` is the `LocalsError` that `--items '[{"locals": {…}}]'` already was.
Over a layer that only overrides, the reading leaves each namespace as the layer holds it, the very dict, so the overrides are coerced in place and an op in one is refused, never read as a list.

Before, every walker skipped what an op held: the append's fragment kept its `locals` key into construction, which refused it as an unknown field, an override of its local was refused as undeclared, and a namespace in an item appended on argv escaped both checks.
Index positions in the merge and in `build()` agree because no default laid below a list holds an item that can hold a namespace: only a tuple of leaves is laid ([FEAT-38](../todo/features/FEAT-38-a-factory-default-is-no-base.md) would change that).

## A list op in a namespace is its list

A namespace has no annotation, and an op means a list whatever it stands in, so `build()` applies a file's `locals: {xs: {__append__: [2, 3]}}` before resolution as the list it makes over the layers below, untyped (`_default_layer._with_namespaces_applied`): `${len(locals.xs)}` counts two.
Until then it did only with a lower file declaring `xs`, where the merge had applied the op, and counted the op dict's keys otherwise.
The declaration is read the same way in `merge()`, so `--locals.xs.0 9` modifies the first item the declared append makes.

## Declare in files, modify anywhere

- **Declaring** a local (introducing a name) is a config-file privilege, because a local has no annotation: its type is whatever its file format produced.
  Only self-describing formats carry a type, so CSV/TSV cells (`_StrToken`) are rejected in a namespace; otherwise `${locals.n + 1}` would concatenate.
  One walk (`_check_locals_are_typed`) covers every route a data file can take into a namespace.
- **Modifying** a declared local has full parity across env and CLI.
  The override is coerced to the declared value's runtime type with `_coerce_leaf` (not `_try_coerce`, which would swallow a failure), so `${locals.n * 2}` keeps multiplying and a type-changing override is a `TypeCoercionError`.
  Containers may only be replaced by containers.
- Writing an undeclared name is a `LocalsError` (typo detection).
  Adding or removing locals (`+`, `-` markers, `DICT_DELETE`) from env/CLI is refused: which locals exist belongs to the declaring files.
  Assigning the whole namespace from env/CLI is refused too.
- Expression tokens are exempt from override coercion ([expressions](expressions/deferral-rule.md#deferral-rule)).

**Why these checks live in the pipeline, not in the parsers**: config files are loaded *after* argv and env are parsed, so at parse time neither "is it declared?" nor "what type?" is answerable; an undeclared local is not provable wrong at parse time ([pipeline](pipeline/merge-build-contract.md#merge-build-contract)).
The parsers accept `locals.*` permissively.
`_iter_namespace_nodes` walks the union of the three sources' key structures (not the merged result), so a namespace written only on the CLI is still checked against the declarations.

## Walk-target graft

At the root, the parser resolves paths against `target | _LocalsRoot` (a synthetic dataclass with one `dict[str, Any]` field per locals name), so nested paths and indices ride the machinery real dict fields already use — including adapter patch-flag registration.

- The graft is used **only for path resolution**.
  The real target is kept to classify the root (scalar vs struct) and for the config-flag conflict check: a union is struct-like, so grafting would misclassify a scalar root.
- **Only graft the names `_locals_keys` returns.**
  The graft is a union and the type walk searches every variant, so grafting a name that is also a real field silently routes `--<name>.x` to the synthetic dict instead of the field — the one mistake here that changes parsing without any error.
- **The graft answers its keys and nothing else.**
  No class is dispatched on it, so the walk never answers the union tag at it by its fallback.
  It once did, and its `str` branch then disagreed with a real field named like the tag, so the walk's fold typed `--kind 5` as a string on a struct root with a `kind: int` field.
- A **non-struct root** is set whole, from `__root__`, so its walk target is the graft alone: the namespace beside its value is all a dotted path reaches there ([CLI parsing](cli-parsing/cli-prefix.md#a-non-struct-root-is-set-whole)).
- The **environment** spells its segments against the same graft (BUG-115), case-insensitively, so a root field that differs from a namespace name only by case (`Locals`) is an ambiguous segment there ([environment parsing](environment-parsing.md#environment-parsing)).

## Stripping

`_strip_locals` copies rather than pops, and only where something is dropped: `resolve_expressions` returns the caller's own dict when there are no expressions, so mutating would strip the namespace out of the caller's data.

## Assigning the whole namespace

`--locals VALUE` is rejected in every front-end, by confarg rather than by a host framework.
The graft makes `locals` a `dict[str, Any]` path, so `_is_collection_patch_path` accepts it and the adapters register the flag; the token then reaches `_apply_locals_overrides`, which raises `LocalsError.not_assignable`.
Nothing here is locals-specific machinery — it is the same route a bare `--<dictfield>` takes ([CLI adapters](cli-adapters/whole-value-flags.md#whole-value-flags)).
