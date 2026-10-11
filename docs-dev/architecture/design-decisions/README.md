# Design decisions

One decision per file. Each entry: the decision, why, and what it costs. Precedents are cited
where known.

A decision lands here when a ticket closes and the answer turns out to be "we will not do
that"; when it changes what the library *cannot* do, the boundary goes to
[limitations](../limitations.md) instead.

## Shape of the library

| Decision | In one line |
|---|---|
| [No custom types required](no-custom-types-required.md) | plain dataclasses and standard annotations, no base class, decorator or field marker |
| [Plain dicts between stages](plain-dicts-between-stages.md) | no container type of confarg's own between the stages |
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
| [The `+` suffix is a merge operator, not a list spelling](plus-is-a-merge-operator.md) | appending is confarg's axis; how many tokens a value takes is the framework's |
| [union_tag defaults to "class"](union-tag-defaults-to-class.md) | a Python keyword can never collide with a field name |
| [Environment variables off by default](environment-variables-off-by-default.md) | `env_prefix=None`, because the environment is shared with every other process |
| [Double underscore separator](double-underscore-separator.md) | `__` splits nesting so single underscores stay usable in names |
| [Explicit boolean values](explicit-boolean-values.md) | `--verbose true`, not `--verbose`/`--no-verbose` |
| [A lone none word nulls an optional sequence](a-lone-none-word-nulls-an-optional-sequence.md) | `--xs none` is `None` for `list[X] \| None`, as `APP_XS=none` is, whatever `X` |
| [Real field wins over reserved words](real-field-wins.md) | a reserved name is reserved only where it shadows nothing |
| [A shadowed tag warns on use](a-shadowed-tag-warns-on-use.md) | the structural selection is named where the tag could have dispatched, and nowhere else |
| [Strict CLI, lenient environment](strict-cli-lenient-environment.md) | an unknown flag is an error, an unknown variable a warning |
| [A typed call's sibling needs its opener on the command line](a-typed-call-sibling-needs-its-opener-on-the-command-line.md) | `--n.x` below an `int` is an argument only where argv opens `--n.call`; a typo below an unopened field stays an error |
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

## Types and construction

| Decision | In one line |
|---|---|
| [A class tag replaces, not merges](class-tag-replaces.md) | naming a class says "this is a new object" |
| [No implicit subclass inference](no-implicit-subclass-inference.md) | a subclass exists only once imported, so confarg never scans for one |
| [A call spec yields to data the annotation can hold](call-yields-to-the-data-a-type-holds.md) | `call:` fills any typed field, except where a dict type, `Any` or a member named `call` holds the key as data |
| [Class names a subclass; call computes](class-names-a-subclass-call-computes.md) | `class:` on a typed field names a subclass of it, and an unrelated class is refused with a pointer to `call:` |
| [Bind yields a partial of its target](bind-yields-a-partial-of-its-target.md) | `bind:` is an opener whose siblings are its target's arguments; `fn:` and the `bind:` kwargs dict are removed outright |
| [Classfn names an instance method](classfn-names-an-instance-method.md) | `classfn:` siblings build the owner the path names; static and class methods need no owner; `call:` takes any callable spec as `bind:` does |
| [Class names the type it builds](class-names-the-type-it-builds.md) | `class:` and a `classfn:` owner are built exactly as named, never through subclass dispatch |
| [Stealing rule for text in unions](stealing-rule-for-text-in-unions.md) | a total, fixed rank; declaration order is only a tie-break |
| [A registered leaf is never a struct variant](registered-leaf-is-never-a-struct-variant.md) | registration is a promise that the type is opaque to every implicit decision |
| [An explicit tag opts a leaf back in](an-explicit-tag-opts-a-leaf-back-in.md) | …and the tag is the one thing that may take that promise back |
| [A named tag is imported before registration](a-named-tag-is-imported-before-registration.md) | five readers of `__subclasses__()` agree because the import happens first |
| [A namedtuple is a fixed-length sequence](namedtuple-is-a-fixed-length-sequence.md) | one classification, not three special cases |

## Dumping

| Decision | In one line |
|---|---|
| [Dump round-trips at the built object](dump-round-trips-at-the-built-object.md) | not at the merged dict: a file's values are never re-interpreted |
| [A stolen leaf dumps with its cast](a-stolen-leaf-dumps-with-its-cast.md) | `{__cast__, __value__}` exactly where the bare scalar would be taken back |
| [Registered leaf types dump through a registered serializer](registered-leaf-serializer.md) | registration is two directions; `str` is only the default for the second |

## CLI front-ends

| Decision | In one line |
|---|---|
| [cli_prefix is given at registration and recovered at merge](cli-prefix-at-registration.md) | `populate_*` owns flag naming, so it owns the prefix |
| [The `=` form is the escape for a dashed value](equals-escapes-a-dashed-value.md) | `--key=--value`, because shape alone cannot decide |
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
