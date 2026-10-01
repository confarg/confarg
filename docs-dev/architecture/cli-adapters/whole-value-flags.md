# Whole-value flags

A bare `--<field> '{…}'` assigns an entire object in one token — the CLI peer of the env
channel's `PFX_ENV='{"a":"b"}'`. `_parse_cli._accepts_object_value` is the one predicate
deciding which field types take one: struct (dataclass *or* plain class), namedtuple, dict,
callable, or a union with any of those as a variant. It answers for the vanilla parser (which
writes the adapters' CLI channel too, [argv is the only writer](model.md#argv-is-the-only-writer)),
for static registration and for the env channel's `{`-led value, so they cannot drift. A plain class counts because the blob is taken apart into fields and
construction takes both spellings of a struct apart the same way; env and files accepted it
while the CLI alone refused until BUG-39 deleted the env channel's second answer.

The struct arm asks `_is_struct`, **not** the narrower
`typedload._coerce._is_struct_variant` that construction's dispatchers ask
([types](../types/leaf-coercion.md#leaf-coercion)). The two disagree on a registered leaf
with an `__init__` — `UUID`, say — and this question comes first: an explicit tag naming
such a class still builds it from its fields
([design decisions](../design-decisions/an-explicit-tag-opts-a-leaf-back-in.md#an-explicit-tag-opts-a-leaf-back-in)), and the tag cannot be
seen until the token is decoded. Refusing the token here would put that hatch out of the
CLI's reach while leaving it open to env and files, and would silently coerce the JSON
*text* into a leaf instead. Vanilla's `_consume_value` honors the decoded whole value before
falling back to scalar coercion. A token no blob decodes is kept raw, not dropped: it is
stored for `build()` to refuse (`--inner 7` → `{'inner': '7'}` → `expected dict, got str
'7'`) — when the adapters still had a collector of their own, the token once vanished there,
and a typo'd CLI value silently built the field's default on four of the five front-ends
(BUG-82, closed). The `--help` metavar stays `VALUE` there: the rule is that
`JSON` implies the token is decoded, not the converse, and a registered leaf's ordinary
spelling is its scalar, with the tagged blob an escape hatch rather than the syntax to
advertise.

The flags are **static**, not argv-scanned: the field is declared, so it belongs in `--help`
next to the bare `--tags` / `--pair` flags lists and tuples already get, and completion can
offer it. `nargs=None` — vanilla consumes exactly one token here, rejects a second as a stray
positional, and rejects none at all with `Missing value`
([design decisions](../design-decisions/a-whole-value-flag-needs-its-value.md#a-whole-value-flag-needs-its-value)): the `FlagSpec` vocabulary
deliberately has no optional-value `"?"`, because cyclopts cannot express one. The metavar is `JSON` only where the predicate says the token is decoded, so a field that
keeps its token raw does not advertise a syntax it will not honour. Optionality is not one of
the things that decides this: `dict[str, str] | None` takes the mapping `dict[str, str]` takes,
`Callable[…] | None` takes the spec `Callable[…]` takes, and both get the same `JSON` metavar
([design decisions](../design-decisions/optionality-and-whole-values.md#optionality-does-not-change-what-a-whole-value-accepts)).
The hatch's *flat* spelling crossed the same seam one step later (BUG-56):
`--id.class uuid.UUID --id.hex …` is what the environment says with `ID__CLASS` /
`ID__HEX`, and vanilla accepted it all along because its type walk treats a registered
leaf structurally — the tag segment resolves through the `union_tag` rule, a parameter
through the leaf's `__init__` fields. The adapters' registration mirrors that walk: it is
argv-scanned ([static and dynamic flags](static-and-dynamic-flags.md#static-and-dynamic-flags)),
accepting exactly what `_parse_cli._resolve_field_type` accepts — so `--id.bogus` stays
unregistered and the framework's rejection stands in for vanilla's `no_such_field` — and the
values are vanilla's loop's to write. A registered leaf as the *root* target crossed the same
seam one step later (BUG-71): it has no field to descend from, so the scan's leaf is the target
itself, at the empty prefix of the path — and the tag flag, whose only segment is the tag,
registers exactly as a field's does. The root's `__init__` parameters were static all along —
the root is walked structurally, exactly as a union holding the same leaf is — so the tag is
the one flag the scan adds.

A decoded callable blob buys the factory and `bind` flags its class implies, exactly as a
`--<field>.class` opener does. Neither half of that is a
second decision: `_blob_document_from_argv` nests argv's `{`-prefixed tokens into one
config-file-shaped document and hands it to the *same* target walk that reads a `--config`
file's openers, so a blob's `class` selects the directive form and registers the sibling
`--<field>.<param>` init kwargs the opener flag registers. Feeding the walk rather than
pattern-matching argv is what keeps a mapping field whose value happens to carry a `class` key
from being read as a callable spec — the walk is type-guided. The opener scan
(`_collect_fn_paths_from_argv`) pattern-matches the `.fn`/`.class`/`.call` suffix too,
so a struct field literally named like an opener would be misread as an opener for its
parent; it now asks the same type-guided question — does the path resolve to a
callable-typed field? — before accepting the match, so a plain struct field named `fn`
(or `class`/`call`) is a value, not an opener (BUG-30). The string shorthand
`--<field> some.module.fn` buys them too: it is the spelling `{fn: …}` abbreviates, so the argv
scan collects a bare string as a whole value beside a `{`-prefixed blob and hands both to the
same type-guided walk, which has always read a config file's string spec that way. What the
flags then write — the shorthand opened into the spec its sibling flags refine, a delete flag
included — is vanilla's loop's answer
([CLI parsing](../cli-parsing/token-consumption.md#token-consumption)).

A **fixed-arity** flag — a namedtuple or a `tuple[X, Y]` — is registered with the framework's
own exact token count, which is decided before argv is parsed and therefore cannot also admit
the single whole-value token vanilla takes (`--pair '[13, 42]'` for the tuple, `--pair
'{"x": 13}'` for the namedtuple). `FlagSpec.whole_value` marks those specs, and each adapter
grants what its framework can express (BUG-20, closed):

| Front-end | Registration | `--pair 13 42` | `--pair '[13, 42]'` | `--pair=1 2` |
|---|---|---|---|---|
| vanilla | — | ✅ | ✅ | ✅ |
| argparse | `nargs="*"` | ✅ | ✅ | ❌ |
| cyclopts | `consume_multiple=True` | ✅ | ✅ | ✅ |
| click | `nargs=<n>` | ✅ | ❌ | ✅ |
| typer | `nargs=<n>` | ✅ | ❌ | ✅ |

Each ✅/❌ pair marks an approved divergence of its own: click and typer decline the
whole-value token (below), and argparse alone declines the `=`-spelled run continued by
bare tokens — the BUG-75 paragraph below names it.

click and typer are the exception, and it is an **approved divergence**
([invariants](../invariants.md#cross-channel-parity)). A click `Option` cannot vary its token count:
`nargs=-1` raises `nargs=-1 is not supported for options`, and the only alternative,
`multiple=True`, would buy the whole-value token by taking `--pair 13 42` away and demanding
`--pair 13 --pair 42` in its place. Inline JSON is not what a CLI user reaches for, so click
keeps the readable positional form and declines the whole value, per
[design decisions](../design-decisions/divergence-leans-to-the-backend.md#a-divergence-leans-towards-the-affected-backends-own-idiom). The
divergence is confined to the two clicklike front-ends — typer inherits it along with the
option class it forked ([the clicklike seam](clicklike-seam.md#the-clicklike-seam)); argparse and cyclopts, which *can* vary
the count, get both.

Registering `nargs="*"` hands **arity enforcement back to confarg** — the framework no longer
counts the tokens, and vanilla's loop, reading argv, does it the way it always has: one
`_require_value` per positional token, so a short run is `Missing value for '--pair'` and not a
shorter tuple
([design decisions](../design-decisions/a-whole-value-flag-needs-its-value.md#a-whole-value-flag-needs-its-value)),
and consumption stops at the declared count, so the next token is a stray. Vanilla refuses that
stray at the top of its loop. In the adapters' `host_parsed` mode a stray may be a positional of
the host's, so the loop asks the host: argparse and cyclopts bound every token up to the next
flag to this flag (`binds_runs`, `_build._binds_a_run`), so the token is the stray vanilla
refuses, `Unexpected positional argument: '3'`; click and typer counted the tokens themselves
and never reach the question ([argv is the only writer](model.md#argv-is-the-only-writer)).
The two errors have one owner each — `ConfargError.missing_value` and
`UnknownArgumentError.unexpected_positional` — so the adapters raise what vanilla raises
(BUG-58, BUG-60). A whole value is one token whatever arity it spells, so `--pair '[13]'` stays
the arity error `build()` owns and the `9` in `--pair '[13]' 9` is surplus.

What a *repeat* of the flag means is vanilla's answer too — the last occurrence's run, every
occurrence's bounds checked as it is consumed (`--pair 1 --pair 3 4` refuses the first) — however
the framework binds the repeat. Before REF-72 the adapters read it off the parse result, and
each framework's idiom needed a repair: cyclopts' `consume_multiple=True` joins every
occurrence's run into one list, so a converter kept the last run off the `CliToken.index`
restart (BUG-62), and the bounds were re-read per occurrence off argv
(`_fixed_arity_occurrence_runs`, `_require_fixed_arity`, BUG-73).

The `=`-spelled run's *continuation* is the one spelling argparse cannot take, and it is an **approved
divergence** narrowed to it (BUG-75, closed): argparse's `=` binds exactly the text after
it, so the tokens that would complete the run arrive as unrecognized arguments and its
parser exits with its own usage error before any confarg code runs — no registration can
express "continue my `=` run on the next token", where vanilla simply normalizes
`--key=value` to `--key value` before parsing
([CLI parsing](../cli-parsing/token-consumption.md#token-consumption)). The decline keeps
argparse's native behavior, so confarg's arguments blend with the host application's own
([design decisions](../design-decisions/divergence-leans-to-the-backend.md#a-divergence-leans-towards-the-affected-backends-own-idiom)),
and it is every `=`-spelled run's, not the fixed-arity family's: `--tags=a b` and
`--config=a.yaml b.yaml` exit the same way, while their space forms parse. On the clicklike
front-ends the continuation survives exactly where the space run does — a fixed-arity
flag's exact-count parser takes `--pair=1 2` natively, and their varlen flags decline the
space form itself ([list syntax divergence](list-syntax-divergence.md#list-syntax-divergence)).

A bare occurrence is the lower bound at zero, and on cyclopts it never reaches confarg's loop:
`consume_multiple` reads one as an implicit empty container, which survives a lone occurrence
but asserts inside cyclopts' own parse the moment it meets a real token — so `--pair --pair 3 4` and `--pair 1 2 --pair` both crash with no message of
confarg's own (BUG-74, closed). `FlagSpec.refuses_bare` marks the fixed-arity specs — the
`_fixed_seq_types(resolved)` gate, asked without unwrapping `Optional`, the type vanilla
dispatches on — and
`cli._argv.refuse_bare_occurrences` raises vanilla's missing-value error off the argv the user
typed before cyclopts parses, the pre-parse refusal pattern of the `--config` scan (BUG-51,
closed). A dynamic element flag addressing a fixed-arity type carries the marker too, so
`--pairs.0 --pairs.0 3 4` answers the same way; vanilla's loop would have refused the bare
occurrence anyway, but the framework's parse never gets far enough to ask it.

A union with a sequence variant (`str | tuple[str, str]`) owes neither bound: that field
consumes greedily in vanilla, so `build()` judging its arity is parity, not a gap. An
`Optional[<sequence>]` field is such a union to vanilla's dispatch *and* to registration, so
its flag registers the way that union's own flag does: `nargs="*"`,
`accumulates=True`, `stands_bare=True`, no `whole_value` (BUG-79). Until it did, the unwrapped
core's fixed-arity spec was registered instead, so a repeated occurrence kept only its own run —
argparse's plain store and cyclopts' last-occurrence converter answered `--pair 1 2 --pair 3 4`
with `(3, 4)` where vanilla joins the runs and defers the arity to `build()` — and the clicklike
front-ends answered `--pair 1` at their own parse where vanilla defers to `build()`. On the
clicklike front-ends the flag now joins the
[list syntax divergence](list-syntax-divergence.md#list-syntax-divergence) — `--pair 1 --pair 2` is
their spelling of `--pair 1 2`, as `list[int] | None`'s flag always was — and the lone whole-value
token reaches them too, decoded from the one item their repeated idiom holds.

Its tokens are shaped by vanilla's `_union_seq_value` — a valued run stored raw, its
per-position coercion deferred to `build()`, a bare occurrence that meets an empty accumulation
refused with `Missing value for '--pair'`, a trailing one joining whatever the earlier
occurrences left, a whole-field delete ending the accumulation, and a whole-value blob a write of
its own that the later of a blob and a run wins (BUG-61, BUG-79). Before REF-72 the adapters
replayed that accumulation off argv with a reader of their own
(`_union_seq_occurrence_writes`), because a parse result joins what argv kept apart.

A namedtuple's sub-flags keep their spelling across the move, merged in argv order as on the plain
spelling; what differs is the shape a sub-flag written last descends into: the generic `_set_nested`
`'*'` base, because vanilla's by-field-name promotion asks the field as resolved and finds the union
there — so `--pt 1 2 --pt.y 9` under `Point | None` is `{'*': ['1', '2'], 'y': 9}` on all five
front-ends, and `build()` rejects it on all five alike.

For the namedtuple, the lone token is decoded by vanilla's two decoders (`_lone_json_array`
for `[…]`, `_accepts_object_value` + `_parse_json_arg` for `{…}`). Sub-flags refine it as they
refine a struct's whole value, and each is stored under the key the user spelled, name and
index alike (BUG-65): `--pt.x 13 --pt.0 9` reaches the merged dict as `{'x': 13, '0': 9}`, and
`build()` owns the win, constructing an all-index dict positionally and refusing a mixed one
with `Unknown field(s)`. The arity flag's positions meet a later sub-flag re-keyed by field
name (`_parse_cli._promote_namedtuple_positional`), so `--pt 1 2 --pt.0 9` is
`{'x': 1, 'y': 2, '0': 9}`, the mixed spelling `build()` refuses. Every occurrence is written
where argv puts it, so the latest writer wins and an earlier one is overwritten as it is in any
sequential loop — `--pair.y 7 --pair 13 42` is `[13, 42]`, the reverse order joins by field
name, and `--pt.x 1 --pt 7 8 --pt.y 2` is `{'x': 7, 'y': 2}`
([design decisions](../design-decisions/namedtuple-arity-flag-argv-order.md#a-namedtuples-arity-flag-and-its-sub-flags-merge-in-argv-order)).

A sub-flag one level below a struct-shaped field — a struct, or another namedtuple, however
wrapped — is not a scalar, and the spellings of such a field take what that field type takes at
any other depth (BUG-68): the static walk recurses into them as it recurses into a struct's
fields, so `--pt.inner.a` registers next to `--pt.inner`, under the index spellings too.

Everything else about a namedtuple is shared — the arity flag, the per-field and per-index
flags (the negative index included, BUG-80), and the vanilla positional form
([design decisions](../design-decisions/namedtuple-is-a-fixed-length-sequence.md#a-namedtuple-is-a-fixed-length-sequence));
the index spellings are hidden from `--help`
([design decisions](../design-decisions/index-spellings-are-hidden-from-help.md#index-spellings-are-hidden-from-help)).

A dict field's bare flag is its *only* static flag (its keys are unknown until argv is read);
subkeys arrive as patch flags, registered when typed, and refine the whole value, so
`--env '{"a":"b"}' --env.c d` yields `{"a": "b", "c": "d"}` as in vanilla.

The same sequential writes answer a struct, registered-leaf or union field's bare value against
its sub-flags (BUG-85), and the interleaved spellings no per-flag summary of argv could describe
(BUG-111): `--s.a 1 --s '{"b": 5}' --s.b 2` is `{'s': {'b': 2}}` on every front-end.
