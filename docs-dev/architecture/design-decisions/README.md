# Design decisions

One decision per file.
Each entry: the decision, why, and what it costs.
Precedents are cited where known.

A decision lands here when a ticket closes and the answer turns out to be "we will not do that"; when it changes what the library *cannot* do, the boundary goes to [limitations](../limitations.md) instead.

## Shape of the library

| Decision | In one line |
|---|---|
| [No custom types required](no-custom-types-required.md) | plain dataclasses and standard annotations, no base class, decorator or field marker |
| [Plain dicts between stages](plain-dicts-between-stages.md) | no container type of confarg's own between the stages |
| [Merge ops are markers no channel types](merge-ops-are-markers-no-channel-types.md) | a list op is a key no flag, variable or file types; a file writes it, and `dump_file` dumps it, by a reserved name |
| [One merge pipeline for every front-end](one-merge-pipeline.md) | the adapters translate into it; they never re-implement it |
| [Adapters instead of an own CLI framework](adapters-not-a-cli-framework.md) | users keep argparse/click/typer/cyclopts, and need no CLI library at all |
| [Zero runtime dependencies](zero-runtime-dependencies.md) | YAML, TOML writing, completion and the adapters are extras |
| [Adapter argument names keep the framework's noun](adapter-argument-names-keep-the-framework-noun.md) | `populate_*` and `merge_*` name the object the user holds, `ctx` or `app`, not one generic `cli` |

## Parity, and where it has to give

| Decision | In one line |
|---|---|
| [A divergence leans towards the affected backend's own idiom](divergence-leans-to-the-backend.md) | which way to lean when a spelling cannot reach every front-end, and how far it spreads |

## How each channel spells things

| Decision | In one line |
|---|---|
| [The mount keyword is spelled per channel](mount-keyword-per-channel.md) | `--config`, `CONFIG__…` and `__include__` are one operation with three names |
| [Every mount point has a help entry](every-mount-point-has-a-help-entry.md) | `--config.<path>` is listed at every depth the walk reaches, read off the walk that checks a mount |
| [A node already on the path is not entered](a-node-already-on-the-path-is-not-entered.md) | a type that holds itself lists its node once; the deeper flags are registered when argv types them |
| [The `+` suffix is a merge operator, not a list spelling](plus-is-a-merge-operator.md) | appending is confarg's axis, spelled by the same suffix on every channel's path, the environment's variable names included, and in a file's value; how many tokens a value takes is the framework's |
| [union_tag defaults to "class"](union-tag-defaults-to-class.md) | a Python keyword can never collide with a field name |
| [Environment variables off by default](environment-variables-off-by-default.md) | `env_prefix=None`, because the environment is shared with every other process |
| [Double underscore separator](double-underscore-separator.md) | `__` splits nesting so single underscores stay usable in names |
| [Explicit boolean values](explicit-boolean-values.md) | `--verbose true`, not `--verbose`/`--no-verbose` |
| [A lone none word nulls an optional sequence](a-lone-none-word-nulls-an-optional-sequence.md) | `--xs none` is `None` for `list[X] \| None`, as `APP_XS=none` is, whatever `X` |
| [Real field wins over reserved words](real-field-wins.md) | a reserved name is reserved only where it shadows nothing |
| [A decoded value is data](a-decoded-value-is-data.md) | a JSON value on argv or in the environment never spells a merge op, and holds no reserved key; only a file's reserved keys spell ops |
| [A file spells an op in its value](a-file-spells-an-op-in-its-value.md) | a file's op is a reserved key of the value at its path (`xs: {__append__: …}`, `name: {__unset__: true}`), every other key data; argv and the environment keep their suffixes on the path |
| [A fixed-length delete unsets a position](a-fixed-length-delete-unsets-a-position.md) | `--pt.0-` and `--t.0-` unset the position in place, the field default's included, rather than shift what follows: a namedtuple field takes its class default, a tuple's position `None` or a missing field |
| [An argv delete is shaped by the type](an-argv-delete-is-shaped-by-the-type.md) | `--xs.1-` and `--d.1-` share a suffix but not a shape: the walk's type picks an index delete (`__delete__`) or a key delete, so a list keeps its delete-then-patch chains |
| [A field default is the base layer](a-field-default-is-the-base-layer.md) | `build()`, `resolve()` and `from_dict()` lay the declared defaults under the data, so a patch applies over a default and an expression reads one; `merge()` is untouched |
| [A cast names a type the field holds](a-cast-names-a-type-the-field-holds.md) | no channel's cast places a value the field's annotation does not accept, so an unheld cast is refused everywhere alike |
| [A shadowed tag warns on use](a-shadowed-tag-warns-on-use.md) | the structural selection is named where the tag could have dispatched, and nowhere else |
| [Strict CLI, lenient environment](strict-cli-lenient-environment.md) | an unknown flag is an error, an unknown variable a warning |
| [The broader environment variable applies first](the-broader-environment-variable-applies-first.md) | nested variables merge as their flags typed broader first, whatever the mapping's order |

## Where a document comes from

| Decision | In one line |
|---|---|
| [A scheme handler returns bytes](scheme-handler-returns-bytes.md) | decoding is one decision per format, not one per handler — and the registry can be emptied |
| [A remote document reaches only its own origin](remote-document-same-origin.md) | so a config URL is not a local-file-read primitive |

## Expressions

| Decision | In one line |
|---|---|
| [Expressions resolved after merging, by a whitelisted interpreter](expressions-resolved-after-merging.md) | any channel can override an input of a file-defined formula, and nothing calls `eval` |
| [`::` spells the configuration root, a leading dot counts upwards](anchor-spellings.md) | the three anchor spellings, and what was rejected for each |
| [An expression reads a typed leaf as its object](an-expression-reads-a-typed-leaf-as-its-object.md) | `merge()` holds an `Enum` or registered leaf as written on every channel; an expression reads it as its object and leaves its dump form, never `str()` |
| [An entry reads its key with an expression](an-entry-reads-its-key-with-an-expression.md) | `name: ${key(.)}` names an entry after the key it is filed under; the link lives in the configuration, not in the type |

## Types and construction

| Decision | In one line |
|---|---|
| [A class tag replaces, not merges](class-tag-replaces.md) | naming a class says "this is a new object" |
| [A call replaces what lies below](a-call-replaces-what-lies-below.md) | a `call:` is a finished value, so the merge drops what lower layers set at its node, the root included |
| [The type decides whether a value replaces or refines](the-type-decides-replace-or-refine.md) | a tag, an opener or a call replaces what lies below only where the type reads it so; a key the type holds as data refines, and a lower shorthand opens under the arguments above it |
| [No implicit subclass inference](no-implicit-subclass-inference.md) | a subclass exists only once imported, so confarg never scans for one |
| [A call spec yields to data the annotation can hold](call-yields-to-the-data-a-type-holds.md) | `call:` fills any typed field, except where a dict type or a member named `call` holds the key as data |
| [An `Any` node reads every opener](an-any-node-reads-every-opener.md) | `class:`, `classfn:`, `bind:` and `call:` build on an `Any` field at any depth, a bare string stays text; `dump()` writes the spec back when it reads back, untyped with a warning otherwise |
| [Class names a subclass; call computes](class-names-a-subclass-call-computes.md) | `class:` on a typed field names a subclass of it, and an unrelated class is refused; `call:` computes a value the annotation accepts, so it is no way around the refusal |
| [Bind yields a partial of its target](bind-yields-a-partial-of-its-target.md) | `bind:` is an opener whose `args` are its target's arguments; `fn:` and the `bind:` kwargs dict are removed outright, with no migration table |
| [A computation's arguments nest under args](a-computations-arguments-nest-under-args.md) | `bind:` and `call:` hold their arguments under `args`, `class:` and `classfn:` their fields beside them; the escaped openers and the CLI's opener scan are gone |
| [Classfn names an instance method](classfn-names-an-instance-method.md) | `classfn:` fields build the owner the path names; static and class methods need no owner; `call:` takes any callable spec as `bind:` does |
| [Class names the type it builds](class-names-the-type-it-builds.md) | `class:` and a `classfn:` owner are built exactly as named, never through subclass dispatch |
| [Stealing rule for text in unions](stealing-rule-for-text-in-unions.md) | a total, fixed rank; declaration order is only a tie-break |
| [A node types its keys by the class it names](a-node-types-its-keys-by-the-class-it-names.md) | an opener or a tag types the keys below it on every channel, from argv's naming before the key or a lower layer's; registration reads the same layers, and the merge refuses a source it did not |
| [A Callable beside another variant reads its spec](a-callable-beside-another-variant-reads-its-spec.md) | a string in rank below type references, an opener before any variant's data unless a struct owns the key, a `call:` the union's to take |
| [A union ranks every value](a-union-ranks-every-value.md) | a file's value meets the rank a token does; only a token is converted, any value is recognized |
| [Int ranks above float](int-ranks-above-float.md) | a whole number is an `int` and anything else a `float`, in `int \| float` and `float \| int`, from every channel |
| [A float reads an int as its digits](a-float-reads-an-int-as-its-digits.md) | a file's `1` is the `1.0` of `--f 1`; a number too large for a float is `inf` with a `FloatOverflowWarning`, naming the field or the flag that gave it |
| [A Literal member is what PEP 586 allows](a-literal-member-is-what-pep-586-allows.md) | a member a value spells is read, a `bytes` one skipped as an unsupported union branch is, any other refused wherever a value reaches it, its union included; a union's refusal names the branches it skipped |
| [A registration is one construction reaches](a-registration-is-one-construction-reaches.md) | `register_leaf_type` refuses with a `TypeError` a key no value would be coerced through: no class, a `NewType` (read as its supertype everywhere), a built-in leaf, a shape, `object` |
| [A builtin's subclass is that builtin](a-builtins-subclass-is-that-builtin.md) | an `OrderedDict`, a `Counter`, a `dict[str, int]` subclass, an `int` subclass read as the builtin and built through the class; typed as a type checker types it; a `defaultdict`'s factory its value type's class; a dataclass, an `Enum` and a registration read their own way; a bare `collections.abc.Sequence` is a list |
| [A registered leaf is never a struct variant](registered-leaf-is-never-a-struct-variant.md) | registration is a promise that the type is opaque to every implicit decision |
| [The date and time types are built-in leaves](the-date-and-time-types-are-built-in-leaves.md) | `date`, `datetime`, `time`, `timedelta` and `timezone` read ISO 8601 text only, a file's native value as its text; a number is no time and no duration; `native_types` keeps a date native for a writer that holds one |
| [Decimal and UUID are built-in leaves](decimal-and-uuid-are-built-in-leaves.md) | registered as `Path` is, so a type whose text is its value is never a struct of its constructor's parameters; a file's float reads through its `repr`, so every channel's `1.1` is one decimal |
| [A struct's members are its constructor's parameters](a-structs-members-are-its-constructors-parameters.md) | a dataclass is set through its `__init__` as a plain class is: `init=False` is no member, an `InitVar` is one, a class taking nothing is a struct with no fields |
| [An explicit tag opts a leaf back in](an-explicit-tag-opts-a-leaf-back-in.md) | …and the tag is the one thing that may take that promise back |
| [A named tag is imported before registration](a-named-tag-is-imported-before-registration.md) | five readers of `__subclasses__()` agree because the import happens first |
| [A namedtuple is a fixed-length sequence](namedtuple-is-a-fixed-length-sequence.md) | one classification, not three special cases |

## Dumping

| Decision | In one line |
|---|---|
| [The object dump writes state](the-object-dump-writes-state.md) | the merged dict dumps as written, the built object as the state it holds, forensically: a dataclass its stored fields, a plain class its parameters as held |
| [Dump round-trips at the built object](dump-round-trips-at-the-built-object.md) | not at the merged dict: a file's values are never re-interpreted |
| [A stolen leaf dumps with its cast](a-stolen-leaf-dumps-with-its-cast.md) | `{__cast__, __value__}` exactly where the bare scalar would be taken back |
| [Registered leaf types dump through a registered serializer](registered-leaf-serializer.md) | registration is two directions; `str` is only the default for the second |
| [Dumped files carry raw UTF-8](dumped-files-carry-raw-utf-8.md) | non-ASCII text is written as it stands, escaped nowhere — what the TOML writer always did |
| [A written file holds what its reader reads back](a-written-file-holds-what-its-reader-reads-back.md) | `dump_file` refuses, naming the path and before opening the file, a value its format does not hold; a TOML or JSON key that is no string is written as the text the merge meets it by |

## CLI front-ends

| Decision | In one line |
|---|---|
| [cli_prefix is given at registration and recovered at merge](cli-prefix-at-registration.md) | `populate_*` owns flag naming, so it owns the prefix |
| [The `=` form is the escape for a dashed value](equals-escapes-a-dashed-value.md) | `--key=--value`, because shape alone cannot decide; a single-dash value is each backend's to read |
| [allow_abbrev disabled](allow-abbrev-disabled.md) | adding a field must not silently change what an abbreviation means |
| [Optionality does not change what a whole value accepts](optionality-and-whole-values.md) | `\| None` says what a field may be unset to, not what its syntax is |
| [A whole-value flag needs its value](a-whole-value-flag-needs-its-value.md) | `--db` with nothing after it is an error, like `--port` with nothing after it |
| [A namedtuple's arity flag and its sub-flags merge in argv order](namedtuple-arity-flag-argv-order.md) | latest arguments overwrite earlier ones, per path |
| [A whole value followed by a subkey opens rather than collides](whole-value-then-subkey.md) | the scalar is opened into whatever it means to its field, then refined |
| [An op after a whole-field delete applies to nothing below](an-op-after-a-whole-field-delete-applies-to-nothing-below.md) | `--users- --users.0-` fails as with no file; the delete is never silently lost |
| [Index spellings are hidden from help](index-spellings-are-hidden-from-help.md) | patch syntax is accepted, not advertised |

## Internals

| Decision | In one line |
|---|---|
| [Shared reserved key names live in `_defaults.py`](shared-reserved-key-names.md) | any literal the five front-ends must agree on, not only the keyword defaults |
| [A user-facing message lives on the exception that raises it](messages-live-on-exceptions.md) | a message raised from more than one site is a classmethod factory |
| [Look-alike code that behaves differently stays apart](look-alike-code-that-behaves-differently-stays-apart.md) | a collapse that has to take every difference as a parameter is declined; the scalar coercions and the two anchor rewrites stay as written |

## Repository

| Decision | In one line |
|---|---|
| [Line endings are pinned in `.gitattributes`](line-endings-pinned-in-gitattributes.md) | LF for text, `-text` for the PNGs — and the pre-commit hook stays the enforcement, because jj ignores attributes |
| [A lint rule is enabled, not hand-fixed](lint-holds-the-line.md) | banning a pattern is a config edit; `FURB118` and `PLW0717` stay selected, wholesale best-effort blocks carry a `noqa` |
| [Quoted code keeps the formatter's spacing](quoted-code-keeps-formatter-spacing.md) | one blank line between blocks in prose, the formatter's spacing inside a fenced code block |
| [Some quoted blocks stay hand-copied](quoted-blocks-stay-hand-copied.md) | a bare expression, a staged variant, a run-time-written file: no honest source to quote, so the drift risk is accepted |
| [A ticket's fields live in YAML front matter](ticket-fields-in-front-matter.md) | bare values a script reads, qualifiers in comments; `where` is checked against the tree, `blocked_by` against the open tickets |
| [A ticket carries a severity; its priority is derived](ticket-severity-and-work-order.md) | four rungs anchored to what a user meets; `index.py` orders work by severity inherited through `blocked_by`, then effort |
| [A bug ticket names the revision that introduced it](ticket-origin.md) | `introduced_by` and an `Origin:` paragraph, so a fix can go to the cause; the fixing revision keeps it as a trailer |
| [Plans live under `todo/`](plans-live-under-todo.md) | beside the boards that cite them, not as a third top-level folder of `docs-dev/` |
| [The board and anchor checks run as always-on pre-commit hooks](board-and-anchor-checks-run-in-pre-commit.md) | `ticket-boards` and `architecture-anchors` fail the commit, not a CI run nobody watches |
| [The ruff hook and the dev dependency carry one pin](one-ruff-pin.md) | ruff sits in the dev group pinned `==` to the hook's rev, so `uv run ruff` and the hook give one answer |
