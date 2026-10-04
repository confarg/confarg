# Invariants

Rules that must hold after every change. Each links to the document that argues it.

## Cross-channel parity

Every feature behaves identically across the five front-ends (vanilla, argparse, click,
typer, cyclopts) and the three channels (config files in every format, environment, CLI). A
divergence needs a concrete reason **and** the maintainer's explicit approval before it is
implemented, and it leans the way
[design decisions](design-decisions/divergence-leans-to-the-backend.md#a-divergence-leans-towards-the-affected-backends-own-idiom) settles:
towards the affected backend's own idiom, narrowed to the backend that imposes it. Approved
divergences so far: list syntax per framework
([CLI adapters](cli-adapters/list-syntax-divergence.md#list-syntax-divergence)); the whole-value token on a fixed-arity flag,
which only the two clicklike front-ends decline
([CLI adapters](cli-adapters/whole-value-flags.md#whole-value-flags)); the `=`-spelled run
continued by bare tokens, which argparse alone declines — its `=` binds the one token after
it and its parser exits on the rest
([CLI adapters](cli-adapters/whole-value-flags.md#whole-value-flags)); the config flag's
space-separated multi-file run, which only the two clicklike front-ends decline — their
`multiple=True` registration binds one path per occurrence, so repetition is their only
multi-file spelling
([CLI parsing](cli-parsing/config-file-flags.md#config-file-flags)); file-only dunder keys
([config files](config-files/reserved-keys.md#reserved-file-only-keys)); declaring locals only in files
([locals](locals.md#declare-in-files-modify-anywhere)); the mount keyword and the form its path
takes, spelled per channel
([design decisions](design-decisions/mount-keyword-per-channel.md#the-mount-keyword-is-spelled-per-channel)). Known unapproved gaps
are listed in [../todo/bugs/](../todo/bugs/README.md).

## Delegate to the canonical function

When two paths need the same decision, route both through one function instead of adding a
special case; apply a rule wherever its precondition holds. Canonical decision-makers:

| Decision | Function |
|---|---|
| merge order, file loading, locals checks | `_pipeline._merge_sources` |
| the merge options' defaults, `argv` and `env` included, and "is this keyword a merge option?" | `_defaults._resolve_options` — every `**opts: Unpack[MergeOptions]` front-end resolves through it ([pipeline](pipeline/api-seams.md#one-option-set)) |
| "is this root config file a configuration layer?" | `_files._require_layer` |
| "what is the parsed value of the document here?" | `_files._load_document` |
| reading one document, whatever route mounts it | `_files._load_any` |
| "which parser does this location name?" | `_files._loader_for` |
| reading a channel value as an include value | `_files._parse_mount_value` |
| placing a loaded value at a subpath | `_files._mount` |
| "which scheme does this location name?" | `_sources._scheme_of` |
| "what are this location's bytes?" | `_sources._read_bytes` |
| "which format does this location name?" | `_sources._suffix` |
| "what location does this relative include name?" | `_sources._join` |
| "are these two locations the same document?" | `_sources._identity` |
| "would resolution rewrite this value?" | `dictexpr.contains_expression` |
| "where does each `${...}` of this string begin and end?" | `dictexpr._expressions._find_expressions` ([expressions](expressions/values-and-references.md#delimiting-an-expression)) |
| "which config path does this node read?" | `dictexpr._expressions._attribute_chain` — a dot and a constant subscript each spell one segment; reference collection (`_collect_names`, a method's receiver) and evaluation (`_eval_path_or`, behind both `_eval_attribute` and `_eval_subscript`) ask it (BUG-121, [expressions](expressions/values-and-references.md#spelling-a-path)) |
| "is this name a function or a config key?" | `dictexpr._expressions._function_name` — a function only as a call's callee, a key everywhere else; validation, evaluation, `_collect_names` and `_Prefixer` all ask it (BUG-120, [expressions](expressions/safety-model.md#a-function-is-named-only-by-a-call)) |
| "does this segment name a real member?" | `_parse_cli._segment_names_real_field` |
| "does a real field own the union tag's spelling?" | `_types._union_tag_shadowed` |
| "what exact spelling does an env segment resolve to?" | `_parse_env._env_spelling` — a member case-insensitively, among the `_parse_cli._member_names` of every type `_parse_cli._field_types` reaches at the spelled prefix, then the union tag by its own spelling, lowercase otherwise. The spelling is the env channel's only rule: the spelled path is typed by `_parse_cli._resolve_field_type`, as a flag's is (REF-73) |
| "which type does each union branch reach at this path?" | `_parse_cli._field_types` — the one type walk; `_resolve_field_type` is its fold (the common type, `str` when the branches disagree) |
| "which names does this node declare?" | `_parse_cli._member_names` — a struct's `_types._struct_member_names` (the listing view of `_struct_member_type`, subclass-only names included), a namedtuple's fields, either across a union's variants |
| "does this mount subpath name a node of the target?" | `_parse_cli._check_mount_subpath` |
| "is this a cast, and which?" | `_parse_cli.detect_force_cast` (whether) / `_cast` (what) |
| "how do the objects a root `json` cast decoded meet the fields?" | `_cast.fold_root_json` — vanilla's `--json`, the adapters' `apply_root_json` and the environment's `<PREFIX>JSON` (REF-44) |
| "does this token address a reserved name?" | `_parse_cli._addresses_key` |
| "is this argv token a flag, or a value?" | `_parse_cli._looks_like_flag` |
| "does this flag have its value here?" | `_parse_cli._require_value` |
| "what does an op recorded below a node do with what it finds there?" | `_merge._descend_creating` — the one descent `_set_nested` and `_accumulate_list_delete` share: a plain list becomes the `'*'` base, any other non-dict (a scalar, a whole-field delete's sentinel) is replaced, a negative index enters an appended item (BUG-77) |
| "how does a sub-flag write re-key a namedtuple's positional list?" | `_parse_cli._promote_namedtuple_positional` (field names, unlike the `'*'` base `_set_nested` gives a varlen collection) |
| "does a scalar cast land on a plain leaf field (registration)?" | `cli/_build._scalar_cast_parent_is_leaf` |
| reserved-name shadowing | `_parse_cli._check_reserved_key_conflict` |
| locals namespace names | `_parse_cli._locals_keys_at` |
| "is this path a collection patch?" | `_parse_cli._is_collection_patch_path` |
| "who writes the adapters' CLI channel and its `--config` files?" | `_parse_cli._parse_cli(..., host_parsed=True)` — vanilla's loop over the argv the framework parsed, skipping only the host's own tokens (REF-72); the parse result is only checked against argv, by `cli/_collect._require_argv_spells` |
| "would vanilla refuse this path as unknown?" | `_parse_cli._path_unknown` — the delete handler, and the host-mode skip of a flag whose first segment names no member |
| "did the host bind the token after a flag's run to that flag?" | `cli/_build._binds_a_run`, asked by the loop only for a framework that varies a flag's token count (argparse, cyclopts: `binds_runs`) |
| "which flags does argv spell?" | `cli._argv.spelled_flag_names` |
| "does the static walk leave this path's flag to be registered when typed?" | `_parse_cli._registered_when_typed` — a collection patch, or a tag the walk reaches by its fallback, whatever the parent (BUG-106) |
| "does this field take a whole `{…}` token?" | `_parse_cli._accepts_object_value` |
| "is this a whole-value inline JSON array?" | `_parse_cli._lone_json_array` |
| what a multi-token flag's accumulated tokens hold | `_parse_cli._varlen_value` / `_union_seq_value` |
| "is a bare string here a callable shorthand, and must it be opened?" | `_parse_cli._open_callable_shorthand` |
| the dict form a bare callable string abbreviates | `_callable.promote_bare_spec` |
| "how many positional tokens, of which types?" | `_types._fixed_seq_types` |
| "is this variant sequence-shaped?" | `_types._is_seq_variant` |
| "which index spellings does an n-field namedtuple register and accept?" | `_parse_cli._namedtuple_index_spellings` — the one source for `str(i)` and `str(i - n)`, so no odd form (`-0`, `+N`, `007`) slips through (BUG-97); the walk looks a spelling up in it, and registration lists a field's keys through its per-position view `_namedtuple_position_spellings` |
| "which struct does a class tag name, if any?" | `cli/_collect._tag_named_struct` — the argparse completion pre-extend |
| "which flat tagged-leaf flags (`--<leaf>.class`, `--<leaf>.<param>`) does argv spell?" | `cli/_build._collect_leaf_tag_argv_specs`, accepting exactly what `_parse_cli._resolve_field_type` accepts |
| "is this segment the union tag, reached by the walk's fallback?" | `_parse_cli._names_tag_by_fallback` — the walk asked with and without its tag rule (`_resolve_field_type(..., tag_fallback=False)`) |
| "does the walk answer this struct member from the subclasses?" | `_types._answered_by_subclasses` — only a name the struct does not declare; a declared field keeps its own annotation however a subclass overrides it. `_types._struct_member_type` composes it with the subclasses' answer, and is what vanilla's `_advance_field_type` asks for a segment's type and the member predicates `_segment_names_real_field` / `_union_tag_shadowed` ask for its existence; registration's subclass recursion asks its path form `_types._base_declares_path` of a flag path (BUG-86) |
| reconciling a registered `cli_prefix` with one passed to `merge_*` | `cli._prefix.resolve_prefix` |
| "does this argv flag occurrence carry an item?" | `cli._argv._bare_occurrence` |
| "which argv tokens does a host framework parse?" | `cli._argv.drop_bare_occurrences` |
| "does this field's flag consume many tokens, and so stand bare?" | `cli._build._takes_multi_tokens` |
| "which bare occurrence is a missing value, refused before the framework parses?" | `cli._argv.refuse_bare_occurrences`, off `FlagSpec.refuses_bare` — set by the same `_fixed_seq_types(resolved)` gate that arms the fixed-arity guard |
| plain vs escaped callable directives | `_callable.active_directives` |
| single-value (scalar/type-ref) construction | `_construct._construct_scalar` |
| "which `__init__` parameters are `*args` / `**kwargs`?" | `_types._var_params` |
| combine existing value with override | `_merge._merge_existing_value` |
| how a leaf value leaves the library | `_serialize._serialize_leaf` |
| "which union variant does this instance belong to?" | `_serialize._variant_holds` |
| "which shape does this type dispatch as?" | `typedload._coerce._type_kind` — the one ordered table of shape predicates (`_KIND_ORDER`); construction, serialization, `_variant_holds` and the CLI walk's `_advance_field_type` / `_is_collection_patch_path` each `match` on it (REF-47) |
| "does this serialized value read back as itself?" | `_serialize._reads_back` |
| the `{__cast__, __value__}` spelling | `_serialize._cast_dict` |
| "which leaf variant steals a token?" | `typedload._coerce._steal_rank` |
| "does this type get taken apart into fields?" | `typedload._coerce._is_struct_variant` |
| "may an explicit class tag still open this leaf?" | `typedload._coerce._is_taggable_leaf` |
| "is this leaf type eager-coerced from a token?" | `typedload._coerce._is_eagerly_coercible` |
| the error for a field no channel supplied | `typedload._construct._missing_field_error` |
| "what dotted path names this object?" | `_import.dotted_name` |
| "what type is this value, to a reader?" | `_types._src_type` |
| the text of an error raised from more than one site | a classmethod factory on the class in `exceptions.py` |

## Merge stays unvalidated

The merge layer never checks convertibility; parsers reject only what is provably wrong at
parse time; ambiguity that depends on the type is deferred to `build()`
([pipeline](pipeline/merge-build-contract.md#merge-build-contract)).

## Expressions are deferred by rule

Every value gate before `build()` consults `contains_expression`
([expressions](expressions/deferral-rule.md#deferral-rule)).

## Tokens mean untyped text

Only `_StrToken` values are coerced from text; plain strings from files are never
reinterpreted. Tokens never leak into dumps or error messages
([types](types/token-model.md#token-model)).

## Adapter output equals vanilla output

An adapter's merged dict is byte-identical to `confarg.merge()`'s for the same input, key order
included. The adapters' CLI channel is vanilla's loop over argv and nothing else: a rule the CLI
needs goes into that loop, never into a second writer over the framework's parse result
([CLI adapters](cli-adapters/model.md#argv-is-the-only-writer),
[parity](cli-adapters/parity.md#byte-identical-merged-dicts)).

## Fragile couplings

- Do not add lambdas, comprehensions or other binding constructs to `_ALLOWED_NODES`
  without reworking `_Prefixer` ([expressions](expressions/reference-anchoring.md#reference-anchoring)).
- Anchor-marker handling stays lexical ([expressions](expressions/reference-anchoring.md#reference-anchoring)).
- The node anchor is resolved on the AST, never by rewriting expression text: an absolute path
  may hold a list index or a non-identifier key ([expressions](expressions/reference-anchoring.md#implementation-constraints)).
- `canonicalize_references` must not resolve `${.x}` — preserving it through `merge()` is what
  keeps a list element independent of its index
  ([expressions](expressions/reference-anchoring.md#a-relative-reference-is-never-serialized-as-an-absolute-path)).
- Only graft the names `_locals_keys` returns ([locals](locals.md#walk-target-graft)).
- `_strip_locals` must not mutate its input ([locals](locals.md#stripping)).
- `cli/_build.py` imports `_parse_cli` lazily (import cycle) and never imports argparse
  ([CLI adapters](cli-adapters/flag-model.md#framework-neutral-flag-model)).
- `cli/_clicklike/` imports neither click nor typer, so importing one adapter does not drag
  the other's dependency in ([CLI adapters](cli-adapters/clicklike-seam.md#the-clicklike-seam)).
- Anything the click and typer adapters both need lives in `cli/_clicklike/`, parameterised by
  the classes the two frameworks spell differently — never duplicated into both packages
  ([CLI adapters](cli-adapters/clicklike-seam.md#the-clicklike-seam)).
- Completion and dynamic flag registration never raise
  ([CLI adapters](cli-adapters/completion.md#completion)).
- `FlagSpec.stands_bare` is set on what `cli._build._takes_multi_tokens` names, plus the
  append flag. A bare occurrence of such a flag never reaches the framework's parse result,
  which is safe only because the CLI channel is read off the argv the user typed
  ([CLI adapters](cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare)).
- `FlagSpec.refuses_bare` is set by the `_fixed_seq_types(resolved)` gate, asked without
  unwrapping `Optional` — the type vanilla's loop dispatches on — so the pre-parse refusal and
  the loop cannot disagree about which flags are fixed-arity
  ([CLI adapters](cli-adapters/whole-value-flags.md#whole-value-flags)).
- `import_tagged_classes` runs before anything reads `__subclasses__()` — before the static
  type walk in `build_static_flags`, before path resolution in `_parse_cli`, and at the start of
  `build_dynamic_flags`, before any argv scan
  ([design decisions](design-decisions/a-named-tag-is-imported-before-registration.md#a-named-tag-is-imported-before-registration)).
- Defaults and shared reserved key names (`ROOT_KEY`, `LOCALS_KEYS`) live in
  `_defaults.py`; never repeat the literals
  ([design decisions](design-decisions/shared-reserved-key-names.md#shared-reserved-key-names-live-in-_defaultspy)).
- `exceptions.py` imports nothing from `confarg`. It is the whole of what `dictexpr` is allowed
  to depend on, so an import there would drag the rest of the library into `dictexpr`'s closure.
  A message factory that needs `_src_type` or `dotted_name` therefore cannot have them: either
  the caller passes the text in, or the factory's own argument provably cannot be a token
  ([design decisions](design-decisions/messages-live-on-exceptions.md#a-user-facing-message-lives-on-the-exception-that-raises-it)).
- A type in `_LEAF_COERCIONS` must also be in `_LEAF_SERIALIZERS`: registration makes a type
  a leaf in both directions, and only `register_leaf_type` writes them
  ([types](types/leaf-coercion.md#leaf-coercion)).
