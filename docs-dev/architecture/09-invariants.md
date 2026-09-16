# Invariants

Rules that must hold after every change. Each links to the document that argues it.

## Cross-channel parity

Every feature behaves identically across the four front-ends (vanilla, argparse, click,
cyclopts) and the three channels (config files in every format, environment, CLI). A
divergence needs a concrete reason **and** the maintainer's explicit approval before it is
implemented, and it leans the way
[10](10-design-decisions.md#a-divergence-leans-towards-the-affected-backends-own-idiom) settles:
towards the affected backend's own idiom, narrowed to the backend that imposes it. Approved
divergences so far: list syntax per framework
([04](04-cli-adapters.md#list-syntax-divergence)); the whole-value token on a fixed-arity flag,
which click alone declines ([04](04-cli-adapters.md#whole-value-flags)); file-only dunder keys
([02](02-files-and-env.md#reserved-file-only-keys)); declaring locals only in files
([08](08-locals.md#declare-in-files-modify-anywhere)). Known unapproved gaps are listed in
[../todo/bugs.md](../todo/bugs.md).

## Delegate to the canonical function

When two paths need the same decision, route both through one function instead of adding a
special case; apply a rule wherever its precondition holds. Canonical decision-makers:

| Decision | Function |
|---|---|
| merge order, file loading, locals checks | `_pipeline._merge_sources` |
| "would resolution rewrite this value?" | `dictexpr.contains_expression` |
| "does this segment name a real member?" | `_parse_cli._segment_names_real_field` |
| "is this a cast, and which?" | `_parse_cli.detect_force_cast` (whether) / `_cast` (what) |
| "does this token address a reserved name?" | `_parse_cli._addresses_key` |
| reserved-name shadowing | `_parse_cli._check_reserved_key_conflict` |
| locals namespace names | `_parse_cli._locals_keys_at` |
| "is this path a collection patch?" | `_parse_cli._is_collection_patch_path` |
| "does this field take a whole `{…}` token?" | `_parse_cli._accepts_object_value` |
| "is a bare string here a callable shorthand, and must it be opened?" | `_parse_cli._open_callable_shorthand` |
| the dict form a bare callable string abbreviates | `_callable.promote_bare_spec` |
| "how many positional tokens, of which types?" | `_types._fixed_seq_types` |
| "is this variant sequence-shaped?" | `_types._is_seq_variant` |
| reconciling a registered `cli_prefix` with one passed to `merge_*` | `cli._prefix.resolve_prefix` |
| plain vs escaped callable directives | `_callable.active_directives` |
| single-value (scalar/type-ref) construction | `_construct._construct_scalar` |
| "which `__init__` parameters are `*args` / `**kwargs`?" | `_types._var_params` |
| combine existing value with override | `_merge._merge_existing_value` |
| how a leaf value leaves the library | `_serialize._serialize_leaf` |
| "does this type get taken apart into fields?" | `typedload._coerce._is_struct_variant` |
| "may an explicit class tag still open this leaf?" | `typedload._coerce._is_taggable_leaf` |
| the error for a field no channel supplied | `typedload._construct._missing_field_error` |

## Merge stays unvalidated

The merge layer never checks convertibility; parsers reject only what is provably wrong at
parse time; ambiguity that depends on the type is deferred to `build()`
([01](01-pipeline-and-contracts.md#merge-build-contract)).

## Expressions are deferred by rule

Every value gate before `build()` consults `contains_expression`
([07](07-expressions.md#deferral-rule)).

## Tokens mean untyped text

Only `_StrToken` values are coerced from text; plain strings from files are never
reinterpreted. Tokens never leak into dumps or error messages
([05](05-types-and-construction.md#token-model)).

## Adapter output equals vanilla output

An adapter's merged dict is byte-identical to `confarg.merge()`'s for the same input; new
collection logic goes into `cli/_collect.py` mirroring the vanilla decision
([04](04-cli-adapters.md#byte-identical-merged-dicts)).

## Fragile couplings

- Do not add lambdas, comprehensions or other binding constructs to `_ALLOWED_NODES`
  without reworking `_Prefixer` ([07](07-expressions.md#reference-anchoring)).
- Anchor-marker handling stays lexical ([07](07-expressions.md#reference-anchoring)).
- Only graft the names `_locals_keys` returns ([08](08-locals.md#walk-target-graft)).
- `_strip_locals` must not mutate its input ([08](08-locals.md#stripping)).
- `cli/_build.py` imports `_parse_cli` lazily (import cycle) and never imports argparse
  ([04](04-cli-adapters.md#framework-neutral-flag-model)).
- Completion and dynamic flag registration never raise
  ([04](04-cli-adapters.md#completion)).
- `import_tagged_classes` runs before anything reads `__subclasses__()` — before the static
  type walk in `build_static_flags`, and before path resolution in `_parse_cli`
  ([10](10-design-decisions.md#a-named-tag-is-imported-before-registration)).
- Defaults and shared reserved key names (`ROOT_KEY`, `LOCALS_KEYS`) live in
  `_defaults.py`; never repeat the literals
  ([10](10-design-decisions.md#shared-reserved-key-names-live-in-_defaultspy)).
- A type in `_LEAF_COERCIONS` must also be in `_LEAF_SERIALIZERS`: registration makes a type
  a leaf in both directions, and only `register_leaf_type` writes them
  ([05](05-types-and-construction.md#leaf-coercion)).
