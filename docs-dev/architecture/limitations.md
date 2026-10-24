# Limitations

What confarg does **not** do, and why — the boundaries that follow from the design rather than from work nobody has done yet.
A user hitting one of these is not hitting a bug.

Anything open and actionable — defects, parity gaps, refactors, ideas, questions — belongs on the boards in [`../todo/`](../todo/README.md), not here.
When a ticket closes and the answer turns out to be "we will not do that", the reason moves into [design decisions](design-decisions/README.md); when it changes what the library cannot do, the boundary moves here.

## Expressions

- The grammar cannot express collection literals, slices, comprehensions or lambdas.
  The whitelist is the safety model, not an unfinished parser ([expressions](expressions/safety-model.md#safety-model)).
- A computed value is bounded: an `int` to `sys.get_int_max_str_digits()` digits, a `str`, `bytes` or collection to 1 000 000 characters or items, and one resolution to 10 000 000 in total.
  An object no source can produce — a `Fraction` in a caller's data, a registered type — computes with its own operators, unbounded: the application that put it there is trusted ([expressions](expressions/safety-model.md#a-computed-value-is-bounded)).
- A plain `Enum` member equals no text: `${c == 'red'}` is `False` on every channel, since an expression reads the member, and no expression can name the class.
  Compare two fields, or declare a `StrEnum` or an `IntEnum`, which equals its value ([expressions](expressions/values-and-references.md#a-typed-leaf-reads-as-its-object)).
- No attribute of a value is reachable, only keys and indices: `${d.year}` on a YAML date or `${n.real}` on a number is a missing field, and no whitelisted function reads it instead ([expressions](expressions/safety-model.md#a-dot-reads-a-key-never-an-attribute)).
- A malformed expression contributes no dependency edges, and a mounted file's malformed expression takes no prefix: it is not parseable, so nothing can be derived from it.
  The error surfaces at validation instead, with the expression text as written, wherever the file was mounted (BUG-130).
  A body nesting over 100 expression levels, or too deeply for Python's parser, is one of them ([expressions](expressions/resolution.md#resolution-algorithm), BUG-137, BUG-145).
- A document a list op holds (`--config.<path>+`, an include below a file's `__append__`) has its bare references spelled as dot runs in `merge()`, `${name}` as `${.name}`; one at the root of a document that is a single string has no dot run and is refused at load, pointing at `::` ([expressions](expressions/reference-anchoring.md#a-document-a-list-op-holds-is-anchored-by-dot-runs)).
- A list op no type settles as a variable-length sequence, at an `Any` or below a union holding a fixed-length variant beside a list, is applied by construction only, after resolution: an expression reading it is refused rather than reading its list ([expressions](expressions/values-and-references.md#a-pending-list-op-is-read-as-its-list)).
- An expression inside a patch over an expression, which reads the patched node through a data key (`db: {__base__: '${proto}', host: '${.port}'}`), waits for the node it is part of to settle, and is refused as a cycle; read `${proto.port}` instead ([design decisions](design-decisions/a-patch-over-an-expression-patches-its-value.md#how-build-settles-it)).
- A node-relative reference counts *path segments*, and a list index is one: from `dbs.0.url`, `${..host}` names the list rather than the mapping holding it ([expressions](expressions/reference-anchoring.md#reference-anchoring)).
- `${key(.)}` names an entry after its key only where it is written: each entry of a `dict[str, Foo]` writes `name: ${key(.)}` itself.
  A class default cannot carry it, since a default string is text ([design decisions](design-decisions/a-field-default-is-the-base-layer.md#a-default-string-stays-text)), and no declared default reaches every entry of a dict yet ([FEAT-19](../todo/features/FEAT-19-app-declared-defaults.md)).
  An item a list op no type settles holds has no key until construction applies the op ([expressions](expressions/safety-model.md#a-path-function-reads-a-position-not-a-value)).
- A merged dict is no longer uniformly root-anchored: `${.x}` is preserved through `merge()` and `dump_file()` on purpose, so a dumped fragment stays position-independent, and so is `${::['web-1']}`, which no plain path spells ([expressions](expressions/reference-anchoring.md#a-relative-reference-is-never-serialized-as-an-absolute-path)).
- A bare reference in a file mounted under a root key that is no identifier is written `${::['web-1'].p}`, the one spelling of that path.
  Dumped and mounted again under another key, that `::` still names the configuration root, so the dump does not re-anchor the way one holding `${db.p}` does ([expressions](expressions/reference-anchoring.md#a-document-is-prefixed-once-by-its-whole-mount-path)).
- A key Python would normalize as a name (`ﬁle`, `ｘ`) is read only through a subscript, `${svc['ﬁle']}` or `${::['ﬁle']}`: written as a name, `${ﬁle}` or `${svc.ﬁle}`, it is refused ([expressions](expressions/values-and-references.md#spelling-a-path)).
- A non-string key at the document root is not reachable: `${::[0]}` reads the root key `"0"`.
  Below the root the subscript's fallback indexes by the integer, but the root has no node to index ([expressions](expressions/reference-anchoring.md#implementation-constraints)).
- A reference to a whole node substitutes that node's *value*, so each referencing site is constructed separately: two fields referring to one struct hold equal, non-identical objects.
  There is no way to share one instance ([expressions](expressions/values-and-references.md#referencing-a-whole-subtree)).
- In a `resolve()`d dict those paths do alias one sub-dict, so mutating it in place reaches every site that referenced it.
  Inspect and dump the resolved dict; do not edit it.
- An expression may not read a node that holds it, even through a function that would not need its own value: inside `svc`, `${len(svc)}` and `${svc[k]}` are cycles.
  The dependency graph is built from syntax and cannot see what a function reads or which key `k` names ([expressions](expressions/resolution.md#a-reference-reads-everything-its-path-reaches)).

## Collections

- A whole value and a deeper key for the same field resolve last-write-wins, and the loser goes quietly.
  Only a `Callable` field's bare string survives the pair, being the shorthand for `{bind: …}`; at a union like `dict[str, str] | str`, where a scalar is legitimate but abbreviates nothing, `--d oops --d.c x` keeps only the subkey ([design decisions](design-decisions/whole-value-then-subkey.md#a-whole-value-followed-by-a-subkey-opens-rather-than-collides)).
- List deletion and negative indices need a base list to apply to: they are patches, and a patch has nothing to bite on in an empty document.
- A key delete that meets nothing in any layer, the defaults included, deletes nothing and says nothing: a misspelled `--data.kye-` is not refused below a dict, as it is not over a dict that lacks the key, and a delete below a `default_factory` default, which is no base yet, leaves that default whole ([design decisions](design-decisions/a-field-default-is-the-base-layer.md#a-delete-meets-the-defaults-last)).
- Index-keyed lists must be gap-free, unless the element type is Optional — a gap would otherwise have to invent an element of an unknown type.
- Below a sequence, argv and the environment take an index only as `str()` writes one, while a config file's key is read by the merge's `int()`: `--xs.01` is refused and `xs: {"01": 5}` patches index 1.
  A file is not walked against the type ([CLI parsing](cli-parsing/collection-patches.md#a-segment-below-a-sequence-is-an-index)).
- On a node no type describes (an `Any`, a callable's spec, a union whose list and dict variants both take the segment), argv and the environment read a delete of a segment spelling an index as an index delete: `--a.1-` cannot delete the key `1` of an `Any` holding a dict, where a file's `a: {"1": {__unset__: true}}` can ([design decisions](design-decisions/an-argv-delete-is-shaped-by-the-type.md#what-it-costs)).
- The [reserved keys](config-files/reserved-keys.md#reserved-file-only-keys) (`__include__`, `__cast__`, `__value__`, `__root__`, the node delete `__unset__`, and the list ops `__append__`, `__delete__`, `__delete_after__`, `__base__`) are no data key anywhere: a file reads one as its own, and a flag, a variable, a mount point or a JSON value naming one is refused.
  A field or a dict key spelled like one cannot be set, and `dump()` refuses to write such a dict key.
- A configuration file cannot order two ops on one key within one dict: it spells an op in the value, and YAML, TOML and JSON hold a key once, so `{xs: [1], xs+: [2]}` or a delete written after an append has no spelling.
  The ops of one value apply in a fixed order, the node delete first ([design decisions](design-decisions/a-file-spells-an-op-in-its-value.md#what-it-costs)); two files, or argv, order them.
- A file deletes a list's index with `__delete__: [N]` only: a bare `"N": {__unset__: true}` under a list is refused, as a delete is wherever it would delete nothing, a list item and a document root included ([design decisions](design-decisions/a-file-spells-an-op-in-its-value.md#where-a-delete-has-no-meaning)).
- `build()` reads a merged dict, not a file's: the list ops and the node delete a parsed file spells by name apply only once `merge()` has read the file.
  A merged dict saved with `dump_file` is read back through `merge(files=[saved])` ([design decisions](design-decisions/merge-ops-are-markers-no-channel-types.md#merge-ops-are-markers-no-channel-types)).
- A construction error names a dict key that is no plain name ambiguously: the key `a.b` reads as nesting (`d.a.b`) and the key `x[0]` as an index (`d.x[0]`).
  The path is held exactly, as segments, so a missing field's remedy still names the right flag ([types](types/construction.md#a-construction-path-is-a-sequence-of-segments)).

## Field defaults

A field default is the layer below every source only where the class declares it as a value ([design decisions](design-decisions/a-field-default-is-the-base-layer.md#tier-1-defaults-read-without-running-code)):

- A `default_factory` is never called to be laid, so a list, dict or set default is no base: a `list[int]` defaulting to `[0]` with `--xs+ 1` builds `[1]`, and `${xs}` misses (tier 2).
- A struct instance default is not laid, nor its fields: `${sub.a}` misses under `sub: Sub = field(default_factory=Sub)` unless a source names `sub` (tier 3).
- A default of a leaf type confarg has no registration for (`complex`, `ZoneInfo`) is not laid.
- Below a tag that is an expression, a union a structural match decides, or a struct with subclasses and no tag, no default is laid: which class's defaults apply is not known before construction.
- An expression that produces a patch dict replaces the default rather than patching it: the defaults are combined with the data before expressions resolve.

## Casts

- A cast is admitted only where the field's type holds its named type, so it cannot disambiguate a `Literal`'s stealing: `Literal["16", 16]` reads the token `"16"` as `16`, and `--u.str 16` is refused for naming a type the field does not hold — a type-level rule cannot promise the coerced value stays a member ([design decisions](design-decisions/a-cast-names-a-type-the-field-holds.md#a-cast-names-a-type-the-field-holds)).
- A cast names only a scalar or a registered leaf, so a container an `Any` variant holds cannot be pinned: `S | Any` holding the dict `{a: 1}` dumps it bare with a `ConfargWarning`, and it reads back as `S(a=1)` ([stealing rule](types/stealing-rule.md#casting-a-stolen-leaf)).

## CLI front-ends

- A multi-token flag is spelled per framework: space-separated for vanilla/argparse/cyclopts, repeated for click/typer/cyclopts ([CLI adapters](cli-adapters/list-syntax-divergence.md#list-syntax-divergence)).
  The `--<config_flag>` flag is spelled the same way, so its multi-file run declines on click and typer and repetition is the spelling to use there ([CLI parsing](cli-parsing/config-file-flags.md#config-file-flags)).
  Only the spelling diverges: repeating such a flag accumulates in every front-end, and a bare `--<list>` clears the collection in every front-end ([CLI adapters](cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare)).
- There is no end-of-options separator: a bare `--` is an ordinary token everywhere.
  A value that starts with `--` is written `--key=--value`, the form every front-end honors ([design decisions](design-decisions/equals-escapes-a-dashed-value.md#the--form-is-the-escape-for-a-dashed-value)).
  argparse and cyclopts also refuse most values that start with a single dash in the space form (`--host -x`), each by its own option-like rule, so `--host=-x` is the portable spelling there too; a negative number such as `--port -5` works everywhere ([design decisions](design-decisions/equals-escapes-a-dashed-value.md#a-single-dash-value-is-the-backends-to-read)).
- A fixed-arity flag (`tuple[X, Y]`, namedtuple) takes one whole-value token — `--pair '[13, 42]'`, `--pair '{"x": 13}'` — everywhere except click and typer, whose options cannot vary their token count at parse time.
  They keep `--pair 13 42`, which is the spelling a CLI user reaches for, and decline the JSON one ([CLI adapters](cli-adapters/whole-value-flags.md#whole-value-flags)).
  Use a config file, an environment variable or the per-field flags (`--pair.x 13`) to set it whole under those two.
- The adapters read the CLI channel off the `argv` passed to `merge_*` / `from_*`, so it must be the list the framework parsed: `parser.parse_args(custom)` or `CliRunner().invoke(cmd, custom)` needs `argv=custom` too, since the default is `sys.argv[1:]`.
  A confarg flag the parse result holds and that argv does not spell raises `ConfargError`; a mismatch the parse result cannot show (argv spelling *more* than the framework parsed) is read as typed ([CLI adapters](cli-adapters/model.md#argv-is-the-only-writer)).
- The adapters shape nothing in the framework's parse result beyond accepting the flags argv spells: the values it holds are never read, so a host application reading the framework's own result sees the framework's native semantics.
  Under argparse a repeated multi-token flag (`--tags x --tags y`) leaves only the last occurrence in the Namespace, while the merge accumulates both ([CLI adapters](cli-adapters/model.md#argv-is-the-only-writer)).
- A flag the adapters register and vanilla refuses (BUG-113) passes the framework's parse and is refused at merge, with vanilla's error, rather than at parse time with the framework's ([CLI adapters](cli-adapters/model.md#argv-is-the-only-writer)).
- An adapter types its flags by the sources `populate_*` read when the parser, the command or the app was built, `files=` and the environment included, so those go to `populate_*`; `merge_*` / `from_*` reuse them and refuse a different one.
  The environment is read again at the merge: a program that changes a variable naming a class in between types argv by one class and builds it by another ([design decisions](design-decisions/a-node-types-its-keys-by-the-class-it-names.md#the-adapters)).
- An argparse `Namespace` from a parser `populate_parser` filled carries one confarg key, `__confarg_registration__` (two under a `cli_prefix`), which a host spreading `**vars(ns)` drops ([design decisions](design-decisions/a-node-types-its-keys-by-the-class-it-names.md#the-adapters)).
- The typer adapter needs `typer>=0.27` and reads two of its private modules (`typer._types`, `typer._click`): the option, choice and context classes it must subclass have no public spelling since typer forked click, so a typer release that moves them breaks the adapter rather than degrading it ([CLI adapters](cli-adapters/clicklike-seam.md#the-clicklike-seam)).
- A registered leaf as the *root* has no whole-value CLI spelling: the bare `--<cli_prefix> VALUE` form is refused — it names no field, and the root `.json` cast requires a JSON object there ([CLI parsing](cli-parsing/cli-prefix.md#cli_prefix)).
  It is spelled through its tag instead (`--<cli_prefix>.class uuid.UUID --<cli_prefix>.hex …`), or supplied by the file and environment channels.
- A `MissingFieldError` names the flag under the `cli_prefix` only when `load()` or an adapter's `from_*` built the object: `build()` is never given the prefix, so called directly, even on what `merge(cli_prefix="app")` returned, it offers `--port` where the CLI accepts `--app.port` ([types](types/construction.md#a-missing-fields-remedy-is-spelled-as-the-cli-spells-it)).
- On a type that holds itself (`child: Node | None`), `--help` lists the field's own flags (`--child`, `--config.child`) and not its members': `--child.a` and every deeper flag are accepted when typed, and shown nowhere ([design decisions](design-decisions/a-node-already-on-the-path-is-not-entered.md#a-node-already-on-the-path-is-not-entered)).
- What confarg writes into a flag's help is escaped for the help format read at registration: cyclopts' `help_format` on the app `populate_app` is given (cyclopts' Markdown default when it has none), typer's `rich_markup_mode` on the command `populate_command` is given. cyclopts resolves the format when it renders, through the app stack, so a format set only on a parent app, or set after `populate_app`, is not seen: under a parent's `help_format="plaintext"`, a default's repr prints with the backslashes escaped for Markdown (`'\*.py'`).
  Set the format on the app confarg populates ([CLI adapters](cli-adapters/framework-specifics.md#help-text-is-format-neutral)).

## Subclasses

- `--help` lists a subclass's flags only once something has imported it: naming the class is what makes it visible, and nothing names it on a bare `--help` ([design decisions](design-decisions/a-named-tag-is-imported-before-registration.md#a-named-tag-is-imported-before-registration)).
  Import the plugin module, or name the class earlier on the same command line.
- A subclass-only field spelled exactly like `union_tag` turns subclass dispatch structural: the tag's class-path route is unreachable at that position, so the subclass is selected by its fields, several matches are an error, and a subclass needing more fields than provided is refused — a build-time `ConfargWarning` names the substitution when the spelling is used ([CLI parsing](cli-parsing/casts-and-reserved-words.md#real-field-wins)).

## Callables and serialization

- An instance method is recognized only when its path names the class that holds it: a module-level alias of a method (`m = C.m`, named as `pkg.m`) is a plain function, used unbound ([callables](callables.md#auto-binding)).
  A callable confarg did not build may not be serializable at all ([callables](callables.md#round-trip)).
- Where the merge cannot type a node — a key the type does not declare, a tag, a class or a target that does not import, a parameter with no annotation under `args`, or a merge with no target, such as `_load_file` on its own — a union tag or a `call` key replaces what lower layers set there by key alone, even where the data meant it as data, and a bare string below a refining dict is replaced rather than opened ([design decision](design-decisions/the-type-decides-replace-or-refine.md#the-type-decides-whether-a-value-replaces-or-refines)).
- Restating an opener, in a higher layer or later in one source, drops the arguments given for the first, even for the same target: `{bind: f}` over `{bind: f, args: {a: 1}}` is `f` alone, and so is `--fn.bind f --fn.args.a 1 --fn.bind f`.
  A layer or a flag refines a spec by writing its `args` only ([design decision](design-decisions/the-type-decides-replace-or-refine.md#the-type-decides-whether-a-value-replaces-or-refines)).
- Every `Any` field, and every value nested in what one holds, lets a file, an environment variable or a flag build any importable class with `class:` and call any importable function with `call:`, as a `call:` already can on any field that takes a typed call.
  A configuration source that is not trusted must not reach a field typed `Any` ([design decision](design-decisions/an-any-node-reads-every-opener.md)).
- A dict a program puts in an `Any` field with a `class`, `classfn`, `bind` or `call` key cannot be loaded back as that dict: it reads back as the spec it spells, and `dump()` warns when it writes one.
  An object no spec rebuilds, such as a `Path`, an `Enum` member, a `datetime`, a tuple or a closure, is written untyped with a `ConfargWarning` ([serialization](types/serialization.md#an-any-node-dumps-the-spec-that-rebuilds-it)).
- A `datetime` keeps its UTC offset through a dump, not its zone: one built with a `ZoneInfo` reads back with a fixed `timezone` of the same offset, equal to it but no longer following the zone's daylight-saving rules, and a `timezone` reads back without the name it was given ([design decisions](design-decisions/the-date-and-time-types-are-built-in-leaves.md#a-timezone-is-an-iso-8601-offset)).
- `zoneinfo.ZoneInfo` is no built-in leaf, whether a zone exists depending on the host's time zone database ([design decisions](design-decisions/the-date-and-time-types-are-built-in-leaves.md#the-date-and-time-types-are-built-in-leaves)).
- A `time` field takes no number and a `timedelta` field none either, so YAML's unquoted `10:20` and `1:30:00`, which YAML 1.1 reads as the base-60 numbers 620 and 5400, are refused: a time is quoted, a duration written in ISO 8601 (`PT1H30M`); the refusal says so ([design decisions](design-decisions/the-date-and-time-types-are-built-in-leaves.md#a-number-is-no-time-and-no-duration)).
- A `timezone` field reads a lowercase `z`, but a `datetime`'s text does not end with one: `datetime.fromisoformat` refuses `2021-02-03T10:00z`, and confarg reads that text as Python does ([design decisions](design-decisions/the-date-and-time-types-are-built-in-leaves.md#the-text-each-type-reads)).
- Digits finer than a microsecond are truncated in a `date`, `datetime` or `time`, as `fromisoformat` truncates them, and rounded half-even in a duration, as `timedelta` rounds them ([design decisions](design-decisions/the-date-and-time-types-are-built-in-leaves.md#a-duration-is-iso-8601-text)).
- On the command line the opener comes first: a key below a Callable or an `Any` written before the opener that names its class is an untyped token, so `--f.parts a b --f.class pkg.Joiner` refuses `b` where `--f.class pkg.Joiner --f.parts a b` takes the run, and a lower layer's class does not type it either.
  Below a node naming no class at all, every key takes one token ([a node types its keys by the class it names](design-decisions/a-node-types-its-keys-by-the-class-it-names.md#which-naming-types-a-key)).
- `--help` lists a nested spec's arguments (`--f.inner.factor` below `Wrap`'s Callable argument) only once argv spells its opener; a flag below it is accepted whenever typed ([callables](callables.md#cli)).
- A `call:` on a field whose struct has a member named `args` holds its arguments as files and the environment write them, but the CLI cannot spell them: `--n.args.<p>` reaches the member ([design decision](design-decisions/a-computations-arguments-nest-under-args.md#a-computations-arguments-nest-under-args)).
  A typed call at the root is spelled in files only ([callables](callables.md#cli)).
- Under the `args` of a `bind:` or `call:`, a name always fills the declared parameter: with `def f(a, /, **kw)`, `{a: 1}` is `a`, and no spec puts a key `a` into `kw`.
  A struct can, since its `**kwargs` is a field of its own (`--item.kw.a`) ([callables](callables.md#arguments-go-by-position-where-they-can)).
- A partial built in code with a later positional-or-keyword parameter bound by keyword behind one bound by position, `partial(g, 3, factor=2)`, dumps as `{v: 3, factor: 2}` and reads back as `partial(g, 3, 2)`: every call computes the same value, except one that passes `factor` again by keyword ([callables](callables.md#arguments-go-by-position-where-they-can)).
- A constructor parameter named `classfn` cannot be filled beside a `class:` or `classfn:` opener, since two object openers are refused; it is reached under the `args` of a `call:` or a `bind:` of the class ([callables](callables.md#an-openers-word-is-never-an-argument)).
- The flags a nested target spec's outer arguments take are described only when the nested spec yields a callable with a signature: a `call:` yields whatever its target returns, so `--f.args.<p>` beside `--f.call.call` is accepted with a generic help line ([callables](callables.md#cli)).
- `dump()` writes a dataclass as the fields it stores, so a dataclass with an `init=False` field dumps as a file that does not load back as it stands (`Unknown field(s) ['derived']`), and one with an `InitVar` that has no default as one that misses it; a defaulted `InitVar` reloads with its default ([the object dump is forensic](design-decisions/the-object-dump-writes-state.md#the-object-dump-is-forensic)).
  No artifact replays such a run exactly yet: the resolved dict keeps each `call:` and leaves out the defaults nothing touched (FEAT-48).
- A plain class is dumped as its constructor's parameters, so it must hold each one as a same-named attribute, slot or property — confarg reads attributes, it does not replay constructor calls; a plain class attribute spelled like a parameter is not one the instance holds, and is refused ([a plain class dumps the parameters it holds](design-decisions/the-object-dump-writes-state.md#a-plain-class-dumps-the-parameters-it-holds)).
  How a class dumps cannot be registered yet (FEAT-49).
- A subclass whose own `__init__` forwards `**kwargs` to its parent is set through a `kwargs` dict, untyped, not through the parent's members, and an undecorated subclass of a dataclass dumps its parent's fields alone (FEAT-50, [a dataclass is read by its `__init__`](design-decisions/a-structs-members-are-its-constructors-parameters.md#a-dataclass-is-read-by-its-__init__)).
- A class whose constructor signature does not read, as `zoneinfo.ZoneInfo`'s, is an unsupported leaf until registered: construction refuses its value and `dump()` refuses to write one ([types](types/serialization.md#an-unsupported-leaf-is-refused-both-ways)).
- No channel spells a `bytes` value: a `bytes` field is an unsupported leaf, and a `bytes` member of a `Literal` reads as nothing, so `Literal[b"ab", "cd"]` takes only `"cd"` and `dump()` refuses to write `b"ab"` ([design decisions](design-decisions/a-literal-member-is-what-pep-586-allows.md#a-literal-member-is-what-pep-586-allows)).
- A class implementing a collection ABC without subclassing a builtin (`deque`, `UserDict`, `ChainMap`) is not read as a collection ([FEAT-53](../todo/features/FEAT-53-a-collections-abc-implementer-reads-as-a-struct.md)).
- A builtin's subclass takes no cast: `--port.int 80` on a `Port(int)` field would pin a plain `int`, which the annotation does not hold, and a constructor's parameters other than the value (a dict subclass's `strict`) are no key a configuration sets, unless the class is registered ([design decisions](design-decisions/a-builtins-subclass-is-that-builtin.md#a-subclass-is-built-by-its-constructor)).
- TOML has no null: `dump_file()` refuses a `None` to a TOML file, naming its path, and a configuration holding one is dumped to YAML or JSON ([FEAT-54](../todo/features/FEAT-54-a-toml-file-spells-a-none.md)).
- A JSON dump writes an infinite or a NaN float as `Infinity` or `NaN`, and a TOML dump an integer past 64 bits, as Python's writers do: confarg reads such a file back, another parser may refuse it ([design decisions](design-decisions/a-written-file-holds-what-its-reader-reads-back.md#a-written-file-holds-what-its-reader-reads-back)).
- A TOML or a JSON file writes a dict key that is no string as its text, so under an `Any` `{1: 5}` reads back as `{'1': 5}`; two keys spelled alike, `1` and `'1'`, and a key with no text, a tuple, are written by no format but YAML, which writes no tuple key either ([design decisions](design-decisions/a-written-file-holds-what-its-reader-reads-back.md#a-key-is-written-as-the-text-it-is-met-by)).
- A union's unsupported branch is skipped: `bytes | int` reads an int and refuses every other value, naming `bytes` ([design decisions](design-decisions/a-literal-member-is-what-pep-586-allows.md#an-unsupported-branch-is-skipped-and-named)).
- A `call:` result is dumped from the object as the value it produced, never as the call ([design decision](design-decisions/the-object-dump-writes-state.md#the-object-dump-writes-state)).
  A result that no configuration spells, such as a closure, a lambda or an instance whose fields cannot be read, cannot be dumped from the object.
  The merged dict keeps the call, and `dump_file()` writes it as written.
- A callable instance and a bound method's owner dump as a plain class does, their constructor parameters read off the same-named attributes: one that stores a parameter transformed dumps the transformed value, which the constructor transforms again on read-back, and one that keeps it under another name cannot be dumped from the object ([callables](callables.md#an-object-dumps-the-state-it-holds)).
- An expression cannot read a `call:` result: expressions resolve before construction ([expressions](expressions/resolution.md#calls-and-expressions-share-one-graph)).
- Attribute docstrings used as `--help` text require the class source, which is unavailable for dynamically created classes ([CLI adapters](cli-adapters/flag-model.md#framework-neutral-flag-model)).
- A union leaf `__cast__` cannot name does not round-trip: an unregistered `Enum` beside another `Enum` of its rank that shares its value, a `Literal` holding `Enum` members, a collection variant a fixed-arity sibling takes back.
  `dump()` writes the bare value and warns with the field path ([design decisions](design-decisions/a-stolen-leaf-dumps-with-its-cast.md#a-stolen-leaf-dumps-with-its-cast)).
- In `Callable | str`, a bare builtin name (`help`, `format`, `print`) is the builtin and a typo'd path is the text; a file that means the text writes `{__cast__: str, __value__: …}` ([a Callable beside another variant reads its spec](design-decisions/a-callable-beside-another-variant-reads-its-spec.md#what-it-costs)).
- A dotted string a union tries as a type reference or a Callable imports the module its path names, from any channel: `"json.loads"` in a `type | str` field imports `json` before the type variant refuses a function.
  A bare word imports nothing ([dotted imports](types/dotted-imports.md#a-bare-word-is-never-imported)).
  A file that means the text writes `{__cast__: str, __value__: …}`.

## Remote sources

- **Nothing is cached.**
  A root `--config` location is read twice per run — once by the union-tag pre-scan in `_tags.py`, once by the pipeline — as local files already are (REF-26).
  Over the network that is two fetches.
  A caching handler is three lines through `register_scheme`, which is why no cache is built in.
- **No retries, no timeouts you can configure, no authentication.**
  The built-in `http`/`https` reader is `urlopen` with a fixed timeout; anything more — a proxy, a bearer token, a retry policy — is a handler the application registers over the built-in one.
- **Writing stays local.**
  `dump_file()` takes a filesystem path; there is no scheme registry for output.
- **No content sniffing.**
  The format comes from the location's suffix only, so an extension-less endpoint (`https://h/api/config?env=prod`) cannot be loaded even when it answers with a `Content-Type`.
- **A URL in `files=` must be a `str`.**
  `Path("https://h/x.yaml")` collapses the `//`, so passing a `Path` there cannot work.
- **A relative filename whose first segment holds a colon** (`weird:name.yaml`) reads as a scheme and must be written `./weird:name.yaml` ([config files](config-files/locations-and-schemes.md#locations-and-schemes)).
- **`file://` path translation is platform-dependent**, as `urllib.request.url2pathname` is: on Windows `file:/home/bob/c.yaml` names `\home\bob\c.yaml` on the current drive.
  A `file://` URL with a host other than `localhost` is refused rather than silently reinterpreted.
