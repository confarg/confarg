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

## A divergence leans towards the affected backend's own idiom

Parity is the rule ([09](09-invariants.md#cross-channel-parity)): a feature is spelled the same
way in all five front-ends and all three channels. Some spellings cannot reach every front-end,
because a host framework fixes at registration what confarg decides from argv. This section says
which way to lean when that happens; it does not lower the bar for *whether* it happens, which
still needs a concrete reason and the maintainer's explicit approval, obtained before the
divergence is implemented.

When parity cannot be reached, the front-end that has to give something up keeps **its own way
of working**, so the result stays native to the people who chose that framework. A confarg
spelling is not worth making a click user type something click would never ask them to type.
Concretely: the backend that cannot express the shared spelling declines it, rather than every
backend being dragged down to the narrowest common form.

The tie breaks towards the **CLI-oriented** backend, not towards confarg's config-oriented
philosophy. Command-line parameters are first and foremost user-friendly knobs for tweaking a
configuration at the last minute; they are not a configuration-file format that happens to live
in argv. Inline JSON on a command line is not friendly, so a whole-value `'[13, 42]'` or
`'{"x": 13}'` token is the half that gives way -- not the readable `--pair 13 42` a CLI user
expects, and not a framework's own native convention. Files and the environment remain where a
whole object is spelled comfortably; the CLI is where it is tweaked.

The corollary is that a divergence is **narrowed to the backend that imposes it**, never widened
to keep the five front-ends symmetrical. A front-end that *can* express the spelling gets it.
Symmetry is not the goal -- parity is, and where parity is unreachable the goal is the smallest
number of surprised users.

Worked example: [04](04-cli-adapters.md#whole-value-flags) -- a fixed-arity flag (`tuple[X, Y]`,
namedtuple) registers `nargs="*"` for argparse and cyclopts, which can take both the positional
form and a single whole-value token, while click keeps its exact token count and declines the
whole-value token, because click's only alternative (`multiple=True`) would have cost click
users `--pair 13 42`.

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

## The `=` form is the escape for a dashed value

`--key=--value` sets `key` to `--value` in all five front-ends; `--key --value` is
`Missing value for '--key'` in all four. A value that starts with `--` is indistinguishable
from a flag by shape, so something other than shape has to decide, and the `=` is the only
thing the user can write that already says "this is the value of that flag"
([03](03-cli-parsing.md#token-consumption)). Vanilla used to lose that information by
splitting `--key=--value` into two bare tokens before any flag-check ran
(BUG-27, closed); the dict-subkey and append spellings
(`--d.x=--v`, `--tags+=--a`) go through the same scan and so were broken in every front-end,
adapters included.

Rejected: **binding a dashed token in the space form** when exactly one value is expected.
click does this, and it is the outlier — argparse, cyclopts, `getopt` and jsonargparse all
refuse. Adopting it would have replaced a gap where vanilla stood alone against three
adapters with a gap where vanilla and click stood against two, and it makes a mistyped
`--key --verbose true` swallow `--verbose` as a value instead of erroring.

Rejected: **a bare `--` end-of-options separator**. No adapter can offer one — the host
framework tokenizes argv before confarg is called — so it would be a vanilla-only spelling,
and the environment has no equivalent at all. Filed as
[FEAT-17](../todo/features/FEAT-17-end-of-options-separator.md) rather than decided here
([11](11-limitations.md#cli-front-ends)).

## allow_abbrev disabled

`make_parser` sets `allow_abbrev=False`: with abbreviations, adding a field can silently change
which flag an abbreviated invocation means.

## Stealing rule for text in unions

Text is converted to the most specific type that accepts it, with `str` last, but only for
untyped channels ([05](05-types-and-construction.md#stealing-rule)). Coercion happens only when
the target type allows it, so this is not the YAML "Norway problem".

The rank is **total and fixed**, and the order a union is declared in never enters into it:
`int | Decimal` and `Decimal | int` read `5` the same way, or the documented rule would only
describe half the unions it is written for. Declaration order survives as the tie-break inside a
rank, which is all it can decide without being a rule of its own
(BUG-4, closed — no link: the board holds open work only).

The rule names five kinds; the type machinery has more. **Type references, `Literal` and a
`bytes` Literal member rank together, below `Enum` and above the numbers** — maintainer's
choice. They are *recognition*, not conversion: the token has to be the name of a member of a
closed set or a class that actually imports, so a match is evidence that this variant was meant,
where coercing `5` to a float merely shows that floats accept digits. The rejected alternative
put them just above `str`, letting the numbers win every tie; it was the smaller change to
reason about but reads a `Literal["1"] | int` field's `1` as the number, discarding the one
variant that spelled that value out. Precedent: pydantic v2's smart union runs a strict pass
over every member before any lax coercion, which likewise settles `Literal["1"] | int` on the
literal.

## Dump round-trips at the built object

`dump_file(merge(...), path)` writes a coerced leaf in its scalar form (`Path` → string,
`Enum` → value), so re-reading the file gives a plain `str` and the merged dicts are not
equal; the *built* objects are. The alternative — re-coercing values read from config files
so the dict itself round-trips — was rejected: it would make file values type-directed and
break the token model, whose whole point is that a self-describing file is never
re-interpreted ([05](05-types-and-construction.md#token-model)). Round-trip fidelity is
claimed one seam later instead ([01](01-pipeline-and-contracts.md#public-api-seams)).

A force-cast is the one value that is *not* degraded to its scalar form: a `_Pinned` is written
back as its `{__cast__, __value__}` file spelling, because the bare scalar would be stolen by an
earlier union variant and the built objects would then differ too
([05](05-types-and-construction.md#cast-pinning-in-files)).

Precedents: pydantic draws the same line with `model_dump(mode="json")` — `Path`, `Enum` and
`UUID` degrade to scalars on the way out and are re-validated, not re-typed, on the way in;
cattrs likewise pairs a lossy `unstructure` with a typed `structure`, never claiming that the
unstructured forms compare equal to the originals.

## A stolen leaf dumps with its cast

`dump()` writes `{__cast__, __value__}` for a union **leaf** whose bare scalar another variant
would take back — the typed sibling of the pin `_serialize_untyped` already writes
([05](05-types-and-construction.md#casting-a-stolen-leaf)). `Color | str` holding `"FOO"` dumped
`"FOO"` and rebuilt as `Color.FOO`, breaking the one round trip the library promises
([01](01-pipeline-and-contracts.md#public-api-seams); BUG-15, closed).
The cast is emitted only where the bare form fails to read back, so every dump that round-tripped
before is unchanged.

Rejected alternatives:

- **Cast every leaf union member.** Uniform and cheap to decide, but it turns every `int | str`
  field into a two-key dict in a file a human reads and edits; the file spelling earns its
  ugliness by being the exception. `tag_policy="always"` was the obvious lever for it and stays
  a *class-tag* policy for the same reason — a leaf has no class to name.
- **Re-read file values by declared type**, so the bare scalar selects the right variant on the
  way in. Rejected once already, above: it breaks the token model, in which a self-describing
  file is never re-interpreted ([05](05-types-and-construction.md#token-model)).
- **Decide by mirroring the stealing rule** rather than by calling `construct`. That is a second
  model of variant selection, and wrong for native values — which keep declaration order — on
  the day it is written ([09](09-invariants.md#delegate-to-the-canonical-function)).

The cost is one `construct()` call per leaf union value at dump time, and two where a cast is
emitted, since the cast is vetted the same way before it is written. `dump()` is not a hot path,
and the alternative is a rule that can be wrong in silence.

A variant `__cast__` cannot name — an unregistered `Enum` beside a `str`, a collection
variant — gets a `ConfargWarning` and the bare value, rather than an error or a cast no reader accepts:
`dump()` of a working object must not start raising, and the value stays correct for every consumer
that does not feed it back into `build()`. A `Literal` over `Enum` members no longer joins them: its
bare value (the `Enum` member's value) reads back as the member, because the native branch of
`_coerce_literal_value` matches it the way the token branch already did — one `_match_literal_member`
answers for both channels (BUG-32, closed) — so no cast is needed. Widening `__cast__` to dotted
paths would close the `Enum` half ([FEAT-16](../todo/features/FEAT-16-dotted-cast-names.md)); the
warning outlives that for a collection variant, which has no dotted name.

Precedents: YAML emitters tag a scalar (`!!str 5`) exactly when the plain form would resolve to
another type, and leave it bare otherwise. pydantic warns
(`PydanticSerializationUnexpectedValue`) instead of raising when `model_dump` meets a value its
serializer cannot represent faithfully.

## Registered leaf types dump through a registered serializer

`register_leaf_type(tp, coerce, *, serialize=str)` registers **both** directions, and
`_serialize_leaf` looks an instance up in `_LEAF_SERIALIZERS`. Before that, registration made
a type a leaf only on the way in: `dump_file` handed the writers an object they could not
represent, and `dump()` took the value for a struct and emitted its attributes — silent
garbage no loader reads back.

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
would be a spelling trap. Both predicates —
`_parse_cli._accepts_object_value` and the `accepts_obj` test in `_parse_env._store_env_value` —
therefore ask their union arm about every type the bare arm accepts: structs, namedtuples,
dicts and callables. In `_accepts_object_value` that is literally one test, the inner
`accepts()`, applied to the type and then to each non-`None` union variant; nothing may answer
only for the bare arm.

Both channels were fixed in one change on purpose. The gap was symmetric, so repairing only the
CLI would have *created* a divergence where none existed, which
[09](09-invariants.md#cross-channel-parity) forbids. Collections were already consistent under
this rule (`list[str] | None` takes a JSON array in the environment, and the CLI's
`_union_has_seq_variant` reaches it), so dicts were the outlier, not the precedent.

- Cost: a token that used to survive as a string now decodes, so a target with an
  `Any`-tolerant `| None` arm that was relying on the raw text sees a mapping instead. Nothing
  in the channel model ever promised that text; the raw value could not be built.
- Callables came second, the same way. `Callable[…]`
  had its own bare-arm-only test — `_is_callable` sat *beside* the union walk in
  `_accepts_object_value`, not inside it — so `Callable[…] | None` kept the spec token raw and
  handed the whole JSON blob to the importer, in both channels. Folding `_is_callable` into
  `accepts()` removed the second place a whole value could be decided, which is why the fix is
  one line smaller than the bug. The namedtuple half was settled separately, by making a
  namedtuple a sequence everywhere
  ([#a-namedtuple-is-a-fixed-length-sequence](#a-namedtuple-is-a-fixed-length-sequence)).
- Decoding the blob was not yet registering the flags it implies: the adapters learned a
  callable's factory and `bind` flags from a `--<field>.class` opener on argv only, so a class
  named inside the blob left them unregistered, fixed the same way — by widening an
  existing walk, not by adding a scan. Vanilla, which re-reads argv, was
  never affected; the divergence was in the scan, not in this predicate, which is why it
  survived the fix above and needed its own.

## A namedtuple is a fixed-length sequence

A namedtuple field takes every CLI spelling a same-arity `tuple` takes, and the whole `{...}`
object its field names additionally make meaningful. Vanilla used to treat it as a scalar: it
consumed one token, so `--pair 13 42` was `Unexpected positional argument: '42'`, `--pair
'[13, 42]'` and `--pair '{"x": 13}'` were stored as raw text and died in `build()`, and the
four adapters — which have registered the arity flag and the per-field flags all along —
disagreed with vanilla on a field shape they all support.

The fix is one classification, not three special cases. A namedtuple *is* a tuple subclass of
known arity, so:

- `_types._is_seq_variant` counts it as sequence-shaped, which is what
  `_union_has_seq_variant` and `_union_has_scalar_variant` are built from — so `Point | None`
  consumes its arity exactly as `tuple[int, int] | None` does, and optionality stays a
  statement about being unset rather than about syntax
  ([#optionality-does-not-change-what-a-whole-value-accepts](#optionality-does-not-change-what-a-whole-value-accepts));
- `_types._fixed_seq_types` answers "how many positional tokens, of which types?" for both
  spellings, so the parser's collection test and its consumption branch cannot learn about
  namedtuples separately and drift apart;
- `_parse_cli._accepts_object_value` gains the namedtuple arm the env channel's `accepts_obj`
  has had all along, in both its direct and its union half — which is the parity gap the
  ticket was actually filed for.

The rejected alternative was to teach the whole-`{...}` arm alone, as the ticket proposed. It
closes the env/CLI gap the ticket names and leaves the larger one: vanilla would take a whole
object for a namedtuple but still refuse the positional form all four adapters accept. A
predicate that says "this field is sequence-shaped" cannot be right for `tuple[int, int]` and
wrong for a two-field namedtuple; splitting them is what produced the gap.

Precedent: `typing.NamedTuple` is documented as a tuple subclass, and every consumer here
already treated it as one *somewhere* — the env channel accepts both JSON shapes for it, the
adapters register its arity, `construct` builds it from a list. Vanilla's argv parser was the
only holdout.

- Follow-through: the classification had to reach `construct`'s union split too. A lone token
  on a multi-variant union with a namedtuple variant used to fail in the parser (`--v 3 4` was
  a stray positional on `str | Point`); it parses greedily like `str | tuple[int, int]` now, so
  the failure moved down to `_construct_union_leaf`, which still partitioned variants with
  `_is_tuple` and left the namedtuple among the *scalar* leaves. The split asks `_fixed_seq_types` instead, and so does
  the arity filter it feeds, so the one function that answers "fixed arity, of which types?"
  answers on the way in as well
  ([05](05-types-and-construction.md#leaf-coercion)).
- Boundary: taking a whole `{...}` or `[...]` token on a fixed-arity flag needs a framework
  that can vary a flag's token count at parse time. argparse and cyclopts can and now do;
  click cannot and declines, the approved divergence argued in
  [04](04-cli-adapters.md#whole-value-flags). That was never a namedtuple property —
  `tuple[int, int]` behaved identically — so it was filed once, for both (BUG-20, closed).

A note on the ID: `BUG-16` was used twice. The first one —
[#an-explicit-tag-opts-a-leaf-back-in](#an-explicit-tag-opts-a-leaf-back-in) — closed long
before the namedtuple ticket was filed under the same number, against
[todo/README.md](../todo/README.md)'s rule that IDs are never reused. Both are closed, and the
next free number on `bugs.md` is what the rule intends.

## A whole-value flag needs its value

`--db` with nothing after it is an error in every front-end, exactly like `--port` with
nothing after it. Vanilla used to make one exception: a **non-optional dataclass** field
consumed no token and merged nothing. The exception was
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

A type in `_LEAF_COERCIONS` is not taken apart into fields by anything that *infers* it should
be: not by the construction and serialization dispatchers, and not by the union-variant filters
on either side. Only an explicit tag still opens it, and that is the next section. The one
predicate is `_is_struct_variant`
([05](05-types-and-construction.md#leaf-coercion)); asking `_is_struct` was the bug.

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
keep the registry out of the union filters and require an explicit tag on every union with a
registered leaf in it — pushes the cost of an introspection accident onto every user of such a
union, to spell out a variant that the leaf path already resolves on its own.

## An explicit tag opts a leaf back in

`register_leaf_type` may not take a spelling away. Before registration a struct-shaped type is
built from its fields like any other, tag included: `{"class": "uuid.UUID", "int": 5}` produces
`UUID(int=5)` for a field typed `UUID` or `Release | UUID`. Registering `UUID` broke the plain
field — `UUID.__init__` got the dict and its `AttributeError` escaped `build()` — which is the
previous section's promise misapplied to a value that was never inferred to be a struct in the
first place. An existing configuration file is not wrong because a type it names was later
registered.

So the rule splits by who asked. A registered leaf is opaque to every **implicit** decision:
struct dispatch on a bare dict, the "struct with all-default fields is built from `{}`" shortcut
for a missing field, structural union disambiguation, tag emission on the way out
([`_is_struct_variant`](09-invariants.md#delegate-to-the-canonical-function)). An **explicit**
tag naming its class asks for field construction in so many words and gets it
(`_is_taggable_leaf`). Both halves meet in `_construct_scalar`, the canonical single-value
constructor, so the tag works wherever a leaf is addressed — a plain field, a list element, a
union variant — and not just where the bug was noticed.

An untagged dict stays an error, and the message says how to ask for fields. The rejected
alternative — let *any* dict rebuild a registered leaf from its fields, exactly as before
registration — keeps more old configurations working, but it leaves registration meaning nothing
for dict-shaped data and re-opens the introspection accident the previous section closes: the
maintainer's call is that the tag is the opt-in, and nothing else is.

Precedent: nobody else lets a tag name an opaque type, but nobody else has this tag. cattrs'
`configure_tagged_union`, pydantic's discriminated unions and msgspec's tagged unions are
closed-world discriminators over modeled variants, so an opaque type cannot appear in one at
all. confarg's `class` is a dotted import path that names any class and fills its parameters
([#no-implicit-subclass-inference](#no-implicit-subclass-inference)); a registered leaf is a
class like another, and refusing to import it would be the special case.

## Shared reserved key names live in `_defaults.py`

`__root__` — the key under which a non-struct target's value sits in the merged dict — is
written by all three channels and read by `build()`, so the five front-ends must agree on
the spelling; every site that spelled it inline was a place they could drift apart.
It is now `_defaults.ROOT_KEY`, next to
`LOCALS_KEYS`, which is a reserved name rather than a keyword default too: `_defaults.py` is
the home for **any** literal the front-ends have to agree on, not only the public keyword
defaults, and its "never repeat the literals" invariant
([09](09-invariants.md#fragile-couplings)) covers both kinds.

The rejected alternative was a separate `_reserved.py` collecting `__root__` alongside
`__include__`, `__cast__` and `__value__`. It names the concept more honestly, but those
three are file-only keys read in one module each
([02](02-files-and-env.md#reserved-file-only-keys)) — they have an owner, and a literal with
an owner is not the problem this invariant exists to prevent. A second module would split the
"where do I look this up?" answer in two for no gain.

A key that does have an owner keeps it: `JSON_CAST_NAME` stays in `_cast.py`, the module that
decides what a cast means, in the same way that `_parse_cli` owns the reserved-name conflict
rules ([09](09-invariants.md#delegate-to-the-canonical-function)). `_defaults.py` is for the
names with no such home.

## A named tag is imported before registration

Whatever the configuration names by its `union_tag` — on argv, or in a `--config` file argv
points at — is imported before anything walks the target type (`_tags.import_tagged_classes`,
called from `_parse_cli` and `build_static_flags`). A subclass exists, as far as
`__subclasses__()` is concerned, only once its module has run, and five separate readers
depend on that answer: the CLI selector spec, the subclass field specs, the completer paths,
vanilla's `_subclass_field_type` path resolution, and completion's parser pre-extension. Each
of them was import-order-dependent; making the import happen first fixes all five at once.

The rejected alternative was to make registration independent of `__subclasses__()` — register
`--<field>.<union_tag>` on every struct field, since `build()` accepts the tag on any struct.
It closes the CLI half and nothing else: vanilla still cannot resolve `--handler.path` for a
subclass nobody imported, so it buys a `--help` entry per nested struct and leaves the parity
gap open one channel over. `_construct_struct_dispatch` already checks `union_tag in data`
*before* `tp.__subclasses__()`; this makes the CLI agree with it rather than inventing a second
rule.

- Cost: a `populate_*` call imports modules the command line names, so a class path is
  side-effecting at registration time and not only at construction time. confarg already
  imported `--<field>.class` targets there for callables, so the exposure is not new. A failed
  import is swallowed — it is a visibility hint, not a decision point, and `construct` raises
  the authoritative `SymbolImportError` naming the path a moment later.
- Cost: a subclass that nobody imported *and* nobody names is still absent from `--help`
  ([11-limitations.md](11-limitations.md)).

This completes [#no-implicit-subclass-inference](#no-implicit-subclass-inference) rather than
reopening it: confarg still never *searches* for a subclass. It imports exactly the one class
the user named, which is what the tag is for.

Precedent: jsonargparse resolves a `class_path` by importing it during `parse_args`, and its
help reports `known subclasses:` from whatever is loaded — naming a class earlier on the same
command line grows the list (verified, jsonargparse 4.52.0). It accepts the same
import-dependent help this decision accepts, and answers discovery with a separate on-demand
`--<field>.help CLASS_PATH` action instead of pre-registering anything
([FEAT-15](../todo/features/FEAT-15-inspect-flags-of-unnamed-class.md)).

## A whole value followed by a subkey opens rather than collides

`--<field> <scalar> --<field>.<sub> <v>` used to let Python's own `TypeError` out of
`_set_nested` — the merge core cannot subscript a string. What the pair should *mean* is not
one question but three, because the parse is type-guided and the scalar means something
different at each field:

| The scalar at that field | Example | Was |
|---|---|---|
| provably meaningless | `dict[str, str] \| None`, a dataclass | already headed for a build error on its own |
| a legitimate value | `dict[str, str] \| str` | builds fine on its own |
| a documented shorthand | `Callable[…]` | `"pkg.func"` ≡ `{fn: "pkg.func"}` |

The rule chosen: **open the scalar into whatever it means to its field, then let the subkey
refine it**; where it means nothing, the subkey replaces it. Only `Callable` has such a
meaning today, so only it is promoted, and `promote_bare_spec` writes that equivalence down
once. The alternatives, and why not:

- **One blanket rule, "the subkey replaces the scalar."** Smallest possible change — a single
  branch in the type-blind `_set_nested` — and it matches the adapters and `_deep_merge`
  exactly. Rejected because it discards a value the user meaningfully typed, and the callable
  case then fails with *must specify one of 'fn', 'class', or 'call'*: an error that says the
  user named no target when they named one two tokens earlier.
- **One blanket rule, "raise a `ConfargError`."** Never silent. Rejected because vanilla would
  then refuse a pair the four adapters and the file-then-CLI path keep accepting, which is a
  new unapproved parity gap, not a fix; making *those* raise instead is a much larger change
  reaching into `_deep_merge`, and pushes a type-shaped judgement into the layer whose
  contract is that it does not make them ([01](01-pipeline-and-contracts.md#merge-build-contract)).
- **Split by whether the scalar was meaningful** — replace for a dict field, raise for
  `dict | str` and for `Callable`. The most conservative reading: nothing meaningful is ever
  dropped and no spelling is invented. Rejected because it gives one syntax two outcomes
  decided by the field's type, which is hard to document and harder to predict, and it refuses
  the callable pair rather than doing the obvious thing with it.

Cost: at a union like `dict[str, str] | str`, where a scalar *is* legitimate but is not a
shorthand for anything, the subkey still discards it silently. That is the same last-write-wins
the other three cells of the table already had, and the reverse argv order discards the subkeys
just as quietly ([01](01-pipeline-and-contracts.md#scalar-intermediates)).

Making this reach the adapters is what kept it from being a vanilla-only fix: the argv scan
that discovers bind parameters already reads a callable named by an opener flag, a `{…}` blob
or a config file, so the bare string became a fourth source feeding the same type-guided walk
rather than a new mechanism ([04](04-cli-adapters.md#static-and-dynamic-flags)).
