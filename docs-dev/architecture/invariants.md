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
([CLI adapters](cli-adapters/whole-value-flags.md#whole-value-flags)); file-only dunder keys
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
| "does this segment name a real member?" | `_parse_cli._segment_names_real_field` |
| "does a real field own the union tag's spelling?" | `_types._union_tag_shadowed` |
| "what exact spelling does an env segment resolve to?" | `_parse_env._match_env_part` — a member case-insensitively, then the union tag by its own spelling, lowercase otherwise |
| "does this mount subpath name a node of the target?" | `_parse_cli._check_mount_subpath` |
| "is this a cast, and which?" | `_parse_cli.detect_force_cast` (whether) / `_cast` (what) |
| "does this token address a reserved name?" | `_parse_cli._addresses_key` |
| "is this argv token a flag, or a value?" | `_parse_cli._looks_like_flag` |
| "does this flag have its value here?" | `_parse_cli._require_value` |
| "is this fixed-arity flag's token run exactly its run?" | `cli/_collect._require_fixed_arity` (the adapters' peer of the `_require_value` loop, which counts argv one token at a time; answers both bounds) |
| "which token runs did argv spell for a repeated fixed-arity flag?" | `cli/_collect._fixed_arity_occurrence_runs`, read off argv — a greedy registration keeps only the surviving run |
| "which plain-occurrence tokens survive the last whole-field delete at a path?" | `cli/_collect._tokens_past_whole_field_delete`, read off argv — a framework's parse result has the pre-delete ones folded into the value after it |
| "how long is a fixed-arity flag's token run?" | `cli/_collect._fixed_arity_whole_value` on its first token — one for a whole value, the arity otherwise |
| "how is an `Optional[<sequence>]` field's flag value shaped?" | `cli/_collect._collect_ns_optional_seq` — the union shaper `_collect_union_seq_value`, asked of the resolved union as vanilla's `_union_seq_value` is |
| "what did argv's occurrences of a union-seq flag write, and which bare one was a missing value?" | `cli/_collect._union_seq_occurrence_writes`, read off argv — the accumulation each occurrence joins, the whole-value blob that never joins it, the delete that ends it, and the bare occurrence the shaper refuses on an empty accumulation |
| "how does a sub-flag write re-key a namedtuple's positional list?" | `_parse_cli._promote_namedtuple_positional` (field names, unlike the `'*'` base `_set_nested` gives a varlen collection) |
| "which keys does a namedtuple's sub-flag collection keep?" | `cli/_collect._namedtuple_sub_flags` — the keys as spelled, name and index alike; the win belongs to construction |
| "which of a namedtuple's fields does a deep path reach, and who collects it?" | `cli/_collect._namedtuple_deep_fields` (which — a struct-shaped field, however wrapped) / `cli/_collect._collect_field` (the collector — the one per-field dispatch, shared with a struct's own fields) |
| "which of a bare flag and its sub-flags is the latest writer?" | `cli/_collect._arity_flag_writes_last`, read off argv (`_last_flag_occurrence` is the occurrence-index reader it and the conflict stores descend from) — the namedtuple's arity flag (BUG-66) and the bare value at a struct, registered-leaf or union field (BUG-85) |
| "does a scalar cast land on a plain leaf field (registration)?" | `cli/_build._scalar_cast_parent_is_leaf` — the leaf answer mirrors the collector's dispatch, so the frameworks never accept a cast flag the collector drops |
| "which scalar spelling of a leaf field wrote last — the plain flag or a cast?" | `cli/_collect._last_leaf_cast_spelling`, read off argv — vanilla writes the occurrences sequentially and only the survivor's pin coerces |
| "which occurrence of a repeated fixed-arity flag reaches the collector, on cyclopts?" | `cli/cyclopts/_register._last_occurrence_convert`, read off the `CliToken` index |
| reserved-name shadowing | `_parse_cli._check_reserved_key_conflict` |
| locals namespace names | `_parse_cli._locals_keys_at` |
| "is this path a collection patch?" | `_parse_cli._is_collection_patch_path` |
| "which patch ops does a plain flag occurrence supersede?" | `_merge._pop_nested`, replayed at the patch scan's skip sites |
| "what does a collected list meet when a patch op addresses it?" | `cli/_collect._promote_patched_lists` — the `'*'` base of the op dict, the promotion vanilla's own descent makes |
| "does this field take a whole `{…}` token?" | `_parse_cli._accepts_object_value` |
| "is this a whole-value inline JSON array?" | `_parse_cli._lone_json_array` |
| what a multi-token flag's accumulated tokens hold | `_parse_cli._varlen_value` / `_union_seq_value` |
| "is a bare string here a callable shorthand, and must it be opened?" | `_parse_cli._open_callable_shorthand` |
| the dict form a bare callable string abbreviates | `_callable.promote_bare_spec` |
| "how many positional tokens, of which types?" | `_types._fixed_seq_types` |
| "is this variant sequence-shaped?" | `_types._is_seq_variant` |
| "which struct does a class tag name, if any?" | `cli/_collect._tag_named_struct` — the collector's two tag branches and the argparse completion pre-extend |
| "which flat tagged-leaf flags (`--<leaf>.class`, `--<leaf>.<param>`) does argv spell?" | `cli/_build._collect_leaf_tag_argv_specs`, accepting exactly what `_parse_cli._resolve_field_type` accepts |
| "write a class tag back, then descend into the struct it names and the path's other variants" | `cli/_collect._collect_named_variant` (the tag first, the import after, the siblings last) |
| "descend into every variant a path holds, each in its own guard" | `cli/_collect._collect_variant_fields` — the named variant's siblings, a union field's variants, and a base class's subclasses with no tag (BUG-83); a flag the variants own with disagreeing types is collected before the walks, once, as vanilla's raw-token answer (BUG-84) |
| "which flags do several variants own with disagreeing types?" | `cli/_collect._disagreeing_owner_flags` — vanilla's per-variant resolution, the common type when every owner agrees and `str` when they do not |
| reconciling a registered `cli_prefix` with one passed to `merge_*` | `cli._prefix.resolve_prefix` |
| "does this argv flag occurrence carry an item?" | `cli._argv._bare_occurrence` |
| "which argv tokens does a host framework parse?" | `cli._argv.drop_bare_occurrences` |
| "does this field's flag consume many tokens, and so stand bare?" | `cli._build._takes_multi_tokens` |
| "which flags did the framework never see, and what did they mean?" | `cli._argv.bare_only_flag_names` (which) / `cli._collect._bare_multi_token_flags` (what) |
| "which bare occurrence is a missing value, refused before the framework parses?" | `cli._argv.refuse_bare_occurrences`, off `FlagSpec.refuses_bare` — set by the same `_fixed_seq_types(resolved)` gate that arms the fixed-arity guard |
| plain vs escaped callable directives | `_callable.active_directives` |
| single-value (scalar/type-ref) construction | `_construct._construct_scalar` |
| "which `__init__` parameters are `*args` / `**kwargs`?" | `_types._var_params` |
| combine existing value with override | `_merge._merge_existing_value` |
| how a leaf value leaves the library | `_serialize._serialize_leaf` |
| "which union variant does this instance belong to?" | `_serialize._variant_holds` |
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

An adapter's merged dict is byte-identical to `confarg.merge()`'s for the same input; new
collection logic goes into `cli/_collect.py` mirroring the vanilla decision
([CLI adapters](cli-adapters/parity.md#byte-identical-merged-dicts)).

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
  append flag. A bare occurrence of such a flag never reaches the framework's parse result, so
  marking anything else needs a reader for what the dropped token meant — or the information
  is gone ([CLI adapters](cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare)).
- `FlagSpec.refuses_bare` is set by the same `_fixed_seq_types(resolved)` gate that arms
  `cli/_collect._require_fixed_arity`, asked without unwrapping `Optional`, so the pre-parse
  refusal and the collector's guard cannot disagree about which flags are fixed-arity
  ([CLI adapters](cli-adapters/whole-value-flags.md#whole-value-flags)).
- `import_tagged_classes` runs before anything reads `__subclasses__()` — before the static
  type walk in `build_static_flags`, and before path resolution in `_parse_cli`
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
