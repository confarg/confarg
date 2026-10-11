# Invariants

Rules that must hold after every change. Each links to the document that argues it.

## Contracts

* The configuration object that is returned must respect the field annotations provided as input.

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
([design decisions](design-decisions/mount-keyword-per-channel.md#the-mount-keyword-is-spelled-per-channel)); a `--help` ahead of a refused bare flag, which shows help on argparse and cyclopts and which only the two clicklike front-ends answer with their own usage error — their parser refuses a missing value before any eager flag runs
([CLI adapters](cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare)); a single-dash token after a value-taking flag, a value on vanilla, click and typer, which argparse and cyclopts read by their own option-like rule and refuse — `--key=-x` is the spelling all five take ([design decisions](design-decisions/equals-escapes-a-dashed-value.md#a-single-dash-value-is-the-backends-to-read)). Known unapproved gaps
are listed in [../todo/bugs/](../todo/bugs/README.md).

## Delegate to the canonical function

When two paths need the same decision, route both through one function instead of adding a
special case; apply a rule wherever its precondition holds. Canonical decision-makers:

| Decision | Function |
|---|---|
| merge order, file loading, locals checks | `_pipeline._merge_sources` |
| "what lies below the data a target is built from?" | `_default_layer.lay_defaults` — the target's declared defaults, laid in `build()`, `resolve()` and `from_dict()` and never in `merge()`, combined with a patch through `_merge._merge_existing_value`; the class construction will build below a node is the one whose defaults are laid. `drop_untouched` takes out, after resolution, what no source touched ([design decisions](design-decisions/a-field-default-is-the-base-layer.md#a-field-default-is-the-base-layer)) |
| the merge options' defaults, `argv` and `env` included, and "is this keyword a merge option?" | `_defaults._resolve_options` — every `**opts: Unpack[MergeOptions]` front-end resolves through it ([pipeline](pipeline/api-seams.md#one-option-set)) |
| "is this root config file a configuration layer?" | `_files._require_layer` |
| "what is the parsed value of the document here?" | `_files._load_document` |
| reading one document, whatever route mounts it | `_files._load_any` |
| "which parser does this location name?" | `_files._loader_for` |
| reading a channel value as an include value | `_files._parse_mount_value` |
| mounting a channel value at a subpath | `_files._load_mount` — `--config.<path>` and the env pointers; `__include__` reaches the same outcome through `_files._resolve_dict` |
| "which prefix anchors this document's bare references?" | `_files._load_any`'s *mount* — the whole path from the configuration root, a tuple of segments, applied once by `_files._resolve_node` to the document's own nodes and never to what an include brought in (BUG-127, [expressions](expressions/reference-anchoring.md#a-document-is-prefixed-once-by-its-whole-mount-path)) |
| "which scheme does this location name?" | `_sources._scheme_of` |
| "what are this location's bytes?" | `_sources._read_bytes` |
| "which format does this location name?" | `_sources._suffix` |
| "what location does this relative include name?" | `_sources._join` |
| "are these two locations the same document?" | `_sources._identity` |
| "would resolution rewrite this value?" | `dictexpr.contains_expression` |
| "how is a string spelled so that resolution gives it back unchanged?" | `dictexpr.escape_expressions` — one more `$` before every `${...}` and every escape; the default layer lays a default string with it ([design decisions](design-decisions/a-field-default-is-the-base-layer.md#a-default-string-stays-text)) |
| "where does each `${...}` of this string begin and end?" | `dictexpr._expressions._find_expressions` ([expressions](expressions/values-and-references.md#delimiting-an-expression)) |
| "how is a string rebuilt from its expression spans?" | `dictexpr._expressions._rewrite_spans` — the one accumulate loop over the spans; resolution's interpolation (`_resolve_single`) and the reference rewriters' map (`_map_expressions`) each pass the replacement as a `Callable[[_ExpressionSpan], str]`, escape handling included, and `escape_expressions` answers one more `$` per span (REF-54, [design decisions](design-decisions/look-alike-code-that-behaves-differently-stays-apart.md#look-alike-code-that-behaves-differently-stays-apart)) |
| "which expression reads this path?" | `dictexpr._expressions._path_to_ast` — a dot only where the segment parses back as a name (`_spells_as_name`), a constant subscript elsewhere, a first segment that is no name off `::`; `_Prefixer` and `_AnchorResolver` both spell a path with it (BUG-127, [expressions](expressions/values-and-references.md#spelling-a-path)) |
| "does Python read this name as written?" | `dictexpr._expressions._reads_as_written` — NFKC-stable (PEP 3131). `_parse_expression` refuses a body writing any other name, as one that does not parse (`_refuse_normalized_names`), and `_path_to_ast` never spells a segment as one (`_spells_as_name`), so `${ﬁle}` never reads `file` (BUG-132, [expressions](expressions/values-and-references.md#spelling-a-path)) |
| "which config path does this node read?" | `dictexpr._expressions._attribute_chain` — a dot and a constant subscript each spell one segment, which `_segment` reads off one link; reference collection (`_collect_names`, a method's receiver) asks it of the syntax alone, evaluation (`_eval_path_or`, the one evaluator of an attribute and of a subscript) with its namespace, so a computed key spells the segment its value does (BUG-121, BUG-128, [expressions](expressions/values-and-references.md#spelling-a-path)) |
| "which segment does this subscript key spell?" | `dictexpr._expressions._key_segment` — a string the key, an integer the list index, anything else none; asked of a constant key (`_subscript_segment`) and of an evaluated one (`_segment` with a namespace), so `${svc[k]}` reads and misses as `${svc['web']}` does (BUG-128, [expressions](expressions/values-and-references.md#spelling-a-path)) |
| "what does a dot or a subscript read when no path answers it?" | `dictexpr._expressions._eval_path_or` — the evaluated base indexed by the key the node spells, a dot's name as a string key; never `getattr`, so no attribute of a value, bound methods included, is reachable (BUG-125, [expressions](expressions/safety-model.md#a-dot-reads-a-key-never-an-attribute)). Its miss is the path's own; with no path to name, the key or index it looked for (`_ValueMissError`, BUG-134, [expressions](expressions/values-and-references.md#spelling-a-path)) |
| "how does an expression's runtime failure read?" | `dictexpr._expressions._eval_expr` — an `ExpressionEvalError` quoting the expression as written, then Python's own text; the evaluators let Python's exception through rather than wrap it, and `MissingReferenceError` passes unchanged (BUG-135, [expressions](expressions/resolution.md#an-evaluation-failure-names-its-expression)) |
| "how does an expression's refusal read?" | the validation loop in `dictexpr._expressions.resolve_expressions` and `_eval_expr` (a method off a value that is no string) — each quotes the `${...}` it refused around the reason a private `_RefusedError` carries; every other refusal site raises that bare reason, and `exceptions._in_expression` spells refusal and runtime failure alike (BUG-143, [expressions](expressions/resolution.md#a-refusal-names-its-expression)) |
| "which expressions must resolve before this one?" | `dictexpr._expressions._dependency_graph` — every expression a reference's path reaches: at it, below it, or above it, so a reference to an ancestor from inside it is a cycle (BUG-123, [expressions](expressions/resolution.md#a-reference-reads-everything-its-path-reaches)) |
| "does this path segment spell a list index?" | `dictexpr._expressions._list_index` — only what `str()` of an integer writes (`0`, `1`, `-1`), never `+1`, `01`, `1_0` or `-0`; `_step` reads a list element with it and `_segment_link` writes an index as the integer subscript with it (BUG-133, [expressions](expressions/values-and-references.md#spelling-a-path)) |
| "which node does this path segment reach, and how does the scan name it?" | `dictexpr._expressions._step` — the one walk over the data: evaluation reads a value with it (`_get_nested`), the write-back reaches an expression's container with it (`_set_nested_by_path`) and the graph names a reference with it (`_scan_path`), so `xs[-1]` depends on the element it reads (BUG-123). On a list it reads only a segment `_list_index` spells as an index (BUG-133). A position is a tuple of segments throughout, never a dotted string, so a key holding a dot is one segment (BUG-124, [expressions](expressions/values-and-references.md#a-position-is-a-sequence-of-segments)) |
| "does this dot run climb above the root, and what does it stand for?" | `dictexpr._expressions._anchor_prefix` — resolution (`_AnchorResolver`) and the file loader's clamp (`check_anchor_depth`) both ask it, of a position held as segments (BUG-124, [expressions](expressions/reference-anchoring.md#dots-are-clamped-at-the-file-root)) |
| "at which offset of this body does a token begin and end?" | `dictexpr._expressions._significant_tokens` — rows counted over the very lines the tokenizer read, each ending at a `\n` and only there, never `str.splitlines`; `_anchor_markers` finds a marker with it, so `_name_anchor` and `_strip_anchor` edit where it is (BUG-139, [expressions](expressions/reference-anchoring.md#implementation-constraints)) |
| "does a name follow this anchor marker?" | `dictexpr._expressions._anchor_markers` — the stand-in owns a dot only before a name (`_name_anchor`: `.host` → `__UP1__.host`, `.[0]` → `__UP1__[0]`), and only before a name does `canonicalize_references` drop a `::` (`_strip_anchor`), so `${::['web-1']}` keeps it (BUG-126, [expressions](expressions/reference-anchoring.md#implementation-constraints)) |
| "where does an anchor marker become a name that parses?" | `dictexpr._expressions._parse_expression` — the one parse cache names a body's markers (`_name_anchor`) as it parses it; every other step of resolution carries the body as written, so a message quotes `.x`, never `__UP1__.x` (BUG-129, [expressions](expressions/reference-anchoring.md#implementation-constraints)). Mounting a file parses through it too (`_prefix_content`), so the two agree on which bodies parse, and one that does not is left as written for validation to refuse (BUG-130) |
| "does this body parse?" | `dictexpr._expressions._parse_expression` — a `SyntaxError` for every body that does not, including a name Python would normalize (BUG-132) and a body too deeply nested for Python's parser, whose `RecursionError` or `MemoryError` `_parse_body` reports as `_TooDeepError`; reference extraction skips it, mounting leaves it as written, validation refuses it quoting it (BUG-137, [expressions](expressions/resolution.md#resolution-algorithm)) |
| "how does a message, or a mounted file, spell a node of an expression?" | `dictexpr._expressions._unparse` — each stand-in as its marker, and each path `_AnchorResolver` resolved as the node it replaced (`_resolved`), so the uncalled-method hint off `${.n.upper}` is `.n.upper(...)` wherever the node sits; a field is still named by its absolute path (BUG-136). Mounting writes a prefixed body with it too (`_prefix_content`), and it puts back the parentheses a root marker needs inside a `[`, `items[(::step)]`, which `ast.unparse` drops (BUG-138, [expressions](expressions/reference-anchoring.md#implementation-constraints)) |
| "is this name an anchor stand-in, and how far does it climb?" | `dictexpr._expressions._anchor_dot_count` — true only of a `_StandIn` id, which `_parse_expression` gives each stand-in it parses and `_path_to_ast` the root it hangs a key off; never of a spelling, so a written `${__ROOT__}` or a root key `..` reads a key (BUG-131, [expressions](expressions/reference-anchoring.md#implementation-constraints)) |
| "is this name a function or a config key?" | `dictexpr._expressions._function_name` — a function only as a call's callee, a key everywhere else; validation, evaluation, `_collect_names` and `_Prefixer` all ask it (BUG-120, [expressions](expressions/safety-model.md#a-function-is-named-only-by-a-call)) |
| "what key is this position filed under?" | `dictexpr._expressions._eval_key`, the evaluator of `${key(p)}` — a dict key, or a list element's position as `_step` names it; the argument is a path, never read, so it is no dependency (`_collect_names_from_call`), and the configuration root and an item a pending list op holds have none ([expressions](expressions/safety-model.md#a-path-function-reads-a-position-not-a-value)) |
| "is this call a method call, and which?" | `dictexpr._expressions._method_name` — a callee that is an attribute; validation checks its name against `_SAFE_METHODS`, evaluation (`_eval_method`) its receiver is a `str`, `_collect_names` depends on the receiver, never on the callee's path (BUG-122, [expressions](expressions/safety-model.md#a-method-is-a-string-method)) |
| "which node does a dotted path from the root start at?" | `_parse_cli._walk_target` — the target with the locals graft beside it, or the graft alone on a non-struct root, which is set whole from `__root__`; vanilla's loop, the adapters' patch-flag registration, the host-mode skip, the mount check and every environment variable all resolve against it, so no flag, mount or variable reaches below such a root (BUG-172, BUG-115, [CLI parsing](cli-parsing/cli-prefix.md#a-non-struct-root-is-set-whole)) |
| "does this segment name a real member?" | `_parse_cli._segment_names_real_field` |
| "does this segment name an element of a list, set or variadic tuple?" | `dictexpr._expressions._list_index`, asked by the walk's `_advance_field_type` — an index only as `str()` writes it, so no segment reaches the merge as one of its list-patch keys (BUG-170, [CLI parsing](cli-parsing/collection-patches.md#a-segment-below-a-sequence-is-an-index)) |
| "does a sequence refuse this path, whatever a dict above it takes?" | `_parse_cli._refuses_at_a_sequence`, per branch of the walk — `_is_dict_at_path` takes no such branch as a dict key, and the environment refuses its variable at parse through `_sequence_refusal` (BUG-170) |
| "does a real field own the union tag's spelling?" | `_types._union_tag_shadowed` |
| "what exact spelling does an env segment resolve to?" | `_parse_env._env_spelling` — a member case-insensitively, among the `_parse_cli._member_names` of every type `_parse_cli._field_types` reaches at the spelled prefix from `_walk_target`, then the union tag by its own spelling, lowercase otherwise. The spelling is the env channel's only rule: the spelled path is typed by `_parse_cli._resolve_field_type`, as a flag's is (REF-73) |
| "which type does each union branch reach at this path?" | `_parse_cli._walk_path` — the one type walk, forking at a union and yielding whole branches; `_field_types` reads their ends and `_resolve_field_type` folds them (`_common_type`: the common type, `str` when the branches disagree), and `_addresses_callable_key`, `_is_collection_patch_path`, `_is_dict_at_path` and `cli._build._collect_leaf_tag_argv_specs` read the stones they stood on (REF-43, [CLI parsing](cli-parsing/type-guided-parsing.md#one-walk-many-questions)) |
| "which names does this node declare?" | `_parse_cli._member_names` — a struct's `_types._struct_member_names` (the listing view of `_struct_member_type`, subclass-only names included), a namedtuple's fields, either across a union's variants |
| "does this mount subpath name a node of the target?" | `_parse_cli._check_mount_subpath` |
| "does a registration walk enter this node?" | `cli._build._Descent.into` — not a struct or namedtuple already on the path, unless argv types a flag below it; the flag walk and the mount-point listing both ask it, so a type that holds itself registers its node once and its deeper flags when typed (BUG-224, [design decisions](design-decisions/a-node-already-on-the-path-is-not-entered.md#a-node-already-on-the-path-is-not-entered)) |
| "which mount points does `--help` list?" | `cli._build._collect_subconfig_specs` — every node holding a fragment at any depth, named by `_parse_cli._member_names` and typed by `_parse_cli._field_types` against the `_walk_target` the mount check resolves against, so registration lists no mount point the parse refuses (BUG-88, [design decisions](design-decisions/every-mount-point-has-a-help-entry.md#every-mount-point-has-a-help-entry)) |
| "is this a cast, and which?" | `_parse_cli.detect_force_cast` (whether) / `_cast` (what) |
| "does this field's type hold this cast's type?" | `_cast.holds_the_cast` — a leaf holds its own type, a union its variants, `Any` everything; `detect_force_cast` asks it of each branch the walk reaches at the field (`_field_types`), never of their fold, so vanilla's parse and the adapters' registration refuse the same spellings and a file's pin and a flag admit the same casts below a union of structs (BUG-214), and `construct()` asks it of a pin, so a file's `__cast__` and a hand-built merge's stored pin are refused alike (BUG-210, [design decisions](design-decisions/a-cast-names-a-type-the-field-holds.md#a-cast-names-a-type-the-field-holds)) |
| "which type does a file's `__cast__` name, and which name does a pinned type dump as?" | `_cast.type_for_cast_name` / `_cast.cast_name_for_type` — the two directions of one vocabulary, side by side ([types](types/stealing-rule.md#cast-pinning-in-files)) |
| "how do the objects a root `json` cast decoded meet the fields?" | `_cast.fold_root_json` — vanilla's `--json`, the adapters' `apply_root_json` and the environment's `<PREFIX>JSON` (REF-44); the fields fold in through `_merge._merge_within_source`, so a field's delete still deletes in the layers below (BUG-186, [pipeline](pipeline/deep-merge.md#a-delete-within-one-source-deletes-below-it-too)) |
| "how do two parts of one source merge?" | `_merge._merge_within_source` — `_deep_merge`, with every key delete of the override kept for the layers below, spent (`_SPENT_DELETE`) where it met a key, so `_drop_deleted_bases` drops it if no layer below did (BUG-186, [pipeline](pipeline/deep-merge.md#a-delete-within-one-source-deletes-below-it-too)) |
| "does this token address a reserved name?" | `_parse_cli._addresses_key` |
| "is this argv token a flag, or a value?" | `_parse_cli._looks_like_flag` |
| "does this flag have its value here?" | `_parse_cli._require_value` |
| "how does a fixed-arity flag's missing value spell its positions?" | `_parse_cli._fixed_arity_usage` — one `<value>` per position of a `tuple[X, Y]`, a namedtuple's field names (`<x> <y>`); vanilla's `_consume_fixed_tuple_args` passes it to `_require_value`, and `cli._build._refusing_bare` sets it as `FlagSpec.usage` for the pre-parse refusal (BUG-171, [CLI parsing](cli-parsing/token-consumption.md#token-consumption)) |
| "what does an op recorded at or below a node do with what it finds there?" | `_merge._open_for_ops` — a plain list becomes the `__base__`, a whole-field delete's sentinel the `__base__` `DICT_DELETE` that cuts the ops off from every lower layer, any other non-dict (a scalar) is replaced; the one descent `_descend_creating`, which `_set_nested` and `_accumulate_list_delete` share and which enters an appended item at a negative index, opens each node with it, and so do the CLI's append, a file's `key+:`, and `_merge._written_over` for a dict value written over a delete on any channel (BUG-77, BUG-116, [pipeline](pipeline/deep-merge.md#an-op-after-a-whole-field-delete-has-nothing-below-it)) |
| "in which order are the environment's variables written?" | `_parse_env._env_order` — by the depth of the path each writes, then delete, cast, plain value at one path, so a deeper variable refines a broader one whatever the mapping's order, as its flag typed after the broader flag does (BUG-116, [environment parsing](environment-parsing.md#the-broader-variable-applies-first)) |
| "does this patch over a list need the type to apply?" | `_merge._patch_needs_the_type` — a key that is no integer, or an index outside the base, in a patch with no append or delete: deferred to `build()` as `{__base__: base, **patch}` ([pipeline](pipeline/merge-build-contract.md#merge-build-contract)) |
| "how does a missing field's error read, and which flag does it offer?" | `exceptions.MissingFieldError.__str__` — the field by its construction path (`items[0].size`), the remedy by the flag the CLI accepts for it, each segment of the path one dotted segment (`--items.0.size`, and `--d.x[0].size` for the key `x[0]`), spelled when shown so that `_api._build_for_cli` can first set the `cli_prefix` `load()` and the adapters' `from_*` resolved (`--app.items.0.size`); a field inside a non-struct target's value, which `build()` marks, the root cast that sets the whole value (`--app.json <json>`); every missing field, and a scalar target nothing supplied, raises it (BUG-165, BUG-168, BUG-169, BUG-172, BUG-184, [types](types/construction.md#a-missing-fields-remedy-is-spelled-as-the-cli-spells-it)) |
| "how does a message name a construction path?" | `exceptions._spell_field_path` — each key after a dot, each index in brackets, off the path held as a tuple of segments; construction, the callable specs and `dump()`'s diagnostics thread the tuple and spell it only for a message, so a key spelled like an index stays one segment and a field below a dict target has no leading dot (BUG-169, [types](types/construction.md#a-construction-path-is-a-sequence-of-segments)) |
| "could this value select a union's `None` as a none word, and so be told how to?" | `typedload._construct._reads_none_word` — only a token, for a union counting `None`; the single-variant union, the scalar variants' ranking and the multi-variant refusal all ask it, so a file's `"none"` is never offered the remedy it just failed (BUG-159, BUG-162, [types](types/construction.md#an-optional-field-fails-as-its-variant)) |
| "does this value select a union's `None`?" | `typedload._construct._selects_none` — a token `_reads_none_word` admits, spelling a none word; construction selects `None` with it, and the CLI's `_parse_cli._union_seq_value` stores a lone run bare when it answers yes, so `--xs none` nulls a `list[int] \| None` as `APP_XS=none` does (BUG-163, [design decisions](design-decisions/a-lone-none-word-nulls-an-optional-sequence.md#a-lone-none-word-nulls-an-optional-sequence)) |
| "how does a patch meet a namedtuple's positional base?" | `typedload._construct._lay_patch_over_positions` — the `__base__` list keyed by field name, an all-index patch by position, a name patch by name, each value refined through `_merge._merge_existing_value`; the CLI's arity flag, the env and the files all reach it through the one `__base__` shape (BUG-160, [design decisions](design-decisions/namedtuple-arity-flag-argv-order.md#build-reconciles-the-positions-with-the-patch)) |
| "which flags does this field register?" | `cli/_build._specs_for_field` — a struct's field, and a namedtuple's at each of its name and index spellings, with the help `_spec._build_help` writes for it (BUG-68, BUG-112, [CLI adapters](cli-adapters/whole-value-flags.md#whole-value-flags)) |
| "does a scalar cast land on a plain leaf field (registration)?" | `cli/_build._scalar_cast_parent_is_leaf` |
| reserved-name shadowing | `_parse_cli._check_reserved_key_conflict` |
| locals namespace names | `_parse_cli._locals_keys_at` |
| "is this path a collection patch?" | `_parse_cli._is_collection_patch_path` |
| "does a `+` append here, and what are its items coerced by?" | `_parse_cli._append_element_type` — asked of each branch the walk reaches at the flag's path, a union spread into its variants, never of their fold, so `--xs+` takes every field `--xs.<i>` and a file's `xs+:` take (D4, [CLI parsing](cli-parsing/collection-patches.md#an-append-reaches-every-sequence-variant)) |
| "who writes the adapters' CLI channel and its `--config` files?" | `_parse_cli._parse_cli(..., host_parsed=True)` — vanilla's loop over the argv the framework parsed, skipping only the host's own tokens (REF-72); the parse result is only checked against argv, by `cli/_collect._require_argv_spells` |
| "would vanilla refuse this path as unknown?" | `_parse_cli._path_unknown` — the delete handler, the host-mode skip of a flag whose first segment names no member, and the environment's warning about a variable whose first segment names none (BUG-115) |
| "did the host bind the token after a flag's run to that flag?" | `cli/_build._binds_a_run`, asked by the loop only for a framework that varies a flag's token count (argparse, cyclopts: `binds_runs`); a subkey or element flag registers greedily exactly where it holds, so a one-token type's flag leaves the token after its value a stray (BUG-179, [CLI adapters](cli-adapters/collection-patch-parity.md#collection-patch-parity)) |
| "which flags does argv spell?" | `cli._argv.spelled_flag_names` |
| "does the static walk leave this path's flag to be registered when typed?" | `_parse_cli._registered_when_typed` — a collection patch, or a tag the walk reaches by its fallback, whatever the parent (BUG-106) |
| "does this field take a whole `{…}` token?" | `_parse_cli._accepts_object_value` |
| "is the token after this flag decoded as a whole `{…}` value?" | `_parse_cli._takes_whole_value` — a `{`-led token at a field `_accepts_object_value` admits; vanilla's loop, the typed-call openings scan and the adapters' blob scan (`cli._build._blob_document_from_argv`) all ask it, so a value the loop keeps as text opens no call and buys no flag (BUG-216, [CLI adapters](cli-adapters/whole-value-flags.md#whole-value-flags)) |
| "is this a whole-value inline JSON array?" | `_parse_cli._lone_json_array` |
| what a multi-token flag's accumulated tokens hold | `_parse_cli._varlen_value` / `_union_seq_value` |
| "is a bare string here a callable shorthand, and must it be opened?" | `_parse_cli._open_callable_shorthand` |
| the dict form a bare callable string abbreviates | `_callable.promote_bare_spec` |
| "how many positional tokens, of which types?" | `_types._fixed_seq_types` |
| "is this variant sequence-shaped?" | `_types._is_seq_variant` |
| "which index spellings does an n-field namedtuple register and accept?" | `_parse_cli._namedtuple_index_spellings` — the one source for `str(i)` and `str(i - n)`, so no odd form (`-0`, `+N`, `007`) slips through (BUG-97); the walk looks a spelling up in it, and registration lists a field's keys through its per-position view `_namedtuple_position_spellings` |
| "which struct does a class tag name, if any?" | `_tags._tag_named_struct` — the argparse completion pre-extend, and the default layer choosing whose defaults lie below a tagged node |
| "which flat tagged-leaf flags (`--<leaf>.class`, `--<leaf>.<param>`) does argv spell?" | `cli/_build._collect_leaf_tag_argv_specs`, accepting exactly what `_parse_cli._resolve_field_type` accepts |
| "is this segment the union tag, reached by the walk's fallback?" | `_parse_cli._names_tag_by_fallback` — the walk asked with and without its tag rule (`_resolve_field_type(..., tag_fallback=False)`) |
| "does the walk answer this struct member from the subclasses?" | `_types._answered_by_subclasses` — only a name the struct does not declare; a declared field keeps its own annotation however a subclass overrides it. `_types._struct_member_type` composes it with the subclasses' answer, and is what vanilla's `_advance_field_type` asks for a segment's type and the member predicates `_segment_names_real_field` / `_union_tag_shadowed` ask for its existence; registration's subclass recursion asks its path form `_types._base_declares_path` of a flag path (BUG-86) |
| reconciling a registered `cli_prefix` with one passed to `merge_*` | `cli._prefix.resolve_prefix` |
| "how does a flag's help read in its framework?" | `cli._spec.FlagSpec.rendered_help` — the field's own prose as written, then confarg's note escaped by `cli._markup.help_escape` for the format the framework renders (`escape_percent` for argparse); `_spec._build_help` is the one place a field's help is split into the two (BUG-226, [CLI adapters](cli-adapters/framework-specifics.md#help-text-is-format-neutral)) |
| "what describes the group a struct's fields head?" | `cli._spec._struct_doc` — the struct's docstring, none for a dataclass whose `__doc__` is the signature Python wrote for it; the static walk and argparse completion both ask it ([CLI adapters](cli-adapters/framework-specifics.md#help-text-is-format-neutral)) |
| "what flag name does this path take under `cli_prefix`?" | `cli._prefix.in_prefix` — the bare prefix for the empty path (the scalar root, a root union's tag); `apply_prefix`, argparse completion and the root `--config` help all spell it ([CLI adapters](cli-adapters/cli-prefix-boundaries.md#help-names-a-flag-as-typed)) |
| "does this argv flag occurrence carry an item?" | `cli._argv._bare_occurrence` |
| "which argv tokens does a host framework parse?" | `cli._argv.drop_bare_occurrences` |
| "does this field's flag consume many tokens, and so stand bare?" | `cli._build._takes_multi_tokens` |
| "what does this spec look like forced to a single token?" | `cli._spec.FlagSpec.as_single_token` — the one inverse of the shape attributes (`nargs`, `whole_value`, `stands_bare`), asked by `_scalar_root_spec`, so a non-struct root's one-token flag cannot drift from the shape vocabulary it undoes (REF-68, [CLI adapters](cli-adapters/flag-model.md#framework-neutral-flag-model)) |
| "which bare occurrence is a missing value, refused before the framework parses?" | `cli._argv.refuse_bare_occurrences`, off `FlagSpec.refuses_bare` and `FlagSpec.usage` — both set by `cli._build._refusing_bare`, the same `_fixed_seq_types(resolved)` gate that arms the fixed-arity guard |
| "what does a bare occurrence of this flag raise?" | `cli._spec.FlagSpec.bare_refusal` — a config-file spec's `bare_error` (`_missing_config_path_msg`, set by `cli._build._config_file_spec`), or the missing-value error of a spec that `refuses_bare`; argparse's `_RefusingBareAction` and cyclopts' `refuse_bare_occurrences` both raise it, in argv order up to a help flag (BUG-63, [CLI adapters](cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare)) |
| plain vs escaped callable directives | `_callable.active_directives` |
| "does a `call` key open a typed call on a field of this type?" | `typedload._construct._takes_typed_call` — the type half of construction's `_is_typed_call`; the CLI walk asks it of a path through `_parse_cli._opens_target` ([callables](callables.md#call-in-a-typed-field)) |
| "at which paths does this command line open a typed call?" | `_parse_cli._typed_call_openings` — a flag below the `call` key, a key of a whole value, a key of a root `--config` file; vanilla's loop and the adapters' registration both pass it to the walk ([design decisions](design-decisions/a-typed-call-sibling-needs-its-opener-on-the-command-line.md)) |
| "whose arguments may argv spell below a callable spec?" | `cli._build._callable_argument_targets` — nested target specs included; flag registration and argparse's completion both ask it ([callables](callables.md#cli)) |
| "is this dotted path an instance method, and which class owns it?" | `_callable._instance_method_owner` — the class the path names, holding the method as a Python function; auto-binding, `classfn:` and the CLI's discovery of a `classfn` target's flags all ask it ([callables](callables.md#auto-binding)) |
| "which callable does a `bind:` or `call:` target name?" | `_callable._resolve_target` — a dotted path through `_import_target`, or a callable spec of its own ([callables](callables.md#spec-grammar)) |
| "build this named class from these keys" | `typedload._construct.construct_named_class` — exactly the class, never through subclass dispatch; `class:` and a `classfn:` owner both build through it ([design decisions](design-decisions/class-names-the-type-it-builds.md#class-names-the-type-it-builds)) |
| "which parameters does a caller fill one argument each?" | `_callable._fillable_params` — every one but `*args` and `**kwargs`, read off a signature as written, so a function that declares `self` has one; construction and the CLI's argument flags both ask it, registration of the signature `_callable._target_signature` reads, an instance method's receiver bound off (BUG-218, [callables](callables.md#one-coercion-route)) |
| "a class asked to build from no key refused: how does it read?" | `typedload._construct.build_from_nothing` — a defaulted field, the root, a union's tag, a struct field's subclass tag and a `class:` / `classfn:` opener all build through it; nothing supplied reads as `MissingFieldError`, a class a tag or an opener named as `TypeCoercionError.refused_empty_call` (BUG-184, BUG-213, BUG-215, [types](types/construction.md#a-class-built-from-nothing)) |
| single-value (scalar/type-ref) construction | `_construct._construct_scalar` |
| "which `__init__` parameters are `*args` / `**kwargs`?" | `_types._var_params` |
| "what does a plain class's `__init__` declare?" | `_types._init_params` — the one signature walk, cached per class; `_is_plain_class`, `_init_fields`, `_init_defaults`, `_var_params`, `_struct_required` and construction's `*args` call read it (REF-48, [types](types/introspection.md#introspection-is-cached-per-class)) |
| "which of this struct's fields have no default?" | `_types._struct_required` — without building a default, so no `default_factory` runs to answer it |
| "which defaults does this struct declare as values?" | `_types._struct_declared_defaults` — a dataclass field's `default`, never its `default_factory`, and a plain class's `__init__` defaults; read, never built, never cached |
| "which base list does this patch carry?" | `_merge._replace_base` — for the merge and for construction alike, refusing a value that is no list rather than reading it with `list()` (BUG-170) |
| "which indices does this delete op remove?" | `_merge._delete_indices` — the one reader of `__delete__` and `__delete_after__`, in `_apply_list_ops` and where two layers' deletes combine, refusing a value that is no list of integers rather than iterating it (BUG-175) |
| "is this key a list op, and how does a file spell it?" | `_merge.MERGE_OP_KEYS` — each op's `confarg.ListOp` member by the reserved key a file writes it with; only `_merge._normalize_merge_ops` turns a key into a marker, and `_serialize._serialize_untyped` writes one back as its key, so no channel's own key is read as an op (FEAT-3, [pipeline](pipeline/deep-merge.md#no-channel-types-an-op)) |
| "may a flag, a variable or a mount point write this key?" | `_parse_cli._reserved_segment` — never one of `_defaults.RESERVED_KEYS`, which only a file writes; vanilla's loop, the environment (`_parse_env._refuse_reserved_key`) and the mount check (`_check_mount_subpath`) all ask it (FEAT-3, [config files](config-files/reserved-keys.md#reserved-file-only-keys)) |
| combine existing value with override | `_merge._merge_existing_value` — in the merge, in the default layer combining a field default with the patch over it, and in `build()` wherever a deferred `__base__` meets its patch: a fixed tuple (`_construct_tuple`) and a namedtuple (`_lay_patch_over_positions`) refine each position through it, so deferring a patch never turns a refinement into a replacement (BUG-164, [pipeline](pipeline/merge-build-contract.md#merge-build-contract)). It also lets an override carrying a `__base__` replace a dict below it; a dict's own key `*` is no marker and merges as any other (BUG-185, BUG-199, [design decisions](design-decisions/namedtuple-arity-flag-argv-order.md#a-base-list-carried-with-its-patch-replaces-what-lay-below)) |
| how a leaf value leaves the library | `_serialize._serialize_leaf` |
| "which union variant does this instance belong to?" | `_serialize._variant_holds` |
| "which shape does this type dispatch as?" | `typedload._coerce._type_kind` — the one ordered table of shape predicates (`_KIND_ORDER`); construction, serialization, `_variant_holds` and the CLI walk's `_advance_field_type` each `match` on it, and `_is_collection_patch_path` asks it a narrower question (`_COLLECTION_KINDS`, REF-47, REF-86) |
| "does this serialized value read back as itself?" | `_serialize._reads_back` |
| the `{__cast__, __value__}` spelling | `_serialize._cast_dict` |
| "which leaf variant steals a token?" | `typedload._coerce._steal_rank` |
| "does this type get taken apart into fields?" | `typedload._coerce._is_struct_variant` |
| "may an explicit class tag still open this leaf?" | `typedload._coerce._is_taggable_leaf` |
| "is this leaf type eager-coerced from a token?" | `typedload._coerce._is_eagerly_coercible` |
| "what dotted path names this object?" | `_import.dotted_name` |
| "what type is this value, to a reader?" | `_types._src_type` |
| "which type does this annotation stand for, its wrappers aside?" | `_types._resolve_type` — `TypeAliasType`, `Annotated` and `Final` unwrapped in any nesting, a bare `Final` as `Any`; no walk unwraps a wrapper at its own site ([types](types/introspection.md#wrappers-are-transparent)) |
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
- The default layer's untouched defaults are taken out after resolution and before construction (`_default_layer.drop_untouched`): construction alone applies them, as the class's own objects, so none is ever built through `construct()` ([design decisions](design-decisions/a-field-default-is-the-base-layer.md#untouched-defaults-are-taken-out-again)).
- `_cast.type_for_cast_name` imports the leaf registry lazily: `typedload`'s package init
  imports `_construct`, which imports `_cast`, so a module-level import of
  `typedload._coerce` from `_cast` is a cycle
  ([types](types/stealing-rule.md#cast-pinning-in-files)).
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
- `FlagSpec.refuses_bare` is set by the `_fixed_seq_types(resolved)` gate (`cli._build._refusing_bare`), asked without
  unwrapping `Optional` — the type vanilla's loop dispatches on — so the pre-parse refusal and
  the loop cannot disagree about which flags are fixed-arity
  ([CLI adapters](cli-adapters/whole-value-flags.md#whole-value-flags)).
- `import_tagged_classes` runs before anything reads `__subclasses__()` — before the static
  type walk in `build_static_flags`, before path resolution in `_parse_cli`, and at the start of
  `build_dynamic_flags`, before any argv scan
  ([design decisions](design-decisions/a-named-tag-is-imported-before-registration.md#a-named-tag-is-imported-before-registration)).
- Defaults and shared reserved key names (`ROOT_KEY`, `LOCALS_KEYS`, `RESERVED_KEYS` and the
  file-only keys it lists) live in `_defaults.py`; never repeat the literals
  ([design decisions](design-decisions/shared-reserved-key-names.md#shared-reserved-key-names-live-in-_defaultspy)).
- `exceptions.py` imports nothing from `confarg`. It is the whole of what `dictexpr` is allowed
  to depend on, so an import there would drag the rest of the library into `dictexpr`'s closure.
  A message factory that needs `_src_type` or `dotted_name` therefore cannot have them: either
  the caller passes the text in, or the factory's own argument provably cannot be a token
  ([design decisions](design-decisions/messages-live-on-exceptions.md#a-user-facing-message-lives-on-the-exception-that-raises-it)).
- The per-class introspection caches hold only what is fixed once a class exists, and each answer lives as long as its class (`_types._per_class_cache`). A default (`_dc_defaults`, `_init_defaults`), anything that reads the leaf registry or `__subclasses__()`, and an annotation that did not resolve are never cached, and a cached mapping is read-only ([types](types/introspection.md#introspection-is-cached-per-class)).
- A type in `_LEAF_COERCIONS` must also be in `_LEAF_SERIALIZERS`: registration makes a type
  a leaf in both directions, and only `register_leaf_type` writes them
  ([types](types/leaf-coercion.md#leaf-coercion)).
