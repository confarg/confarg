# Design decisions

Each entry: the decision, why, and what it costs. Precedents are cited where known.

## No custom types required

Plain dataclasses, NamedTuples, plain classes, unions and standard annotations work with no
base class, decorator or field marker; confarg is "not a framework" and its footprint in user
code is a few lines. Break this only for important features that cannot be done otherwise.

- Cost: all knowledge comes from runtime introspection, concentrating complexity in `_types.py`
  and `typedload`. Per-field extras (help, metavar) ride on `Annotated[T, FieldMeta(...)]`, which
  is stdlib and invisible at runtime.
- Precedents: pydantic-settings and Hydra structured configs require their own base classes or
  containers; jsonargparse and cyclopts also introspect plain signatures/dataclasses.

## Plain dicts between stages

See [01](01-pipeline-and-contracts.md#plain-dicts-as-the-intermediate-representation).
Precedents: pydantic-settings and Dynaconf merge mappings before validation; OmegaConf keeps its
own `DictConfig` container. A *plain* dict keeps confarg dependency-free and decomposable.

## One merge pipeline for every front-end

See [01](01-pipeline-and-contracts.md#the-single-merge-pipeline). Cost: adapters must translate
each framework's parse result into confarg's shape, which is where the intricate code lives
(dual parse for patch parity).

## Adapters instead of an own CLI framework

Users keep argparse/click/cyclopts; confarg also parses argv itself, so no CLI library is
needed. Help for large, dynamic configurations is inevitably long and incomplete (derived
classes' fields are unknown until selected), and configuration files are the primary
interface, so a rich CLI UX is a secondary goal.

## union_tag defaults to "class"

`class` is a Python keyword, so no dataclass field can ever be named `class`: the
discriminator can never collide with user data. `type` was rejected as a common field name.
Configurable per call. Cost: unusual for users expecting `type`, and reads slightly oddly in
files. Precedent: Hydra uses a reserved `_target_` key for the same reason.

## Environment variables off by default

`env_prefix=None` disables env parsing. Environment variables are global and shared by every
process, so reading them without an explicit, app-specific prefix is unsafe in shared
environments; `""` (read all) is opt-in, not the default. Cost: one extra argument for the
common case. Precedent: pydantic-settings and Dynaconf both scope by prefix.

## Double underscore separator

`__` splits nesting so single underscores remain usable in names. Precedents:
pydantic-settings `env_nested_delimiter="__"`, Dynaconf `__`. Side effect: dunder keys cannot be
expressed in env ([02](02-files-and-env.md#reserved-file-only-keys)).

## Explicit boolean values

Booleans take a value (`--verbose true`), not `--flag`/`--no-flag`. A bool then behaves like
every other scalar in every channel, with no special parsing or merge rule, and a CLI value can
override a file value in either direction. Cost: less idiomatic for CLI-only users. Precedent:
jsonargparse accepts explicit `true/false` values.

## Zero runtime dependencies

YAML, TOML writing, completion and the CLI adapters are optional; missing libraries produce a
clear install hint. Cost: features depend on extras being installed.

## Expressions resolved after merging, by a whitelisted interpreter

Late resolution lets any channel override an input of a file-defined formula
([07](07-expressions.md#resolution-algorithm)). A small AST interpreter avoids `eval` on
untrusted configuration while covering arithmetic, conditionals and string methods. Precedents:
OmegaConf interpolation resolves lazily with registered resolvers; confarg instead offers a fixed
safe subset of Python syntax.

## A class tag replaces, not merges

A dict carrying the union tag discards the previous value during merge
([01](01-pipeline-and-contracts.md#deep-merge-semantics)), so switching variants does not
inherit the old variant's fields.

## No implicit subclass inference

A base-class field is resolved through the union tag alone; confarg never picks a subclass by
looking at which keys the input supplies. Inference existed (PR #58) and was removed (PR #63)
because a subclass is only discoverable once it has been imported: the candidate set would be
whatever `__subclasses__()` happens to hold at resolution time, so the same configuration would
build different objects depending on which modules were loaded first. Making it deterministic
means requiring users to import every candidate subclass before resolving — a constraint confarg
does not want to impose. Structural matching is unaffected
([05](05-types-and-construction.md#union-construction)): the variants of a `Union[...]` are named
in the annotation, so they are imported by construction. Any later attempt at subclass inference,
including `Annotated` hints, inherits the same import problem and must answer it first.

Precedents: pydantic requires an explicit discriminator for tagged unions and never scans
`__subclasses__()`; cattrs exposes subclass handling only as an opt-in strategy
(`include_subclasses`) applied when hooks are registered, which pins the candidate set at a
moment the user controls.

## Real field wins over reserved words

Reserved names (casts, locals) are only reserved where they would not shadow a real member, so
confarg never forbids a field name ([03](03-cli-parsing.md#real-field-wins)).

## Strict CLI, lenient environment

Unknown CLI flags are errors, unknown env variables only warn
([02](02-files-and-env.md#environment-parsing)).

## cli_prefix is given at registration and recovered at merge

The adapters take `cli_prefix` on `populate_*` — which owns flag naming — record it, and let
`merge_*`/`from_*` recover it; passing one there that disagrees raises
([03](03-cli-parsing.md#cli_prefix)). The prefix is what makes configuration flags
distinguishable from a host CLI's own, so it belongs in the front-ends built for exactly that
coexistence, not in vanilla alone.

Rejected: **merge-time only**, the arrangement that kept the prefix vanilla-only in the first
place — a prefix that disagrees with what was registered matches no flag, and the fields simply
come back missing, so the failure is silent. Rejected: **both ends, "must match"**, the looser
contract `config_flag` already carries — one keyword more to repeat, with the same silent
failure when the two drift. Recording it at registration removes the repetition *and* makes the
disagreement detectable, so the mismatch became an error rather than a documentation note.

- Cost: `populate_*` has to stash the value somewhere that survives into the merge step, and no
  framework hands that step the object the flags were registered on — three different hiding
  places ([04](04-cli-adapters.md#the-cli_prefix-boundaries)).

## allow_abbrev disabled

`make_parser` sets `allow_abbrev=False`: with abbreviations, adding a field can silently change
which flag an abbreviated invocation means.

## Stealing rule for text in unions

Text is converted to the most specific type that accepts it, with `str` last, but only for
untyped channels ([05](05-types-and-construction.md#stealing-rule)). Coercion happens only when
the target type allows it, so this is not the YAML "Norway problem".

## Dump round-trips at the built object

`dump_file(merge(...), path)` writes a coerced leaf in its scalar form (`Path` → string,
`Enum` → value), so re-reading the file gives a plain `str` and the merged dicts are not
equal; the *built* objects are. The alternative — re-coercing values read from config files
so the dict itself round-trips — was rejected: it would make file values type-directed and
break the token model, whose whole point is that a self-describing file is never
re-interpreted ([05](05-types-and-construction.md#token-model)). Round-trip fidelity is
claimed one seam later instead ([01](01-pipeline-and-contracts.md#public-api-seams)).

Precedents: pydantic draws the same line with `model_dump(mode="json")` — `Path`, `Enum` and
`UUID` degrade to scalars on the way out and are re-validated, not re-typed, on the way in;
cattrs likewise pairs a lossy `unstructure` with a typed `structure`, never claiming that the
unstructured forms compare equal to the originals.

## Registered leaf types dump through a registered serializer

`register_leaf_type(tp, coerce, *, serialize=str)` registers **both** directions, and
`_serialize_leaf` looks an instance up in `_LEAF_SERIALIZERS`. Before that, registration made
a type a leaf only on the way in: `dump_file` handed the writers an object they could not
represent, and `dump()` took the value for a struct and emitted its attributes — silent
garbage no loader reads back ([BUG-11](../todo/bugs.md), closed).

The alternative was to infer the outbound spelling as `str(value)` with no new keyword. It is
right for types whose `str()` is their wire form — `UUID`, `Decimal`, `Path` — which is why it
is the *default*, but it cannot be the only rule: `str()` of this repository's own tutorial
type (`examples/4_leaf_types`) is the `repr`-style `Int(value=42)`, which its own coercion
function refuses on the way back in. A lossy default that no user can override would have made
`dump()` quietly unusable for exactly the types registration exists to support.

Precedents: nobody infers one direction from the other. cattrs pairs `register_structure_hook`
with `register_unstructure_hook`, pydantic a validator with `PlainSerializer`, msgspec
`dec_hook` with `enc_hook`, and the standard library's `json` pairs `object_hook` with
`default=`. Registering the pair is the common shape; defaulting the second half to `str` is
confarg's concession to the common case.

## Optionality does not change what a whole value accepts

`--env '{"a": "b"}'` and `MYAPP_ENV='{"a": "b"}'` decode the same for `dict[str, str]` and for
`dict[str, str] | None`. Optionality says what a field may be *unset* to; it is not a statement
about its syntax, so making `| None` the difference between a decoded mapping and a raw string
would be a spelling trap ([BUG-9](../todo/bugs.md), closed). Both predicates —
`_parse_cli._accepts_object_value` and the `accepts_obj` test in `_parse_env._store_env_value` —
therefore ask their union arm about dicts as well as structs.

Both channels were fixed in one change on purpose. The gap was symmetric, so repairing only the
CLI would have *created* a divergence where none existed, which
[09](09-invariants.md#cross-channel-parity) forbids. Collections were already consistent under
this rule (`list[str] | None` takes a JSON array in the environment, and the CLI's
`_union_has_seq_variant` reaches it), so dicts were the outlier, not the precedent.

- Cost: a token that used to survive as a string now decodes, so a target with an
  `Any`-tolerant `| None` arm that was relying on the raw text sees a mapping instead. Nothing
  in the channel model ever promised that text; the raw value could not be built.
- Not extended to unions with a callable or a NamedTuple variant: those are separate gaps with
  their own asymmetries ([BUG-16](../todo/bugs.md), [BUG-17](../todo/bugs.md)), not consequences
  of this rule.

## A whole-value flag needs its value

`--db` with nothing after it is an error in every front-end, exactly like `--port` with
nothing after it. Vanilla used to make one exception: a **non-optional dataclass** field
consumed no token and merged nothing ([BUG-8](../todo/bugs.md), closed). The exception was
indefensible on three counts.

- It bought nothing. The branch returned without calling `_set_nested`, so the flag was a
  silent no-op — and not "use defaults" as its comment claimed, since a value already merged
  from a config file stayed put.
- It was inconsistent inside vanilla. The guard tested `_is_dc(ft)` on the resolved-but-not
  Optional-unwrapped type, so `Sub | None` and `dict[str, str]` — which get the same bare
  whole-value flag — already raised `Missing value`. Only one of the four whole-value shapes
  had the exception.
- No adapter could reproduce it, and one of them never can. argparse has `nargs="?"` and
  click reaches the same shape with `is_flag=False, flag_value=<sentinel>`, but cyclopts
  fixes a parameter's token count by construction: annotating the optional-value shape fails
  with `Cannot Union types that consume different numbers of tokens`. Nor can an adapter
  rewrite argv around the gap — the user owns the framework's parse call, not confarg.

Teaching three front-ends a form that contributes nothing to the merged dict, on a field
shape the fourth already refused, was the worse trade. The rule is now uniform, so
`_accepts_object_value` decides *what* a whole-value flag decodes and nothing decides
*whether* it needs one.

## A registered leaf is never a struct variant

A type in `_LEAF_COERCIONS` is not taken apart into fields anywhere: not by the construction
and serialization dispatchers, and not by the union-variant filters on either side. The one
predicate is `_is_struct_variant`
([05](05-types-and-construction.md#leaf-coercion)); asking `_is_struct` was the bug
([BUG-14](../todo/bugs.md), closed).

The distinction has teeth because `_is_struct` is structural: a class with any `__init__`
parameter is a struct, and `UUID.__init__` takes seven, all with defaults. So a field typed
`Release | UUID` — where `Release` is a struct with a `version` field, a name `UUID.__init__`
also uses — read as a union of two structs. `build()` refused `{"version": 2}` with
`AmbiguousUnionError`, and `dump()` emitted a `class` tag for a union holding exactly one
struct. The two defects hid each other: the spurious tag is what kept `load(dump(x)) == x`
working, so fixing either alone would have broken the round trip
([01](01-pipeline-and-contracts.md#public-api-seams)).

This narrows what `build()` rejects: data that used to be ambiguous now constructs the struct.
That is the intended direction — registration is a promise that the type is opaque, and a
promise that holds in one direction only is worse than none. A registered leaf still claims
the *scalar* form of the same union through the leaf path, so neither variant loses its
spelling.

Precedent: cattrs treats a type with a registered structure hook as opaque and never considers
it in union disambiguation, which only ever looks at attrs classes. The rejected alternative —
keep the registry out of the union filters and require an explicit tag on such unions — pushes
the cost of an introspection accident onto every user of a union with a registered leaf in it,
and says nothing about which of `UUID`'s seven parameters the tagged dict should fill.
